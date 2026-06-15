import importlib.util
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "frank_workflow_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("frank_workflow_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zip_bytes(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            if isinstance(payload, (dict, list)):
                payload = json.dumps(payload)
            archive.writestr(name, payload)
    return buffer.getvalue()


def _handoff_channel_export_entries(asset_id="asset-1", folder="channel-exports/approved-hot"):
    presets = [
        "pdp",
        "email-hero",
        "instagram-feed",
        "instagram-story",
        "paid-social",
        "transparent-png",
        "high-res-master",
    ]
    exports = {}
    files = {}
    for index, preset in enumerate(presets):
        media_bytes = f"fake channel export {preset}".encode("utf-8")
        image_ext = "png" if preset in {"transparent-png", "high-res-master"} else "jpg"
        image_file = f"{folder}/{preset}/{asset_id}-{preset}.{image_ext}"
        metadata_file = f"{folder}/{preset}/{asset_id}-{preset}.json"
        exports[preset] = {
            "preset": preset,
            "format": image_ext,
            "width": 1600 + index,
            "height": 1200 + index,
            "image_file": image_file,
            "metadata_file": metadata_file,
            "media_integrity": {
                "sha256": hashlib.sha256(media_bytes).hexdigest(),
                "file_size_bytes": len(media_bytes),
            },
        }
        files[image_file] = media_bytes
        files[metadata_file] = {"asset_id": asset_id, "preset": preset, "image_file": image_file}
    return {
        "manifest": {
            asset_id: {
                "asset_id": asset_id,
                "asset_title": "Approved Hot",
                "archive_folder": folder,
                "presets": presets,
                "preset_count": len(presets),
                "exports": exports,
            }
        },
        "files": files,
        "preset_count": len(presets),
    }


def test_workflow_smoke_validates_image_export_receipt_sections():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create export",
            "EXPORT_SPEC.md": "# Frank Create Export Spec",
            "asset-email-hero.jpg": b"fake image",
            "asset-email-hero.json": {
                "asset_context": {"id": "asset-1", "approval_status": "approved"},
                "turn_context": {"id": "turn-1", "preset_key": "campaign-variants"},
                "export_context": {"preset": "email-hero", "sync_ready": {"local_first": True}},
            },
        }
    )

    metadata = smoke.validate_export_zip(archive, expected_preset="email-hero")

    assert metadata["asset_context"]["id"] == "asset-1"
    assert metadata["turn_context"]["preset_key"] == "campaign-variants"
    assert metadata["export_context"]["sync_ready"]["local_first"] is True


def test_workflow_smoke_rejects_export_zip_without_spec_sheet():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create export",
            "asset-email-hero.jpg": b"fake image",
            "asset-email-hero.json": {
                "asset_context": {"id": "asset-1", "approval_status": "approved"},
                "turn_context": {"id": "turn-1", "preset_key": "campaign-variants"},
                "export_context": {"preset": "email-hero", "sync_ready": {"local_first": True}},
            },
        }
    )

    try:
        smoke.validate_export_zip(archive, expected_preset="email-hero")
    except smoke.WorkflowSmokeError as exc:
        assert "EXPORT_SPEC.md" in str(exc)
    else:
        raise AssertionError("Expected export ZIP without EXPORT_SPEC.md to fail")


def test_workflow_smoke_writes_demo_doctor_receipt(tmp_path):
    smoke = _load_smoke_module()
    status_path = tmp_path / "workflow_smoke_status.json"

    smoke.write_workflow_smoke_status(
        {
            "ok": True,
            "base_url": "http://127.0.0.1:8190",
            "session_name": "Frank Create Workflow Smoke 20260608-202251",
            "handoff": {"asset_count": 2, "reference_count": 1, "media_file_count": 3},
        },
        status_path=status_path,
    )

    receipt = json.loads(status_path.read_text(encoding="utf-8"))

    assert receipt["ok"] is True
    assert receipt["base_url"] == "http://127.0.0.1:8190"
    assert receipt["completed_at"]
    assert receipt["session_name"] == "Frank Create Workflow Smoke 20260608-202251"
    assert receipt["handoff"]["media_file_count"] == 3


def test_workflow_smoke_rejects_export_zip_without_readme():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "asset-email-hero.jpg": b"fake image",
            "asset-email-hero.json": {
                "asset_context": {"id": "asset-1", "approval_status": "approved"},
                "turn_context": {"id": "turn-1", "preset_key": "campaign-variants"},
                "export_context": {"preset": "email-hero", "sync_ready": {"local_first": True}},
            },
        }
    )

    try:
        smoke.validate_export_zip(archive, expected_preset="email-hero")
    except smoke.WorkflowSmokeError as exc:
        assert "README.md" in str(exc)
    else:
        raise AssertionError("Expected export ZIP without README.md to fail")


def test_workflow_smoke_rejects_export_zip_without_receipt_context():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create export",
            "EXPORT_SPEC.md": "# Frank Create Export Spec",
            "asset-email-hero.json": {"asset_id": "asset-1", "preset": "email-hero"},
        }
    )

    try:
        smoke.validate_export_zip(archive, expected_preset="email-hero")
    except smoke.WorkflowSmokeError as exc:
        assert "asset_context" in str(exc)
    else:
        raise AssertionError("Expected missing receipt context to fail")


def test_workflow_smoke_validates_provider_preflight_response():
    smoke = _load_smoke_module()

    preflight = smoke.validate_provider_preflight_response(
        {
            "status": "ready",
            "ready": True,
            "provider": "local",
            "model_id": "frank-local-comfy",
            "missing_env_vars": [],
            "message": "Local Comfy is ready for generate.",
            "payloadPreview": {
                "provider": "local",
                "model_id": "frank-local-comfy",
                "kind": "generate",
                "reference_count": 1,
                "reference_limit": 8,
                "prompt_length": 96,
                "prompt_preview": "Frank Body campaign prompt preview.",
            },
        },
        expected_status="ready",
    )

    assert preflight["model_id"] == "frank-local-comfy"
    assert preflight["payloadPreview"]["reference_count"] == 1


def test_workflow_smoke_rejects_provider_preflight_secret_leak():
    smoke = _load_smoke_module()

    try:
        smoke.validate_provider_preflight_response(
            {
                "status": "ready",
                "ready": True,
                "provider": "openai",
                "model_id": "openai-gpt-image-2",
                "message": "Using sk-test-secret",
                "payloadPreview": {
                    "kind": "generate",
                    "reference_count": 0,
                    "prompt_length": 20,
                    "prompt_preview": "Prompt",
                },
            },
            expected_status="ready",
        )
    except smoke.WorkflowSmokeError as exc:
        assert "secret" in str(exc).lower()
    else:
        raise AssertionError("Expected provider preflight secret leak to fail")


def test_workflow_smoke_validates_channel_set_manifest_and_receipts():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create channel set",
            "CHANNEL_SPEC.md": "# Frank Create Channel Spec",
            "frank-create-channel-set.json": {
                "asset_id": "asset-1",
                "preset": "channel-set",
                "preset_count": 3,
                "presets": ["pdp", "email-hero", "transparent-png"],
                "asset_context": {"id": "asset-1", "approval_status": "approved"},
                "turn_context": {"id": "turn-1", "preset_key": "campaign-variants"},
                "export_context": {"preset": "channel-set", "sync_ready": {"local_first": True}},
                "exports": {
                    "pdp": {
                        "width": 1600,
                        "height": 2000,
                        "image_file": "pdp/asset-1-pdp.jpg",
                        "metadata_file": "pdp/asset-1-pdp.json",
                    },
                    "email-hero": {
                        "width": 2400,
                        "height": 1350,
                        "image_file": "email-hero/asset-1-email-hero.jpg",
                        "metadata_file": "email-hero/asset-1-email-hero.json",
                    },
                    "transparent-png": {
                        "format": "png",
                        "image_file": "transparent-png/asset-1-transparent-png.png",
                        "metadata_file": "transparent-png/asset-1-transparent-png.json",
                    },
                },
            },
            "pdp/asset-1-pdp.jpg": b"fake image",
            "pdp/asset-1-pdp.json": {
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "pdp", "sync_ready": {"local_first": True}},
            },
            "email-hero/asset-1-email-hero.jpg": b"fake image",
            "email-hero/asset-1-email-hero.json": {
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "email-hero", "sync_ready": {"local_first": True}},
            },
            "transparent-png/asset-1-transparent-png.png": b"fake image",
            "transparent-png/asset-1-transparent-png.json": {
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "transparent-png", "sync_ready": {"local_first": True}},
            },
        }
    )

    manifest = smoke.validate_channel_set_zip(archive, ["pdp", "email-hero", "transparent-png"])

    assert manifest["preset"] == "channel-set"
    assert manifest["exports"]["pdp"]["width"] == 1600
    assert manifest["exports"]["transparent-png"]["format"] == "png"


def test_workflow_smoke_rejects_channel_set_without_spec_sheet():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create channel set",
            "frank-create-channel-set.json": {
                "asset_id": "asset-1",
                "preset": "channel-set",
                "preset_count": 1,
                "presets": ["pdp"],
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "channel-set", "sync_ready": {"local_first": True}},
                "exports": {
                    "pdp": {
                        "image_file": "pdp/asset-1-pdp.jpg",
                        "metadata_file": "pdp/asset-1-pdp.json",
                    }
                },
            },
            "pdp/asset-1-pdp.jpg": b"fake image",
            "pdp/asset-1-pdp.json": {
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "pdp", "sync_ready": {"local_first": True}},
            },
        }
    )

    try:
        smoke.validate_channel_set_zip(archive, ["pdp"])
    except smoke.WorkflowSmokeError as exc:
        assert "CHANNEL_SPEC.md" in str(exc)
    else:
        raise AssertionError("Expected channel-set ZIP without CHANNEL_SPEC.md to fail")


def test_workflow_smoke_rejects_channel_set_without_readme():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "frank-create-channel-set.json": {
                "asset_id": "asset-1",
                "preset": "channel-set",
                "preset_count": 1,
                "presets": ["pdp"],
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "channel-set", "sync_ready": {"local_first": True}},
                "exports": {
                    "pdp": {
                        "image_file": "pdp/asset-1-pdp.jpg",
                        "metadata_file": "pdp/asset-1-pdp.json",
                    }
                },
            },
            "pdp/asset-1-pdp.jpg": b"fake image",
            "pdp/asset-1-pdp.json": {
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "pdp", "sync_ready": {"local_first": True}},
            },
        }
    )

    try:
        smoke.validate_channel_set_zip(archive, ["pdp"])
    except smoke.WorkflowSmokeError as exc:
        assert "README.md" in str(exc)
    else:
        raise AssertionError("Expected channel-set ZIP without README.md to fail")


def test_workflow_smoke_rejects_channel_set_missing_expected_preset():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create channel set",
            "CHANNEL_SPEC.md": "# Frank Create Channel Spec",
            "frank-create-channel-set.json": {
                "asset_id": "asset-1",
                "preset": "channel-set",
                "preset_count": 1,
                "presets": ["pdp"],
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "channel-set", "sync_ready": {"local_first": True}},
                "exports": {
                    "pdp": {
                        "image_file": "pdp/asset-1-pdp.jpg",
                        "metadata_file": "pdp/asset-1-pdp.json",
                    }
                },
            },
            "pdp/asset-1-pdp.jpg": b"fake image",
            "pdp/asset-1-pdp.json": {
                "asset_context": {"id": "asset-1"},
                "turn_context": {"id": "turn-1"},
                "export_context": {"preset": "pdp", "sync_ready": {"local_first": True}},
            },
        }
    )

    try:
        smoke.validate_channel_set_zip(archive, ["pdp", "email-hero"])
    except smoke.WorkflowSmokeError as exc:
        assert "email-hero" in str(exc)
    else:
        raise AssertionError("Expected missing channel-set preset to fail")


def test_workflow_smoke_validates_handoff_manifest():
    smoke = _load_smoke_module()
    approved_bytes = b"fake approved image"
    reference_bytes = b"fake reference image"
    channel_exports = _handoff_channel_export_entries()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "counts": {"channel_export_sets": 1, "channel_export_files": channel_exports["preset_count"]},
                "approved_assets": [
                    {
                        "id": "asset-1",
                        "title": "Approved Hot",
                        "file_path": "output/frank_create/approved.png",
                        "archive_path": "approved/approved-hot-asset-1.png",
                        "workflow_sidecar_path": "workflows/approved-hot-asset-1-workflow.json",
                        "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                        "media_integrity": {
                            "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                            "file_size_bytes": len(approved_bytes),
                        },
                    }
                ],
                "reference_assets": [
                    {
                        "id": "ref-1",
                        "title": "Scrub Reference",
                        "file_path": "input/frank_create/ref.png",
                        "archive_path": "references/scrub-reference-ref-1.png",
                        "media_integrity": {
                            "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                            "file_size_bytes": len(reference_bytes),
                        },
                    }
                ],
                "channel_exports": channel_exports["manifest"],
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": approved_bytes,
            "references/scrub-reference-ref-1.png": reference_bytes,
            "workflows/approved-hot-asset-1-workflow.json": {
                "asset_id": "asset-1",
                "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                "workflow_bridge": {
                    "asset_id": "asset-1",
                    "can_open_raw_canvas": True,
                    "can_load_comfy_api_prompt": False,
                    "raw_canvas_load_status": "receipt_only",
                    "comfy_node_types": ["FrankCreateVariant", "SaveImage"],
                    "raw_canvas_url": "/comfy/?frankAssetId=asset-1",
                    "workflow_receipt_url": "/api/frank/assets/asset-1/workflow",
                },
            },
            **channel_exports["files"],
        }
    )

    manifest = smoke.validate_handoff_zip(archive)

    assert manifest["session"]["name"] == "Cliff Handoff"
    assert manifest["approved_assets"][0]["id"] == "asset-1"
    assert manifest["approved_assets"][0]["archive_path"] == "approved/approved-hot-asset-1.png"
    assert manifest["approved_assets"][0]["workflow_sidecar_path"] == "workflows/approved-hot-asset-1-workflow.json"
    assert manifest["_validated_archive"]["approved_file_count"] == 1
    assert manifest["_validated_archive"]["reference_file_count"] == 1
    assert manifest["_validated_archive"]["channel_export_set_count"] == 1
    assert manifest["_validated_archive"]["channel_export_file_count"] == 7
    assert manifest["_validated_archive"]["workflow_sidecar_count"] == 1


def test_workflow_smoke_rejects_handoff_workflow_sidecar_without_bridge():
    smoke = _load_smoke_module()
    approved_bytes = b"fake approved image"
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [
                    {
                        "id": "asset-1",
                        "title": "Approved Hot",
                        "file_path": "output/frank_create/approved.png",
                        "archive_path": "approved/approved-hot-asset-1.png",
                        "workflow_sidecar_path": "workflows/approved-hot-asset-1-workflow.json",
                        "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                        "media_integrity": {
                            "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                            "file_size_bytes": len(approved_bytes),
                        },
                    }
                ],
                "reference_assets": [],
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": approved_bytes,
            "workflows/approved-hot-asset-1-workflow.json": {
                "asset_id": "asset-1",
                "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
            },
        }
        )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "workflow bridge" in str(exc)
    else:
        raise AssertionError("Expected handoff ZIP without workflow bridge metadata to fail")


def test_workflow_smoke_rejects_handoff_without_channel_exports():
    smoke = _load_smoke_module()
    approved_bytes = b"fake approved image"
    reference_bytes = b"fake reference image"
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "counts": {"channel_export_sets": 0, "channel_export_files": 0},
                "approved_assets": [
                    {
                        "id": "asset-1",
                        "title": "Approved Hot",
                        "archive_path": "approved/approved-hot-asset-1.png",
                        "workflow_sidecar_path": "workflows/approved-hot-asset-1-workflow.json",
                        "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                        "media_integrity": {
                            "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                            "file_size_bytes": len(approved_bytes),
                        },
                    }
                ],
                "reference_assets": [
                    {
                        "id": "ref-1",
                        "archive_path": "references/scrub-reference-ref-1.png",
                        "media_integrity": {
                            "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                            "file_size_bytes": len(reference_bytes),
                        },
                    }
                ],
                "channel_exports": {},
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": approved_bytes,
            "references/scrub-reference-ref-1.png": reference_bytes,
            "workflows/approved-hot-asset-1-workflow.json": {
                "asset_id": "asset-1",
                "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                "workflow_bridge": {
                    "asset_id": "asset-1",
                    "can_open_raw_canvas": True,
                    "can_load_comfy_api_prompt": False,
                    "raw_canvas_load_status": "receipt_only",
                    "comfy_node_types": ["FrankCreateVariant", "SaveImage"],
                    "raw_canvas_url": "/comfy/?frankAssetId=asset-1",
                    "workflow_receipt_url": "/api/frank/assets/asset-1/workflow",
                },
            },
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "channel export" in str(exc)
    else:
        raise AssertionError("Expected handoff ZIP without channel exports to fail")


def test_workflow_smoke_rejects_handoff_media_integrity_mismatch():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [
                    {
                        "id": "asset-1",
                        "title": "Approved Hot",
                        "archive_path": "approved/approved-hot-asset-1.png",
                        "workflow_sidecar_path": "workflows/approved-hot-asset-1-workflow.json",
                        "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                        "media_integrity": {"sha256": "a" * 64, "file_size_bytes": 3},
                    }
                ],
                "reference_assets": [
                    {
                        "id": "ref-1",
                        "title": "Scrub Reference",
                        "archive_path": "references/scrub-reference-ref-1.png",
                        "media_integrity": {"sha256": hashlib.sha256(b"fake reference image").hexdigest(), "file_size_bytes": 20},
                    }
                ],
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": b"fake approved image",
            "references/scrub-reference-ref-1.png": b"fake reference image",
            "workflows/approved-hot-asset-1-workflow.json": {
                "asset_id": "asset-1",
                "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                "workflow_bridge": {
                    "asset_id": "asset-1",
                    "can_open_raw_canvas": True,
                    "can_load_comfy_api_prompt": False,
                    "raw_canvas_load_status": "receipt_only",
                    "comfy_node_types": ["FrankCreateVariant", "SaveImage"],
                    "raw_canvas_url": "/comfy/?frankAssetId=asset-1",
                    "workflow_receipt_url": "/api/frank/assets/asset-1/workflow",
                },
            },
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "approved media integrity mismatch" in str(exc)
    else:
        raise AssertionError("Expected handoff ZIP with mismatched media integrity to fail")


def test_workflow_smoke_rejects_handoff_without_spec_sheet():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [
                    {
                        "id": "asset-1",
                        "title": "Approved Hot",
                        "file_path": "output/frank_create/approved.png",
                        "archive_path": "approved/approved-hot-asset-1.png",
                        "workflow_sidecar_path": "workflows/approved-hot-asset-1-workflow.json",
                        "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                    }
                ],
                "reference_assets": [],
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": b"fake approved image",
            "workflows/approved-hot-asset-1-workflow.json": {
                "asset_id": "asset-1",
                "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
            },
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "HANDOFF_SPEC.md" in str(exc)
    else:
        raise AssertionError("Expected handoff ZIP without HANDOFF_SPEC.md to fail")


def test_workflow_smoke_rejects_handoff_missing_workflow_sidecar():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [
                    {
                        "id": "asset-1",
                        "title": "Approved Hot",
                        "archive_path": "approved/approved-hot-asset-1.png",
                        "workflow_sidecar_path": "workflows/missing-workflow.json",
                        "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"},
                    }
                ],
                "reference_assets": [],
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": b"fake approved image",
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "workflow sidecar" in str(exc)
    else:
        raise AssertionError("Expected handoff ZIP without workflow sidecar to fail")


def test_workflow_smoke_rejects_handoff_without_readme():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [{"id": "asset-1", "archive_path": "approved/approved-hot-asset-1.png"}],
                "reference_assets": [],
                "turns": [{"id": "turn-1"}],
            },
            "approved/approved-hot-asset-1.png": b"fake approved image",
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "README.md" in str(exc)
    else:
        raise AssertionError("Expected handoff ZIP without README.md to fail")


def test_workflow_smoke_rejects_handoff_with_broken_archive_path():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [{"id": "asset-1", "archive_path": "approved/missing-asset-1.png"}],
                "reference_assets": [{"id": "ref-1", "archive_path": "references/scrub-reference-ref-1.png"}],
                "turns": [{"id": "turn-1"}],
            },
            "approved/other-asset-1.png": b"wrong approved image path",
            "references/scrub-reference-ref-1.png": b"fake reference image",
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        assert "approved/ asset media" in str(exc)
        assert "asset-1" in str(exc)
    else:
        raise AssertionError("Expected broken handoff archive_path to fail")


def test_workflow_smoke_rejects_handoff_without_archived_media_files():
    smoke = _load_smoke_module()
    archive = _zip_bytes(
        {
            "README.md": "# Frank Create",
            "HANDOFF_SPEC.md": "# Frank Create Handoff Spec",
            "frank-create-handoff.json": {
                "session": {"id": "session-1", "name": "Cliff Handoff"},
                "approved_assets": [{"id": "asset-1", "title": "Approved Hot"}],
                "reference_assets": [{"id": "ref-1", "title": "Scrub Reference"}],
                "turns": [{"id": "turn-1"}],
            },
        }
    )

    try:
        smoke.validate_handoff_zip(archive)
    except smoke.WorkflowSmokeError as exc:
        message = str(exc)
        assert "approved/ asset media" in message
        assert "references/ asset media" in message
    else:
        raise AssertionError("Expected handoff ZIP without media files to fail")


def test_workflow_smoke_builds_comfy_upload_multipart_body():
    smoke = _load_smoke_module()

    content_type, body = smoke.build_upload_multipart("smoke-reference.png", b"PNGDATA")

    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="image"; filename="smoke-reference.png"' in body
    assert b'name="type"' in body
    assert b"\r\ninput\r\n" in body
    assert b'name="subfolder"' in body
    assert b"\r\nfrank_create\r\n" in body
    assert b'name="overwrite"' in body
    assert b"\r\ntrue\r\n" in body
    assert body.endswith(b"--\r\n")


def test_workflow_smoke_embedded_reference_png_is_valid():
    smoke = _load_smoke_module()

    image = Image.open(BytesIO(smoke.SMOKE_REFERENCE_PNG))
    image.verify()

    assert image.width == 64
    assert image.height == 48


def test_workflow_smoke_validates_edit_response_source_link():
    smoke = _load_smoke_module()
    response = {
        "status": "complete",
        "assets": [
            {
                "id": "asset-edit",
                "source_asset_id": "asset-source",
                "turn_id": "turn-edit",
            }
        ],
    }

    asset = smoke.validate_edit_response(response, expected_source_asset_id="asset-source")

    assert asset["id"] == "asset-edit"


def test_workflow_smoke_validates_masked_edit_response_provenance():
    smoke = _load_smoke_module()
    response = {
        "status": "complete",
        "localEngine": "frank_renderer",
        "assets": [
            {
                "id": "asset-mask-edit",
                "source_asset_id": "asset-source",
                "settings_json": json.dumps(
                    {
                        "workflow_provenance": {
                            "workflow_key": "frank-local-masked-edit-renderer",
                            "masked_edit": True,
                            "mask_asset_id": "asset-mask",
                        }
                    }
                ),
            }
        ],
    }

    asset = smoke.validate_masked_edit_response(response, "asset-source", "asset-mask")

    assert asset["id"] == "asset-mask-edit"


def test_workflow_smoke_validates_checkpoint_inpaint_masked_edit_response():
    smoke = _load_smoke_module()
    response = {
        "status": "complete",
        "localEngine": "comfy",
        "assets": [
            {
                "id": "asset-mask-edit",
                "source_asset_id": "asset-source",
                "settings_json": json.dumps(
                    {
                        "workflow_provenance": {
                            "workflow_key": "comfy-checkpoint-inpaint",
                            "masked_edit": True,
                            "mask_asset_id": "asset-mask",
                        }
                    }
                ),
            }
        ],
    }

    asset = smoke.validate_masked_edit_response(response, "asset-source", "asset-mask")

    assert asset["id"] == "asset-mask-edit"


def test_workflow_smoke_rejects_masked_edit_without_mask_provenance():
    smoke = _load_smoke_module()

    try:
        smoke.validate_masked_edit_response(
            {
                "status": "complete",
                "localEngine": "comfy",
                "assets": [{"id": "asset-mask-edit", "source_asset_id": "asset-source", "settings_json": "{}"}],
            },
            "asset-source",
            "asset-mask",
        )
    except smoke.WorkflowSmokeError as exc:
        assert "mask-aware workflow key" in str(exc)
    else:
        raise AssertionError("Expected masked edit without local renderer provenance to fail")


def test_workflow_smoke_rejects_edit_response_without_source_link():
    smoke = _load_smoke_module()

    try:
        smoke.validate_edit_response({"status": "complete", "assets": [{"id": "asset-edit"}]}, "asset-source")
    except smoke.WorkflowSmokeError as exc:
        assert "source_asset_id" in str(exc)
    else:
        raise AssertionError("Expected missing edit source link to fail")
