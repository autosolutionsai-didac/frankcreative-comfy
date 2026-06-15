import asyncio
import inspect
import shutil
import time
from pathlib import Path

from .comfy_workflow import (
    build_checkpoint_diffusion_prompt,
    build_checkpoint_img2img_prompt,
    build_checkpoint_inpaint_prompt,
    build_frank_variant_prompt,
    extract_saved_images,
)
from .local_image import dimensions_for, _resolve_media_path, _settings_with_workflow_provenance
from .models import get_preferred_checkpoint


class ComfyExecutionUnavailable(RuntimeError):
    pass


async def run_comfy_studio_turn(
    prompt_server,
    store,
    turn,
    payload,
    model,
    timeout_seconds=120,
    poll_interval=0.5,
):
    if prompt_server is None or not getattr(prompt_server, "prompt_queue", None):
        raise ComfyExecutionUnavailable("Comfy PromptServer is unavailable")

    settings = payload.get("settings") or {}
    count = max(1, min(int(settings.get("count") or 1), 4))
    width, height = dimensions_for(settings.get("aspect_ratio", "1:1"), settings.get("image_size", "2K"))
    source_asset = _find_asset(store, payload.get("edit_source_asset_id") or payload.get("source_asset_id"))
    mask_asset = _find_asset(store, payload.get("mask_asset_id"))
    reference_assets = [_find_asset(store, asset_id) for asset_id in payload.get("reference_asset_ids", [])]
    reference_assets = [asset for asset in reference_assets if asset]
    reference_file_path = _comfy_loadable_reference_path(
        (source_asset or (reference_assets[0] if reference_assets else None) or {}).get("file_path"),
        turn["id"],
    )
    mask_file_path = _comfy_loadable_reference_path(mask_asset.get("file_path") if mask_asset else None, turn["id"])
    checkpoint_name = get_preferred_checkpoint()
    if payload.get("kind") == "masked_edit":
        if not checkpoint_name:
            raise ComfyExecutionUnavailable("Masked edit Comfy workflow requires a local checkpoint")
        if not source_asset or not reference_file_path:
            raise ComfyExecutionUnavailable("Masked edit Comfy workflow requires a source image")
        if not mask_asset or not mask_file_path:
            raise ComfyExecutionUnavailable("Masked edit Comfy workflow requires a mask image")
    created_assets = []

    for index in range(count):
        prompt_id = f"frank-{turn['id']}-{index + 1}"
        if checkpoint_name and reference_file_path and mask_file_path:
            workflow = build_checkpoint_inpaint_prompt(
                prompt_text=payload.get("prompt") or turn.get("prompt") or "",
                turn_id=turn["id"],
                checkpoint_name=checkpoint_name,
                width=width,
                height=height,
                variant_index=index,
                reference_file_path=reference_file_path,
                mask_file_path=mask_file_path,
                denoise=_checkpoint_inpaint_denoise(payload),
            )
        elif checkpoint_name and reference_file_path:
            workflow = build_checkpoint_img2img_prompt(
                prompt_text=payload.get("prompt") or turn.get("prompt") or "",
                turn_id=turn["id"],
                checkpoint_name=checkpoint_name,
                width=width,
                height=height,
                variant_index=index,
                reference_file_path=reference_file_path,
                denoise=_checkpoint_img2img_denoise(payload, source_asset),
            )
        elif checkpoint_name:
            workflow = build_checkpoint_diffusion_prompt(
                prompt_text=payload.get("prompt") or turn.get("prompt") or "",
                turn_id=turn["id"],
                checkpoint_name=checkpoint_name,
                width=width,
                height=height,
                variant_index=index,
            )
        else:
            workflow = build_frank_variant_prompt(
                prompt_text=payload.get("prompt") or turn.get("prompt") or "",
                turn_id=turn["id"],
                preset_key=payload.get("preset_key") or "product-shot-lab",
                width=width,
                height=height,
                variant_index=index,
                reference_file_path=reference_file_path,
                edit_mode=bool(source_asset),
            )
        workflow_provenance = _comfy_workflow_provenance(
            workflow=workflow,
            checkpoint_name=checkpoint_name,
            preset_key=payload.get("preset_key") or "product-shot-lab",
            variant_index=index,
            reference_file_path=reference_file_path,
            mask_file_path=mask_file_path,
            source_asset_id=source_asset["id"] if source_asset else None,
            mask_asset_id=mask_asset["id"] if mask_asset else None,
            dimensions=(width, height),
        )
        await _queue_prompt(prompt_server, prompt_id, workflow)
        images = await _wait_for_saved_images(prompt_server, prompt_id, timeout_seconds, poll_interval)
        if not images:
            raise ComfyExecutionUnavailable(f"Comfy produced no saved image for {prompt_id}")

        for image in images:
            asset = store.create_asset(
                {
                    "session_id": turn["session_id"],
                    "turn_id": turn["id"],
                    "kind": "candidate",
                    "title": _asset_title(model, payload.get("preset_key") or "product-shot-lab", len(created_assets)),
                    "media_type": "image",
                    "provider": model["provider"],
                    "model": model["id"],
                    "prompt": payload.get("prompt") or turn.get("prompt") or "",
                    "settings": _settings_with_workflow_provenance(settings, workflow_provenance),
                    "source_asset_id": source_asset["id"] if source_asset else None,
                    "reference_asset_ids": [asset["id"] for asset in reference_assets],
                    "file_path": image["file_path"],
                    "preview_url": image["preview_url"],
                    "width": width,
                    "height": height,
                    "approval_status": "review",
                    "sync_status": "local",
                }
            )
            created_assets.append(asset)

    updated_turn = store.update_turn(
        turn["id"],
        {"status": "complete", "output_asset_ids": [asset["id"] for asset in created_assets]},
    )
    return updated_turn, created_assets


async def _queue_prompt(prompt_server, prompt_id, workflow):
    if getattr(prompt_server, "node_replace_manager", None):
        prompt_server.node_replace_manager.apply_replacements(workflow)

    valid = await _maybe_await(_validate_prompt(prompt_id, workflow, None))
    if not valid[0]:
        raise ComfyExecutionUnavailable(f"Comfy prompt validation failed: {valid[1]}")

    number = getattr(prompt_server, "number", 0)
    prompt_server.number = number + 1
    extra_data = {"create_time": int(time.time() * 1000)}
    prompt_server.prompt_queue.put((number, prompt_id, workflow, extra_data, valid[2], {}))


async def _wait_for_saved_images(prompt_server, prompt_id, timeout_seconds, poll_interval):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        history = prompt_server.prompt_queue.get_history(prompt_id=prompt_id)
        images = extract_saved_images(history, prompt_id)
        if images:
            return images
        await asyncio.sleep(poll_interval)
    return []


async def _validate_prompt(prompt_id, prompt, partial_execution_targets):
    import execution

    return await execution.validate_prompt(prompt_id, prompt, partial_execution_targets)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _find_asset(store, asset_id):
    if not asset_id:
        return None
    for asset in store.list_assets():
        if asset["id"] == asset_id:
            return asset
    return None


def _asset_title(model, preset_key, index):
    label = model.get("short_label") or model.get("label") or model.get("id")
    return f"{label} / {preset_key.replace('-', ' ').title()} {index + 1:02d}"


def _comfy_workflow_provenance(
    workflow,
    checkpoint_name,
    preset_key,
    variant_index,
    reference_file_path,
    mask_file_path,
    source_asset_id,
    mask_asset_id,
    dimensions,
):
    uses_checkpoint_img2img = bool(checkpoint_name and reference_file_path)
    uses_checkpoint_inpaint = bool(checkpoint_name and reference_file_path and mask_file_path)
    return {
        "engine": "checkpoint_diffusion" if checkpoint_name else "frank_renderer",
        "workflow_key": (
            "comfy-checkpoint-inpaint"
            if uses_checkpoint_inpaint
            else (
                "comfy-checkpoint-img2img"
                if uses_checkpoint_img2img
                else ("comfy-checkpoint-txt2img" if checkpoint_name else "frank-local-variant-renderer")
            )
        ),
        "checkpoint_name": checkpoint_name,
        "preset_key": preset_key,
        "variant_index": int(variant_index),
        "width": dimensions[0],
        "height": dimensions[1],
        "reference_file_path": reference_file_path,
        "mask_file_path": mask_file_path,
        "source_asset_id": source_asset_id,
        "mask_asset_id": mask_asset_id,
        "masked_edit": bool(mask_asset_id),
        "comfy_node_types": [
            node.get("class_type")
            for _node_id, node in sorted(workflow.items(), key=lambda item: _node_sort_key(item[0]))
            if isinstance(node, dict) and node.get("class_type")
        ],
        "workflow_json": workflow,
    }


def _node_sort_key(node_id):
    try:
        return (0, int(node_id))
    except (TypeError, ValueError):
        return (1, str(node_id))


def _checkpoint_img2img_denoise(payload, source_asset):
    settings = payload.get("settings") or {}
    raw_value = settings.get("denoise") or settings.get("strength")
    if raw_value is not None:
        try:
            value = float(raw_value)
            if 0.05 <= value <= 1.0:
                return value
        except (TypeError, ValueError):
            pass
    return 0.42 if source_asset else 0.58


def _checkpoint_inpaint_denoise(payload):
    settings = payload.get("settings") or {}
    raw_value = settings.get("denoise") or settings.get("strength")
    if raw_value is not None:
        try:
            value = float(raw_value)
            if 0.05 <= value <= 1.0:
                return value
        except (TypeError, ValueError):
            pass
    return 0.64


def _comfy_loadable_reference_path(file_path, turn_id):
    normalized = str(file_path or "").replace("\\", "/")
    if not normalized:
        return None
    if normalized.startswith("input/"):
        return normalized

    source = _resolve_media_path(normalized)
    if not source or not source.exists() or not source.is_file():
        raise ComfyExecutionUnavailable(f"Reference image is not readable: {normalized}")

    suffix = source.suffix.lower() if source.suffix else ".png"
    destination_name = f"{_safe_filename_part(turn_id)}_{_safe_filename_part(source.stem)}{suffix}"
    stored_path = f"input/frank_create/comfy_refs/{destination_name}"
    destination = _resolve_media_path(stored_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return stored_path


def _safe_filename_part(value):
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value or "asset"))
    return clean.strip("_") or "asset"
