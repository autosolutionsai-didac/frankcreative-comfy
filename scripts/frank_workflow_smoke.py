from __future__ import annotations

import argparse
import base64
import hashlib
import socket
import json
import re
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]

SMOKE_REFERENCE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAYAAAChS3wfAAAA80lEQVR4nOXaLU5DQRSG4Xe+3D2wARyGXFNR2w2w"
    "ADw7QKAruoP6LoAN1CIwDQaHbsIO6iAIFkA755bmffx885OZ5CRn2mG//0IsyAW5IBfkglyQC3JDVfC4"
    "WHTP3G23l3EDxoLNV+W23pXg7yLf33b0dnM7dr8JQS7IBblhiklermZHj51/vnLxB/DjerPkrz7un6gW"
    "5IJckAtyQS7IBbkgN0w10RRFzb89gHlxOXuKIBfkglyQC3JBLsgFuSAX5IJckAtyreKbXFV3uKJFHgpU"
    "9PGrcpv9o+TQK+jx4Y6prdbPJ2cEuWZ/AkEuyOXcCzi3b7Y1MdgBhX7OAAAAAElFTkSuQmCC"
)

IMAGE_CHANNEL_SET_PRESETS = (
    "pdp",
    "email-hero",
    "instagram-feed",
    "instagram-story",
    "paid-social",
    "transparent-png",
    "high-res-master",
)

SMOKE_STATUS_PATH = ROOT / "user" / "frank_create" / "workflow_smoke_status.json"

SECRET_VALUE_RE = re.compile(
    r"(?i)(sk-[a-z0-9_-]{8,}|r8_[a-z0-9_-]{8,}|bearer\s+[a-z0-9._~+/=-]{8,}|server-side-[a-z0-9_-]+)"
)


class WorkflowSmokeError(RuntimeError):
    pass


def validate_provider_preflight_response(response: dict[str, Any], expected_status: str = "ready") -> dict[str, Any]:
    if SECRET_VALUE_RE.search(json.dumps(response, sort_keys=True)):
        raise WorkflowSmokeError("Provider preflight response appears to contain a secret value")

    status = response.get("status")
    if status != expected_status:
        raise WorkflowSmokeError(f"Provider preflight status mismatch: expected {expected_status}, got {status}")

    ready = bool(response.get("ready"))
    if expected_status == "ready" and not ready:
        raise WorkflowSmokeError("Provider preflight was expected to be ready")
    if expected_status != "ready" and ready:
        raise WorkflowSmokeError("Provider preflight unexpectedly reported ready=true")

    preview = response.get("payloadPreview") or {}
    missing = [
        key
        for key in ("model_id", "kind", "reference_count", "prompt_length", "prompt_preview")
        if key not in preview and key not in response
    ]
    if missing:
        raise WorkflowSmokeError(f"Provider preflight is missing preview fields: {', '.join(missing)}")

    if not response.get("model_id") and not preview.get("model_id"):
        raise WorkflowSmokeError("Provider preflight is missing model_id")
    if not preview.get("kind"):
        raise WorkflowSmokeError("Provider preflight preview is missing kind")

    return response


def validate_export_zip(zip_payload: bytes | bytearray | Path | str, expected_preset: str | None = None) -> dict[str, Any]:
    _require_zip_entries(zip_payload, "Export ZIP", ("README.md", "EXPORT_SPEC.md"))
    metadata = _find_export_metadata(zip_payload, expected_preset)
    export_context = _validate_receipt_context(metadata, "Export receipt")

    if expected_preset and export_context.get("preset") != expected_preset and metadata.get("preset") != expected_preset:
        raise WorkflowSmokeError(
            f"Export receipt preset mismatch: expected {expected_preset}, got {export_context.get('preset') or metadata.get('preset')}"
        )

    return metadata


def validate_channel_set_zip(
    zip_payload: bytes | bytearray | Path | str,
    expected_presets: list[str] | tuple[str, ...] = IMAGE_CHANNEL_SET_PRESETS,
) -> dict[str, Any]:
    expected = list(expected_presets)
    try:
        with ZipFile(_zip_buffer(zip_payload)) as archive:
            names = set(archive.namelist())
            if "README.md" not in names:
                raise WorkflowSmokeError("Channel-set ZIP is missing README.md")
            if "CHANNEL_SPEC.md" not in names:
                raise WorkflowSmokeError("Channel-set ZIP is missing CHANNEL_SPEC.md")
            if "frank-create-channel-set.json" not in names:
                raise WorkflowSmokeError("Channel-set ZIP is missing frank-create-channel-set.json")

            manifest = json.loads(archive.read("frank-create-channel-set.json"))
            manifest_context = _validate_receipt_context(manifest, "Channel-set manifest")
            if manifest.get("preset") != "channel-set" and manifest_context.get("preset") != "channel-set":
                raise WorkflowSmokeError("Channel-set manifest has the wrong preset")

            manifest_presets = manifest.get("presets") or []
            exports = manifest.get("exports") or {}
            missing = [preset for preset in expected if preset not in manifest_presets or preset not in exports]
            if missing:
                raise WorkflowSmokeError(f"Channel-set ZIP missing expected presets: {', '.join(missing)}")

            if manifest.get("preset_count") != len(manifest_presets):
                raise WorkflowSmokeError("Channel-set preset_count does not match presets")
            if "video-storyboard" in manifest_presets or any("video-storyboard" in name for name in names):
                raise WorkflowSmokeError("Channel-set ZIP should not include video-storyboard")

            for preset in expected:
                export_entry = exports[preset]
                image_file = export_entry.get("image_file")
                metadata_file = export_entry.get("metadata_file")
                if not image_file or image_file not in names:
                    raise WorkflowSmokeError(f"Channel-set ZIP is missing image file for {preset}")
                if not metadata_file or metadata_file not in names:
                    raise WorkflowSmokeError(f"Channel-set ZIP is missing metadata file for {preset}")

                receipt = json.loads(archive.read(metadata_file))
                receipt_context = _validate_receipt_context(receipt, f"Channel-set {preset} receipt")
                if receipt.get("preset") != preset and receipt_context.get("preset") != preset:
                    raise WorkflowSmokeError(f"Channel-set receipt preset mismatch for {preset}")

            return manifest
    except BadZipFile as exc:
        raise WorkflowSmokeError("Channel-set download is not a valid ZIP") from exc


def _validate_receipt_context(metadata: dict[str, Any], label: str) -> dict[str, Any]:
    required_sections = ("asset_context", "turn_context", "export_context")
    missing = [section for section in required_sections if not metadata.get(section)]
    if missing:
        raise WorkflowSmokeError(f"{label} is missing required context: {', '.join(missing)}")

    export_context = metadata["export_context"]
    sync_ready = export_context.get("sync_ready") or {}
    if sync_ready.get("local_first") is not True:
        raise WorkflowSmokeError(f"{label} is missing sync_ready.local_first=true")

    return export_context


def validate_handoff_zip(zip_payload: bytes | bytearray | Path | str) -> dict[str, Any]:
    try:
        with ZipFile(_zip_buffer(zip_payload)) as archive:
            names = set(archive.namelist())
            if "README.md" not in names:
                raise WorkflowSmokeError("Handoff ZIP is missing README.md")
            if "HANDOFF_SPEC.md" not in names:
                raise WorkflowSmokeError("Handoff ZIP is missing HANDOFF_SPEC.md")
            if "frank-create-handoff.json" not in names:
                raise WorkflowSmokeError("Handoff ZIP is missing frank-create-handoff.json")
            manifest = json.loads(archive.read("frank-create-handoff.json"))
            workflow_sidecars = _handoff_workflow_sidecars(archive, names, manifest.get("approved_assets") or [])
    except BadZipFile as exc:
        raise WorkflowSmokeError("Handoff download is not a valid ZIP") from exc

    if not manifest.get("session"):
        raise WorkflowSmokeError("Handoff manifest is missing session context")
    if not manifest.get("approved_assets"):
        raise WorkflowSmokeError("Handoff manifest does not include approved assets")
    if "turns" not in manifest:
        raise WorkflowSmokeError("Handoff manifest is missing turn history")

    approved_files = _handoff_asset_files(names, "approved", manifest.get("approved_assets") or [])
    reference_files = _handoff_asset_files(names, "references", manifest.get("reference_assets") or [])
    missing_groups = []
    if approved_files["missing_asset_ids"]:
        missing_groups.append(f"approved/ asset media for {', '.join(approved_files['missing_asset_ids'])}")
    if reference_files["missing_asset_ids"]:
        missing_groups.append(f"references/ asset media for {', '.join(reference_files['missing_asset_ids'])}")
    if missing_groups:
        raise WorkflowSmokeError(f"Handoff ZIP is missing {'; '.join(missing_groups)}")

    with ZipFile(_zip_buffer(zip_payload)) as archive:
        _validate_handoff_media_integrity(archive, names, manifest.get("approved_assets") or [], "approved")
        _validate_handoff_media_integrity(archive, names, manifest.get("reference_assets") or [], "reference")
        channel_exports = _validate_handoff_channel_exports(archive, names, manifest)

    manifest["_validated_archive"] = {
        "approved_file_count": approved_files["file_count"],
        "reference_file_count": reference_files["file_count"],
        "media_file_count": approved_files["file_count"] + reference_files["file_count"],
        "channel_export_set_count": channel_exports["set_count"],
        "channel_export_file_count": channel_exports["file_count"],
        "workflow_sidecar_count": workflow_sidecars["file_count"],
    }
    return manifest


def validate_edit_response(response: dict[str, Any], expected_source_asset_id: str) -> dict[str, Any]:
    if response.get("status") != "complete":
        raise WorkflowSmokeError(f"Edit did not complete: {response}")
    assets = response.get("assets") or []
    if not assets:
        raise WorkflowSmokeError("Edit completed without output assets")
    asset = assets[0]
    if asset.get("source_asset_id") != expected_source_asset_id:
        raise WorkflowSmokeError(
            f"Edit asset source_asset_id mismatch: expected {expected_source_asset_id}, got {asset.get('source_asset_id')}"
        )
    return asset


def validate_masked_edit_response(
    response: dict[str, Any],
    expected_source_asset_id: str,
    expected_mask_asset_id: str,
) -> dict[str, Any]:
    asset = validate_edit_response(response, expected_source_asset_id)
    if response.get("localEngine") not in {"frank_renderer", "fallback", "comfy"}:
        raise WorkflowSmokeError(f"Local masked edit used the wrong engine: {response.get('localEngine')}")

    try:
        settings = json.loads(asset.get("settings_json") or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise WorkflowSmokeError("Masked edit asset settings_json was not readable JSON") from exc

    provenance = settings.get("workflow_provenance") or {}
    if provenance.get("workflow_key") not in {"frank-local-masked-edit-renderer", "comfy-checkpoint-inpaint"}:
        raise WorkflowSmokeError("Masked edit did not record the mask-aware workflow key")
    if provenance.get("masked_edit") is not True:
        raise WorkflowSmokeError("Masked edit provenance did not set masked_edit=true")
    if provenance.get("mask_asset_id") != expected_mask_asset_id:
        raise WorkflowSmokeError("Masked edit provenance mask_asset_id mismatch")
    return asset


def _handoff_asset_files(names: set[str], folder: str, assets: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [name for name in names if name.startswith(f"{folder}/") and not name.endswith("/")]
    missing_asset_ids = []
    lowered_entries = [entry.lower() for entry in entries]

    for asset in assets:
        archive_path = asset.get("archive_path")
        if archive_path:
            if not str(archive_path).startswith(f"{folder}/") or archive_path not in names:
                missing_asset_ids.append(asset.get("id"))
            continue
        asset_id = str(asset.get("id") or "").lower()
        if asset_id and not any(asset_id in entry for entry in lowered_entries):
            missing_asset_ids.append(asset.get("id"))

    return {"file_count": len(entries), "missing_asset_ids": missing_asset_ids}


def _validate_handoff_media_integrity(
    archive: ZipFile,
    names: set[str],
    assets: list[dict[str, Any]],
    label: str,
) -> None:
    for asset in assets:
        archive_path = asset.get("archive_path")
        integrity = asset.get("media_integrity") or {}
        expected_sha256 = str(integrity.get("sha256") or "").lower()
        expected_size = int(integrity.get("file_size_bytes") or 0)
        asset_id = str(asset.get("id") or "asset")
        if not expected_sha256 or len(expected_sha256) != 64 or expected_size <= 0:
            raise WorkflowSmokeError(f"Handoff manifest is missing {label} media_integrity for {asset_id}")
        if not archive_path or archive_path not in names:
            raise WorkflowSmokeError(f"Handoff ZIP is missing {label} media for {asset_id}")
        media_bytes = archive.read(archive_path)
        actual_sha256 = hashlib.sha256(media_bytes).hexdigest()
        if actual_sha256 != expected_sha256 or len(media_bytes) != expected_size:
            raise WorkflowSmokeError(f"Handoff manifest has {label} media integrity mismatch for {asset_id}")


def _handoff_workflow_sidecars(archive: ZipFile, names: set[str], assets: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [name for name in names if name.startswith("workflows/") and name.endswith(".json")]
    required_assets = [asset for asset in assets if asset.get("workflow_provenance")]
    missing_asset_ids = []
    broken_asset_ids = []
    broken_bridge_asset_ids = []

    for asset in required_assets:
        sidecar_path = asset.get("workflow_sidecar_path")
        if not sidecar_path or not str(sidecar_path).startswith("workflows/") or sidecar_path not in names:
            missing_asset_ids.append(str(asset.get("id") or "asset"))
            continue
        try:
            sidecar = json.loads(archive.read(sidecar_path))
        except (KeyError, json.JSONDecodeError):
            broken_asset_ids.append(str(asset.get("id") or "asset"))
            continue
        bridge = sidecar.get("workflow_bridge") if isinstance(sidecar, dict) else None
        if sidecar.get("asset_id") != asset.get("id") or not sidecar.get("workflow_provenance"):
            broken_asset_ids.append(str(asset.get("id") or "asset"))
            continue
        if not _workflow_bridge_is_valid(bridge, asset.get("id")):
            broken_bridge_asset_ids.append(str(asset.get("id") or "asset"))

    if missing_asset_ids:
        raise WorkflowSmokeError(f"Handoff ZIP is missing workflow sidecar for {', '.join(missing_asset_ids)}")
    if broken_asset_ids:
        raise WorkflowSmokeError(f"Handoff ZIP has invalid workflow sidecar for {', '.join(broken_asset_ids)}")
    if broken_bridge_asset_ids:
        raise WorkflowSmokeError(f"Handoff ZIP has invalid workflow bridge metadata for {', '.join(broken_bridge_asset_ids)}")

    return {
        "file_count": len(entries),
        "missing_asset_ids": missing_asset_ids,
        "broken_asset_ids": broken_asset_ids,
        "broken_bridge_asset_ids": broken_bridge_asset_ids,
    }


def _validate_handoff_channel_exports(archive: ZipFile, names: set[str], manifest: dict[str, Any]) -> dict[str, int]:
    channel_exports = manifest.get("channel_exports")
    counts = manifest.get("counts") or {}
    if not isinstance(channel_exports, dict) or not channel_exports:
        raise WorkflowSmokeError("Handoff manifest is missing channel export metadata")
    if int(counts.get("channel_export_sets") or 0) < 1 or int(counts.get("channel_export_files") or 0) < 1:
        raise WorkflowSmokeError("Handoff manifest is missing channel export counts")

    file_count = 0
    for asset_id, export_set in channel_exports.items():
        exports = export_set.get("exports") if isinstance(export_set, dict) else None
        if not isinstance(exports, dict):
            raise WorkflowSmokeError(f"Handoff channel export set is incomplete for {asset_id}")
        missing_presets = [preset for preset in IMAGE_CHANNEL_SET_PRESETS if preset not in exports]
        if missing_presets:
            raise WorkflowSmokeError(f"Handoff channel export set is missing {', '.join(missing_presets)} for {asset_id}")
        for preset in IMAGE_CHANNEL_SET_PRESETS:
            export = exports.get(preset) or {}
            image_file = export.get("image_file")
            metadata_file = export.get("metadata_file")
            if not image_file or image_file not in names or not str(image_file).startswith("channel-exports/"):
                raise WorkflowSmokeError(f"Handoff ZIP is missing channel export image for {asset_id} {preset}")
            if not metadata_file or metadata_file not in names:
                raise WorkflowSmokeError(f"Handoff ZIP is missing channel export metadata for {asset_id} {preset}")
            integrity = export.get("media_integrity") or {}
            expected_sha256 = str(integrity.get("sha256") or "").lower()
            expected_size = int(integrity.get("file_size_bytes") or 0)
            if not expected_sha256 or len(expected_sha256) != 64 or expected_size <= 0:
                raise WorkflowSmokeError(f"Handoff channel export is missing media_integrity for {asset_id} {preset}")
            media_bytes = archive.read(image_file)
            actual_sha256 = hashlib.sha256(media_bytes).hexdigest()
            if actual_sha256 != expected_sha256 or len(media_bytes) != expected_size:
                raise WorkflowSmokeError(f"Handoff channel export integrity mismatch for {asset_id} {preset}")
            file_count += 1

    return {"set_count": len(channel_exports), "file_count": file_count}


def _workflow_bridge_is_valid(bridge: Any, asset_id: Any) -> bool:
    if not isinstance(bridge, dict):
        return False
    if bridge.get("asset_id") != asset_id:
        return False
    if bridge.get("can_open_raw_canvas") is not True:
        return False
    if bridge.get("raw_canvas_load_status") not in {"api_prompt_attached", "receipt_only"}:
        return False
    if not isinstance(bridge.get("comfy_node_types"), list) or not bridge.get("comfy_node_types"):
        return False
    raw_canvas_url = str(bridge.get("raw_canvas_url") or "")
    receipt_url = str(bridge.get("workflow_receipt_url") or "")
    return "frankAssetId=" in raw_canvas_url and "/workflow" in receipt_url


def build_upload_multipart(filename: str, image_bytes: bytes) -> tuple[str, bytes]:
    boundary = "----FrankCreateWorkflowSmokeBoundary"
    fields = [
        ("type", "input"),
        ("subfolder", "frank_create"),
        ("overwrite", "true"),
    ]
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8")
        + image_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


def run_workflow(base_url: str, keep_session: bool = False, timeout: float = 90.0) -> dict[str, Any]:
    client = FrankApiClient(base_url=base_url, timeout=timeout)
    session_id = None
    session_name = f"Frank Create Workflow Smoke {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    summary: dict[str, Any] = {"base_url": client.root_url, "session_name": session_name}

    try:
        health = client.request("GET", "/health")
        _require(health.get("ok"), "Frank Create health check failed")
        _log(f"Health OK: {health.get('product', 'Frank Create')}")

        session = client.request("POST", "/sessions", {"name": session_name, "mode": "image", "status": "active"})[
            "session"
        ]
        session_id = session["id"]
        summary["session_id"] = session_id
        _log(f"Created smoke session: {session_name}")

        uploaded_reference = _upload_smoke_reference(client, session_id)
        reference_ids = [uploaded_reference["id"]]
        summary["uploaded_reference_id"] = uploaded_reference["id"]
        _log("Uploaded product reference through Comfy and created Frank reference asset")

        generation_payload = {
            "session_id": session_id,
            "kind": "generate",
            "model": "frank-local-comfy",
            "prompt": "Create a Frank Body coffee scrub campaign product image for a director review.",
            "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
            "reference_asset_ids": reference_ids,
            "frank_body_mode": True,
            "preset_key": "campaign-variants",
        }
        local_preflight = validate_provider_preflight_response(
            client.request("POST", "/provider-preflight", generation_payload),
            expected_status="ready",
        )
        summary["local_preflight"] = {
            "status": local_preflight["status"],
            "model_id": local_preflight.get("model_id") or local_preflight.get("payloadPreview", {}).get("model_id"),
            "kind": local_preflight.get("payloadPreview", {}).get("kind"),
            "reference_count": local_preflight.get("payloadPreview", {}).get("reference_count"),
        }
        _log("Validated selected-model provider preflight")

        turn_response = client.request(
            "POST",
            "/inference/turn",
            generation_payload,
        )
        _require(turn_response.get("status") == "complete", f"Generation did not complete: {turn_response}")
        image_assets = turn_response.get("assets") or []
        _require(image_assets, "Generation completed without output assets")
        image_asset = image_assets[0]
        _log(f"Generated image asset: {image_asset['id']}")

        edit_response = client.request(
            "POST",
            "/edits",
            {
                "session_id": session_id,
                "model": "frank-local-comfy",
                "prompt": "Retouch this Frank Body product shot: sharpen the label, keep the product honest, improve the set polish.",
                "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
                "reference_asset_ids": reference_ids,
                "edit_source_asset_id": image_asset["id"],
                "frank_body_mode": True,
                "preset_key": "product-cleanup",
            },
        )
        edit_asset = validate_edit_response(edit_response, image_asset["id"])
        summary["edit_asset_id"] = edit_asset["id"]
        _log(f"Edited generated image asset: {edit_asset['id']}")

        mask_asset = _create_smoke_mask_asset(client, session_id, uploaded_reference, image_asset["id"])
        masked_edit_response = client.request(
            "POST",
            "/inference/turn",
            {
                "session_id": session_id,
                "kind": "masked_edit",
                "model": "frank-local-comfy",
                "prompt": "Retouch only the masked label area, keep the Frank Body product honest.",
                "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
                "reference_asset_ids": reference_ids,
                "edit_source_asset_id": image_asset["id"],
                "mask_asset_id": mask_asset["id"],
                "frank_body_mode": True,
                "preset_key": "product-cleanup",
            },
        )
        masked_edit_asset = validate_masked_edit_response(masked_edit_response, image_asset["id"], mask_asset["id"])
        summary["masked_edit_asset_id"] = masked_edit_asset["id"]
        summary["mask_asset_id"] = mask_asset["id"]
        _log(f"Validated local masked edit asset: {masked_edit_asset['id']}")

        image_asset = client.request(
            "PATCH",
            f"/assets/{masked_edit_asset['id']}",
            {
                "approval_status": "approved",
                "favorite": True,
                "notes": "Workflow smoke approved this masked edit asset for export and handoff validation.",
            },
        )["asset"]
        _log("Approved masked edit image asset")

        image_export_presets = ["transparent-png", "email-hero"]
        image_exports = []
        for preset in image_export_presets:
            export = _create_and_validate_export(client, image_asset["id"], preset)
            image_exports.append(export)
            _log(f"Validated {preset} export receipt")
        summary["image_exports"] = image_exports

        channel_set_export = _create_and_validate_channel_set(client, image_asset["id"])
        summary["channel_set_export"] = channel_set_export
        _log("Validated channel-set export pack")

        video_response = client.request(
            "POST",
            "/videos",
            {
                "session_id": session_id,
                "source_asset_id": image_asset["id"],
                "prompt": "Create a short Frank Body motion storyboard from the approved campaign image.",
                "settings": {"aspect_ratio": "16:9", "image_size": "1K", "count": 1},
            },
        )
        _require(video_response.get("status") == "complete", f"Video storyboard did not complete: {video_response}")
        video_assets = video_response.get("assets") or []
        _require(video_assets, "Video storyboard completed without an asset")
        video_asset = video_assets[0]
        client.request(
            "PATCH",
            f"/assets/{video_asset['id']}",
            {
                "approval_status": "approved",
                "favorite": True,
                "notes": "Workflow smoke approved this storyboard for mixed-media handoff validation.",
            },
        )
        _log(f"Generated and approved video storyboard asset: {video_asset['id']}")

        video_export = _create_and_validate_export(client, video_asset["id"], "video-storyboard")
        summary["video_export"] = video_export
        _log("Validated video storyboard export receipt")

        handoff_response = client.request(
            "POST",
            f"/sessions/{session_id}/handoff",
            {"summary": "Frank Create workflow smoke handoff for Cliff readiness."},
        )
        handoff = handoff_response["handoff"]
        handoff_manifest = validate_handoff_zip(client.download(f"/api/frank/exports/{handoff['id']}/download"))
        validated_archive = handoff_manifest.get("_validated_archive") or {}
        summary["handoff"] = {
            "id": handoff["id"],
            "asset_count": len(handoff_manifest.get("approved_assets") or []),
            "reference_count": len(handoff_manifest.get("reference_assets") or []),
            "media_file_count": validated_archive.get("media_file_count"),
            "approved_file_count": validated_archive.get("approved_file_count"),
            "reference_file_count": validated_archive.get("reference_file_count"),
            "channel_export_set_count": validated_archive.get("channel_export_set_count"),
            "channel_export_file_count": validated_archive.get("channel_export_file_count"),
            "turn_count": len(handoff_manifest.get("turns") or []),
        }
        _log("Validated mixed-media handoff pack")

        summary["ok"] = True
        return summary
    finally:
        if session_id and not keep_session:
            try:
                client.request("PATCH", f"/sessions/{session_id}", {"status": "archived"})
                _log(f"Archived smoke session: {session_id}")
            except WorkflowSmokeError as exc:
                _log(f"Could not archive smoke session {session_id}: {exc}")


class FrankApiClient:
    def __init__(self, base_url: str, timeout: float = 90.0):
        self.root_url = _root_url(base_url)
        self.api_url = f"{self.root_url}/api/frank"
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_url}{path if path.startswith('/') else '/' + path}"
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method.upper())
        response_bytes = self._open(request)
        try:
            return json.loads(response_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowSmokeError(f"{method} {path} did not return JSON") from exc

    def download(self, path_or_url: str) -> bytes:
        url = path_or_url if path_or_url.startswith("http") else urljoin(f"{self.root_url}/", path_or_url.lstrip("/"))
        return self._open(Request(url, headers={"Accept": "application/octet-stream"}))

    def upload_image(self, filename: str, image_bytes: bytes) -> dict[str, Any]:
        content_type, body = build_upload_multipart(filename, image_bytes)
        request = Request(
            f"{self.root_url}/api/upload/image",
            data=body,
            headers={"Accept": "application/json", "Content-Type": content_type},
            method="POST",
        )
        response_bytes = self._open(request)
        try:
            return json.loads(response_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowSmokeError("Comfy upload did not return JSON") from exc

    def _open(self, request: Request) -> bytes:
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise WorkflowSmokeError(f"{request.method} {request.full_url} failed with {exc.code}: {detail}") from exc
        except URLError as exc:
            raise WorkflowSmokeError(f"{request.method} {request.full_url} failed: {exc}") from exc
        except TimeoutError as exc:
            raise WorkflowSmokeError(f"{request.method} {request.full_url} timed out after {self.timeout}s") from exc
        except socket.timeout as exc:
            raise WorkflowSmokeError(f"{request.method} {request.full_url} timed out after {self.timeout}s") from exc


def _upload_smoke_reference(client: FrankApiClient, session_id: str) -> dict[str, Any]:
    filename = f"frank-create-smoke-reference-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.png"
    uploaded = client.upload_image(filename, SMOKE_REFERENCE_PNG)
    clone = client.request(
        "POST",
        "/references",
        {
            "session_id": session_id,
            "title": filename,
            "file_path": _stored_image_path(uploaded),
            "preview_url": _view_url(uploaded),
            "media_type": "image",
            "sync_status": "local",
            "metadata": {"workflow_smoke": True, "uploaded_through_comfy": True},
        },
    )["asset"]
    return clone


def _create_smoke_mask_asset(
    client: FrankApiClient,
    session_id: str,
    uploaded_reference: dict[str, Any],
    source_asset_id: str,
) -> dict[str, Any]:
    return client.request(
        "POST",
        "/assets",
        {
            "session_id": session_id,
            "kind": "mask",
            "title": "Workflow smoke mask",
            "file_path": uploaded_reference["file_path"],
            "preview_url": uploaded_reference.get("preview_url"),
            "media_type": "image",
            "source_asset_id": source_asset_id,
            "sync_status": "local",
            "metadata": {"workflow_smoke": True, "mask_source": "uploaded_reference"},
        },
    )["asset"]


def _stored_image_path(upload: dict[str, Any]) -> str:
    folder = f"{upload.get('subfolder')}/" if upload.get("subfolder") else ""
    return f"{upload.get('type') or 'input'}/{folder}{upload['name']}"


def _view_url(upload: dict[str, Any]) -> str:
    query = f"filename={upload['name']}&type={upload.get('type') or 'input'}"
    if upload.get("subfolder"):
        query += f"&subfolder={upload['subfolder']}"
    return f"/api/view?{query}"


def _create_and_validate_export(client: FrankApiClient, asset_id: str, preset: str) -> dict[str, Any]:
    response = client.request(
        "POST",
        "/exports",
        {"asset_id": asset_id, "preset": preset, "metadata": {"app": "Frank Create Workflow Smoke"}},
    )
    export = response["export"]
    metadata = validate_export_zip(client.download(f"/api/frank/exports/{export['id']}/download"), preset)
    return {
        "id": export["id"],
        "preset": preset,
        "asset_id": asset_id,
        "width": metadata.get("export_context", {}).get("width"),
        "height": metadata.get("export_context", {}).get("height"),
    }


def _create_and_validate_channel_set(client: FrankApiClient, asset_id: str) -> dict[str, Any]:
    response = client.request(
        "POST",
        f"/assets/{asset_id}/export-set",
        {
            "presets": list(IMAGE_CHANNEL_SET_PRESETS),
            "metadata": {"app": "Frank Create Workflow Smoke", "smoke_check": "channel-set"},
        },
    )
    export = response["export"]
    download_path = response.get("download_url") or f"/api/frank/exports/{export['id']}/download"
    manifest = validate_channel_set_zip(client.download(download_path), IMAGE_CHANNEL_SET_PRESETS)
    return {
        "id": export["id"],
        "preset": "channel-set",
        "asset_id": asset_id,
        "preset_count": manifest.get("preset_count"),
        "presets": manifest.get("presets"),
    }


def _find_export_metadata(zip_payload: bytes | bytearray | Path | str, expected_preset: str | None) -> dict[str, Any]:
    try:
        with ZipFile(_zip_buffer(zip_payload)) as archive:
            candidates = [name for name in archive.namelist() if name.lower().endswith(".json")]
            if not candidates:
                raise WorkflowSmokeError("Export ZIP does not contain a JSON receipt")
            for name in candidates:
                metadata = json.loads(archive.read(name))
                export_context = metadata.get("export_context") or {}
                if expected_preset is None or metadata.get("preset") == expected_preset or export_context.get("preset") == expected_preset:
                    return metadata
    except BadZipFile as exc:
        raise WorkflowSmokeError("Export download is not a valid ZIP") from exc

    raise WorkflowSmokeError(f"Export ZIP does not contain metadata for preset {expected_preset}")


def _require_zip_readme(zip_payload: bytes | bytearray | Path | str, label: str) -> None:
    _require_zip_entries(zip_payload, label, ("README.md",))


def _require_zip_entries(zip_payload: bytes | bytearray | Path | str, label: str, required_entries: tuple[str, ...]) -> None:
    try:
        with ZipFile(_zip_buffer(zip_payload)) as archive:
            names = set(archive.namelist())
            for entry in required_entries:
                if entry not in names:
                    raise WorkflowSmokeError(f"{label} is missing {entry}")
    except BadZipFile as exc:
        raise WorkflowSmokeError(f"{label} download is not a valid ZIP") from exc


def write_workflow_smoke_status(summary: dict[str, Any], status_path: Path | str = SMOKE_STATUS_PATH) -> dict[str, Any]:
    receipt = {
        **summary,
        "ok": bool(summary.get("ok")),
        "completed_at": summary.get("completed_at") or datetime.now(timezone.utc).isoformat(),
    }
    path = Path(status_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def _zip_buffer(zip_payload: bytes | bytearray | Path | str) -> BytesIO:
    if isinstance(zip_payload, (bytes, bytearray)):
        return BytesIO(zip_payload)
    return BytesIO(Path(zip_payload).read_bytes())


def _root_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/api/frank"):
        cleaned = cleaned[: -len("/api/frank")]
    return cleaned


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise WorkflowSmokeError(message)


def _log(message: str) -> None:
    print(f"[Frank Workflow] {message}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Frank Create end-to-end workflow smoke test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8190", help="Frank Create server root URL.")
    parser.add_argument("--keep-session", action="store_true", help="Leave the smoke session active for inspection.")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout in seconds.")
    args = parser.parse_args(argv)

    try:
        summary = run_workflow(args.base_url, keep_session=args.keep_session, timeout=args.timeout)
    except WorkflowSmokeError as exc:
        write_workflow_smoke_status(
            {
                "ok": False,
                "base_url": args.base_url,
                "error": str(exc),
            }
        )
        print(f"[Frank Workflow] FAILED: {exc}", file=sys.stderr)
        return 1

    write_workflow_smoke_status(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
