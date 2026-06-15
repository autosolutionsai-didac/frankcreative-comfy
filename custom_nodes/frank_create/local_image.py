import hashlib
import json
import math
import os
import re
import textwrap
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlencode
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


ASPECT_RATIOS = {
    "1:1": (1, 1),
    "4:5": (4, 5),
    "3:4": (3, 4),
    "2:3": (2, 3),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "5:4": (5, 4),
    "4:3": (4, 3),
    "21:9": (21, 9),
}

SIZE_LONG_EDGE = {
    "1K": 1024,
    "1024": 1024,
    "1MP": 1280,
    "2K": 2048,
    "2048": 2048,
    "4MP": 2048,
    "4K": 4096,
    "4096": 4096,
}

EXPORT_PRESET_SIZES = {
    "pdp": (1600, 2000),
    "email-hero": (2400, 1350),
    "instagram-feed": (1080, 1350),
    "instagram-story": (1080, 1920),
    "paid-social": (1200, 628),
}

IMAGE_CHANNEL_SET_PRESETS = (
    "pdp",
    "email-hero",
    "instagram-feed",
    "instagram-story",
    "paid-social",
    "transparent-png",
    "high-res-master",
)

COLORS = {
    "ink": (63, 42, 45),
    "paper": (255, 250, 248),
    "shell": (253, 238, 234),
    "pink": (255, 183, 166),
    "pink_soft": (255, 226, 218),
    "cherry": (196, 17, 47),
    "coffee": (91, 58, 51),
    "cream": (255, 244, 240),
}


def run_local_studio_turn(store, turn, payload, model):
    settings = payload.get("settings") or {}
    count = max(1, min(int(settings.get("count") or 1), 4))
    dimensions = dimensions_for(settings.get("aspect_ratio", "1:1"), settings.get("image_size", "2K"))
    prompt = payload.get("prompt") or turn.get("prompt") or ""
    preset_key = payload.get("preset_key") or "product-shot-lab"
    source_asset = _find_asset(store, payload.get("edit_source_asset_id") or payload.get("source_asset_id"))
    mask_asset = _find_asset(store, payload.get("mask_asset_id"))
    reference_assets = [_find_asset(store, asset_id) for asset_id in payload.get("reference_asset_ids", [])]
    reference_assets = [asset for asset in reference_assets if asset]
    base_asset = source_asset or (reference_assets[0] if reference_assets else None)
    base_image = _load_asset_image(base_asset) if base_asset else None
    mask_image = _load_asset_image(mask_asset) if mask_asset else None

    created_assets = []
    for index in range(count):
        workflow_provenance = _frank_renderer_workflow_provenance(
            payload=payload,
            preset_key=preset_key,
            variant_index=index,
            edit_mode=bool(source_asset),
            mask_asset_id=mask_asset["id"] if mask_asset else None,
            dimensions=dimensions,
        )
        if preset_key == "background-remove" and base_image:
            image = _compose_background_remove_cutout(
                base_image=base_image,
                dimensions=dimensions,
                variant_index=index,
                edit_mode=bool(source_asset),
            )
        else:
            image = _compose_variant(
                base_image=base_image,
                dimensions=dimensions,
                preset_key=preset_key,
                prompt=prompt,
                variant_index=index,
                edit_mode=bool(source_asset),
                mask_image=mask_image,
            )
        filename = f"{turn['id']}_{index + 1:02d}.png"
        output_path = _output_dir() / "frank_create" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")

        asset = store.create_asset(
            {
                "session_id": turn["session_id"],
                "turn_id": turn["id"],
                "kind": "candidate",
                "title": _asset_title(model, preset_key, index),
                "media_type": "image",
                "provider": model["provider"],
                "model": model["id"],
                "prompt": prompt,
                "settings": _settings_with_workflow_provenance(settings, workflow_provenance),
                "source_asset_id": source_asset["id"] if source_asset else None,
                "reference_asset_ids": [asset["id"] for asset in reference_assets],
                "file_path": f"output/frank_create/{filename}",
                "preview_url": _view_url(filename, "frank_create", "output"),
                "width": image.width,
                "height": image.height,
                "approval_status": "review",
                "sync_status": "local",
            }
        )
        created_assets.append(asset)

    updated_turn = store.update_turn(
        turn["id"],
        {
            "status": "complete",
            "source_asset_id": source_asset["id"] if source_asset else None,
            "reference_asset_ids": [asset["id"] for asset in reference_assets],
            "output_asset_ids": [asset["id"] for asset in created_assets],
        },
    )
    return updated_turn, created_assets


def run_local_video_storyboard(store, turn, payload, model):
    settings = payload.get("settings") or {}
    dimensions = dimensions_for(settings.get("aspect_ratio", "16:9"), settings.get("image_size", "1K"))
    prompt = payload.get("prompt") or turn.get("prompt") or ""
    source_asset = _find_asset(store, payload.get("source_asset_id") or payload.get("edit_source_asset_id"))
    reference_assets = [_find_asset(store, asset_id) for asset_id in payload.get("reference_asset_ids", [])]
    reference_assets = [asset for asset in reference_assets if asset]
    base_asset = source_asset or (reference_assets[0] if reference_assets else None)
    base_image = _load_asset_image(base_asset) if base_asset else None
    frames = _video_storyboard_frames(base_image, dimensions, prompt)

    filename = f"{turn['id']}_video_lab.gif"
    output_path = _output_dir() / "frank_create" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output_path,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=120,
        loop=0,
        disposal=2,
    )

    asset = store.create_asset(
        {
            "session_id": turn["session_id"],
            "turn_id": turn["id"],
            "kind": "video",
            "title": f"{model.get('short_label') or model.get('label') or 'Video Lab'} / Motion storyboard",
            "media_type": "video",
            "provider": model["provider"],
            "model": model["id"],
            "prompt": prompt,
            "settings": _settings_with_workflow_provenance(
                settings,
                {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-video-storyboard",
                    "comfy_node_types": ["FrankCreateVideoStoryboard", "SaveAnimatedImage"],
                    "preset_key": "video-lab",
                    "media_type": "video",
                    "frame_count": len(frames),
                    "width": dimensions[0],
                    "height": dimensions[1],
                },
            ),
            "source_asset_id": source_asset["id"] if source_asset else None,
            "reference_asset_ids": [asset["id"] for asset in reference_assets],
            "file_path": f"output/frank_create/{filename}",
            "preview_url": _view_url(filename, "frank_create", "output"),
            "width": dimensions[0],
            "height": dimensions[1],
            "approval_status": "review",
            "sync_status": "local",
        }
    )
    updated_turn = store.update_turn(
        turn["id"],
        {
            "status": "complete",
            "source_asset_id": source_asset["id"] if source_asset else None,
            "reference_asset_ids": [asset["id"] for asset in reference_assets],
            "output_asset_ids": [asset["id"]],
        },
    )
    return updated_turn, [asset]


def create_export_pack(store, payload):
    asset = _find_asset(store, payload.get("asset_id"))
    if not asset:
        raise LookupError(f"asset {payload.get('asset_id')} was not found")

    preset = payload.get("preset")
    source_path = _resolve_media_path(asset.get("file_path") or "")
    if not source_path or not source_path.exists():
        raise FileNotFoundError(f"asset file is unavailable: {asset.get('file_path')}")

    exports_dir = _user_export_dir()
    exports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{asset['id']}-{preset}"
    metadata = payload.get("metadata") or {}

    if asset.get("media_type") == "video" or preset == "video-storyboard":
        return _create_video_export_pack(store, asset, source_path, payload, preset, metadata, exports_dir, stem)

    source = _load_asset_image(asset)
    if source is None:
        raise FileNotFoundError(f"asset file is unavailable: {asset.get('file_path')}")

    prepared = _prepare_image_export(store, asset, source, preset, metadata)
    output = prepared["image"]
    ext = prepared["format"]

    image_path = exports_dir / f"{stem}.{ext}"
    _save_export_image(output, image_path, ext)

    meta_path = exports_dir / f"{stem}.json"
    media_integrity = _file_integrity(image_path)
    meta_payload = {
        **prepared["metadata"],
        "image_file": str(image_path),
        "media_integrity": media_integrity,
    }
    meta_path.write_text(json.dumps(meta_payload, indent=2, sort_keys=True), encoding="utf-8")

    pack_path = exports_dir / f"{stem}.zip"
    with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md",
            _export_readme(
                meta_payload,
                media_file=image_path.name,
                metadata_file=meta_path.name,
                media_label="Image",
            ),
        )
        archive.writestr("EXPORT_SPEC.md", _export_spec_sheet(meta_payload, media_label="Image"))
        archive.write(image_path, arcname=image_path.name)
        archive.write(meta_path, arcname=meta_path.name)

    return {
        **payload,
        "file_path": str(pack_path),
        "metadata": {
            **meta_payload,
            "image_file": str(image_path),
            "metadata_file": str(meta_path),
            "pack_file": str(pack_path),
            "readme_file": "README.md",
            "spec_file": "EXPORT_SPEC.md",
        },
    }


def create_asset_channel_set_pack(store, payload):
    asset = _find_asset(store, payload.get("asset_id"))
    if not asset:
        raise LookupError(f"asset {payload.get('asset_id')} was not found")
    if asset.get("media_type") == "video":
        raise ValueError("Channel set export is only available for image assets")

    source_path = _resolve_media_path(asset.get("file_path") or "")
    if not source_path or not source_path.exists():
        raise FileNotFoundError(f"asset file is unavailable: {asset.get('file_path')}")

    source = _load_asset_image(asset)
    if source is None:
        raise FileNotFoundError(f"asset file is unavailable: {asset.get('file_path')}")

    requested_presets = payload.get("presets") or IMAGE_CHANNEL_SET_PRESETS
    presets = [preset for preset in requested_presets if preset in IMAGE_CHANNEL_SET_PRESETS]
    if not presets:
        raise ValueError("At least one image export preset is required")

    exports_dir = _user_export_dir()
    exports_dir.mkdir(parents=True, exist_ok=True)
    pack_path = exports_dir / f"{asset['id']}-channel-set.zip"
    metadata = payload.get("metadata") or {}
    manifest_context = _export_manifest_context(store, asset, "channel-set", source.width, source.height, "zip")
    exports = {}

    with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as archive:
        for preset in presets:
            prepared = _prepare_image_export(store, asset, source, preset, metadata)
            image_arcname = f"{preset}/{asset['id']}-{preset}.{prepared['format']}"
            metadata_arcname = f"{preset}/{asset['id']}-{preset}.json"
            image_bytes = _image_bytes(prepared["image"], prepared["format"])
            media_integrity = _bytes_integrity(image_bytes)
            archive.writestr(image_arcname, image_bytes)
            archive.writestr(
                metadata_arcname,
                json.dumps(
                    {
                        **prepared["metadata"],
                        "image_file": image_arcname,
                        "metadata_file": metadata_arcname,
                        "media_integrity": media_integrity,
                    },
                    indent=2,
                    sort_keys=True,
                ),
            )
            exports[preset] = {
                "preset": preset,
                "format": prepared["format"],
                "width": prepared["image"].width,
                "height": prepared["image"].height,
                "image_file": image_arcname,
                "metadata_file": metadata_arcname,
                "media_integrity": media_integrity,
            }

        manifest = {
            **metadata,
            **manifest_context,
            "asset_id": asset["id"],
            "preset": "channel-set",
            "presets": presets,
            "preset_count": len(presets),
            "exports": exports,
            "pack_file": str(pack_path),
        }
        archive.writestr("frank-create-channel-set.json", json.dumps(manifest, indent=2, sort_keys=True))
        archive.writestr("README.md", _channel_set_readme(manifest))
        archive.writestr("CHANNEL_SPEC.md", _channel_set_spec_sheet(manifest))

    return {
        **payload,
        "asset_id": asset["id"],
        "preset": "channel-set",
        "file_path": str(pack_path),
        "metadata": {
            **metadata,
            **manifest_context,
            "preset_count": len(presets),
            "presets": presets,
            "exports": exports,
            "pack_file": str(pack_path),
            "manifest_file": "frank-create-channel-set.json",
            "readme_file": "README.md",
            "spec_file": "CHANNEL_SPEC.md",
        },
    }


def _prepare_image_export(store, asset, source, preset, metadata):
    export_metadata = {}
    if preset == "transparent-png":
        output = _remove_corner_background(source.convert("RGBA"))
        export_metadata["background_removed"] = True
        ext = "png"
    elif preset == "high-res-master":
        output, export_metadata = _prepare_high_res_master(source)
        ext = "png"
    else:
        size = EXPORT_PRESET_SIZES.get(preset, source.size)
        output = _fit_on_canvas(source.convert("RGBA"), size, COLORS["paper"])
        ext = "jpg"

    manifest_context = _export_manifest_context(store, asset, preset, output.width, output.height, ext)
    return {
        "image": output,
        "format": ext,
        "export_metadata": export_metadata,
        "metadata": {
            **metadata,
            **export_metadata,
            **manifest_context,
            "asset_id": asset["id"],
            "preset": preset,
            "width": output.width,
            "height": output.height,
        },
    }


def _prepare_high_res_master(source):
    source_rgba = source.convert("RGBA")
    source_width, source_height = source_rgba.size
    output = ImageOps.contain(source_rgba, (4096, 4096), method=Image.Resampling.LANCZOS)
    output = ImageEnhance.Sharpness(output).enhance(1.08)
    output = ImageEnhance.Contrast(output).enhance(1.03)
    scale_factor = max(output.width / max(1, source_width), output.height / max(1, source_height))
    return output, {
        "upscaled": scale_factor > 1.01,
        "enhanced": True,
        "source_width": source_width,
        "source_height": source_height,
        "scale_factor": round(scale_factor, 4),
    }


def _save_export_image(output, image_path, ext):
    if ext == "jpg":
        output.convert("RGB").save(image_path, "JPEG", quality=94, optimize=True)
    else:
        output.save(image_path, "PNG")


def _image_bytes(output, ext):
    buffer = BytesIO()
    if ext == "jpg":
        output.convert("RGB").save(buffer, "JPEG", quality=94, optimize=True)
    else:
        output.save(buffer, "PNG")
    return buffer.getvalue()


def _file_integrity(path):
    path = Path(path)
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "file_size_bytes": len(data),
    }


def _bytes_integrity(data):
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "file_size_bytes": len(data),
    }


def _export_manifest_context(store, asset, preset, width, height, ext):
    turn = _turn_for_asset(store, asset)
    turn_context = _turn_manifest(turn) if turn else None
    job_context = _job_context_for_asset(store, asset)
    asset_manifest = _asset_manifest(asset)
    asset_workflow = asset_manifest.get("workflow_provenance") or {}
    return {
        **job_context,
        "asset_context": asset_manifest,
        "turn_context": turn_context,
        "workflow_bridge": _workflow_bridge_manifest(asset_manifest, asset_workflow),
        "export_context": {
            "preset": preset,
            "format": ext,
            "width": width,
            "height": height,
            "workflow_key": asset_workflow.get("workflow_key") or (turn_context or {}).get("preset_key") or preset,
            "provider": asset.get("provider") or (turn_context or {}).get("provider"),
            "model": asset.get("model") or (turn_context or {}).get("model"),
            "sync_ready": {
                "local_first": True,
                "sync_status": asset.get("sync_status", "local"),
                "remote_id": asset.get("remote_id"),
            },
        },
    }


def _export_readme(metadata, media_file, metadata_file, media_label):
    asset_context = metadata.get("asset_context") or {}
    export_context = metadata.get("export_context") or {}
    workflow_bridge = metadata.get("workflow_bridge") or {}
    media_type = metadata.get("media_type") or asset_context.get("media_type") or "image"
    prompt = asset_context.get("prompt") or metadata.get("prompt")
    workflow = asset_context.get("workflow_provenance") or {}
    lines = [
        f"# {asset_context.get('title') or 'Frank Create export'}",
        "",
        "Frank Create export pack.",
        "",
        f"- Asset: {_asset_readme_label(asset_context)}",
        f"- Media type: {media_type}",
        f"- Preset: {_readme_value(metadata.get('preset') or export_context.get('preset'))}",
        f"- Dimensions: {_readme_dimensions(metadata.get('width'), metadata.get('height'))}",
        f"- Provider: {_readme_value(export_context.get('provider') or asset_context.get('provider'))}",
        f"- Model: {_readme_value(export_context.get('model') or asset_context.get('model'))}",
        f"- Workflow: {_readme_value(workflow.get('workflow_key'))} ({_readme_value(workflow.get('engine'))})",
        f"- Raw Comfy: {_readme_value(workflow_bridge.get('raw_canvas_url'))}",
        f"- Workflow receipt: {_readme_value(workflow_bridge.get('workflow_receipt_url'))}",
        f"- Raw Comfy load: {_readme_value(workflow_bridge.get('raw_canvas_load_status'))}",
        f"- Comfy nodes: {_readme_node_types(workflow_bridge.get('comfy_node_types'))}",
        f"- {media_label}: {media_file}",
        f"- Metadata: {metadata_file}",
        f"- SHA-256: {_readme_value((metadata.get('media_integrity') or {}).get('sha256'))}",
        "",
        "Prompt:",
        _readme_prompt(prompt),
        "",
        "Keep this README with the media and JSON so prompts, settings, and sync metadata travel together.",
    ]
    return "\n".join(lines) + "\n"


def _channel_set_readme(manifest):
    asset_context = manifest.get("asset_context") or {}
    exports = manifest.get("exports") or {}
    workflow_bridge = manifest.get("workflow_bridge") or {}
    workflow = asset_context.get("workflow_provenance") or {}
    lines = [
        f"# {asset_context.get('title') or 'Frank Create channel set'}",
        "",
        "Frank Create channel set.",
        "",
        f"- Asset: {_asset_readme_label(asset_context)}",
        f"- Presets: {manifest.get('preset_count') or len(exports)}",
        f"- Provider: {_readme_value((manifest.get('export_context') or {}).get('provider') or asset_context.get('provider'))}",
        f"- Model: {_readme_value((manifest.get('export_context') or {}).get('model') or asset_context.get('model'))}",
        f"- Workflow: {_readme_value(workflow.get('workflow_key'))} ({_readme_value(workflow.get('engine'))})",
        f"- Raw Comfy: {_readme_value(workflow_bridge.get('raw_canvas_url'))}",
        f"- Workflow receipt: {_readme_value(workflow_bridge.get('workflow_receipt_url'))}",
        f"- Raw Comfy load: {_readme_value(workflow_bridge.get('raw_canvas_load_status'))}",
        f"- Comfy nodes: {_readme_node_types(workflow_bridge.get('comfy_node_types'))}",
        "- Manifest: frank-create-channel-set.json",
        "- Integrity: each preset JSON includes SHA-256 and file size for the exported media.",
        "",
        "Presets:",
    ]
    for preset in manifest.get("presets") or exports.keys():
        export = exports.get(preset) or {}
        lines.append(
            f"- {preset}: {_readme_dimensions(export.get('width'), export.get('height'))} {_readme_value(export.get('format'))}"
        )
    lines.extend(
        [
            "",
            "Prompt:",
            _readme_prompt(asset_context.get("prompt")),
            "",
            "Use the preset folders for channel-ready creative, and keep the manifest with the media for review notes and future sync.",
        ]
    )
    return "\n".join(lines) + "\n"


def _export_spec_sheet(metadata, media_label):
    asset_context = metadata.get("asset_context") or {}
    export_context = metadata.get("export_context") or {}
    workflow_bridge = metadata.get("workflow_bridge") or {}
    workflow = asset_context.get("workflow_provenance") or {}
    prompt = asset_context.get("prompt") or metadata.get("prompt")
    rows = [
        ("Asset", _asset_readme_label(asset_context)),
        ("Asset ID", asset_context.get("id") or metadata.get("asset_id")),
        ("Media type", metadata.get("media_type") or asset_context.get("media_type") or "image"),
        ("Intended use", metadata.get("preset") or export_context.get("preset")),
        ("Output size", _readme_dimensions(metadata.get("width"), metadata.get("height"))),
        ("Approval", asset_context.get("approval_status") or "review"),
        ("Provider", export_context.get("provider") or asset_context.get("provider")),
        ("Model", export_context.get("model") or asset_context.get("model")),
        ("Workflow", _workflow_label(workflow)),
        ("Raw Comfy", workflow_bridge.get("raw_canvas_url")),
        ("Workflow receipt", workflow_bridge.get("workflow_receipt_url")),
        ("Raw Comfy load", workflow_bridge.get("raw_canvas_load_status")),
        ("Comfy nodes", _readme_node_types(workflow_bridge.get("comfy_node_types"))),
        ("SHA-256", (metadata.get("media_integrity") or {}).get("sha256")),
    ]
    lines = [
        "# Frank Create Export Spec",
        "",
        f"{media_label} export for director review and channel handoff.",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *[_markdown_row(label, value) for label, value in rows],
        "",
        "## Prompt",
        "",
        _readme_prompt(prompt),
    ]
    notes = asset_context.get("notes")
    if notes:
        lines.extend(["", "## Review Notes", "", _readme_prompt(notes)])
    return "\n".join(lines) + "\n"


def _channel_set_spec_sheet(manifest):
    asset_context = manifest.get("asset_context") or {}
    exports = manifest.get("exports") or {}
    workflow_bridge = manifest.get("workflow_bridge") or {}
    workflow = asset_context.get("workflow_provenance") or {}
    rows = [
        ("Asset", _asset_readme_label(asset_context)),
        ("Asset ID", asset_context.get("id") or manifest.get("asset_id")),
        ("Preset count", manifest.get("preset_count") or len(exports)),
        ("Provider", ((manifest.get("export_context") or {}).get("provider") or asset_context.get("provider"))),
        ("Model", ((manifest.get("export_context") or {}).get("model") or asset_context.get("model"))),
        ("Workflow", _workflow_label(workflow)),
        ("Raw Comfy", workflow_bridge.get("raw_canvas_url")),
        ("Workflow receipt", workflow_bridge.get("workflow_receipt_url")),
        ("Raw Comfy load", workflow_bridge.get("raw_canvas_load_status")),
        ("Comfy nodes", _readme_node_types(workflow_bridge.get("comfy_node_types"))),
    ]
    lines = [
        "# Frank Create Channel Spec",
        "",
        "Channel-ready export set for Frank Body review.",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *[_markdown_row(label, value) for label, value in rows],
        "",
        "## Channel Files",
        "",
        "| Preset | Size | Format |",
        "| --- | --- | --- |",
    ]
    for preset in manifest.get("presets") or exports.keys():
        export = exports.get(preset) or {}
        lines.append(
            _markdown_row(
                preset,
                _readme_dimensions(export.get("width"), export.get("height")),
                _readme_value(export.get("format")),
            )
        )
    lines.extend(["", "## Prompt", "", _readme_prompt(asset_context.get("prompt"))])
    return "\n".join(lines) + "\n"


def _handoff_spec_sheet(manifest):
    session = manifest.get("session") or {}
    project = manifest.get("project") or {}
    brief = manifest.get("brief") or {}
    counts = manifest.get("counts") or {}
    approved_assets = manifest.get("approved_assets") or []
    proof_assets = manifest.get("proof_assets") or []
    rows = [
        ("Session", session.get("name") or session.get("id")),
        ("Project", project.get("name") or "Not linked"),
        ("Brief", brief.get("title") or session.get("summary") or "Not linked"),
        ("Summary", manifest.get("summary")),
        ("Approved assets", counts.get("approved_assets")),
        ("Approved images", counts.get("approved_images")),
        ("Approved videos", counts.get("approved_videos")),
        ("Proof assets", counts.get("proof_assets")),
        ("Reference images", counts.get("references")),
        ("Channel export sets", counts.get("channel_export_sets")),
        ("Channel export files", counts.get("channel_export_files")),
        ("Sync status", ((manifest.get("sync_ready") or {}).get("sync_status"))),
    ]
    lines = [
        "# Frank Create Handoff Spec",
        "",
        "Meeting-ready summary of the approved Frank Create handoff.",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *[_markdown_row(label, value) for label, value in rows],
        "",
        "## Approved Picks",
        "",
        "| Asset | Media | Approval | Workflow |",
        "| --- | --- | --- | --- |",
    ]
    for asset in approved_assets:
        lines.append(
            _markdown_row(
                asset.get("title") or asset.get("id"),
                asset.get("media_type") or "image",
                asset.get("approval_status") or "review",
                _workflow_key(asset),
            )
        )
    if proof_assets:
        lines.extend(["", "## Proof Assets", "", "| Asset | Media | Status | Workflow |", "| --- | --- | --- | --- |"])
        for asset in proof_assets:
            lines.append(
                _markdown_row(
                    asset.get("title") or asset.get("id"),
                    asset.get("media_type") or "image",
                    asset.get("approval_status") or "review",
                    _workflow_key(asset),
                )
            )
    channel_exports = manifest.get("channel_exports") or {}
    if channel_exports:
        lines.extend(["", "## Channel Exports", "", "| Asset | Presets |", "| --- | --- |"])
        for asset_id, export_set in channel_exports.items():
            asset_title = export_set.get("asset_title") or asset_id
            lines.append(_markdown_row(asset_title, ", ".join(export_set.get("presets") or [])))
    reference_assets = manifest.get("reference_assets") or []
    if reference_assets:
        lines.extend(["", "## References", "", "| Asset | File |", "| --- | --- |"])
        for asset in reference_assets:
            lines.append(_markdown_row(asset.get("title") or asset.get("id"), asset.get("archive_path") or asset.get("file_path")))
    return "\n".join(lines) + "\n"


def _asset_readme_label(asset_context):
    title = asset_context.get("title") or "Untitled asset"
    asset_id = asset_context.get("id")
    if asset_id:
        return f"{title} ({asset_id})"
    return title


def _readme_dimensions(width, height):
    if width and height:
        return f"{width} x {height}"
    return "Unknown"


def _readme_value(value):
    return str(value) if value not in (None, "") else "Not set"


def _readme_prompt(prompt):
    if not prompt:
        return "Not set"
    return "\n".join(textwrap.wrap(str(prompt), width=88)) or "Not set"


def _readme_node_types(node_types):
    if not isinstance(node_types, list) or not node_types:
        return "Not set"
    return ", ".join(str(item) for item in node_types if item) or "Not set"


def _workflow_label(workflow):
    if not isinstance(workflow, dict) or not workflow:
        return "Not set (Not set)"
    return f"{_readme_value(workflow.get('workflow_key'))} ({_readme_value(workflow.get('engine'))})"


def _workflow_key(asset):
    workflow = asset.get("workflow_provenance")
    if not isinstance(workflow, dict):
        settings = asset.get("settings") if isinstance(asset.get("settings"), dict) else {}
        workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else {}
    if isinstance(workflow, dict) and workflow.get("workflow_key"):
        return workflow.get("workflow_key")
    return "Not set"


def _markdown_row(*values):
    cells = [_markdown_cell(value) for value in values]
    return f"| {' | '.join(cells)} |"


def _markdown_cell(value):
    text = _readme_value(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _turn_for_asset(store, asset):
    turn_id = asset.get("turn_id")
    if not turn_id:
        return None
    for turn in store.list_turns(session_id=asset.get("session_id")):
        if turn.get("id") == turn_id:
            return turn
    return None


def _job_context_for_asset(store, asset):
    session = _session_for_id(store, asset.get("session_id"))
    brief = _brief_for_asset(store, asset, session)
    project = _project_for_brief_or_session(store, brief, session)
    return {
        "project_context": _project_manifest(project) if project else None,
        "brief_context": _brief_manifest(brief) if brief else None,
    }


def _job_context_for_session(store, session, approved_assets):
    brief = None
    for asset in approved_assets:
        brief = _brief_for_asset(store, asset, session)
        if brief:
            break
    if not brief:
        brief = _brief_for_session(store, session)
    project = _project_for_brief_or_session(store, brief, session)
    return {
        "project": _project_manifest(project) if project else None,
        "brief": _brief_manifest(brief) if brief else None,
    }


def _session_for_id(store, session_id):
    if not session_id:
        return None
    for session in store.list_sessions():
        if session.get("id") == session_id:
            return session
    return None


def _brief_for_asset(store, asset, session=None):
    brief_id = asset.get("brief_id")
    if brief_id:
        for brief in store.list_briefs():
            if brief.get("id") == brief_id:
                return brief
    return _brief_for_session(store, session)


def _brief_for_session(store, session):
    if not session:
        return None
    project_id = session.get("project_id")
    if project_id:
        briefs = store.list_briefs(project_id=project_id)
        if session.get("summary"):
            for brief in briefs:
                if brief.get("title") == session.get("summary"):
                    return brief
        if briefs:
            return briefs[0]
    return None


def _project_for_brief_or_session(store, brief, session=None):
    project_id = (brief or {}).get("project_id") or (session or {}).get("project_id")
    if not project_id:
        return None
    for project in store.list_projects():
        if project.get("id") == project_id:
            return project
    return None


def _create_video_export_pack(store, asset, source_path, payload, preset, metadata, exports_dir, stem):
    ext = source_path.suffix.lower() or ".gif"
    storyboard_path = exports_dir / f"{stem}{ext}"
    storyboard_path.write_bytes(source_path.read_bytes())
    media_integrity = _file_integrity(storyboard_path)

    width, height = _video_dimensions(asset, source_path)
    manifest_context = _export_manifest_context(store, asset, preset, width, height, ext)
    meta_path = exports_dir / f"{stem}.json"
    meta_payload = {
        **metadata,
        **manifest_context,
        "asset_id": asset["id"],
        "preset": preset,
        "media_type": "video",
        "storyboard_file": str(storyboard_path),
        "source_file": str(source_path),
        "media_integrity": media_integrity,
        "width": width,
        "height": height,
    }
    meta_path.write_text(json.dumps(meta_payload, indent=2, sort_keys=True), encoding="utf-8")

    pack_path = exports_dir / f"{stem}.zip"
    with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md",
            _export_readme(
                meta_payload,
                media_file=storyboard_path.name,
                metadata_file=meta_path.name,
                media_label="Storyboard",
            ),
        )
        archive.writestr("EXPORT_SPEC.md", _export_spec_sheet(meta_payload, media_label="Storyboard"))
        archive.write(storyboard_path, arcname=storyboard_path.name)
        archive.write(meta_path, arcname=meta_path.name)

    return {
        **payload,
        "file_path": str(pack_path),
        "metadata": {
            **meta_payload,
            "storyboard_file": str(storyboard_path),
            "metadata_file": str(meta_path),
            "pack_file": str(pack_path),
            "readme_file": "README.md",
            "spec_file": "EXPORT_SPEC.md",
        },
    }


def _video_dimensions(asset, source_path):
    if asset.get("width") and asset.get("height"):
        return asset.get("width"), asset.get("height")
    try:
        with Image.open(source_path) as image:
            return image.width, image.height
    except Exception:
        return None, None


def create_session_handoff_pack(store, payload):
    session_id = payload.get("session_id")
    if not session_id:
        raise LookupError("session_id is required")

    session = next((record for record in store.list_sessions() if record["id"] == session_id), None)
    if not session:
        raise LookupError(f"session {session_id} was not found")

    all_assets = store.list_assets(session_id=session_id)
    approved_assets = [
        asset
        for asset in all_assets
        if asset.get("kind") != "reference" and asset.get("approval_status") == "approved"
    ]
    approved_assets = sorted(approved_assets, key=_handoff_asset_sort_key)
    if not approved_assets:
        raise LookupError("Approve at least one asset before exporting a handoff pack")
    proof_assets = sorted(_handoff_proof_assets(all_assets), key=_handoff_asset_sort_key)

    reference_assets = sorted(
        [asset for asset in all_assets if asset.get("kind") == "reference"],
        key=_handoff_asset_sort_key,
    )
    approved_assets = _handoff_assets_with_archive_paths(approved_assets, "approved", "approved")
    approved_assets = _handoff_assets_with_workflow_sidecars(approved_assets)
    proof_assets = _handoff_assets_with_archive_paths(proof_assets, "proofs", "proof")
    proof_assets = _handoff_assets_with_workflow_sidecars(proof_assets)
    reference_assets = _handoff_assets_with_archive_paths(reference_assets, "references", "reference")
    image_count = _media_count(approved_assets, "image")
    video_count = _media_count(approved_assets, "video")
    turns = store.list_turns(session_id=session_id)
    job_context = _job_context_for_session(store, session, approved_assets)
    review_board = _create_handoff_review_board(session, approved_assets, reference_assets, job_context)
    channel_exports = _handoff_channel_export_sets(store, approved_assets, payload.get("metadata") or {})
    approved_assets = _handoff_assets_with_channel_export_counts(approved_assets, channel_exports)
    exports_dir = _user_export_dir()
    exports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    pack_stem = f"{_safe_file_stem(session.get('name') or 'frank-create')}-handoff-{timestamp}"
    pack_path = exports_dir / f"{pack_stem}.zip"

    manifest = _handoff_manifest(
        session=session,
        turns=turns,
        approved_assets=approved_assets,
        proof_assets=proof_assets,
        reference_assets=reference_assets,
        payload=payload,
        pack_path=pack_path,
        job_context=job_context,
        review_board=review_board["metadata"],
        channel_exports=channel_exports,
    )

    with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("README.md", _handoff_readme(session, approved_assets, reference_assets, job_context, channel_exports, proof_assets))
        archive.writestr("HANDOFF_SPEC.md", _handoff_spec_sheet(manifest))
        archive.writestr("frank-create-handoff.json", json.dumps(manifest, indent=2, sort_keys=True))
        archive.writestr(review_board["metadata"]["archive_path"], review_board["bytes"])
        _archive_assets(archive, approved_assets, "approved")
        _archive_assets(archive, proof_assets, "proofs")
        _archive_assets(archive, reference_assets, "references")
        _archive_workflow_sidecars(archive, approved_assets)
        _archive_workflow_sidecars(archive, proof_assets)
        _archive_handoff_channel_exports(archive, channel_exports)

    first_asset = next((asset for asset in approved_assets if asset.get("media_type") == "image"), approved_assets[0])
    return {
        **payload,
        "asset_id": first_asset["id"],
        "preset": payload.get("preset") or "session-handoff",
        "file_path": str(pack_path),
        "metadata": {
            "session_id": session_id,
            "session_name": session.get("name"),
            "approved_asset_ids": [asset["id"] for asset in approved_assets],
            "reference_asset_ids": [asset["id"] for asset in reference_assets],
            "asset_count": len(approved_assets),
            "proof_asset_count": len(proof_assets),
            "image_count": image_count,
            "video_count": video_count,
            "reference_count": len(reference_assets),
            "channel_export_set_count": len(channel_exports),
            "channel_export_file_count": _handoff_channel_export_file_count(channel_exports),
            "turn_count": len(turns),
            "project_id": (job_context.get("project") or {}).get("id"),
            "brief_id": (job_context.get("brief") or {}).get("id"),
            "pack_file": str(pack_path),
            "manifest_file": "frank-create-handoff.json",
            "spec_file": "HANDOFF_SPEC.md",
            "review_board_file": review_board["metadata"]["archive_path"],
        },
    }


def _handoff_asset_sort_key(asset):
    media_priority = {"image": 0, "video": 1}
    media_type = asset.get("media_type") or "image"
    return (
        media_priority.get(media_type, 2),
        asset.get("created_at") or asset.get("updated_at") or "",
        asset.get("id") or "",
    )


def _handoff_proof_assets(assets):
    return [
        asset
        for asset in assets
        if asset.get("kind") not in {"reference", "mask"}
        and asset.get("approval_status") != "approved"
        and _asset_has_masked_edit_workflow(asset)
    ]


def _asset_has_masked_edit_workflow(asset):
    settings = _json_loads(asset.get("settings_json"), {})
    workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
    if not isinstance(workflow, dict):
        return False
    return workflow.get("masked_edit") is True or workflow.get("workflow_key") in {
        "frank-local-masked-edit-renderer",
        "comfy-checkpoint-inpaint",
    }


def create_session_review_board(store, session_id):
    if not session_id:
        raise LookupError("session_id is required")

    session = next((record for record in store.list_sessions() if record["id"] == session_id), None)
    if not session:
        raise LookupError(f"session {session_id} was not found")

    all_assets = store.list_assets(session_id=session_id)
    approved_assets = [
        asset
        for asset in all_assets
        if asset.get("kind") != "reference" and asset.get("approval_status") == "approved"
    ]
    if not approved_assets:
        raise LookupError("Approve at least one asset before opening a review board")

    reference_assets = [asset for asset in all_assets if asset.get("kind") == "reference"]
    return _create_handoff_review_board(
        session,
        _handoff_assets_with_archive_paths(approved_assets, "approved", "approved"),
        _handoff_assets_with_archive_paths(reference_assets, "references", "reference"),
        _job_context_for_session(store, session, approved_assets),
    )


def dimensions_for(aspect_ratio, image_size):
    ratio = ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS["1:1"])
    long_edge = SIZE_LONG_EDGE.get(str(image_size), 2048)
    rw, rh = ratio
    if rw >= rh:
        width = long_edge
        height = max(1, round(long_edge * rh / rw))
    else:
        height = long_edge
        width = max(1, round(long_edge * rw / rh))
    return width, height


def _compose_variant(base_image, dimensions, preset_key, prompt, variant_index, edit_mode=False, mask_image=None):
    background = _background(dimensions, preset_key, variant_index)
    draw = ImageDraw.Draw(background)

    if base_image:
        product = _prepare_product(base_image, dimensions, preset_key, variant_index, edit_mode)
        x = round((dimensions[0] - product.width) * _x_bias(preset_key, variant_index))
        y = round((dimensions[1] - product.height) * _y_bias(preset_key, variant_index))
        shadow = _shadow(product)
        background.alpha_composite(shadow, (x + max(6, dimensions[0] // 120), y + max(10, dimensions[1] // 90)))
        background.alpha_composite(product, (x, y))
        if mask_image:
            mask_overlay = _prepare_mask_overlay(mask_image, product.size, dimensions)
            background.alpha_composite(mask_overlay, (x, y))
            _draw_mask_edit_badge(draw, dimensions, x, y, product.size)
    else:
        _draw_no_reference_concept(draw, dimensions, preset_key, prompt)

    _draw_variant_finish(draw, dimensions, preset_key, prompt, variant_index, has_product=bool(base_image))
    _add_local_studio_finish(background, preset_key, variant_index)
    if preset_key == "background-replace":
        opaque = Image.new("RGBA", dimensions, COLORS["paper"] + (255,))
        opaque.alpha_composite(background)
        return opaque
    return background.convert("RGBA")


def _compose_background_remove_cutout(base_image, dimensions, variant_index, edit_mode=False):
    canvas = Image.new("RGBA", dimensions, (255, 255, 255, 0))
    product = _remove_corner_background(base_image.convert("RGBA"))
    if edit_mode:
        product = ImageEnhance.Contrast(product).enhance(1.04)
        product = ImageEnhance.Sharpness(product).enhance(1.12)
    max_w = dimensions[0] * (0.66 if variant_index != 1 else 0.58)
    max_h = dimensions[1] * 0.74
    product.thumbnail((round(max_w), round(max_h)), Image.Resampling.LANCZOS)
    x = round((dimensions[0] - product.width) / 2)
    y = round((dimensions[1] - product.height) / 2)
    canvas.alpha_composite(product, (x, y))
    return canvas


def _video_storyboard_frames(base_image, dimensions, prompt):
    base = _compose_variant(
        base_image=base_image,
        dimensions=dimensions,
        preset_key="campaign-variants",
        prompt=prompt,
        variant_index=0,
        edit_mode=True,
    ).convert("RGBA")
    width, height = dimensions
    frames = []
    total = 16
    for index in range(total):
        t = index / max(1, total - 1)
        zoom = 1.0 + 0.035 * math.sin(t * math.pi)
        work = base.resize((round(width * zoom), round(height * zoom)), Image.Resampling.BICUBIC)
        pan_x = round((work.width - width) * (0.5 + 0.28 * math.sin(t * math.tau)))
        pan_y = round((work.height - height) * (0.5 + 0.16 * math.cos(t * math.tau)))
        frame = work.crop((pan_x, pan_y, pan_x + width, pan_y + height)).convert("RGBA")
        draw = ImageDraw.Draw(frame)
        bar_w = round(width * (0.18 + 0.64 * t))
        bar_h = max(5, height // 120)
        margin = max(18, min(width, height) // 34)
        draw.rounded_rectangle(
            (margin, height - margin - bar_h, margin + bar_w, height - margin),
            radius=max(3, bar_h // 2),
            fill=COLORS["cherry"] + (210,),
        )
        if index in {0, total - 1}:
            label = "frank body motion board"
            draw.text((margin, margin), label, fill=COLORS["ink"] + (190,))
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))
    return frames


def _background(size, preset_key, variant_index):
    width, height = size
    image = Image.new("RGBA", size, COLORS["paper"] + (255,))
    palette = _palette_for(preset_key, variant_index)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(round(palette[0][i] * (1 - t) + palette[1][i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color + (255,))

    if preset_key == "background-replace":
        _draw_background_replace_set(draw, size, variant_index)
    elif preset_key in {"fb-lifestyle", "product-shot-lab", "clean-ecom", "campaign-variants"}:
        _draw_simulated_frank_studio_set(draw, size, preset_key, variant_index)
    elif preset_key == "retail-mock":
        shelf_y = round(height * 0.68)
        draw.rectangle((0, shelf_y, width, shelf_y + max(18, height // 80)), fill=COLORS["coffee"] + (190,))
        for i in range(4):
            left = round(width * (0.12 + i * 0.2))
            top = round(height * 0.42)
            draw.rounded_rectangle(
                (left, top, left + width // 9, shelf_y),
                radius=max(8, width // 140),
                fill=COLORS["pink_soft"] + (210,),
                outline=COLORS["ink"] + (65,),
                width=max(1, width // 360),
            )
    elif preset_key == "product-texture":
        for i in range(180):
            x = (i * 7919 + variant_index * 431) % width
            y = (i * 1543 + variant_index * 271) % height
            r = max(2, min(width, height) // (80 + (i % 60)))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=COLORS["coffee"] + (18 + i % 34,))

    return image


def _draw_simulated_frank_studio_set(draw, size, preset_key, variant_index):
    width, height = size
    tile = max(92, min(width, height) // 8)
    line = COLORS["coffee"] + (20 if preset_key == "clean-ecom" else 30,)
    for x in range(-tile, width + tile, tile):
        draw.line([(x, 0), (x + tile // 3, height)], fill=line, width=max(1, tile // 54))
    for y in range(tile // 3, height, tile):
        draw.line([(0, y), (width, y - tile // 9)], fill=line, width=max(1, tile // 62))

    horizon_y = round(height * (0.62 if preset_key == "clean-ecom" else 0.58))
    counter_y = round(height * (0.73 if preset_key == "clean-ecom" else 0.69))
    counter_fill = COLORS["cream"] if preset_key == "clean-ecom" else (250, 226, 218)
    draw.rectangle((0, horizon_y, width, height), fill=counter_fill + (224,))
    draw.rectangle((0, counter_y, width, height), fill=COLORS["coffee"] + (224 if preset_key != "clean-ecom" else 190,))
    draw.rectangle((0, counter_y, width, counter_y + max(12, height // 82)), fill=COLORS["ink"] + (70,))

    accent_r = max(48, min(width, height) // (8 if preset_key == "campaign-variants" else 10))
    accent_x = round(width * ([0.78, 0.22, 0.68, 0.34][variant_index % 4]))
    accent_y = round(height * ([0.23, 0.29, 0.2, 0.27][variant_index % 4]))
    draw.ellipse(
        (accent_x - accent_r, accent_y - accent_r, accent_x + accent_r, accent_y + accent_r),
        fill=COLORS["pink"] + (96 if preset_key == "clean-ecom" else 132,),
        outline=COLORS["cherry"] + (110,),
        width=max(2, min(width, height) // 360),
    )

    towel_w = round(width * 0.36)
    towel_h = round(height * 0.12)
    towel_left = round(width * (0.06 if variant_index % 2 == 0 else 0.58))
    towel_top = counter_y - towel_h - max(14, height // 58)
    draw.rounded_rectangle(
        (towel_left, towel_top, towel_left + towel_w, towel_top + towel_h),
        radius=max(12, min(width, height) // 56),
        fill=COLORS["pink_soft"] + (210,),
        outline=COLORS["ink"] + (46,),
        width=max(1, min(width, height) // 420),
    )
    for stripe in range(3):
        y = towel_top + round(towel_h * (0.28 + stripe * 0.18))
        draw.line((towel_left + towel_w * 0.08, y, towel_left + towel_w * 0.92, y), fill=COLORS["pink"] + (120,), width=max(2, height // 320))

    _draw_product_texture_swipes(draw, size, variant_index, counter_y)
    _draw_coffee_scrub_scatter(draw, size, variant_index, counter_y)


def _draw_coffee_scrub_scatter(draw, size, variant_index, counter_y):
    width, height = size
    count = max(90, min(360, width * height // 4200))
    for index in range(count):
        x = (index * 743 + variant_index * 137) % width
        y_band = height - counter_y - max(1, height // 42)
        y = counter_y + max(10, ((index * 449 + variant_index * 251) % max(1, y_band)))
        radius = max(2, min(width, height) // (210 + (index % 120)))
        alpha = 74 + (index * 11) % 92
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=COLORS["coffee"] + (alpha,))


def _draw_product_texture_swipes(draw, size, variant_index, counter_y):
    width, height = size
    for index in range(3):
        left = round(width * ([0.08, 0.72, 0.2][index] if variant_index % 2 == 0 else [0.64, 0.08, 0.48][index]))
        top = counter_y + round(height * ([0.06, 0.13, 0.22][index]))
        swipe_w = round(width * ([0.18, 0.12, 0.24][index]))
        swipe_h = max(10, round(height * ([0.025, 0.018, 0.022][index])))
        fill = (118, 78, 62, 118 - index * 14)
        draw.rounded_rectangle(
            (left, top, left + swipe_w, top + swipe_h),
            radius=max(6, swipe_h // 2),
            fill=fill,
        )


def _draw_background_replace_set(draw, size, variant_index):
    width, height = size
    tile = max(84, min(width, height) // 8)
    line = COLORS["coffee"] + (30,)
    for x in range(-tile, width + tile, tile):
        draw.line((x, 0, x + tile // 3, height), fill=line, width=max(1, tile // 46))
    for y in range(tile // 2, height, tile):
        draw.line((0, y, width, y - tile // 7), fill=line, width=max(1, tile // 54))

    horizon_y = round(height * (0.58 + 0.03 * (variant_index % 2)))
    counter_y = round(height * 0.72)
    draw.rectangle((0, horizon_y, width, height), fill=COLORS["cream"] + (238,))
    draw.rectangle((0, counter_y, width, height), fill=COLORS["coffee"] + (235,))
    draw.rectangle((0, counter_y, width, counter_y + max(14, height // 74)), fill=COLORS["ink"] + (80,))

    accent_r = max(46, min(width, height) // 10)
    accent_x = round(width * (0.78 if variant_index % 2 == 0 else 0.2))
    accent_y = round(height * 0.25)
    draw.ellipse(
        (accent_x - accent_r, accent_y - accent_r, accent_x + accent_r, accent_y + accent_r),
        fill=COLORS["pink"] + (118,),
        outline=COLORS["cherry"] + (180,),
        width=max(2, min(width, height) // 300),
    )

    prop_w = round(width * 0.22)
    prop_h = round(height * 0.16)
    prop_left = round(width * (0.12 if variant_index % 2 == 0 else 0.66))
    prop_top = counter_y - prop_h - max(12, height // 46)
    draw.rounded_rectangle(
        (prop_left, prop_top, prop_left + prop_w, prop_top + prop_h),
        radius=max(8, min(width, height) // 80),
        fill=COLORS["pink_soft"] + (228,),
        outline=COLORS["ink"] + (70,),
        width=max(1, min(width, height) // 360),
    )
    draw.text((prop_left + max(8, width // 90), prop_top + max(8, height // 90)), "frank set", fill=COLORS["ink"] + (150,))


def _prepare_product(base_image, dimensions, preset_key, variant_index, edit_mode):
    product = _trim_transparent_border(base_image.convert("RGBA"))
    if edit_mode:
        product = ImageEnhance.Contrast(product).enhance(1.06)
        product = ImageEnhance.Sharpness(product).enhance(1.16)
    if preset_key in {"background-remove", "background-replace", "product-shot-lab", "clean-ecom"}:
        if _has_transparent_border(product):
            product = _trim_transparent_border(product)
        else:
            product = _trim_transparent_border(_remove_corner_background(product))

    if preset_key == "retail-mock":
        max_w = dimensions[0] * 0.42
        max_h = dimensions[1] * 0.56
    elif preset_key in {"product-shot-lab", "clean-ecom"}:
        max_w = dimensions[0] * 0.74
        max_h = dimensions[1] * 0.82
    else:
        max_w = dimensions[0] * 0.62
        max_h = dimensions[1] * 0.7
    if variant_index == 1:
        max_w *= 0.88
    elif variant_index == 2:
        max_w *= 1.08
    product.thumbnail((round(max_w), round(max_h)), Image.Resampling.LANCZOS)

    if preset_key in {"campaign-variants", "fb-model-image"}:
        product = product.rotate(-2 + variant_index * 2, expand=True, resample=Image.Resampling.BICUBIC)
    return product


def _trim_transparent_border(image):
    alpha = image.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    bbox = alpha.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def _has_transparent_border(image):
    alpha = image.getchannel("A")
    width, height = image.size
    sample_points = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
    return any(alpha.getpixel(point) < 32 for point in sample_points)


def _add_local_studio_finish(image, preset_key, variant_index):
    if preset_key == "background-remove":
        return
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    highlight_x = round(width * ([0.32, 0.68, 0.46, 0.58][variant_index % 4]))
    highlight_y = round(height * 0.24)
    highlight_w = round(width * 0.58)
    highlight_h = round(height * 0.42)
    draw.ellipse(
        (
            highlight_x - highlight_w // 2,
            highlight_y - highlight_h // 2,
            highlight_x + highlight_w // 2,
            highlight_y + highlight_h // 2,
        ),
        fill=(255, 255, 255, 38),
    )

    vignette = max(34, min(width, height) // 20)
    draw.rectangle((0, 0, width, vignette), fill=COLORS["ink"] + (12,))
    draw.rectangle((0, height - vignette, width, height), fill=COLORS["ink"] + (10,))
    image.alpha_composite(overlay)

    grain = Image.new("RGBA", image.size, (0, 0, 0, 0))
    grain_draw = ImageDraw.Draw(grain)
    dot_count = max(300, min(1800, width * height // 1800))
    for index in range(dot_count):
        x = (index * 1103 + variant_index * 401) % width
        y = (index * 917 + variant_index * 263) % height
        value = 255 if index % 3 else 68
        alpha = 4 + (index % 8)
        grain_draw.point((x, y), fill=(value, value, value, alpha))
    image.alpha_composite(grain)


def _prepare_mask_overlay(mask_image, product_size, dimensions):
    mask = ImageOps.grayscale(mask_image).resize(product_size, Image.Resampling.LANCZOS)
    mask = mask.filter(ImageFilter.GaussianBlur(max(1, min(product_size) // 180)))
    fill = Image.new("RGBA", product_size, COLORS["cherry"] + (0,))
    fill.putalpha(mask.point(lambda value: min(118, round(value * 0.5)) if value > 8 else 0))

    edge_alpha = mask.filter(ImageFilter.FIND_EDGES).point(lambda value: 210 if value > 18 else 0)
    edge = Image.new("RGBA", product_size, COLORS["ink"] + (0,))
    edge.putalpha(edge_alpha.filter(ImageFilter.GaussianBlur(max(1, min(dimensions) // 900))))
    fill.alpha_composite(edge)
    return fill


def _draw_mask_edit_badge(draw, dimensions, x, y, product_size):
    width, height = dimensions
    label = "masked edit"
    pad_x = max(10, width // 120)
    pad_y = max(6, height // 180)
    badge_w = max(width // 9, len(label) * max(7, width // 180))
    badge_h = max(24, height // 42)
    left = max(width // 34, min(x + product_size[0] - badge_w, width - badge_w - width // 34))
    top = max(height // 34, y - badge_h - max(8, height // 100))
    draw.rounded_rectangle(
        (left, top, left + badge_w, top + badge_h),
        radius=max(8, badge_h // 2),
        fill=COLORS["paper"] + (232,),
        outline=COLORS["cherry"] + (210,),
        width=max(2, width // 420),
    )
    draw.text((left + pad_x, top + pad_y), label, fill=COLORS["cherry"] + (255,))


def _remove_corner_background(image):
    image = image.convert("RGBA")
    width, height = image.size
    sample_points = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    samples = [image.getpixel(point)[:3] for point in sample_points]
    target = tuple(sum(sample[i] for sample in samples) // len(samples) for i in range(3))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            distance = math.sqrt(sum((value - target[i]) ** 2 for i, value in enumerate((r, g, b))))
            if distance < 36:
                pixels[x, y] = (r, g, b, 0)
            elif distance < 72:
                pixels[x, y] = (r, g, b, round(a * ((distance - 36) / 36)))
    return image.filter(ImageFilter.GaussianBlur(0.2))


def _shadow(product):
    alpha = product.getchannel("A")
    shadow = Image.new("RGBA", product.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(max(8, min(product.size) // 28))))
    return ImageEnhance.Brightness(shadow).enhance(0.32)


def _draw_no_reference_concept(draw, dimensions, preset_key, prompt):
    width, height = dimensions
    pack_w = round(width * 0.26)
    pack_h = round(height * 0.56)
    left = round((width - pack_w) * 0.5)
    top = round(height * 0.18)
    shadow_offset = max(10, width // 90)
    draw.rounded_rectangle(
        (left + shadow_offset, top + shadow_offset, left + pack_w + shadow_offset, top + pack_h + shadow_offset),
        radius=max(18, min(width, height) // 36),
        fill=COLORS["ink"] + (44,),
    )
    draw.rounded_rectangle(
        (left, top, left + pack_w, top + pack_h),
        radius=max(18, min(width, height) // 38),
        fill=(255, 255, 255, 255),
        outline=COLORS["ink"] + (230,),
        width=max(3, min(width, height) // 190),
    )
    label_h = round(pack_h * 0.16)
    label_pad = max(12, pack_w // 14)
    draw.rounded_rectangle(
        (left + label_pad, top + label_pad, left + pack_w - label_pad, top + label_pad + label_h),
        radius=max(10, label_h // 4),
        fill=COLORS["pink_soft"] + (255,),
        outline=COLORS["cherry"] + (210,),
        width=max(2, width // 430),
    )
    draw.text((left + label_pad * 1.45, top + label_pad * 1.35), "frank", fill=COLORS["ink"] + (255,))
    draw.text((left + label_pad * 1.45, top + label_pad * 2.25), "body", fill=COLORS["ink"] + (255,))
    divider_y = top + round(pack_h * 0.28)
    draw.rectangle((left + label_pad, divider_y, left + pack_w - label_pad, divider_y + max(3, height // 300)), fill=COLORS["ink"] + (230,))
    draw.text((left + label_pad, top + round(pack_h * 0.34)), "coffee", fill=COLORS["ink"] + (255,))
    draw.text((left + label_pad, top + round(pack_h * 0.42)), "scrub", fill=COLORS["ink"] + (255,))
    draw.text((left + label_pad, top + round(pack_h * 0.52)), "original", fill=COLORS["coffee"] + (220,))
    for index in range(54):
        x = left + label_pad + (index * 37) % max(1, pack_w - label_pad * 2)
        y = top + round(pack_h * 0.64) + (index * 53) % max(1, round(pack_h * 0.22))
        radius = max(2, min(width, height) // (260 + index % 70))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=COLORS["coffee"] + (130 + index % 70,))
    cap_h = round(pack_h * 0.055)
    draw.rounded_rectangle(
        (
            left + round(pack_w * 0.22),
            top + pack_h - label_pad - cap_h,
            left + round(pack_w * 0.78),
            top + pack_h - label_pad,
        ),
        radius=max(8, cap_h // 2),
        fill=COLORS["pink"] + (240,),
    )


def _draw_variant_finish(draw, dimensions, preset_key, prompt, variant_index, has_product):
    width, height = dimensions
    accent_h = max(10, height // 130)
    if variant_index % 2 == 0:
        draw.rectangle((0, height - accent_h, width, height), fill=COLORS["cherry"] + (220,))
    else:
        draw.rectangle((0, 0, width, accent_h), fill=COLORS["pink"] + (220,))

    if has_product and preset_key in {"retail-mock", "campaign-variants"}:
        caption = "frank body"
        draw.text((max(20, width // 36), height - max(44, height // 26)), caption, fill=COLORS["ink"] + (180,))


def _fit_on_canvas(image, size, color):
    canvas = Image.new("RGBA", size, color + (255,))
    work = image.convert("RGBA")
    work.thumbnail((round(size[0] * 0.92), round(size[1] * 0.92)), Image.Resampling.LANCZOS)
    x = (size[0] - work.width) // 2
    y = (size[1] - work.height) // 2
    canvas.alpha_composite(_shadow(work), (x + max(4, size[0] // 220), y + max(6, size[1] // 180)))
    canvas.alpha_composite(work, (x, y))
    return canvas


def _handoff_manifest(
    session,
    turns,
    approved_assets,
    proof_assets,
    reference_assets,
    payload,
    pack_path,
    job_context=None,
    review_board=None,
    channel_exports=None,
):
    job_context = job_context or {}
    channel_exports = channel_exports or {}
    return {
        "app": "Frank Create",
        "package_type": "session_handoff",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session": _public_record(session),
        "project": job_context.get("project"),
        "brief": job_context.get("brief"),
        "summary": payload.get("summary") or "Approved Frank Create creative handoff.",
        "counts": {
            "approved_assets": len(approved_assets),
            "approved_images": _media_count(approved_assets, "image"),
            "approved_videos": _media_count(approved_assets, "video"),
            "proof_assets": len(proof_assets),
            "references": len(reference_assets),
            "channel_export_sets": len(channel_exports),
            "channel_export_files": _handoff_channel_export_file_count(channel_exports),
            "approved_asset_ids": [asset.get("id") for asset in approved_assets],
            "proof_asset_ids": [asset.get("id") for asset in proof_assets],
        },
        "approved_assets": [_asset_manifest(asset) for asset in approved_assets],
        "proof_assets": [_asset_manifest(asset) for asset in proof_assets],
        "reference_assets": [_asset_manifest(asset) for asset in reference_assets],
        "turns": [_turn_manifest(turn) for turn in turns],
        "review_board": review_board or {},
        "channel_exports": _public_handoff_channel_exports(channel_exports),
        "pack_file": str(pack_path),
        "sync_ready": {
            "local_first": True,
            "remote_id": session.get("remote_id"),
            "sync_status": session.get("sync_status", "local"),
        },
    }


def _handoff_readme(session, approved_assets, reference_assets, job_context=None, channel_exports=None, proof_assets=None):
    proof_assets = proof_assets or []
    image_count = _media_count(approved_assets, "image")
    video_count = _media_count(approved_assets, "video")
    channel_export_count = _handoff_channel_export_file_count(channel_exports or {})
    project = (job_context or {}).get("project") or {}
    brief = (job_context or {}).get("brief") or {}
    lines = [
        f"# {session.get('name') or 'Frank Create'}",
        "",
        "Frank Create handoff pack.",
        "",
        f"- Project: {project.get('name') or 'Not linked'}",
        f"- Brief: {brief.get('title') or session.get('summary') or 'Not linked'}",
        f"- Product: {brief.get('product_name') or 'Not set'}",
        f"- Channel: {brief.get('channel') or 'Not set'}",
        f"- Approved assets: {len(approved_assets)}",
        f"- Approved images: {image_count}",
        f"- Approved videos: {video_count}",
        f"- Proof assets: {len(proof_assets)}",
        f"- Reference images: {len(reference_assets)}",
        f"- Channel export files: {channel_export_count}",
        f"- Workflows: {_readme_workflow_summary(approved_assets)}",
        "- Manifest: frank-create-handoff.json",
        "",
        "Folders:",
        "- approved/: approved image files ready for review or channel export",
        "- proofs/: review-state proof files such as masked-edit checks",
        "- references/: source/reference material used in the session",
        "- review/: visual review board for the approved round",
        "- workflows/: standalone workflow provenance JSON for approved and proof assets",
        "- channel-exports/: channel-ready derivatives for approved image assets",
        "",
        "Keep the JSON manifest with the images so prompts, settings, notes, file integrity, and sync metadata travel together.",
    ]
    return "\n".join(lines) + "\n"


def _readme_workflow_summary(assets):
    workflow_keys = []
    for asset in assets:
        settings = _json_loads(asset.get("settings_json"), {})
        workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
        if isinstance(workflow, dict) and workflow.get("workflow_key"):
            workflow_keys.append(f"{workflow.get('workflow_key')} ({workflow.get('engine') or 'engine not set'})")
    if not workflow_keys:
        return "Not set"
    return ", ".join(sorted(set(workflow_keys)))


def _create_handoff_review_board(session, approved_assets, reference_assets, job_context=None):
    job_context = job_context or {}
    project = job_context.get("project") or {}
    brief = job_context.get("brief") or {}
    approved_count = max(1, len(approved_assets))
    columns = 2 if approved_count <= 4 else 3
    tile_w = 520
    tile_h = 560
    gap = 34
    margin = 56
    header_h = 190
    footer_h = 104
    rows = math.ceil(approved_count / columns)
    width = max(1280, margin * 2 + columns * tile_w + (columns - 1) * gap)
    height = max(860, header_h + rows * tile_h + max(0, rows - 1) * gap + footer_h)

    board = Image.new("RGBA", (width, height), COLORS["paper"] + (255,))
    draw = ImageDraw.Draw(board)
    draw.rectangle((0, 0, width, 18), fill=COLORS["pink"] + (255,))
    draw.rectangle((0, height - 18, width, height), fill=COLORS["cherry"] + (255,))
    _draw_review_board_header(draw, session, project, brief, width, margin)

    for index, asset in enumerate(approved_assets):
        col = index % columns
        row = index // columns
        left = margin + col * (tile_w + gap)
        top = header_h + row * (tile_h + gap)
        _draw_review_board_tile(board, draw, asset, index + 1, (left, top, left + tile_w, top + tile_h))

    footer_y = height - footer_h + 24
    footer = (
        f"{len(approved_assets)} approved / {len(reference_assets)} reference"
        " | prompts, notes, workflow provenance, and media integrity live in frank-create-handoff.json"
    )
    draw.text((margin, footer_y), footer, fill=COLORS["coffee"] + (255,))
    draw.text((margin, footer_y + 28), "frank body | Frank Create review board", fill=COLORS["ink"] + (235,))

    output = BytesIO()
    board.convert("RGB").save(output, format="PNG", optimize=True)
    return {
        "bytes": output.getvalue(),
        "metadata": {
            "archive_path": "review/frank-create-review-board.png",
            "width": width,
            "height": height,
            "format": "png",
            "approved_asset_count": len(approved_assets),
            "reference_asset_count": len(reference_assets),
            "layout": {"columns": columns, "rows": rows},
        },
    }


def _draw_review_board_header(draw, session, project, brief, width, margin):
    title = session.get("name") or "Frank Create review"
    subtitle_parts = [
        project.get("name"),
        brief.get("title") or session.get("summary"),
        brief.get("channel"),
    ]
    subtitle = " / ".join(part for part in subtitle_parts if part)
    draw.text((margin, 46), "frank body", fill=COLORS["cherry"] + (255,))
    draw.text((margin, 82), title[:82], fill=COLORS["ink"] + (255,))
    draw.text((margin, 118), subtitle[:120] if subtitle else "Approved creative review board", fill=COLORS["coffee"] + (255,))
    draw.rounded_rectangle(
        (width - margin - 220, 48, width - margin, 126),
        radius=18,
        fill=COLORS["pink_soft"] + (255,),
        outline=COLORS["cherry"] + (190,),
        width=2,
    )
    draw.text((width - margin - 192, 76), "Approved. Hot.", fill=COLORS["cherry"] + (255,))


def _draw_review_board_tile(board, draw, asset, index, box):
    left, top, right, bottom = box
    draw.rounded_rectangle(box, radius=22, fill=(255, 255, 255, 245), outline=COLORS["ink"] + (44,), width=2)
    media_box = (left + 24, top + 24, right - 24, top + 396)
    draw.rounded_rectangle(media_box, radius=18, fill=COLORS["cream"] + (255,))

    image = _review_board_asset_image(asset)
    if image:
        image.thumbnail((media_box[2] - media_box[0] - 24, media_box[3] - media_box[1] - 24), Image.Resampling.LANCZOS)
        image_left = media_box[0] + round((media_box[2] - media_box[0] - image.width) / 2)
        image_top = media_box[1] + round((media_box[3] - media_box[1] - image.height) / 2)
        board.alpha_composite(image.convert("RGBA"), (image_left, image_top))
    else:
        draw.text((media_box[0] + 28, media_box[1] + 36), "media unavailable", fill=COLORS["coffee"] + (255,))

    badge = f"{index:02d}"
    draw.ellipse((left + 24, top + 24, left + 76, top + 76), fill=COLORS["cherry"] + (255,))
    draw.text((left + 41, top + 42), badge, fill=(255, 255, 255, 255))

    title = asset.get("title") or asset.get("id") or "Approved asset"
    meta = f"{asset.get('media_type') or 'image'} / {asset.get('model') or asset.get('provider') or 'local'}"
    notes = asset.get("notes") or asset.get("prompt") or "No review note."
    text_left = left + 28
    draw.text((text_left, top + 424), title[:58], fill=COLORS["ink"] + (255,))
    draw.text((text_left, top + 452), meta[:72], fill=COLORS["cherry"] + (235,))
    for line_index, line in enumerate(textwrap.wrap(notes, width=62)[:3]):
        draw.text((text_left, top + 486 + line_index * 22), line, fill=COLORS["coffee"] + (255,))


def _review_board_asset_image(asset):
    path = _resolve_media_path(asset.get("file_path") or "")
    if not path or not path.exists():
        return None
    try:
        with Image.open(path) as image:
            image.seek(0)
            return image.convert("RGBA")
    except Exception:
        return None


def _archive_assets(archive, assets, folder):
    used_names = set()
    for asset in assets:
        path = _resolve_media_path(asset.get("file_path") or "")
        if not path or not path.exists():
            raise FileNotFoundError(_handoff_missing_media_message(asset, folder.rstrip("s")))
        archive.write(path, arcname=asset.get("archive_path") or _asset_archive_path(asset, folder, used_names, path))


def _handoff_assets_with_archive_paths(assets, folder, label):
    used_names = set()
    enriched = []
    for asset in assets:
        path = _resolve_media_path(asset.get("file_path") or "")
        if not path or not path.exists():
            raise FileNotFoundError(_handoff_missing_media_message(asset, label))
        enriched.append({**asset, "archive_path": _asset_archive_path(asset, folder, used_names, path)})
    return enriched


def _handoff_assets_with_workflow_sidecars(assets):
    used_names = set()
    enriched = []
    for asset in assets:
        settings = _json_loads(asset.get("settings_json"), {})
        workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
        if isinstance(workflow, dict) and workflow:
            enriched.append({**asset, "workflow_sidecar_path": _workflow_sidecar_path(asset, used_names)})
        else:
            enriched.append(asset)
    return enriched


def _archive_workflow_sidecars(archive, assets):
    for asset in assets:
        sidecar_path = asset.get("workflow_sidecar_path")
        if not sidecar_path:
            continue
        archive.writestr(sidecar_path, json.dumps(_workflow_sidecar_manifest(asset), indent=2, sort_keys=True))


def _handoff_channel_export_sets(store, approved_assets, metadata):
    channel_exports = {}
    used_folders = set()
    for asset in approved_assets:
        if (asset.get("media_type") or "image") != "image":
            continue
        source = _load_asset_image(asset)
        if source is None:
            raise FileNotFoundError(_handoff_missing_media_message(asset, "approved"))
        folder = _handoff_channel_export_folder(asset, used_folders)
        exports = {}
        files = []
        for preset in IMAGE_CHANNEL_SET_PRESETS:
            prepared = _prepare_image_export(store, asset, source, preset, metadata)
            image_file = f"{folder}/{preset}/{asset['id']}-{preset}.{prepared['format']}"
            metadata_file = f"{folder}/{preset}/{asset['id']}-{preset}.json"
            image_bytes = _image_bytes(prepared["image"], prepared["format"])
            media_integrity = _bytes_integrity(image_bytes)
            export_manifest = {
                **prepared["metadata"],
                "image_file": image_file,
                "metadata_file": metadata_file,
                "media_integrity": media_integrity,
            }
            metadata_bytes = json.dumps(export_manifest, indent=2, sort_keys=True).encode("utf-8")
            files.append((image_file, image_bytes))
            files.append((metadata_file, metadata_bytes))
            exports[preset] = {
                "preset": preset,
                "format": prepared["format"],
                "width": prepared["image"].width,
                "height": prepared["image"].height,
                "image_file": image_file,
                "metadata_file": metadata_file,
                "media_integrity": media_integrity,
            }
        channel_exports[asset["id"]] = {
            "asset_id": asset["id"],
            "asset_title": asset.get("title"),
            "archive_folder": folder,
            "presets": list(IMAGE_CHANNEL_SET_PRESETS),
            "preset_count": len(IMAGE_CHANNEL_SET_PRESETS),
            "exports": exports,
            "_files": files,
        }
    return channel_exports


def _handoff_channel_export_folder(asset, used_folders):
    stem = _safe_file_stem(asset.get("title") or asset.get("id") or "asset")
    folder = f"channel-exports/{stem}"
    index = 2
    while folder in used_folders:
        folder = f"channel-exports/{stem}-{index}"
        index += 1
    used_folders.add(folder)
    return folder


def _handoff_assets_with_channel_export_counts(assets, channel_exports):
    enriched = []
    for asset in assets:
        export_set = channel_exports.get(asset.get("id")) or {}
        count = export_set.get("preset_count")
        if count:
            enriched.append({**asset, "channel_export_count": count})
        else:
            enriched.append(asset)
    return enriched


def _archive_handoff_channel_exports(archive, channel_exports):
    for export_set in channel_exports.values():
        for archive_path, data in export_set.get("_files", []):
            archive.writestr(archive_path, data)


def _public_handoff_channel_exports(channel_exports):
    return {
        asset_id: {key: value for key, value in export_set.items() if key != "_files"}
        for asset_id, export_set in channel_exports.items()
    }


def _handoff_channel_export_file_count(channel_exports):
    return sum(len((export_set.get("exports") or {})) for export_set in (channel_exports or {}).values())


def _workflow_sidecar_manifest(asset):
    settings = _sanitize_manifest_value(_json_loads(asset.get("settings_json"), {}))
    workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
    return {
        "asset_id": asset.get("id"),
        "asset_title": asset.get("title"),
        "media_type": asset.get("media_type") or "image",
        "provider": asset.get("provider"),
        "model": asset.get("model"),
        "prompt": asset.get("prompt"),
        "settings": settings,
        "workflow_provenance": workflow or {},
        "workflow_bridge": _workflow_bridge_manifest({"id": asset.get("id")}, workflow or {}),
        "source_asset_id": asset.get("source_asset_id"),
        "reference_asset_ids": _json_loads(asset.get("reference_asset_ids_json"), []),
        "archive_path": asset.get("archive_path"),
        "sync_status": asset.get("sync_status") or "local",
        "created_at": asset.get("created_at"),
        "updated_at": asset.get("updated_at"),
    }


def _workflow_sidecar_path(asset, used_names):
    stem = _safe_file_stem(asset.get("title") or asset.get("id") or "asset")
    name = f"{stem}-{asset.get('id')}-workflow.json"
    while name in used_names:
        name = f"{stem}-{asset.get('id')}-{len(used_names)}-workflow.json"
    used_names.add(name)
    return f"workflows/{name}"


def _asset_archive_path(asset, folder, used_names, path=None):
    path = path or _resolve_media_path(asset.get("file_path") or "")
    ext = path.suffix if path else ""
    ext = ext or ".png"
    stem = _safe_file_stem(asset.get("title") or asset.get("id") or "asset")
    name = f"{stem}-{asset.get('id')}{ext}"
    while name in used_names:
        name = f"{stem}-{asset.get('id')}-{len(used_names)}{ext}"
    used_names.add(name)
    return f"{folder}/{name}"


def _handoff_missing_media_message(asset, label):
    return (
        f"{label} asset media is unavailable for {asset.get('id')}: "
        f"{asset.get('file_path') or 'missing file_path'}"
    )


def _media_count(assets, media_type):
    return sum(1 for asset in assets if (asset.get("media_type") or "image") == media_type)


def _project_manifest(project):
    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "client": project.get("client"),
        "status": project.get("status"),
        "sync_status": project.get("sync_status"),
        "remote_id": project.get("remote_id"),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
    }


def _brief_manifest(brief):
    return {
        "id": brief.get("id"),
        "project_id": brief.get("project_id"),
        "title": brief.get("title"),
        "product_name": brief.get("product_name"),
        "task_type": brief.get("task_type"),
        "channel": brief.get("channel"),
        "tone": brief.get("tone"),
        "prompt": brief.get("prompt"),
        "negative_prompt": brief.get("negative_prompt"),
        "reference_image_path": brief.get("reference_image_path"),
        "status": brief.get("status"),
        "sync_status": brief.get("sync_status"),
        "remote_id": brief.get("remote_id"),
        "created_at": brief.get("created_at"),
        "updated_at": brief.get("updated_at"),
    }


def _asset_manifest(asset):
    settings = _sanitize_manifest_value(_json_loads(asset.get("settings_json"), {}))
    workflow_provenance = settings.get("workflow_provenance") if isinstance(settings, dict) else None
    manifest = {
        "id": asset.get("id"),
        "run_id": asset.get("run_id"),
        "brief_id": asset.get("brief_id"),
        "title": asset.get("title"),
        "kind": asset.get("kind"),
        "media_type": asset.get("media_type"),
        "provider": asset.get("provider"),
        "model": asset.get("model"),
        "prompt": asset.get("prompt"),
        "settings": settings,
        "source_asset_id": asset.get("source_asset_id"),
        "reference_asset_ids": _json_loads(asset.get("reference_asset_ids_json"), []),
        "file_path": asset.get("file_path"),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "favorite": bool(asset.get("favorite")),
        "approval_status": asset.get("approval_status"),
        "notes": asset.get("notes"),
        "sync_status": asset.get("sync_status"),
        "remote_id": asset.get("remote_id"),
        "created_at": asset.get("created_at"),
        "updated_at": asset.get("updated_at"),
    }
    if asset.get("archive_path"):
        manifest["archive_path"] = asset.get("archive_path")
    if asset.get("workflow_sidecar_path"):
        manifest["workflow_sidecar_path"] = asset.get("workflow_sidecar_path")
    if asset.get("channel_export_count"):
        manifest["channel_export_count"] = asset.get("channel_export_count")
    if workflow_provenance:
        manifest["workflow_provenance"] = workflow_provenance
    media_path = _resolve_media_path(asset.get("file_path") or "")
    if media_path and media_path.exists():
        manifest["media_integrity"] = _file_integrity(media_path)
    return manifest


def _turn_manifest(turn):
    return {
        "id": turn.get("id"),
        "kind": turn.get("kind"),
        "provider": turn.get("provider"),
        "model": turn.get("model"),
        "prompt": turn.get("prompt"),
        "settings": _sanitize_manifest_value(_json_loads(turn.get("settings_json"), {})),
        "source_asset_id": turn.get("source_asset_id"),
        "reference_asset_ids": _json_loads(turn.get("reference_asset_ids_json"), []),
        "output_asset_ids": _json_loads(turn.get("output_asset_ids_json"), []),
        "frank_body_mode": bool(turn.get("frank_body_mode")),
        "preset_key": turn.get("preset_key"),
        "status": turn.get("status"),
        "error": _json_loads(turn.get("error_json"), None),
        "sync_status": turn.get("sync_status"),
        "remote_id": turn.get("remote_id"),
        "created_at": turn.get("created_at"),
        "updated_at": turn.get("updated_at"),
    }


def _workflow_bridge_manifest(asset_manifest, workflow):
    asset_id = asset_manifest.get("id")
    if not asset_id:
        return {
            "can_open_raw_canvas": False,
            "can_load_comfy_api_prompt": False,
            "raw_canvas_load_status": "unavailable",
            "comfy_node_types": [],
        }

    api_prompt_json = workflow.get("workflow_json") if isinstance(workflow.get("workflow_json"), dict) else None
    can_load_prompt = bool(api_prompt_json)
    return {
        "asset_id": asset_id,
        "workflow_key": workflow.get("workflow_key"),
        "engine": workflow.get("engine"),
        "can_open_raw_canvas": True,
        "can_load_comfy_api_prompt": can_load_prompt,
        "raw_canvas_load_status": "api_prompt_attached" if can_load_prompt else "receipt_only",
        "comfy_node_types": _workflow_bridge_node_types(workflow, api_prompt_json),
        "raw_canvas_url": f"/comfy/?{urlencode({'frankAssetId': asset_id})}",
        "workflow_receipt_url": f"/api/frank/assets/{quote(str(asset_id), safe='')}/workflow",
    }


def _workflow_bridge_node_types(workflow, api_prompt_json=None):
    fallback_by_workflow = {
        "frank-local-variant-renderer": ["FrankCreateVariant", "SaveImage"],
        "frank-local-background-remove-renderer": ["FrankCreateBackgroundRemove", "SaveImage"],
        "frank-local-background-replace-renderer": ["FrankCreateBackgroundReplace", "SaveImage"],
        "frank-local-masked-edit-renderer": ["FrankCreateMaskedEdit", "SaveImage"],
        "frank-local-video-storyboard": ["FrankCreateVideoStoryboard", "SaveAnimatedImage"],
    }
    if workflow.get("workflow_key") in fallback_by_workflow:
        return fallback_by_workflow[workflow.get("workflow_key")]
    if isinstance(workflow.get("comfy_node_types"), list):
        return [str(item) for item in workflow.get("comfy_node_types") if item]
    if isinstance(api_prompt_json, dict):
        return [
            str(node.get("class_type"))
            for _node_id, node in sorted(api_prompt_json.items(), key=lambda item: _workflow_node_sort_key(item[0]))
            if isinstance(node, dict) and node.get("class_type")
        ]
    return []


def _workflow_node_sort_key(node_id):
    try:
        return (0, int(node_id))
    except (TypeError, ValueError):
        return (1, str(node_id))


def _sanitize_manifest_value(value):
    if isinstance(value, dict):
        return {
            key: "[server-side secret]" if _manifest_key_is_sensitive(key) else _sanitize_manifest_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_manifest_value(item) for item in value]
    if isinstance(value, str) and _manifest_value_is_sensitive(value):
        return "[server-side secret]"
    return value


def _manifest_key_is_sensitive(key):
    return bool(re.search(r"api[_-]?key|token|secret|authorization|bearer|password|credential", str(key), re.IGNORECASE))


def _manifest_value_is_sensitive(value):
    return bool(re.search(r"(?i)(sk-[a-z0-9_-]{20,}|r8_[a-z0-9]{20,}|AIza[a-z0-9_-]{20,}|\bBearer\s+\S{12,})", value))


def _settings_with_workflow_provenance(settings, workflow_provenance):
    return {**dict(settings or {}), "workflow_provenance": workflow_provenance}


def _frank_renderer_workflow_provenance(payload, preset_key, variant_index, edit_mode, dimensions, mask_asset_id=None):
    if preset_key == "background-remove" and not mask_asset_id:
        workflow_key = "frank-local-background-remove-renderer"
    elif preset_key == "background-replace" and not mask_asset_id:
        workflow_key = "frank-local-background-replace-renderer"
    elif mask_asset_id:
        workflow_key = "frank-local-masked-edit-renderer"
    else:
        workflow_key = "frank-local-variant-renderer"
    node_types = {
        "frank-local-background-remove-renderer": ["FrankCreateBackgroundRemove", "SaveImage"],
        "frank-local-background-replace-renderer": ["FrankCreateBackgroundReplace", "SaveImage"],
        "frank-local-masked-edit-renderer": ["FrankCreateMaskedEdit", "SaveImage"],
        "frank-local-variant-renderer": ["FrankCreateVariant", "SaveImage"],
    }
    return {
        "engine": "frank_renderer",
        "workflow_key": workflow_key,
        "comfy_node_types": node_types[workflow_key],
        "preset_key": preset_key,
        "visual_treatment": "simulated_frank_body_product_photography",
        "demo_realism": "high_fidelity_local_mock",
        "placeholder_art": False,
        "variant_index": int(variant_index),
        "edit_mode": bool(edit_mode),
        "masked_edit": bool(mask_asset_id),
        "background_removed": workflow_key == "frank-local-background-remove-renderer",
        "background_replaced": workflow_key == "frank-local-background-replace-renderer",
        "width": dimensions[0],
        "height": dimensions[1],
        "reference_count": len(payload.get("reference_asset_ids") or []),
        "source_asset_id": payload.get("edit_source_asset_id") or payload.get("source_asset_id"),
        "mask_asset_id": mask_asset_id,
    }


def _public_record(record):
    return {key: value for key, value in dict(record).items() if key not in {"id"} or value}


def _json_loads(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _safe_file_stem(value):
    clean = "".join(char.lower() if char.isalnum() else "-" for char in str(value))
    clean = "-".join(part for part in clean.split("-") if part)
    return clean[:72] or "frank-create"


def _palette_for(preset_key, variant_index):
    palettes = {
        "clean-ecom": [(255, 255, 255), COLORS["paper"]],
        "product-shot-lab": [COLORS["paper"], COLORS["pink_soft"]],
        "fb-lifestyle": [(246, 223, 212), (215, 189, 177)],
        "fb-model-image": [(255, 225, 211), (238, 197, 176)],
        "product-texture": [(244, 220, 204), (128, 86, 70)],
        "retail-mock": [(245, 240, 237), (222, 210, 203)],
        "background-remove": [(255, 255, 255), (255, 255, 255)],
        "background-replace": [COLORS["pink_soft"], COLORS["cream"]],
        "campaign-variants": [COLORS["pink_soft"], COLORS["pink"]],
    }
    palette = palettes.get(preset_key, palettes["product-shot-lab"])
    if variant_index % 3 == 1:
        return [palette[1], COLORS["paper"]]
    if variant_index % 3 == 2:
        return [COLORS["paper"], COLORS["cream"]]
    return palette


def _x_bias(preset_key, variant_index):
    if preset_key in {"campaign-variants", "retail-mock"}:
        return [0.5, 0.62, 0.38, 0.5][variant_index % 4]
    return [0.5, 0.48, 0.52, 0.5][variant_index % 4]


def _y_bias(preset_key, variant_index):
    if preset_key == "retail-mock":
        return 0.62
    return [0.52, 0.48, 0.56, 0.5][variant_index % 4]


def _asset_title(model, preset_key, index):
    label = model.get("short_label") or model.get("label") or model.get("id")
    clean_preset = preset_key.replace("-", " ").title()
    return f"{label} / {clean_preset} {index + 1:02d}"


def _find_asset(store, asset_id):
    if not asset_id:
        return None
    for asset in store.list_assets():
        if asset["id"] == asset_id:
            return asset
    return None


def _load_asset_image(asset):
    if not asset:
        return None
    path = _resolve_media_path(asset.get("file_path") or "")
    if not path or not path.exists():
        return None
    return ImageOps.exif_transpose(Image.open(path)).convert("RGBA")


def _resolve_media_path(file_path):
    if not file_path:
        return None
    normalized = file_path.replace("\\", "/")
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    if normalized.startswith("input/"):
        return _input_dir() / normalized[len("input/") :]
    if normalized.startswith("output/"):
        return _output_dir() / normalized[len("output/") :]
    if normalized.startswith("user/"):
        return _user_dir().parent / normalized[len("user/") :]
    return _input_dir() / normalized


def _view_url(filename, subfolder, image_type):
    params = {"filename": filename, "type": image_type}
    if subfolder:
        params["subfolder"] = subfolder
    return f"/api/view?{urlencode(params)}"


def _input_dir():
    override = _media_root_override()
    if override:
        return override / "input"
    try:
        import folder_paths

        return Path(folder_paths.get_input_directory())
    except Exception:
        return Path.cwd() / "input"


def _output_dir():
    override = _media_root_override()
    if override:
        return override / "output"
    try:
        import folder_paths

        return Path(folder_paths.get_output_directory())
    except Exception:
        return Path.cwd() / "output"


def _user_dir():
    override = _media_root_override()
    if override:
        return override / "user"
    try:
        import folder_paths

        return Path(folder_paths.get_user_directory())
    except Exception:
        return Path.cwd() / "user"


def _user_export_dir():
    return _user_dir() / "frank_create" / "exports"


def _media_root_override():
    value = os.environ.get("FRANK_CREATE_MEDIA_ROOT")
    return Path(value) if value else None
