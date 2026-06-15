import json
import hashlib
import inspect
import io
import os
import re
import zipfile
from pathlib import Path

import pytest
from aiohttp import web
from PIL import Image
from types import SimpleNamespace

from custom_nodes.frank_create import routes
from custom_nodes.frank_create.comfy_local import ComfyExecutionUnavailable
from custom_nodes.frank_create.store import FrankCreateStore


def _write_test_png(path, size=(24, 24), color=(255, 183, 166, 255)):
    Image.new("RGBA", size, color).save(path)


def _test_png_bytes(size=(24, 24), color=(255, 183, 166, 255)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def _write_minimal_readiness_pack(
    path,
    include_cliff_browser_qa=True,
    include_call_day_browser_proofs=True,
    include_local_generate_proof=True,
    include_masked_edit_generate_proof=True,
    include_model_preflight_proof=True,
):
    checks = [
        {
            "key": "studio_interactions",
            "status": "ready",
            "detail": (
                "copies a safe production unlock plan with env-var names/checkpoint path/rotation step and no secret values"
                if include_call_day_browser_proofs
                else "copies a safe provider key plan with env-var names and no secret values"
            ),
        },
        *(
            [{"key": "demo_doctor_checksum", "status": "ready", "detail": "Verified SHA-256 " + "a" * 64}]
            if include_call_day_browser_proofs
            else []
        ),
        *(
            [
                {
                    "key": "studio_local_generate",
                    "status": "ready",
                    "detail": "Browser QA local generate proof: the live Studio Generate button created output assets.",
                }
            ]
            if include_local_generate_proof
            else []
        ),
        *(
            [
                {
                    "key": "studio_masked_edit_generate",
                    "status": "ready",
                    "detail": "Browser QA masked edit proof: the masked edit Generate button created output assets.",
                }
            ]
            if include_masked_edit_generate_proof
            else []
        ),
        *(
            [
                {
                    "key": "studio_model_preflight",
                    "status": "ready",
                    "detail": "Browser QA no-spend selected model preflight proof: selected model preflight returned a safe payload preview.",
                }
            ]
            if include_model_preflight_proof
            else []
        ),
        {"key": "video_lab", "status": "included", "browser_status": "ready"},
        {"key": "provider_audit", "status": "included", "browser_status": "ready"},
        {"key": "advanced_graph", "status": "included", "browser_status": "ready"},
        {"key": "raw_comfy", "status": "included", "browser_status": "ready"},
        {"key": "raw_comfy_receipt", "status": "included", "browser_status": "ready"},
    ]
    browser_qa = {"status": "ready", "checks": checks}
    cliff_prep = {"ok": True}
    if include_cliff_browser_qa:
        cliff_prep["browser_qa"] = browser_qa
    manifest = {
        "purpose": "Cliff call-day readiness pack",
        "browser_qa": browser_qa,
        "shareable_pack_hygiene": {"status": "clean"},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("readiness-pack-manifest.json", json.dumps(manifest))
        archive.writestr("qa/browser-qa-receipt.json", json.dumps(browser_qa))
        archive.writestr("receipts/cliff_prep_status.json", json.dumps(cliff_prep))


def test_demo_doctor_route_has_dash_and_nested_aliases():
    source = inspect.getsource(routes.register_routes)

    assert '@routes.get("/frank/demo-doctor")' in source
    assert '@routes.get("/frank/demo/doctor")' in source


def test_backend_config_declares_every_task_provider():
    declared = {provider["key"] for provider in routes.PROVIDERS}
    used = {provider for task in routes.TASKS for provider in task["providers"]}

    assert used.issubset(declared)
    assert declared == {"local", "google", "replicate", "openai"}
    curated = {provider["key"] for provider in routes.PROVIDERS if provider["status"] == "curated"}
    assert curated == {"google", "replicate", "openai"}


def test_backend_registry_only_exposes_gemini_replicate_and_openai_keys():
    config = {
        "tasks": routes.TASKS,
        "providers": routes.PROVIDERS,
        **routes._model_registry_response(),
    }
    allowed_env_vars = {"GOOGLE_API_KEY", "REPLICATE_API_TOKEN", "OPENAI_API_KEY"}
    live_env_vars = {
        env_var
        for model in config["models"]
        for env_var in (model.get("env_vars") or model.get("missing_env_vars") or [])
    }
    forbidden_text = "FAL_KEY|RECRAFT|IDEOGRAM|XAI|RUNWAY|Grok|Recraft|Ideogram|Runway|fal.ai"

    assert live_env_vars == allowed_env_vars
    assert not re.search(forbidden_text, json.dumps(config))


class FakePromptServer:
    def __init__(self):
        self.sockets = {}
        self.sockets_metadata = {}
        self.client_id = None
        self.last_node_id = None
        self.sent = []

    def get_queue_info(self):
        return {"exec_info": {"queue_remaining": 0}}

    async def send(self, event, data, sid):
        self.sent.append((event, data, sid))
        await self.sockets[sid].send_json({"type": event, "data": data})


def _add_approved_masked_asset(store, session, media_root):
    masked_path = Path(media_root) / "output" / "frank_create" / "masked.png"
    masked_path.parent.mkdir(parents=True, exist_ok=True)
    _write_test_png(masked_path, color=(196, 17, 47, 255))
    return store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Masked edit",
            "file_path": "output/frank_create/masked.png",
            "media_type": "image",
            "settings": {
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-masked-edit-renderer",
                    "masked_edit": True,
                }
            },
            "approval_status": "approved",
        }
    )


def test_inference_turn_dispatches_non_google_live_adapters(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai")

    calls = []

    def fake_run_live_provider_turn(store_arg, turn, payload, model, provider_payload):
        calls.append(
            {
                "provider": model["provider"],
                "turn_status": turn["status"],
                "prompt": provider_payload["prompt"],
            }
        )
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": []})
        return updated_turn, []

    monkeypatch.setattr(routes, "run_live_provider_turn", fake_run_live_provider_turn)

    result = routes._create_inference_turn(
        {
            "kind": "generate",
            "model": "openai-gpt-image-2",
            "prompt": "Clean Frank Body product image.",
            "settings": {"aspect_ratio": "1:1", "image_size": "4096", "count": 1},
            "reference_asset_ids": [],
        }
    )

    assert result["status"] == "complete"
    assert result["turn"]["provider"] == "openai"
    assert calls == [
        {
            "provider": "openai",
            "turn_status": "queued",
            "prompt": "Clean Frank Body product image.",
        }
    ]


def test_inference_turn_dispatches_google_live_adapter_with_metadata(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")

    calls = []

    def fake_run_live_provider_turn(store_arg, turn, payload, model, provider_payload):
        calls.append(
            {
                "provider": model["provider"],
                "model": model["id"],
                "provider_model": model["provider_model"],
                "turn_status": turn["status"],
                "settings": payload["settings"],
                "prompt": provider_payload["prompt"],
            }
        )
        asset = store_arg.create_asset(
            {
                "session_id": turn["session_id"],
                "turn_id": turn["id"],
                "kind": "candidate",
                "title": "Nano Banana Pro / Candidate 01",
                "media_type": "image",
                "provider": "google",
                "model": "google-nb-pro",
                "prompt": provider_payload["prompt"],
                "settings": payload["settings"],
                "file_path": "output/frank_create/google.png",
                "preview_url": "/api/view?filename=google.png&type=output&subfolder=frank_create",
                "approval_status": "review",
                "sync_status": "local",
            }
        )
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": [asset["id"]]})
        return updated_turn, [asset]

    monkeypatch.setattr(routes, "run_live_provider_turn", fake_run_live_provider_turn)

    result = routes._create_inference_turn(
        {
            "kind": "generate",
            "model": "google-nb-pro",
            "prompt": "Frank Body coffee scrub pack shot on pink tile.",
            "settings": {"aspect_ratio": "1:1", "image_size": "4K", "count": 1},
            "reference_asset_ids": [],
        }
    )

    assert result["status"] == "complete"
    assert result["turn"]["provider"] == "google"
    assert result["turn"]["model"] == "google-nb-pro"
    assert result["assets"][0]["provider"] == "google"
    assert result["assets"][0]["model"] == "google-nb-pro"
    assert calls == [
        {
            "provider": "google",
            "model": "google-nb-pro",
            "provider_model": "gemini-3-pro-image",
            "turn_status": "queued",
            "settings": {"aspect_ratio": "1:1", "image_size": "4K", "count": 1},
            "prompt": "Frank Body coffee scrub pack shot on pink tile.",
        }
    ]
    assert "server-side-google" not in json.dumps(result)


@pytest.mark.asyncio
async def test_local_inference_turn_uses_comfy_runner_first(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    calls = []

    async def fake_run_comfy_studio_turn(prompt_server, store_arg, turn, payload, model):
        calls.append({"prompt_server": prompt_server, "turn_status": turn["status"], "model": model["id"]})
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": []})
        return updated_turn, []

    monkeypatch.setattr(routes, "run_comfy_studio_turn", fake_run_comfy_studio_turn)

    result = await routes._create_inference_turn_async(
        {
            "kind": "generate",
            "model": "frank-local-comfy",
            "prompt": "Clean Frank Body product image.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [],
        },
        prompt_server=object(),
    )

    assert result["status"] == "complete"
    assert result["localEngine"] == "comfy"
    assert calls == [{"prompt_server": calls[0]["prompt_server"], "turn_status": "running", "model": "frank-local-comfy"}]


@pytest.mark.asyncio
async def test_local_inference_turn_falls_back_when_comfy_unavailable(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    fallback_calls = []

    async def fake_run_comfy_studio_turn(*_args, **_kwargs):
        raise ComfyExecutionUnavailable("No Comfy queue")

    def fake_run_local_studio_turn(store_arg, turn, payload, model):
        fallback_calls.append({"turn_status": turn["status"], "prompt": payload["prompt"], "model": model["id"]})
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": []})
        return updated_turn, []

    monkeypatch.setattr(routes, "run_comfy_studio_turn", fake_run_comfy_studio_turn)
    monkeypatch.setattr(routes, "run_local_studio_turn", fake_run_local_studio_turn)

    result = await routes._create_inference_turn_async(
        {
            "kind": "generate",
            "model": "frank-local-comfy",
            "prompt": "Clean Frank Body product image.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [],
        },
        prompt_server=object(),
    )

    assert result["status"] == "complete"
    assert result["localEngine"] == "fallback"
    assert result["fallbackReason"] == "No Comfy queue"
    assert fallback_calls == [
        {
            "turn_status": "running",
            "prompt": "Clean Frank Body product image.",
            "model": "frank-local-comfy",
        }
    ]


@pytest.mark.asyncio
async def test_local_masked_edit_uses_comfy_runner_when_available(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    comfy_calls = []
    local_calls = []

    async def fake_run_comfy_studio_turn(prompt_server, store_arg, turn, payload, model):
        comfy_calls.append(
            {
                "prompt_server": prompt_server,
                "turn_status": turn["status"],
                "kind": payload["kind"],
                "mask_asset_id": payload["mask_asset_id"],
                "model": model["id"],
            }
        )
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": []})
        return updated_turn, []

    def fake_run_local_studio_turn(store_arg, turn, payload, model):
        local_calls.append(
            {
                "turn_status": turn["status"],
                "kind": payload["kind"],
                "mask_asset_id": payload["mask_asset_id"],
                "model": model["id"],
            }
        )
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": []})
        return updated_turn, []

    monkeypatch.setattr(routes, "run_comfy_studio_turn", fake_run_comfy_studio_turn)
    monkeypatch.setattr(routes, "run_local_studio_turn", fake_run_local_studio_turn)

    result = await routes._create_inference_turn_async(
        {
            "kind": "masked_edit",
            "model": "frank-local-comfy",
            "prompt": "Retouch only the masked label edge.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "edit_source_asset_id": "asset-source",
            "mask_asset_id": "asset-mask",
            "reference_asset_ids": [],
        },
        prompt_server=object(),
    )

    assert result["status"] == "complete"
    assert result["localEngine"] == "comfy"
    assert comfy_calls == [
        {
            "prompt_server": comfy_calls[0]["prompt_server"],
            "turn_status": "running",
            "kind": "masked_edit",
            "mask_asset_id": "asset-mask",
            "model": "frank-local-comfy",
        }
    ]
    assert local_calls == []


@pytest.mark.asyncio
async def test_local_masked_edit_falls_back_to_mask_aware_renderer_without_comfy_queue(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    local_calls = []

    async def fake_run_comfy_studio_turn(*_args, **_kwargs):
        raise ComfyExecutionUnavailable("Masked edit Comfy workflow requires a local checkpoint")

    def fake_run_local_studio_turn(store_arg, turn, payload, model):
        local_calls.append(
            {
                "turn_status": turn["status"],
                "kind": payload["kind"],
                "mask_asset_id": payload["mask_asset_id"],
                "model": model["id"],
            }
        )
        updated_turn = store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": []})
        return updated_turn, []

    monkeypatch.setattr(routes, "run_comfy_studio_turn", fake_run_comfy_studio_turn)
    monkeypatch.setattr(routes, "run_local_studio_turn", fake_run_local_studio_turn)

    result = await routes._create_inference_turn_async(
        {
            "kind": "masked_edit",
            "model": "frank-local-comfy",
            "prompt": "Retouch only the masked label edge.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "edit_source_asset_id": "asset-source",
            "mask_asset_id": "asset-mask",
            "reference_asset_ids": [],
        },
        prompt_server=object(),
    )

    assert result["status"] == "complete"
    assert result["localEngine"] == "fallback"
    assert result["fallbackReason"] == "Masked edit Comfy workflow requires a local checkpoint"
    assert local_calls == [
        {
            "turn_status": "running",
            "kind": "masked_edit",
            "mask_asset_id": "asset-mask",
            "model": "frank-local-comfy",
        }
    ]


def test_raw_comfy_canvas_url_is_same_server_route():
    assert routes.RAW_COMFY_CANVAS_URL == "/comfy/"


def test_workflow_blueprints_expose_curated_stock_comfy_graphs():
    response = routes._workflow_blueprints_response()

    assert response["status"] == "ready"
    assert response["checkpoint_name"] == "frank-create-placeholder.safetensors"
    assert [blueprint["key"] for blueprint in response["blueprints"]] == [
        "comfy-checkpoint-txt2img",
        "comfy-checkpoint-img2img",
        "comfy-checkpoint-inpaint",
    ]
    by_key = {blueprint["key"]: blueprint for blueprint in response["blueprints"]}
    assert by_key["comfy-checkpoint-txt2img"]["node_types"] == [
        "CheckpointLoaderSimple",
        "CLIPTextEncode",
        "CLIPTextEncode",
        "EmptyLatentImage",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ]
    assert "VAEEncode" in by_key["comfy-checkpoint-img2img"]["node_types"]
    assert "InpaintModelConditioning" in by_key["comfy-checkpoint-inpaint"]["node_types"]
    assert by_key["comfy-checkpoint-inpaint"]["workflow_json"]["4"]["class_type"] == "LoadImageMask"
    assert not re.search(r"sk-[A-Za-z0-9]|r8_[A-Za-z0-9]|AIza", json.dumps(response))


def test_asset_workflow_receipt_links_selected_pick_to_raw_comfy_canvas(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    session = store.create_session({"name": "Workflow bridge"})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Pink product set.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "status": "complete",
        }
    )
    asset = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": turn["id"],
            "kind": "candidate",
            "title": "Comfy bridge pick",
            "media_type": "image",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Pink product set.",
            "settings": {
                "workflow_provenance": {
                    "engine": "checkpoint_diffusion",
                    "workflow_key": "comfy-checkpoint-txt2img",
                    "workflow_json": {
                        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "frank.safetensors"}},
                        "2": {"class_type": "SaveImage", "inputs": {"api_key": "server-side-openai-secret"}},
                    },
                    "authorization": "Bearer server-side-openai-secret",
                }
            },
            "file_path": "output/frank_create/pick.png",
            "approval_status": "approved",
            "sync_status": "local",
        }
    )

    receipt = routes._asset_workflow_receipt(asset["id"])

    assert receipt["product"] == "Frank Create"
    assert receipt["asset"]["id"] == asset["id"]
    assert receipt["turn"]["id"] == turn["id"]
    assert receipt["workflow_key"] == "comfy-checkpoint-txt2img"
    assert receipt["engine"] == "checkpoint_diffusion"
    assert receipt["api_prompt_json"]["1"]["class_type"] == "CheckpointLoaderSimple"
    assert receipt["raw_canvas_url"] == f"/comfy/?frankAssetId={asset['id']}"
    assert receipt["can_open_raw_canvas"] is True
    assert receipt["can_load_comfy_api_prompt"] is True
    assert receipt["raw_canvas_load_status"] == "api_prompt_attached"
    assert receipt["comfy_node_types"] == ["CheckpointLoaderSimple", "SaveImage"]
    assert "server-side-openai-secret" not in json.dumps(receipt)
    assert receipt["workflow_provenance"]["authorization"] == "[server-side secret]"
    assert receipt["api_prompt_json"]["2"]["inputs"]["api_key"] == "[server-side secret]"


def test_create_video_storyboard_uses_local_asset_registry(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)

    calls = []

    def fake_video_runner(store_arg, turn, payload, model):
        calls.append({"turn_kind": turn["kind"], "model": model["id"], "source": payload["source_asset_id"]})
        asset = store_arg.create_asset(
            {
                "session_id": turn["session_id"],
                "turn_id": turn["id"],
                "kind": "video",
                "title": "Video storyboard",
                "media_type": "video",
                "file_path": "output/frank_create/storyboard.gif",
            }
        )
        return store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": [asset["id"]]}), [asset]

    monkeypatch.setattr(routes, "run_local_video_storyboard", fake_video_runner)
    session = store.create_session({"name": "Video QA", "mode": "video"})

    result = routes._create_video_storyboard(
        {
            "session_id": session["id"],
            "source_asset_id": "asset-source",
            "prompt": "Make a motion board.",
            "settings": {"aspect_ratio": "16:9"},
        }
    )

    assert result["status"] == "complete"
    assert result["assets"][0]["media_type"] == "video"
    assert calls == [{"turn_kind": "video", "model": "frank-local-comfy", "source": "asset-source"}]


def test_create_video_storyboard_rejects_over_limit_local_references_before_turn(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    session = store.create_session({"name": "Video Limit QA", "mode": "video"})
    calls = []

    def fake_video_runner(*args):
        calls.append(args)
        raise AssertionError("Video runner should not be called for over-limit references")

    monkeypatch.setattr(routes, "run_local_video_storyboard", fake_video_runner)

    with pytest.raises(routes.UnsupportedModelCapability, match="frank-local-comfy supports at most 8 reference images"):
        routes._create_video_storyboard(
            {
                "session_id": session["id"],
                "model": "frank-local-comfy",
                "source_asset_id": "asset-source",
                "prompt": "Make a local motion board.",
                "settings": {"aspect_ratio": "16:9", "image_size": "2K", "count": 1},
                "reference_asset_ids": [f"ref-{index}" for index in range(9)],
            }
        )

    assert calls == []
    assert store.list_turns(session_id=session["id"]) == []
    assert store.list_assets(session_id=session["id"]) == []


@pytest.mark.skip(reason="legacy xAI video provider is outside the three-key app boundary")
def test_create_video_storyboard_dispatches_live_video_model(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("XAI_API_KEY", "server-side-xai")
    session = store.create_session({"name": "xAI Video QA", "mode": "video"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Source image",
            "media_type": "image",
            "file_path": "output/frank_create/source.png",
        }
    )
    calls = []

    def fake_live_runner(store_arg, turn, payload, model, provider_payload):
        calls.append(
            {
                "turn_kind": turn["kind"],
                "turn_status": turn["status"],
                "provider": model["provider"],
                "model": model["id"],
                "prompt": provider_payload["prompt"],
                "source": payload["source_asset_id"],
            }
        )
        asset = store_arg.create_asset(
            {
                "session_id": turn["session_id"],
                "turn_id": turn["id"],
                "kind": "video",
                "title": "Grok Imagine / Motion",
                "media_type": "video",
                "provider": "xai",
                "model": model["id"],
                "file_path": "output/frank_create/grok.mp4",
            }
        )
        return store_arg.update_turn(turn["id"], {"status": "complete", "output_asset_ids": [asset["id"]]}), [asset]

    monkeypatch.setattr(routes, "run_live_provider_turn", fake_live_runner)

    result = routes._create_video_storyboard(
        {
            "session_id": session["id"],
            "model": "grok-imagine-quality",
            "source_asset_id": source["id"],
            "prompt": "Make a Grok motion board.",
            "settings": {"aspect_ratio": "16:9", "image_size": "2K", "count": 1},
            "reference_asset_ids": [],
        }
    )

    assert result["status"] == "complete"
    assert result["localEngine"] == "xai"
    assert result["assets"][0]["media_type"] == "video"
    assert calls == [
        {
            "turn_kind": "video",
            "turn_status": "queued",
            "provider": "xai",
            "model": "grok-imagine-quality",
            "prompt": "Make a Grok motion board.",
            "source": source["id"],
        }
    ]


@pytest.mark.skip(reason="legacy xAI video provider is outside the three-key app boundary")
def test_blocked_video_turn_records_missing_live_provider_key(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)

    turn = routes._create_blocked_video_turn(
        {
            "model": "grok-imagine-quality",
            "prompt": "Make a motion board.",
            "settings": {"aspect_ratio": "16:9", "image_size": "2K", "count": 1},
            "source_asset_id": "asset-source",
        },
        routes.MissingProviderKey("grok-imagine-quality", ["XAI_API_KEY"]),
    )

    assert turn["kind"] == "video"
    assert turn["provider"] == "xai"
    assert turn["model"] == "grok-imagine-quality"
    assert turn["status"] == "blocked"
    assert turn["source_asset_id"] == "asset-source"
    assert json.loads(turn["error_json"]) == {"code": "missing_key", "env_vars": ["XAI_API_KEY"]}
    assert store.list_sessions()[0]["mode"] == "video"


def test_inference_context_rejects_unsupported_settings_before_creating_turn(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(routes.UnsupportedModelCapability, match="google-nb-2 does not support image size 8K"):
        routes._create_turn_context(
            {
                "model": "google-nb-2",
                "kind": "generate",
                "prompt": "Fast ideation.",
                "settings": {"aspect_ratio": "1:1", "image_size": "8K", "count": 1},
            }
        )

    assert store.list_turns() == []
    assert store.list_sessions() == []


def test_comfy_user_css_contains_frank_theme_tokens():
    css = routes._comfy_user_css_text()

    assert "#FFB6A5" in css
    assert "#3F2A2D" in css
    assert '"Pitch"' in css
    assert "Founders Grotesk Text" in css
    assert "Frank Create" in css


def test_demo_readiness_pack_route_runs_pack_builder_off_event_loop():
    source = Path(routes.__file__).read_text(encoding="utf-8")

    assert 'routes.post("/frank/demo/readiness-pack")' in source
    assert "run_in_executor" in source
    assert "_demo_readiness_pack_response(payload)" in source


def test_provider_readiness_alias_matches_provider_status_route():
    source = Path(routes.__file__).read_text(encoding="utf-8")

    assert 'routes.get("/frank/provider-status")' in source
    assert 'routes.get("/frank/provider-readiness")' in source
    assert 'routes.post("/frank/demo/provider-readiness")' in source
    assert 'routes.get("/frank/demo/provider-readiness/{filename}")' in source
    assert 'routes.post("/frank/demo/brand-context")' in source
    assert 'routes.get("/frank/demo/brand-context/{filename}")' in source
    assert source.count("_provider_readiness_response()") >= 2


def test_provider_readiness_receipt_route_writes_openable_evidence(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)

    response = routes._demo_provider_readiness_receipt_response()

    assert response["latest_markdown_file"] == "frank-create-provider-readiness-latest.md"
    assert response["latest_markdown_url"] == "/api/frank/demo/provider-readiness/frank-create-provider-readiness-latest.md"
    assert response["latest_json_url"] == "/api/frank/demo/provider-readiness/frank-create-provider-readiness-latest.json"
    markdown_path = Path(response["latest_markdown_path"])
    json_path = Path(response["latest_json_path"])
    assert markdown_path.exists()
    assert json_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Frank Create Provider Readiness" in markdown
    assert "No-Spend Adapter Audit" in markdown
    assert "Operation request previews: 12 checked / 0 failures" in markdown
    assert "gpt-image-2 (openai):" in markdown
    assert "3 operation preview(s): generate, edit, masked_edit" in markdown
    json_receipt = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_receipt["adapter_audit"]["summary"]["operation_preview_count"] == 12
    assert json_receipt["adapter_audit"]["summary"]["operation_preview_failures"] == 0
    assert routes._resolve_demo_provider_readiness_file(response["latest_markdown_file"]) == markdown_path
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_provider_readiness_file("../provider_keys.env")
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_provider_readiness_file("provider_keys.env")


def test_brand_context_receipt_summarizes_references_and_lora_readiness(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    monkeypatch.setattr(routes, "_STORE", store)
    session = store.create_session({"name": "Brand Context QA", "mode": "image", "status": "active"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Body scrub pack shot",
            "file_path": "input/frank_create/body-scrub.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved hero",
            "file_path": "output/frank_create/approved.png",
            "media_type": "image",
            "approval_status": "approved",
        }
    )

    response = routes._demo_brand_context_receipt_response({"session_id": session["id"]})

    assert response["latest_markdown_file"] == "frank-create-brand-context-latest.md"
    assert response["latest_markdown_url"] == "/api/frank/demo/brand-context/frank-create-brand-context-latest.md"
    receipt = response["receipt"]
    assert receipt["summary"]["reference_asset_count"] == 1
    assert receipt["summary"]["approved_asset_count"] == 1
    assert receipt["summary"]["prompt_guided_status"] == "starter"
    assert receipt["summary"]["lora_training_status"] == "starter"
    assert receipt["reference_assets"][0]["id"] == reference["id"]
    assert "Future LoRA still needs at least 99 more rights-cleared references." in receipt["next_inputs"]
    markdown_path = Path(response["latest_markdown_path"])
    assert markdown_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Frank Create Brand Context Brief" in markdown
    assert "Prompt-guided target" in markdown
    assert "Do not train on Slack screenshots" in markdown
    assert routes._resolve_demo_brand_context_file(response["latest_markdown_file"]) == markdown_path
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_brand_context_file("../provider_keys.env")
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_brand_context_file("provider_keys.env")


def test_project_update_route_preserves_sync_metadata():
    source = Path(routes.__file__).read_text(encoding="utf-8")

    assert 'routes.patch("/frank/projects/{project_id}")' in source
    assert "update_project" in source


def test_session_sync_manifest_exposes_local_first_records(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    project = store.create_project({"name": "Body Scrub Launch", "remote_id": "frankhub_project_123"})
    brief = store.create_brief(
        {
            "project_id": project["id"],
            "title": "Coffee scrub PDP refresh",
            "product_name": "Original Coffee Scrub",
            "task_type": "product-shot-lab",
            "channel": "PDP",
            "sync_status": "pending",
        }
    )
    session = store.create_session(
        {
            "project_id": project["id"],
            "name": "Sync Manifest QA",
            "summary": "Approved PDP direction.",
            "sync_status": "pending",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Clean Frank Body product image.",
            "settings": {"aspect_ratio": "4:5", "workflow_provenance": {"workflow_key": "frank-local-variant-renderer"}},
            "frank_body_mode": True,
            "preset_key": "product-shot-lab",
            "sync_status": "pending",
        }
    )
    asset = store.create_asset(
        {
            "brief_id": brief["id"],
            "session_id": session["id"],
            "turn_id": turn["id"],
            "kind": "candidate",
            "title": "Approved hot PDP",
            "media_type": "image",
            "file_path": "output/frank_create/approved-hot.png",
            "approval_status": "approved",
            "settings": {"workflow_provenance": {"workflow_key": "frank-local-variant-renderer"}},
            "sync_status": "pending",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Pack reference",
            "media_type": "image",
            "file_path": "input/frank_create/reference.png",
            "sync_status": "local",
        }
    )
    export = store.create_export(
        {
            "asset_id": asset["id"],
            "preset": "high-res-master",
            "file_path": str(tmp_path / "exports" / "approved-hot.zip"),
            "metadata": {"manifest_file": "frank-create-export.json", "asset_id": asset["id"]},
            "sync_status": "pending",
        }
    )

    manifest = routes._session_sync_manifest(session["id"])

    assert manifest["schema_version"] == "frank-create.sync.v1"
    assert manifest["sync_contract"]["tables"]["assets"] == "frank_create_assets"
    assert manifest["sync_contract"]["remote_id_field"] == "remote_id"
    assert manifest["session"]["id"] == session["id"]
    assert manifest["project"]["remote_id"] == "frankhub_project_123"
    assert manifest["brief"]["id"] == brief["id"]
    assert manifest["counts"] == {
        "assets": 2,
        "approved_assets": 1,
        "reference_assets": 1,
        "turns": 1,
        "exports": 1,
        "pending_records": 5,
    }
    assert manifest["records"]["turns"][0]["settings"]["aspect_ratio"] == "4:5"
    assert manifest["records"]["assets"][0]["settings"]["workflow_provenance"]["workflow_key"] == "frank-local-variant-renderer"
    assert "settings_json" not in manifest["records"]["assets"][0]
    assert manifest["records"]["exports"][0]["id"] == export["id"]
    assert manifest["records"]["exports"][0]["metadata"]["manifest_file"] == "frank-create-export.json"


def test_local_engine_setup_route_prepares_model_folders():
    source = Path(routes.__file__).read_text(encoding="utf-8")

    assert 'routes.post("/frank/local-engine/setup")' in source
    assert "prepare_local_engine_folders()" in source


def test_comfy_brand_boot_script_themes_litegraph_canvas():
    script = routes._comfy_brand_boot_script()

    assert "window.LiteGraph" in script
    assert "NODE_DEFAULT_BGCOLOR" in script
    assert "NODE_TITLE_HEIGHT" in script
    assert "NODE_WIDGET_HEIGHT" in script
    assert "#FFB6A5" in script
    assert "#3F2A2D" in script


def test_comfy_brand_boot_script_keeps_raw_comfy_canvas_lightweight():
    script = routes._comfy_brand_boot_script()

    assert "applyFrankPalette" in script
    assert "window.LiteGraph" in script
    assert "NODE_DEFAULT_BGCOLOR" in script
    assert "clearStockStarterWorkflow" in script
    assert "frank-comfy-brand-chrome" in script
    assert "frank-comfy-workflow-receipt" in script
    assert "frank-comfy-empty-state" not in script
    assert "installFrankGraphRenderSkin" not in script
    assert "drawFrankCanvasTexture" not in script
    assert "drawFrankNodeStageBadge" not in script
    assert "applyFrankSlotBranding" not in script
    assert "drawFrankGraphLinkLabels" not in script
    assert "__frankCreateNodeGraphProof" not in script
    assert "FRANK_NODE_BADGE_HEIGHT" not in script


def test_comfy_brand_boot_script_adds_frank_graph_chrome():
    script = routes._comfy_brand_boot_script()
    blocking_overlays = (
        "frank-comfy-brand-strip",
        "frank-comfy-lane-map",
        "frank-comfy-action-rail",
        "frank-comfy-art-direction",
        "frank-comfy-node-legend",
        "frank-comfy-node-style-card",
        "frank-comfy-stage-ribbon",
        "frank-comfy-canvas-watermark",
        "frank-comfy-palette-card",
        "frank-comfy-status-dock",
        "frank-comfy-production-plate",
    )

    assert "ensureFrankChrome" in script
    assert "syncFrankWorkflowLabels" in script
    assert "frank-comfy-brand-chrome" in script
    assert "frank-comfy-workflow-receipt" in script
    assert all(overlay not in script for overlay in blocking_overlays)
    assert "frankAssetId" in script
    assert "/api/frank/assets/" in script
    assert "tryLoadFrankApiPrompt" in script
    assert "loadGraphData" in script
    assert "Loaded into canvas" in script
    assert "Advanced Comfy canvas" in script
    assert "Frank Graph / Raw Goods" in script
    assert "Frank Canvas" in script
    assert 'document.body.dataset.frankCreateGraph = "rawGoods"' in script


def test_comfy_brand_boot_script_guards_early_graph_access():
    script = routes._comfy_brand_boot_script()

    assert "const getGraph = () => {" in script
    assert "const graph = window.app?.canvas?.graph;" in script
    assert "window.app?.graph" not in script
    assert "window.app?.rootGraph" not in script
    assert "rootGraphInternal" not in script
    assert "return graph && Array.isArray(graph._nodes) ? graph : null;" in script


def test_comfy_brand_boot_script_filters_known_comfy_graph_init_noise_only():
    script = routes._comfy_brand_boot_script()

    assert "__frankComfyConsoleFilter" in script
    assert 'message.includes("ComfyApp graph accessed before initialization")' in script
    assert "originalConsoleError(...args)" in script
    assert "__frankComfyWarnFilter" in script
    assert "legacy queue/history menu is deprecated" in script
    assert "ComfyApp.open_maskeditor is deprecated" in script
    assert "originalConsoleWarn(...args)" in script


def test_comfy_user_css_brands_raw_canvas_graph_chrome():
    css = routes._comfy_user_css_text()
    blocking_overlays = (
        "#frank-comfy-brand-strip",
        "#frank-comfy-lane-map",
        "#frank-comfy-action-rail",
        "#frank-comfy-art-direction",
        "#frank-comfy-node-legend",
        "#frank-comfy-node-style-card",
        "#frank-comfy-stage-ribbon",
        "#frank-comfy-canvas-watermark",
        "#frank-comfy-palette-card",
        "#frank-comfy-status-dock",
        "#frank-comfy-production-plate",
    )

    assert "#frank-comfy-brand-chrome" in css
    assert "#frank-comfy-workflow-receipt" in css
    assert "#frank-comfy-empty-state" not in css
    assert all(overlay not in css for overlay in blocking_overlays)
    assert "body[data-frank-create-graph=\"rawGoods\"]" in css
    assert "pointer-events: none" in css
    assert 'content: "frank body"' in css
    assert "z-index: 48" in css
    assert "z-index: 56" in css


def test_comfy_brand_boot_script_shims_noisy_canvas_fetches():
    script = routes._comfy_brand_boot_script()

    assert "window.fetch" in script
    assert "/api/userdata" in script
    assert "comfy.templates.json" in script
    assert "pagination.limit" in script
    assert "isStockCheckpointHead" in script
    assert "v1-5-pruned-emaonly-fp16\\.safetensors" in script
    assert 'status: 204' in script


def test_provider_readiness_reports_missing_keys_without_secret_values(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)

    status = routes._provider_readiness_response()

    assert status["summary"]["readyModels"] == 1
    assert status["summary"]["waitingModels"] == 4
    local = next(provider for provider in status["providers"] if provider["provider"] == "local")
    assert local["configured"] is True
    google = next(provider for provider in status["providers"] if provider["provider"] == "google")
    assert google["configured"] is False
    assert google["missing_env_vars"] == ["GOOGLE_API_KEY"]
    assert "server-side-openai" not in str(status)


def test_provider_readiness_treats_replicate_as_flux_ready(monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "server-side-replicate")

    status = routes._provider_readiness_response()
    flux = next(model for model in status["models"] if model["id"] == "flux-1-1-pro-ultra")

    assert flux["configured"] is True
    assert flux["configured_env_var"] == "REPLICATE_API_TOKEN"
    assert "server-side-replicate" not in str(status)


def test_activation_checklist_summarizes_external_unlocks_without_secrets(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(tmp_path / "models"))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai-secret")
    monkeypatch.delenv("RECRAFT_API_KEY", raising=False)
    monkeypatch.delenv("RECRAFT_API_TOKEN", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("IDEOGRAM_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    checklist = routes._activation_checklist_response()

    assert checklist["status"] == "action_needed"
    assert checklist["summary"]["ready_provider_models"] == 2
    assert checklist["summary"]["waiting_provider_models"] == 3
    assert checklist["summary"]["diffusion_ready"] is False
    assert checklist["summary"]["checkpoint_count"] == 0
    assert checklist["summary"]["server_key_file"].endswith("provider_keys.env")
    assert "OPENAI_API_KEY" in checklist["summary"]["configured_env_vars"]
    assert "server-side-openai-secret" not in str(checklist)

    by_key = {step["key"]: step for step in checklist["steps"]}
    assert by_key["server-provider-keys"]["status"] == "action_needed"
    assert "GOOGLE_API_KEY" in by_key["server-provider-keys"]["env_vars"]
    assert "REPLICATE_API_TOKEN" in by_key["server-provider-keys"]["env_vars"]
    assert "IDEOGRAM_API_KEY" not in by_key["server-provider-keys"]["env_vars"]
    assert by_key["local-checkpoint"]["status"] == "action_needed"
    assert by_key["local-checkpoint"]["path"].endswith("checkpoints")
    assert by_key["adapter-audit"]["status"] == "ready"
    assert by_key["replicate-rotation"]["status"] == "recommended"
    assert "rotated" in by_key["replicate-rotation"]["action"].lower()


def test_provider_adapter_audit_reports_every_launch_adapter_without_spend(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RECRAFT_API_KEY", raising=False)
    monkeypatch.delenv("RECRAFT_API_TOKEN", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("IDEOGRAM_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    audit = routes._provider_adapter_audit_response()

    assert audit["summary"]["model_count"] == 5
    assert audit["summary"]["runner_registered"] == 5
    assert audit["summary"]["missing_runners"] == 0
    assert audit["summary"]["no_spend"] is True
    assert audit["summary"]["secret_values_returned"] is False
    assert audit["summary"]["waiting_for_key"] == 4
    assert audit["summary"]["operation_preview_count"] == 12
    assert audit["summary"]["operation_preview_failures"] == 0
    openai = next(model for model in audit["models"] if model["model_id"] == "openai-gpt-image-2")
    assert openai["status"] == "waiting_for_key"
    assert openai["operation_kinds"] == ["generate", "edit", "masked_edit"]
    assert openai["request_preview"]["endpoint"] == "https://api.openai.com/v1/images/generations"
    assert openai["request_preview"]["body_preview"]["prompt"] == "<composed prompt>"
    assert set(openai["request_previews"]) == {"generate", "edit", "masked_edit"}
    assert openai["request_previews"]["edit"]["endpoint"] == "https://api.openai.com/v1/images/edits"
    assert openai["request_previews"]["masked_edit"]["body_preview"]["files"] == ["image[]", "mask"]
    flux = next(model for model in audit["models"] if model["model_id"] == "flux-1-1-pro-ultra")
    assert flux["provider"] == "replicate"
    assert flux["request_preview"]["endpoint"].endswith("/black-forest-labs/flux-1.1-pro-ultra/predictions")
    assert "server-side-openai-secret" not in str(audit)
    assert "server-side-replicate" not in str(audit)


def test_provider_adapter_audit_reflects_configured_keys_without_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai-secret")

    audit = routes._provider_adapter_audit_response()
    openai = next(model for model in audit["models"] if model["model_id"] == "openai-gpt-image-2")

    assert openai["status"] == "ready"
    assert openai["configured_env_var"] == "OPENAI_API_KEY"
    assert "server-side-openai-secret" not in str(audit)


def test_provider_audit_route_is_registered():
    source = inspect.getsource(routes.register_routes)

    assert '@routes.get("/frank/provider-audit")' in source


def test_provider_preflight_reports_missing_key_without_secret_values(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    preflight = routes._provider_preflight_response(
        {
            "kind": "generate",
            "model": "openai-gpt-image-2",
            "prompt": "Clean Frank Body product image.",
            "settings": {"aspect_ratio": "1:1", "image_size": "4096", "count": 1},
            "reference_asset_ids": [],
        }
    )

    assert preflight["status"] == "blocked"
    assert preflight["ready"] is False
    assert preflight["missing_env_vars"] == ["OPENAI_API_KEY"]
    assert preflight["payloadPreview"]["model_id"] == "openai-gpt-image-2"
    assert preflight["payloadPreview"]["kind"] == "generate"
    assert "server-side" not in str(preflight)


def test_provider_preflight_returns_ready_local_payload_preview(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)

    preflight = routes._provider_preflight_response(
        {
            "kind": "generate",
            "model": "frank-local-comfy",
            "prompt": "Body scrub on pink tile.",
            "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 2},
            "reference_asset_ids": ["ref-1", "ref-2"],
            "frank_body_mode": True,
            "preset_key": "campaign-variants",
        }
    )

    assert preflight["status"] == "ready"
    assert preflight["ready"] is True
    assert preflight["missing_env_vars"] == []
    assert preflight["payloadPreview"]["provider"] == "local"
    assert preflight["payloadPreview"]["reference_count"] == 2
    assert preflight["payloadPreview"]["prompt_length"] > len("Body scrub on pink tile.")
    assert "Frank Body" in preflight["payloadPreview"]["prompt_preview"]


@pytest.mark.skip(reason="legacy Recraft provider is outside the three-key app boundary")
def test_provider_preflight_reports_unsupported_model_capability(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("RECRAFT_API_KEY", "server-side-recraft")

    preflight = routes._provider_preflight_response(
        {
            "kind": "edit",
            "model": "recraft-v4-pro",
            "prompt": "Retouch the product.",
            "settings": {"aspect_ratio": "1:1", "image_size": "4MP", "count": 1},
            "reference_asset_ids": [],
            "edit_source_asset_id": "asset-source",
        }
    )

    assert preflight["status"] == "unsupported"
    assert preflight["ready"] is False
    assert "does not support edit" in preflight["message"]
    assert "server-side-recraft" not in str(preflight)


@pytest.mark.skip(reason="legacy xAI video provider is outside the three-key app boundary")
def test_provider_preflight_rejects_over_limit_video_references(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("XAI_API_KEY", "server-side-xai")

    preflight = routes._provider_preflight_response(
        {
            "kind": "video",
            "model": "grok-imagine-quality",
            "prompt": "Make this approved image move for paid social.",
            "settings": {"aspect_ratio": "9:16", "image_size": "2K"},
            "source_asset_id": "asset-approved-source",
            "reference_asset_ids": ["ref-1", "ref-2", "ref-3", "ref-4", "ref-5"],
        }
    )

    assert preflight["status"] == "unsupported"
    assert preflight["ready"] is False
    assert "supports at most 4 reference images" in preflight["message"]
    assert preflight["payloadPreview"]["kind"] == "video"
    assert preflight["payloadPreview"]["reference_count"] == 5
    assert preflight["payloadPreview"]["reference_limit"] == 4
    assert "server-side-xai" not in str(preflight)


def test_provider_env_template_and_reload_do_not_expose_secret_values(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    template_status = routes._create_provider_env_template()
    env_file = tmp_path / "frank_create" / "provider_keys.env"

    assert template_status["created"] is True
    assert template_status["fileExists"] is True
    assert env_file.exists()
    assert "OPENAI_API_KEY=" in env_file.read_text(encoding="utf-8")

    env_file.write_text("OPENAI_API_KEY=server-side-openai-secret\nIGNORED_KEY=nope\n", encoding="utf-8")
    reloaded = routes._reload_provider_env_file()

    assert "OPENAI_API_KEY" in reloaded["loadedEnvVars"]
    assert "OPENAI_API_KEY" in reloaded["configuredEnvVars"]
    assert reloaded["readiness"]["summary"]["readyModels"] >= 2
    assert "server-side-openai-secret" not in str(reloaded)


def test_provider_env_save_writes_known_keys_only_and_returns_no_secret_values(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    env_file = tmp_path / "frank_create" / "provider_keys.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("GOOGLE_API_KEY=existing-google-secret\n", encoding="utf-8")

    status = routes._save_provider_env_values(
        {
            "keys": {
                "OPENAI_API_KEY": "server-side-openai-secret",
                "GOOGLE_API_KEY": "",
                "NOT_ALLOWED_KEY": "should-not-save",
            }
        }
    )

    text = env_file.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY=server-side-openai-secret" in text
    assert "GOOGLE_API_KEY=existing-google-secret" in text
    assert "NOT_ALLOWED_KEY" not in text
    assert "OPENAI_API_KEY" in status["savedEnvVars"]
    assert "NOT_ALLOWED_KEY" in status["ignoredEnvVars"]
    assert "OPENAI_API_KEY" in status["configuredEnvVars"]
    assert status["readiness"]["summary"]["readyModels"] >= 2
    assert "server-side-openai-secret" not in str(status)
    assert "existing-google-secret" not in str(status)


def test_provider_env_save_rejects_newline_values(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)

    with pytest.raises(ValueError, match="single key value"):
        routes._save_provider_env_values({"keys": {"OPENAI_API_KEY": "first\nsecond"}})


def test_provider_env_placeholders_do_not_count_as_configured_keys(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("OPENAI_API_KEY", "paste key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    status = routes._provider_env_status()

    assert "OPENAI_API_KEY" not in status["configuredEnvVars"]
    assert "OPENAI_API_KEY" in status["missingEnvVars"]
    assert next(model for model in routes._provider_readiness_response()["models"] if model["id"] == "openai-gpt-image-2")["configured"] is False

    saved = routes._save_provider_env_values({"keys": {"OPENAI_API_KEY": "YOUR_KEY_HERE"}})

    assert saved["savedEnvVars"] == []
    assert saved["ignoredPlaceholderEnvVars"] == ["OPENAI_API_KEY"]
    assert os.environ.get("OPENAI_API_KEY") is None
    assert "OPENAI_API_KEY=" in (tmp_path / "frank_create" / "provider_keys.env").read_text(encoding="utf-8")


def test_provider_env_reload_ignores_placeholder_file_values(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("OPENAI_API_KEY", "old-real-key")

    env_file = tmp_path / "frank_create" / "provider_keys.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("OPENAI_API_KEY=<paste key>\nGOOGLE_API_KEY=server-side-google-secret\n", encoding="utf-8")

    reloaded = routes._reload_provider_env_file()

    assert reloaded["loadedEnvVars"] == ["GOOGLE_API_KEY"]
    assert reloaded["ignoredPlaceholderEnvVars"] == ["OPENAI_API_KEY"]
    assert os.environ.get("OPENAI_API_KEY") == "old-real-key"
    assert os.environ.get("GOOGLE_API_KEY") == "server-side-google-secret"
    assert "OPENAI_API_KEY" in reloaded["configuredEnvVars"]
    assert "server-side-google-secret" not in str(reloaded)


def test_provider_env_reload_leaves_placeholder_process_env_unconfigured(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("OPENAI_API_KEY", "YOUR_KEY_HERE")

    env_file = tmp_path / "frank_create" / "provider_keys.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("OPENAI_API_KEY=<paste key>\n", encoding="utf-8")

    reloaded = routes._reload_provider_env_file()

    assert reloaded["loadedEnvVars"] == []
    assert reloaded["ignoredPlaceholderEnvVars"] == ["OPENAI_API_KEY"]
    assert os.environ.get("OPENAI_API_KEY") == "YOUR_KEY_HERE"
    assert "OPENAI_API_KEY" not in reloaded["configuredEnvVars"]
    assert "OPENAI_API_KEY" in reloaded["missingEnvVars"]


def test_brand_kit_response_persists_local_guidance(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)

    initial = routes._brand_kit_response()
    assert initial["brandKit"]["style_guidance"]
    assert initial["filePath"].endswith("brand_kit.json")

    updated = routes._update_brand_kit_response(
        {
            "style_guidance": "FrankHub pink tile, cherry-red accent, direct flash, coffee scrub texture.",
            "negative_prompt": "No beige spa stock sets, no warped labels.",
            "reference_notes": "Use the approved body scrub pack shots before lifestyle references.",
        }
    )

    assert updated["brandKit"]["style_guidance"].startswith("FrankHub pink tile")
    assert updated["brandKit"]["negative_prompt"] == "No beige spa stock sets, no warped labels."
    assert updated["brandKit"]["sync_status"] == "local"

    loaded = routes._brand_kit_response()
    assert loaded["brandKit"]["reference_notes"] == "Use the approved body scrub pack shots before lifestyle references."
    assert "brand_kit.json" in loaded["filePath"]
    assert "server-side" not in str(loaded)


def test_demo_doctor_reports_seeded_local_demo_ready_with_warnings(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")
    _write_test_png(tmp_path / "output" / "frank_create" / "masked.png", color=(196, 17, 47, 255))

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Starter image",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "settings": {
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-variant-renderer",
                }
            },
            "approval_status": "approved",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Masked edit",
            "file_path": "output/frank_create/masked.png",
            "media_type": "image",
            "settings": {
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-masked-edit-renderer",
                    "masked_edit": True,
                }
            },
            "approval_status": "approved",
        }
    )
    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is True
    assert doctor["status"] == "ready_with_warnings"
    assert doctor["summary"]["activeSessionCount"] == 1
    assert doctor["summary"]["outputAssetCount"] == 2
    assert doctor["summary"]["imageOutputAssetCount"] == 2
    assert doctor["summary"]["demoCurated"] is False
    assert doctor["summary"]["maskedEditReady"] is True
    assert doctor["summary"]["graphBrandingReady"] is True
    assert doctor["summary"]["callBriefReady"] is False
    assert doctor["summary"]["readinessPackReady"] is False
    assert doctor["summary"]["providerAdapterCount"] == 5
    assert doctor["summary"]["missingProviderAdapterCount"] == 0
    assert checks["demo_session"]["status"] == "ready"
    assert checks["graph_branding"]["status"] == "ready"
    assert "Advanced Graph" in checks["graph_branding"]["detail"]
    assert checks["provider_adapters"]["status"] == "ready"
    assert "5 / 5 launch provider runners registered" in checks["provider_adapters"]["detail"]
    assert "12 operation request previews checked" in checks["provider_adapters"]["detail"]
    assert "no external calls" in checks["provider_adapters"]["detail"]
    assert checks["starter_assets"]["status"] == "ready"
    assert checks["asset_files"]["status"] == "ready"
    assert checks["cliff_pack"]["status"] == "ready"
    assert checks["masked_edit"]["status"] == "ready"
    assert checks["motion_board"]["status"] == "warning"
    assert "No storyboard asset" in checks["motion_board"]["detail"]
    assert checks["curated_demo"]["status"] == "warning"
    assert "Demo is not in the Cliff-ready curated shape" in checks["curated_demo"]["detail"]
    assert checks["secret_hygiene"]["status"] == "ready"
    assert checks["provider_keys"]["status"] == "warning"
    assert "Provider Setup -> Save server keys" in checks["provider_keys"]["action"]
    assert "provider_keys.env" in checks["provider_keys"]["action"]
    assert checks["local_engine"]["status"] == "warning"
    assert "Prepare model folders" in checks["local_engine"]["action"]
    assert "checkpoints" in checks["local_engine"]["action"]
    assert "full checkpoint" in checks["local_engine"]["action"]
    assert "incomplete downloads" in checks["local_engine"]["action"]
    assert checks["workflow_smoke"]["status"] == "warning"
    assert "server-side-openai-secret" not in json.dumps(doctor)


def test_demo_doctor_accepts_nano_banana_image_edit_proof_without_placeholder_video(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    _write_test_png(tmp_path / "input" / "frank_create" / "product.png")
    for index in range(1, 6):
        _write_test_png(tmp_path / "input" / "frank_create" / f"nano-{index}.png")

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    hero = None
    for index in range(1, 5):
        asset = store.create_asset(
            {
                "session_id": session["id"],
                "kind": "candidate",
                "title": f"Nano Banana product shot {index}",
                "file_path": f"input/frank_create/nano-{index}.png",
                "media_type": "image",
                "provider": "google",
                "model": "google-nb-pro",
                "reference_asset_ids": [reference["id"]],
                "approval_status": "approved" if index == 1 else "review",
                "settings": {"workflow_provenance": {"workflow_key": "google-nano-banana-live-seed"}},
            }
        )
        if index == 1:
            hero = asset
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Nano Banana edit proof",
            "file_path": "input/frank_create/nano-5.png",
            "media_type": "image",
            "provider": "google",
            "model": "google-nb-pro",
            "source_asset_id": hero["id"],
            "reference_asset_ids": [reference["id"]],
            "approval_status": "review",
            "settings": {"workflow_provenance": {"workflow_key": "google-nano-banana-live-seed"}},
        }
    )

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is True
    assert doctor["summary"]["imageOutputAssetCount"] == 5
    assert doctor["summary"]["maskedEditReady"] is False
    assert doctor["summary"]["editProofReady"] is True
    assert doctor["summary"]["demoCurated"] is True
    assert checks["masked_edit"]["status"] == "ready"
    assert checks["masked_edit"]["label"] == "Edit proof"
    assert "Image edit proof is ready" in checks["masked_edit"]["detail"]
    assert checks["motion_board"]["status"] == "warning"
    assert checks["curated_demo"]["status"] == "ready"


def test_graph_branding_report_verifies_frank_graph_and_raw_canvas_tokens(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")
    (dist / "app.js").write_text(
        "Workflow Map Studio workflow map Real node graph lives in Comfy Canvas. "
        "Frank Create workflow map Selected workflow stage View details "
        "Workflow receipts Use in Studio Open Comfy Canvas",
        encoding="utf-8",
    )

    report = routes._graph_branding_report(dist)

    assert report["status"] == "ready"
    assert "raw Comfy canvas branding" in report["detail"]
    assert "frank-comfy-brand-chrome" in routes._comfy_brand_boot_script()
    assert "frank-comfy-workflow-receipt" in routes._comfy_brand_boot_script()
    assert "frank-comfy-production-plate" not in routes._comfy_brand_boot_script()
    assert "frank-create-raw-canvas" in routes._comfy_brand_boot_script()
    assert "Advanced Comfy canvas" in routes._comfy_brand_boot_script()
    assert "FRANK_NODE_BADGE_HEIGHT" not in routes._comfy_brand_boot_script()
    assert "drawFrankNodeTitlePlate" not in routes._comfy_brand_boot_script()
    assert "applyFrankSlotBranding" not in routes._comfy_brand_boot_script()
    assert "drawFrankGraphLinkLabels" not in routes._comfy_brand_boot_script()
    assert "__frankCreateNodeGraphProof" not in routes._comfy_brand_boot_script()
    assert "frank-comfy-node-style-card" not in routes._comfy_brand_boot_script()


def test_graph_branding_report_requires_workflow_map_tokens(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")
    (dist / "app.js").write_text("Workflow Map Studio workflow map Open Comfy Canvas", encoding="utf-8")

    report = routes._graph_branding_report(dist)

    assert report["status"] == "fail"
    assert "Real node graph lives in Comfy Canvas." in report["detail"]
    assert "npm run build" in report["action"]


def test_graph_branding_report_fails_when_shell_tokens_are_missing(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")

    report = routes._graph_branding_report(dist)

    assert report["status"] == "fail"
    assert "Branded graph shell is missing token" in report["detail"]
    assert "npm run build" in report["action"]


def test_provider_adapter_report_fails_when_visible_provider_has_no_runner(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_visible_models",
        lambda: [
            {
                "id": "mystery-image",
                "provider": "mystery",
                "status": "ready",
                "capabilities": {"generation": True, "edit": False, "masked_edit": False, "video": False},
            },
            {
                "id": "frank-local-comfy",
                "provider": "local",
                "status": "ready",
                "capabilities": {"generation": True, "edit": True, "masked_edit": False, "video": True},
            },
        ],
    )

    report = routes._provider_adapter_report()

    assert report["status"] == "fail"
    assert report["missing_count"] == 1
    assert "mystery" in report["detail"]


def test_demo_doctor_fails_when_source_file_contains_provider_token(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    leaked_token = "r8_" + "abcdefghijklmnopqrstuvwxyz123456"
    leaky_file = tmp_path / "frank-create" / "src" / "leaky.ts"
    leaky_file.parent.mkdir(parents=True)
    leaky_file.write_text(f'const token = "{leaked_token}";\n', encoding="utf-8")
    monkeypatch.setattr(routes, "SECRET_HYGIENE_SCAN_PATHS", (leaky_file,))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Starter image",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "approval_status": "approved",
        }
    )
    _add_approved_masked_asset(store, session, tmp_path)

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is False
    assert doctor["status"] == "needs_attention"
    assert checks["secret_hygiene"]["status"] == "fail"
    assert "1 Frank app file" in checks["secret_hygiene"]["detail"]
    assert "provider_keys.env" in checks["secret_hygiene"]["action"]
    assert str(leaky_file) in checks["secret_hygiene"]["detail"]
    assert leaked_token not in json.dumps(doctor)
    assert "server-side" not in str(doctor)


def test_secret_hygiene_detects_provider_env_assignments_but_allows_placeholders():
    assert routes._contains_secret_like_token('OPENAI_API_KEY="server-side-openai-secret"\n')
    assert routes._contains_secret_like_token("$env:REPLICATE_API_TOKEN='server-side-replicate-secret'\n")
    assert not routes._contains_secret_like_token("RUNWAYML_API_SECRET=server-side-runway-secret\n")
    assert not routes._contains_secret_like_token("$env:RUNWAY_API_KEY='server-side-runway-secret'\n")
    assert not routes._contains_secret_like_token('OPENAI_API_KEY="..."\n')
    assert not routes._contains_secret_like_token('$env:GOOGLE_API_KEY="..."\n')
    assert not routes._contains_secret_like_token("RUNWAYML_API_SECRET=<paste key>\n")


def test_demo_doctor_fails_when_cliff_pack_has_no_approved_asset(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Starter image",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "approval_status": "review",
        }
    )

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is False
    assert doctor["status"] == "needs_attention"
    assert doctor["summary"]["approvedAssetCount"] == 0
    assert checks["cliff_pack"]["status"] == "fail"
    assert "Cliff Pack export is disabled" in checks["cliff_pack"]["detail"]
    assert "Approve one seeded output" in checks["cliff_pack"]["action"]


def test_demo_doctor_reports_recent_workflow_smoke_receipt(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")
    store.root_dir.mkdir(parents=True, exist_ok=True)
    (store.root_dir / "workflow_smoke_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "completed_at": "2026-06-08T20:22:51+00:00",
                "session_name": "Frank Create Workflow Smoke 20260608-202251",
                "handoff": {
                    "asset_count": 2,
                    "reference_count": 1,
                    "media_file_count": 3,
                    "channel_export_set_count": 2,
                    "channel_export_file_count": 14,
                },
            }
        ),
        encoding="utf-8",
    )
    (store.root_dir / "cliff_prep_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "completed_at": "2026-06-08T21:25:37+00:00",
                "cliff_pack": {
                    "export_id": "export_seeded_pack",
                    "approved_asset_count": 1,
                    "reference_asset_count": 1,
                    "archive_file_count": 4,
                },
            }
        ),
        encoding="utf-8",
    )

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Starter image",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "approval_status": "approved",
        }
    )

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert checks["workflow_smoke"]["status"] == "ready"
    assert checks["demo_evidence"]["status"] == "warning"
    assert "Save evidence" in checks["demo_evidence"]["action"]
    assert checks["call_brief"]["status"] == "warning"
    assert "Call brief" in checks["call_brief"]["label"]
    assert "PREP_FRANK_CREATE_FOR_CLIFF.cmd" in checks["call_brief"]["action"]
    assert checks["activation_checklist"]["status"] == "warning"
    assert "activation checklist" in checks["activation_checklist"]["detail"].lower()
    assert "BUILD_FRANK_CREATE_READINESS_PACK.cmd" in checks["activation_checklist"]["action"]
    assert checks["readiness_pack"]["status"] == "warning"
    assert "BUILD_FRANK_CREATE_READINESS_PACK.cmd" in checks["readiness_pack"]["action"]
    assert "Workflow Smoke 20260608-202251" in checks["workflow_smoke"]["detail"]
    assert "3 handoff media files and 14 channel exports" in checks["workflow_smoke"]["detail"]
    assert doctor["summary"]["workflowSmokeOk"] is True
    assert doctor["summary"]["workflowSmokeAt"] == "2026-06-08T20:22:51+00:00"
    assert doctor["summary"]["workflowSmokeMediaFileCount"] == 3
    assert doctor["summary"]["workflowSmokeChannelExportFileCount"] == 14


def test_demo_doctor_reports_latest_call_brief_and_readiness_pack(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")
    evidence_dir = store.root_dir / "demo_evidence"
    readiness_dir = store.root_dir / "readiness_packs"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    readiness_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "frank-create-demo-evidence-latest.md").write_text("# Evidence", encoding="utf-8")
    (evidence_dir / "frank-create-demo-evidence-latest.json").write_text("{}", encoding="utf-8")
    (evidence_dir / "frank-create-call-brief-latest.md").write_text("# Brief", encoding="utf-8")
    (evidence_dir / "frank-create-call-brief-latest.json").write_text("{}", encoding="utf-8")
    (evidence_dir / "frank-create-activation-checklist-latest.md").write_text("# Activation", encoding="utf-8")
    (evidence_dir / "frank-create-activation-checklist-latest.json").write_text("{}", encoding="utf-8")
    _write_minimal_readiness_pack(readiness_dir / "frank-create-cliff-readiness-latest.zip")
    expected_sha = hashlib.sha256((readiness_dir / "frank-create-cliff-readiness-latest.zip").read_bytes()).hexdigest()
    (readiness_dir / "frank-create-cliff-readiness-latest.zip.sha256").write_text(
        f"{expected_sha}  frank-create-cliff-readiness-latest.zip\n",
        encoding="utf-8",
    )

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Starter image",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "approval_status": "approved",
        }
    )

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert checks["demo_evidence"]["status"] == "ready"
    assert "demo evidence receipt is ready" in checks["demo_evidence"]["detail"]
    assert checks["call_brief"]["status"] == "ready"
    assert "one-page Cliff call brief is ready" in checks["call_brief"]["detail"]
    assert checks["activation_checklist"]["status"] == "ready"
    assert "production activation checklist is ready" in checks["activation_checklist"]["detail"]
    assert checks["readiness_pack"]["status"] == "ready"
    assert "Latest Cliff readiness ZIP is ready" in checks["readiness_pack"]["detail"]
    assert doctor["summary"]["demoEvidenceReady"] is True
    assert doctor["summary"]["callBriefReady"] is True
    assert doctor["summary"]["activationChecklistReady"] is True
    assert doctor["summary"]["readinessPackReady"] is True
    assert doctor["summary"]["readinessPackBytes"] > 0
    assert doctor["summary"]["readinessPackSha256"] == expected_sha


def test_demo_doctor_warns_when_latest_readiness_pack_is_invalid(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    readiness_dir = store.root_dir / "readiness_packs"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    (readiness_dir / "frank-create-cliff-readiness-latest.zip").write_bytes(b"not a zip")

    report = routes._readiness_pack_report()

    assert report["status"] == "warning"
    assert "could not be verified" in report["detail"]
    assert "VERIFY_CLIFF_PACK.cmd" in report["action"]
    assert report["file_size_bytes"] == len(b"not a zip")


def test_demo_doctor_warns_when_latest_readiness_pack_has_stale_cliff_prep_browser_qa(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    readiness_dir = store.root_dir / "readiness_packs"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_readiness_pack(
        readiness_dir / "frank-create-cliff-readiness-latest.zip",
        include_cliff_browser_qa=False,
    )

    report = routes._readiness_pack_report()

    assert report["status"] == "warning"
    assert "Cliff prep" in report["detail"]
    assert "VERIFY_CLIFF_PACK.cmd" in report["action"]


def test_demo_doctor_warns_when_latest_readiness_pack_lacks_call_day_browser_proofs(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    readiness_dir = store.root_dir / "readiness_packs"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_readiness_pack(
        readiness_dir / "frank-create-cliff-readiness-latest.zip",
        include_call_day_browser_proofs=False,
    )

    report = routes._readiness_pack_report()

    assert report["status"] == "warning"
    assert "Browser QA" in report["detail"]
    assert "demo_doctor_checksum" in report["detail"] or "production unlock" in report["detail"]
    assert "VERIFY_CLIFF_PACK.cmd" in report["action"]


def test_demo_doctor_warns_when_latest_readiness_pack_lacks_local_generate_proof(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    readiness_dir = store.root_dir / "readiness_packs"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_readiness_pack(
        readiness_dir / "frank-create-cliff-readiness-latest.zip",
        include_local_generate_proof=False,
    )

    report = routes._readiness_pack_report()

    assert report["status"] == "warning"
    assert "studio_local_generate" in report["detail"] or "Generate" in report["detail"]
    assert "VERIFY_CLIFF_PACK.cmd" in report["action"]


def test_demo_doctor_warns_when_latest_readiness_pack_lacks_masked_edit_generate_proof(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    readiness_dir = store.root_dir / "readiness_packs"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_readiness_pack(
        readiness_dir / "frank-create-cliff-readiness-latest.zip",
        include_masked_edit_generate_proof=False,
    )

    report = routes._readiness_pack_report()

    assert report["status"] == "warning"
    assert "studio_masked_edit_generate" in report["detail"] or "masked edit" in report["detail"].lower()
    assert "VERIFY_CLIFF_PACK.cmd" in report["action"]


def test_demo_doctor_warns_when_latest_readiness_pack_lacks_model_preflight_proof(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    readiness_dir = store.root_dir / "readiness_packs"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_readiness_pack(
        readiness_dir / "frank-create-cliff-readiness-latest.zip",
        include_model_preflight_proof=False,
    )

    report = routes._readiness_pack_report()

    assert report["status"] == "warning"
    assert "studio_model_preflight" in report["detail"] or "preflight" in report["detail"].lower()
    assert "VERIFY_CLIFF_PACK.cmd" in report["action"]


def test_demo_reset_response_reseeds_local_session_and_assets(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    old_session = store.create_session({"name": "Messy Scratch", "mode": "image"})
    store.create_asset(
        {
            "session_id": old_session["id"],
            "kind": "candidate",
            "title": "Old output",
            "file_path": "output/frank_create/old.png",
            "media_type": "image",
        }
    )
    store.root_dir.mkdir(parents=True, exist_ok=True)
    (store.root_dir / "workflow_smoke_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "completed_at": "2026-06-08T20:22:51+00:00",
                "session_name": "Old workflow smoke",
                "handoff": {"media_file_count": 3, "channel_export_file_count": 14},
            }
        ),
        encoding="utf-8",
    )

    response = routes._reset_demo_response({})
    session = response["session"]
    assets = response["assets"]
    references = [asset for asset in assets if asset["kind"] == "reference"]
    outputs = [asset for asset in assets if asset["kind"] not in {"reference", "mask"}]
    masks = [asset for asset in assets if asset["kind"] == "mask"]
    videos = [asset for asset in outputs if asset["media_type"] == "video"]
    doctor_checks = {check["key"]: check for check in response["doctor"]["checks"]}
    reset_receipt = json.loads((store.root_dir / "workflow_smoke_status.json").read_text(encoding="utf-8"))

    assert session["name"] == "Frank Body Demo Studio"
    assert response["project"]["name"] == "Frank Body Demo Campaign"
    assert response["brief"]["title"] == "Coffee Scrub Product Image Lab"
    assert response["turn"]["session_id"] == session["id"]
    assert len(references) == 1
    assert len(masks) == 1
    assert len(outputs) == 6
    assert len(videos) == 1
    assert response["doctor"]["summary"]["outputAssetCount"] == 6
    assert response["doctor"]["summary"]["imageOutputAssetCount"] == 5
    assert response["doctor"]["summary"]["approvedAssetCount"] == 2
    assert response["doctor"]["summary"]["videoAssetCount"] == 1
    assert response["doctor"]["summary"]["demoCurated"] is True
    assert response["doctor"]["readyForDemo"] is True
    assert response["doctor"]["summary"]["workflowSmokeOk"] is False
    assert doctor_checks["curated_demo"]["status"] == "ready"
    assert "Clean first screen" in doctor_checks["curated_demo"]["detail"]
    assert doctor_checks["motion_board"]["status"] == "ready"
    assert doctor_checks["workflow_smoke"]["status"] == "warning"
    assert "Demo was reset" in doctor_checks["workflow_smoke"]["detail"]
    assert reset_receipt["ok"] is False
    assert reset_receipt["reason"] == "demo_reset"
    assert store.list_sessions() == [session]
    for asset in assets:
        path = routes._resolve_media_path(asset["file_path"])
        assert path and path.exists()


def test_demo_doctor_warns_when_demo_session_is_overloaded(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    _write_test_png(tmp_path / "input" / "frank_create" / "product.png")
    _write_test_png(tmp_path / "output" / "frank_create" / "video-proof.png")

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    _add_approved_masked_asset(store, session, tmp_path)
    for index in range(6):
        filename = f"extra-{index}.png"
        _write_test_png(tmp_path / "output" / "frank_create" / filename)
        store.create_asset(
            {
                "session_id": session["id"],
                "kind": "candidate",
                "title": f"Extra output {index + 1}",
                "file_path": f"output/frank_create/{filename}",
                "media_type": "image",
                "approval_status": "review",
            }
        )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "video",
            "title": "Motion proof",
            "file_path": "output/frank_create/video-proof.png",
            "media_type": "video",
            "approval_status": "approved",
        }
    )

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is True
    assert doctor["summary"]["imageOutputAssetCount"] == 7
    assert doctor["summary"]["demoCurated"] is False
    assert checks["curated_demo"]["status"] == "warning"
    assert "hide or reset 7 visible image outputs" in checks["curated_demo"]["detail"]
    assert "Reset demo data" in checks["curated_demo"]["action"]


def test_session_review_board_response_returns_png_with_counts(tmp_path, monkeypatch):
    from PIL import Image

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (700, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "approved.png")
    Image.new("RGBA", (320, 420), (255, 244, 240, 255)).save(tmp_path / "input" / "frank_create" / "ref.png")
    session = store.create_session({"name": "Direct board route"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Coffee scrub ref",
            "file_path": "input/frank_create/ref.png",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved board shot",
            "file_path": "output/frank_create/approved.png",
            "approval_status": "approved",
        }
    )

    response = routes._session_review_board_response(session["id"])

    assert response.status == 200
    assert response.content_type == "image/png"
    assert response.body.startswith(b"\x89PNG\r\n\x1a\n")
    assert response.headers["X-Frank-Review-Board-Approved"] == "1"
    assert response.headers["X-Frank-Review-Board-References"] == "1"


def test_demo_evidence_response_writes_markdown_and_json(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")
    store.root_dir.mkdir(parents=True, exist_ok=True)
    (store.root_dir / "workflow_smoke_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "completed_at": "2026-06-08T21:04:31+00:00",
                "session_name": "Frank Create Workflow Smoke 20260608-210428",
                "handoff": {"media_file_count": 3, "channel_export_file_count": 14},
            }
        ),
        encoding="utf-8",
    )
    (store.root_dir / "cliff_prep_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "completed_at": "2026-06-08T21:25:37+00:00",
                "cliff_pack": {
                    "export_id": "export_seeded_pack",
                    "approved_asset_count": 1,
                    "reference_asset_count": 1,
                    "archive_file_count": 4,
                },
            }
        ),
        encoding="utf-8",
    )
    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    evidence_dir = store.root_dir / "demo_evidence"
    readiness_dir = store.root_dir / "readiness_packs"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    readiness_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "frank-create-call-brief-latest.md").write_text("# Frank Create Cliff Call Brief", encoding="utf-8")
    (evidence_dir / "frank-create-call-brief-latest.json").write_text("{}", encoding="utf-8")
    _write_minimal_readiness_pack(readiness_dir / "frank-create-cliff-readiness-latest.zip")
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved starter",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "settings": {
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-variant-renderer",
                }
            },
            "approval_status": "approved",
        }
    )
    _add_approved_masked_asset(store, session, tmp_path)

    response = routes._demo_evidence_response({"base_url": "http://127.0.0.1:8190"})
    markdown_path = Path(response["markdown_path"])
    json_path = Path(response["json_path"])
    latest_markdown_path = Path(response["latest_markdown_path"])
    latest_json_path = Path(response["latest_json_path"])
    markdown = markdown_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert markdown_path.exists()
    assert json_path.exists()
    assert latest_markdown_path.exists()
    assert latest_json_path.exists()
    assert markdown_path.parent == store.root_dir / "demo_evidence"
    assert latest_markdown_path.parent == store.root_dir / "demo_evidence"
    assert latest_markdown_path.name == "frank-create-demo-evidence-latest.md"
    assert latest_json_path.name == "frank-create-demo-evidence-latest.json"
    assert latest_markdown_path.read_text(encoding="utf-8") == markdown
    assert json.loads(latest_json_path.read_text(encoding="utf-8"))["headline"] == payload["headline"]
    assert "Frank Create Demo Evidence" in markdown
    assert "Frank Create Workflow Smoke 20260608-210428" in markdown
    assert "Workflow smoke channel exports: 14" in markdown
    assert "Approved assets: 2" in markdown
    assert "Graph branding: verified" in markdown
    assert "Call brief: ready" in markdown
    assert "Readiness pack: ready" in markdown
    assert "Provider adapter families: 5 registered, 0 missing" in markdown
    assert "Launch Model Roster" in markdown
    assert "Local Comfy (local, Ready): ready; gen, edit, mask, video; 8 refs" in markdown
    assert "gpt-image-2 (openai, 4K): needs OPENAI_API_KEY; gen, edit, mask; 10 refs" in markdown
    assert "Cliff Prep Receipt" in markdown
    assert "export_seeded_pack" in markdown
    assert "Secret hygiene" in markdown
    assert payload["ready_for_demo"] is True
    assert payload["summary"]["graph_branding_ready"] is True
    assert payload["summary"]["call_brief_ready"] is True
    assert payload["summary"]["readiness_pack_ready"] is True
    assert payload["summary"]["readiness_pack_bytes"] > 0
    assert payload["summary"]["provider_adapter_count"] == 5
    assert payload["summary"]["missing_provider_adapter_count"] == 0
    assert len(payload["model_roster"]) == 5
    assert payload["model_roster"][0]["label"] == "Local Comfy"
    assert "OPENAI_API_KEY" in next(model for model in payload["model_roster"] if model["id"] == "openai-gpt-image-2")["missing_env_vars"]
    assert payload["summary"]["approved"] == 2
    assert payload["workflow_smoke"]["session_name"] == "Frank Create Workflow Smoke 20260608-210428"
    assert payload["workflow_smoke"]["channel_export_file_count"] == 14
    assert payload["cliff_prep"]["cliff_pack"]["export_id"] == "export_seeded_pack"
    assert response["markdown_url"] == f"/api/frank/demo/evidence/{markdown_path.name}"
    assert response["json_url"] == f"/api/frank/demo/evidence/{json_path.name}"
    assert response["latest_markdown_url"] == "/api/frank/demo/evidence/frank-create-demo-evidence-latest.md"
    assert response["latest_json_url"] == "/api/frank/demo/evidence/frank-create-demo-evidence-latest.json"
    assert routes._resolve_demo_evidence_file(markdown_path.name) == markdown_path
    assert routes._resolve_demo_evidence_file(latest_markdown_path.name) == latest_markdown_path
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_evidence_file("../provider_keys.env")
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_evidence_file("provider_keys.env")
    assert "server-side-openai-secret" not in json.dumps(response)


def test_demo_call_brief_response_writes_one_page_meeting_brief(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")
    store.root_dir.mkdir(parents=True, exist_ok=True)
    (store.root_dir / "workflow_smoke_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "completed_at": "2026-06-08T21:04:31+00:00",
                "session_name": "Frank Create Workflow Smoke 20260608-210428",
                "handoff": {"media_file_count": 3, "channel_export_file_count": 14},
            }
        ),
        encoding="utf-8",
    )
    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved starter",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "settings": {
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-variant-renderer",
                }
            },
            "approval_status": "approved",
        }
    )
    _add_approved_masked_asset(store, session, tmp_path)

    response = routes._demo_call_brief_response({"base_url": "http://127.0.0.1:8190"})
    markdown_path = Path(response["markdown_path"])
    latest_markdown_path = Path(response["latest_markdown_path"])
    markdown = markdown_path.read_text(encoding="utf-8")
    payload = json.loads(Path(response["json_path"]).read_text(encoding="utf-8"))

    assert markdown_path.exists()
    assert latest_markdown_path.exists()
    assert latest_markdown_path.name == "frank-create-call-brief-latest.md"
    assert "Frank Create Cliff Call Brief" in markdown
    assert "Call-Day Decision" in markdown
    assert "**GO WITH WARNINGS**" in markdown
    assert "`local_engine` No diffusion checkpoint detected" in markdown
    assert "`provider_keys` 4 live models are waiting on server keys" in markdown
    assert "What Passed" in markdown
    assert "Talk Track" in markdown
    assert "What To Hand Over" in markdown
    assert "Provider readiness: `provider-readiness/frank-create-provider-readiness-latest.md`" in markdown
    assert "Brand context: `brand-context/frank-create-brand-context-latest.md`" in markdown
    assert "Activation checklist: `activation-checklist/frank-create-activation-checklist-latest.md`" in markdown
    assert "Launch models: 1 ready / 4 waiting on keys" in markdown
    assert "Frank Create Workflow Smoke 20260608-210428" in markdown
    assert "Handoff channel exports in smoke: 14" in markdown
    assert "SHA-256 integrity metadata" in markdown
    assert payload["ready_for_demo"] is True
    assert payload["call_decision"]["status"] == "GO WITH WARNINGS"
    assert payload["call_decision"]["can_present"] is True
    assert "local_engine" in payload["call_decision"]["warning_keys"]
    assert "provider_keys" in payload["call_decision"]["warning_keys"]
    assert payload["summary"]["approved"] == 2
    assert payload["model_summary"]["ready_models"] == 1
    assert payload["model_summary"]["waiting_models"] == 4
    assert payload["workflow_smoke"]["handoff_media_files"] == 3
    assert payload["workflow_smoke"]["handoff_channel_exports"] == 14
    assert response["latest_markdown_url"] == "/api/frank/demo/call-brief/frank-create-call-brief-latest.md"
    assert routes._resolve_demo_call_brief_file(latest_markdown_path.name) == latest_markdown_path
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_call_brief_file("../provider_keys.env")
    assert "server-side-openai-secret" not in json.dumps(response)


def test_demo_readiness_pack_response_bundles_latest_receipts_and_screenshots(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        routes,
        "_capture_readiness_screenshots",
        lambda root_dir, base_url: {
            "status": "captured",
            "generated_at": "2026-06-09T00:00:00+00:00",
            "tool": "playwright screenshot",
            "base_url": base_url,
                "captured": [
                    {"key": "studio_desktop", "label": "Studio desktop", "file": "studio-live-desktop-latest.png"},
                    {"key": "studio_mobile", "label": "Studio mobile", "file": "studio-live-mobile-latest.png"},
                    {"key": "video_lab", "label": "Video Lab desktop", "file": "video-lab-live-desktop-latest.png"},
                    {"key": "provider_audit", "label": "Provider Adapter Audit", "file": "provider-audit-live-desktop-latest.png"},
                {"key": "advanced_graph", "label": "Advanced Graph", "file": "graph-live-desktop-latest.png"},
                {"key": "advanced_graph_mobile", "label": "Advanced Graph mobile", "file": "graph-live-mobile-latest.png"},
                {"key": "raw_comfy", "label": "Raw Comfy canvas", "file": "raw-comfy-live-quiet-latest.png"},
                {
                    "key": "raw_comfy_receipt",
                    "label": "Raw Comfy selected workflow receipt",
                    "file": "raw-comfy-workflow-receipt-latest.png",
                },
            ],
            "issues": [],
            "issue_count": 0,
            "notes": ["All canonical QA screenshots were refreshed before the pack was written."],
        },
    )
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)

    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")
    (store.root_dir / "qa").mkdir(parents=True)
    (store.root_dir / "qa" / "raw-comfy-branded-latest.png").write_bytes(b"png")
    (store.root_dir / "qa" / "studio-live-desktop-latest.png").write_bytes(b"studio desktop")
    (store.root_dir / "qa" / "studio-live-mobile-latest.png").write_bytes(b"studio mobile")
    (store.root_dir / "qa" / "video-lab-live-desktop-latest.png").write_bytes(b"video lab")
    (store.root_dir / "qa" / "provider-audit-live-desktop-latest.png").write_bytes(b"provider audit")
    (store.root_dir / "qa" / "graph-live-desktop-latest.png").write_bytes(b"graph desktop")
    (store.root_dir / "qa" / "graph-live-mobile-latest.png").write_bytes(b"graph mobile")
    (store.root_dir / "qa" / "raw-comfy-live-quiet-latest.png").write_bytes(b"raw quiet")
    (store.root_dir / "qa" / "raw-comfy-workflow-receipt-latest.png").write_bytes(b"raw receipt")
    (store.root_dir / "qa-graph-brand-desktop.png").write_bytes(b"graph png")
    studio_interaction_detail = (
        "Main Studio renders the provider key-order plan, copies a safe provider key plan with env-var names and no secret values, "
        "opens the direct visual review-board PNG, paints and saves a mask into the masked-edit composer, "
        "cleans QA mask assets/files, and has no horizontal overflow or console warnings/errors."
    )
    (store.root_dir / "browser_qa_status.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "completed_at": "2026-06-09T12:14:18.022497+00:00",
                "checks": [
                    {
                        "key": "studio_interactions",
                        "label": "Studio interaction path",
                        "status": "ready",
                        "url": "http://127.0.0.1:8190",
                        "detail": studio_interaction_detail,
                    },
                    {
                        "key": "video_lab",
                        "label": "Video Lab",
                        "status": "ready",
                        "url": "http://127.0.0.1:8190/?mode=video-lab",
                        "detail": "Video Lab opens directly from URL mode with motion proof copy present.",
                    },
                    {
                        "key": "provider_audit",
                        "label": "Provider Adapter Audit",
                        "status": "ready",
                        "url": "http://127.0.0.1:8190/?provider_audit=1",
                        "detail": "No-spend adapter audit renders without console warnings/errors.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (store.root_dir / "workflow_smoke_status.json").write_text(
        json.dumps(
            {
                "ok": True,
                "session_name": "Frank Create Workflow Smoke",
                "handoff": {"media_file_count": 3, "channel_export_file_count": 14},
            }
        ),
        encoding="utf-8",
    )
    (store.root_dir / "cliff_prep_status.json").write_text(
        json.dumps({"ok": True, "cliff_pack": {"export_id": "export_seeded_pack", "approved_asset_count": 1}}),
        encoding="utf-8",
    )
    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved starter",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "approval_status": "approved",
            "settings": {
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-variant-renderer",
                }
            },
        }
    )
    _add_approved_masked_asset(store, session, tmp_path)

    response = routes._demo_readiness_pack_response({"base_url": "http://127.0.0.1:8190"})
    zip_path = Path(response["file_path"])

    assert zip_path.exists()
    assert zip_path.parent == store.root_dir / "readiness_packs"
    assert response["download_url"] == f"/api/frank/demo/readiness-pack/{zip_path.name}"
    latest_zip_path = store.root_dir / "readiness_packs" / "frank-create-cliff-readiness-latest.zip"
    assert latest_zip_path.exists()
    assert response["latest_file_path"] == str(latest_zip_path)
    assert response["latest_file_name"] == "frank-create-cliff-readiness-latest.zip"
    assert response["latest_download_url"] == "/api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip"
    latest_implementation_manifest = store.root_dir / "readiness_packs" / "frank-create-implementation-manifest-latest.md"
    assert Path(response["latest_implementation_manifest_path"]) == latest_implementation_manifest
    assert (
        response["latest_implementation_manifest_url"]
        == "/api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md"
    )
    assert latest_implementation_manifest.exists()
    assert "Frank Create Implementation Manifest" in latest_implementation_manifest.read_text(encoding="utf-8")
    assert Path(response["checksum_path"]).exists()
    assert Path(response["latest_checksum_path"]).exists()
    assert response["checksum_sha256"] == Path(response["checksum_path"]).read_text(encoding="utf-8").split()[0]
    assert response["latest_checksum_sha256"] == Path(response["latest_checksum_path"]).read_text(encoding="utf-8").split()[0]
    assert len(response["checksum_sha256"]) == 64
    assert len(response["latest_checksum_sha256"]) == 64
    assert response["latest_file_size_bytes"] == latest_zip_path.stat().st_size
    assert routes._resolve_demo_readiness_pack_file("frank-create-cliff-readiness-latest.zip") == latest_zip_path
    assert response["manifest"]["screenshot_count"] == 8
    assert response["manifest"]["screenshot_capture"]["status"] == "captured"
    assert response["manifest"]["browser_qa"]["status"] == "ready"
    assert response["manifest"]["missing_files"] == []
    assert response["manifest"]["cliff_pack"]["status"] == "included"
    assert response["manifest"]["cliff_pack"]["approved_asset_count"] == 2
    assert response["manifest"]["cliff_pack"]["reference_count"] == 1
    assert response["provider_readiness"]["latest_markdown_file"] == "frank-create-provider-readiness-latest.md"
    assert response["brand_context"]["latest_markdown_file"] == "frank-create-brand-context-latest.md"
    assert response["activation_checklist"]["latest_markdown_file"] == "frank-create-activation-checklist-latest.md"
    assert routes._resolve_demo_readiness_pack_file(zip_path.name) == zip_path
    assert (
        routes._resolve_demo_readiness_pack_file("frank-create-implementation-manifest-latest.md")
        == latest_implementation_manifest
    )
    latest_manifest_text = latest_implementation_manifest.read_text(encoding="utf-8")
    assert "starts or reuses the local Studio" in latest_manifest_text
    assert "Google Gemini/Nano Banana is the first live API path" in latest_manifest_text
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_readiness_pack_file("../provider_keys.env")
    with pytest.raises(web.HTTPForbidden):
        routes._resolve_demo_readiness_pack_file("provider_keys.env")

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "README.md" in names
        assert "OPEN_ME_FIRST.md" in names
        assert "IMPLEMENTATION_MANIFEST.md" in names
        assert "readiness-pack-manifest.json" in names
        assert "FRANK_CREATE_CALL_DAY.md" in names
        assert "FRANK_CREATE_DEMO.md" in names
        assert "OPEN_FOR_CLIFF.md" in names
        assert "setup/frank-create.env.example" in names
        assert "call-brief/frank-create-call-brief-latest.md" in names
        assert "call-brief/frank-create-call-brief-latest.json" in names
        assert "provider-readiness/frank-create-provider-readiness-latest.md" in names
        assert "provider-readiness/frank-create-provider-readiness-latest.json" in names
        assert "activation-checklist/frank-create-activation-checklist-latest.md" in names
        assert "activation-checklist/frank-create-activation-checklist-latest.json" in names
        assert "brand-context/frank-create-brand-context-latest.md" in names
        assert "brand-context/frank-create-brand-context-latest.json" in names
        assert "evidence/frank-create-demo-evidence-latest.md" in names
        assert "evidence/frank-create-demo-evidence-latest.json" in names
        assert "receipts/workflow_smoke_status.json" in names
        assert "receipts/cliff_prep_status.json" in names
        assert "qa/browser-qa-receipt.json" in names
        assert "qa/browser-qa-receipt.md" in names
        assert "qa/screenshot-capture-receipt.json" in names
        assert "qa/screenshot-capture-receipt.md" in names
        assert "qa/shareable-pack-hygiene.json" in names
        assert "qa/shareable-pack-hygiene.md" in names
        assert "sync/frank-create-sync-manifest-latest.json" in names
        assert "launchers/CLIFF_START_HERE.cmd" in names
        assert "launchers/START_FRANK_CREATE_DEMO.cmd" in names
        assert "launchers/START_FRANK_CREATE.cmd" in names
        assert "launchers/CHECK_FRANK_CREATE.cmd" in names
        assert "launchers/VERIFY_CLIFF_PACK.cmd" in names
        assert "launchers/PREP_FRANK_CREATE_FOR_CLIFF.cmd" in names
        assert "launchers/BUILD_FRANK_CREATE_READINESS_PACK.cmd" in names
        assert "launchers/STOP_FRANK_CREATE.cmd" in names
        assert "screenshots/studio-live-desktop-latest.png" in names
        assert "screenshots/studio-live-mobile-latest.png" in names
        assert "screenshots/video-lab-live-desktop-latest.png" in names
        assert "screenshots/provider-audit-live-desktop-latest.png" in names
        assert "screenshots/graph-live-desktop-latest.png" in names
        assert "screenshots/graph-live-mobile-latest.png" in names
        assert "screenshots/raw-comfy-live-quiet-latest.png" in names
        assert "screenshots/raw-comfy-workflow-receipt-latest.png" in names
        assert "screenshots/raw-comfy-branded-latest.png" not in names
        assert "screenshots/qa-graph-brand-desktop.png" not in names
        assert any(name.startswith("handoffs/") and name.endswith(".zip") for name in names)
        assert all("provider_keys.env" not in name for name in names)
        manifest = json.loads(archive.read("readiness-pack-manifest.json").decode("utf-8-sig"))
        assert manifest["purpose"] == "Cliff call-day readiness pack"
        assert manifest["screenshot_count"] == 8
        assert [item["capability"] for item in manifest["acceptance_matrix"]] == [
            "Conversational Image Studio",
            "Product Shot Lab flow",
            "Generate, edit, approve, export",
            "Video Lab storyboard",
            "Advanced Graph + raw Comfy",
            "Curated Comfy workflow blueprints",
            "Frank Body Mode + brand context",
            "Live provider adapters",
            "Production activation checklist",
            "Server-side key hygiene",
            "Cliff handoff integrity",
        ]
        assert manifest["acceptance_matrix"][5]["status"] == "ready"
        assert "txt2img, img2img, and inpaint workflow JSON blueprints" in manifest["acceptance_matrix"][5]["proof"]
        assert manifest["acceptance_matrix"][6]["status"] == "ready"
        assert "Brand-context brief packaged with 1 reference asset(s)" in manifest["acceptance_matrix"][6]["proof"]
        assert "future LoRA" in manifest["acceptance_matrix"][6]["proof"]
        assert manifest["acceptance_matrix"][7]["status"] == "ready"
        assert manifest["acceptance_matrix"][8]["status"] == "ready"
        assert "Activation checklist packaged with 4 setup step(s)" in manifest["acceptance_matrix"][8]["proof"]
        assert "rotated live provider keys" in manifest["acceptance_matrix"][8]["proof"]
        assert studio_interaction_detail in manifest["acceptance_matrix"][0]["proof"]
        assert "No-spend audit: 5 / 5 launch runners registered" in manifest["acceptance_matrix"][7]["proof"]
        assert "provider keys" in manifest["acceptance_matrix"][7]["proof"]
        assert "byte-for-byte media integrity" in manifest["acceptance_matrix"][10]["proof"]
        assert "compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata" in manifest["acceptance_matrix"][10]["proof"]
        assert manifest["screenshot_capture"]["status"] == "captured"
        assert manifest["browser_qa"]["status"] == "ready"
        assert manifest["browser_qa"]["completed_at"] == "2026-06-09T12:14:18.022497+00:00"
        assert manifest["shareable_pack_hygiene"]["status"] == "clean"
        assert manifest["shareable_pack_hygiene"]["issue_count"] == 0
        assert {check["key"] for check in manifest["browser_qa"]["checks"]} == {
            "studio_interactions",
            "studio_desktop",
            "studio_mobile",
            "video_lab",
            "provider_audit",
            "advanced_graph",
            "advanced_graph_mobile",
            "raw_comfy",
            "raw_comfy_receipt",
        }
        provider_audit_check = next(
            check for check in manifest["browser_qa"]["checks"] if check["key"] == "provider_audit"
        )
        assert provider_audit_check["status"] == "included"
        assert provider_audit_check["browser_status"] == "ready"
        assert provider_audit_check["url"] == "http://127.0.0.1:8190/?provider_audit=1"
        assert "without console warnings/errors" in provider_audit_check["detail"]
        video_lab_check = next(check for check in manifest["browser_qa"]["checks"] if check["key"] == "video_lab")
        assert video_lab_check["status"] == "included"
        assert video_lab_check["browser_status"] == "ready"
        assert video_lab_check["url"] == "http://127.0.0.1:8190/?mode=video-lab"
        assert "motion proof copy" in video_lab_check["detail"]
        browser_qa = json.loads(archive.read("qa/browser-qa-receipt.json").decode("utf-8-sig"))
        assert browser_qa["status"] == "ready"
        assert browser_qa["completed_at"] == "2026-06-09T12:14:18.022497+00:00"
        packaged_provider_audit_check = next(
            check for check in browser_qa["checks"] if check["key"] == "provider_audit"
        )
        assert packaged_provider_audit_check["browser_status"] == "ready"
        assert packaged_provider_audit_check["url"] == "http://127.0.0.1:8190/?provider_audit=1"
        assert "without console warnings/errors" in packaged_provider_audit_check["detail"]
        assert any(
            check["key"] == "studio_interactions"
            and check["status"] == "ready"
            and "paints and saves a mask into the masked-edit composer" in check["detail"]
            for check in browser_qa["checks"]
        )
        cliff_prep = json.loads(archive.read("receipts/cliff_prep_status.json").decode("utf-8-sig"))
        assert cliff_prep["browser_qa"]["status"] == "ready"
        assert {check["key"] for check in cliff_prep["browser_qa"]["checks"]} >= {
            "studio_interactions",
            "video_lab",
            "provider_audit",
            "advanced_graph",
            "raw_comfy",
            "raw_comfy_receipt",
        }
        browser_qa_markdown = archive.read("qa/browser-qa-receipt.md").decode("utf-8-sig")
        assert "Frank Create Browser QA Receipt" in browser_qa_markdown
        assert "Provider Adapter Audit" in browser_qa_markdown
        assert "Browser: `ready`" in browser_qa_markdown
        assert "http://127.0.0.1:8190/?provider_audit=1" in browser_qa_markdown
        assert "No-spend adapter audit renders without console warnings/errors." in browser_qa_markdown
        assert "visible UI checksum at browser-QA time" in browser_qa_markdown
        assert "readiness ZIP .sha256 sidecar" in browser_qa_markdown
        screenshot_capture = json.loads(archive.read("qa/screenshot-capture-receipt.json").decode("utf-8-sig"))
        assert screenshot_capture["status"] == "captured"
        assert "Frank Create Screenshot Capture Receipt" in archive.read("qa/screenshot-capture-receipt.md").decode(
            "utf-8-sig"
        )
        hygiene = json.loads(archive.read("qa/shareable-pack-hygiene.json").decode("utf-8-sig"))
        assert hygiene["status"] == "clean"
        assert "Frank Create Shareable Pack Hygiene" in archive.read("qa/shareable-pack-hygiene.md").decode("utf-8-sig")
        assert manifest["cliff_pack"]["status"] == "included"
        assert manifest["cliff_pack"]["archive_path"].startswith("handoffs/")
        assert "No provider secrets are included." in manifest["notes"]
        assert "For the shortest meeting view, open call-brief/frank-create-call-brief-latest.md." in manifest["notes"]
        assert "For live-model setup status, open provider-readiness/frank-create-provider-readiness-latest.md." in manifest["notes"]
        assert "For production unlock actions, open activation-checklist/frank-create-activation-checklist-latest.md." in manifest["notes"]
        assert "For Frank Body Mode and future training inputs, open brand-context/frank-create-brand-context-latest.md." in manifest["notes"]
        assert "The call-day handoff copy is frank-create-cliff-readiness-latest.zip." in manifest["notes"]
        assert "sync/frank-create-sync-manifest-latest.json" in manifest["includes"]
        assert "OPEN_ME_FIRST.md" in manifest["includes"]
        assert "IMPLEMENTATION_MANIFEST.md" in manifest["includes"]
        assert "OPEN_FOR_CLIFF.md" in manifest["includes"]
        open_for_cliff = archive.read("OPEN_FOR_CLIFF.md").decode("utf-8-sig")
        assert "Double-click `CLIFF_START_HERE.cmd`." in open_for_cliff
        assert "frank-create-cliff-readiness-latest.zip.sha256" in open_for_cliff
        assert "frank-create.sync.v1" in open_for_cliff
        assert "byte-for-byte media integrity" in open_for_cliff
        assert "compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata" in open_for_cliff
        open_me = archive.read("OPEN_ME_FIRST.md").decode("utf-8-sig")
        assert "This is the Frank Create Cliff readiness pack." in open_me
        assert "CLIFF_START_HERE.cmd" in open_me
        assert "sync/frank-create-sync-manifest-latest.json" in open_me
        assert "setup/frank-create.env.example" in open_me
        assert "activation-checklist/frank-create-activation-checklist-latest.md" in open_me
        assert "brand-context/frank-create-brand-context-latest.md" in open_me
        assert "The local Frank Create workflow runs end to end" in open_me
        assert "channel-ready approved-image exports" in open_me
        assert "byte-for-byte media integrity" in open_me
        assert "No provider API keys or local secret files are included." in open_me
        implementation_manifest = archive.read("IMPLEMENTATION_MANIFEST.md").decode("utf-8-sig")
        assert "Frank Create Implementation Manifest" in implementation_manifest
        assert "Conversational Image Studio" in implementation_manifest
        assert "paints and saves a mask into the masked-edit composer" in implementation_manifest
        assert "cleans QA mask assets/files" in implementation_manifest
        assert "No-spend adapter audit: 5 / 5 launch runners" in implementation_manifest
        assert "Production activation checklist" in implementation_manifest
        assert "Activation checklist packaged with 4 setup step(s)" in implementation_manifest
        assert "mixed-media Cliff handoff ZIPs with channel-ready approved-image derivatives" in implementation_manifest
        assert "byte-for-byte media integrity" in implementation_manifest
        assert "CLIFF_START_HERE.cmd" in implementation_manifest
        env_example = archive.read("setup/frank-create.env.example").decode("utf-8-sig")
        assert "GOOGLE_API_KEY=" in env_example
        assert "OPENAI_API_KEY=" in env_example
        assert "REPLICATE_API_TOKEN=" in env_example
        assert "RUNWAYML_API_SECRET=" not in env_example
        assert "RUNWAY_API_KEY=" not in env_example
        assert "sk-" not in env_example
        assert "r8_" not in env_example
        readme = archive.read("README.md").decode("utf-8-sig")
        assert "Call-day file: frank-create-cliff-readiness-latest.zip." in readme
        assert "OPEN_ME_FIRST.md" in readme
        assert "IMPLEMENTATION_MANIFEST.md" in readme
        assert "OPEN_FOR_CLIFF.md" in readme
        assert "setup/frank-create.env.example" in readme
        assert "Checksum sidecar: frank-create-cliff-readiness-latest.zip.sha256." in readme
        assert "## Acceptance Matrix" in readme
        assert "| Conversational Image Studio | ready |" in readme
        assert "| Generate, edit, approve, export | ready | Workflow smoke media files: 3; channel exports: 14. |" in readme
        assert "| Frank Body Mode + brand context | ready |" in readme
        assert "| Live provider adapters | ready |" in readme
        assert "| Production activation checklist | ready |" in readme
        assert "| Cliff handoff integrity | ready |" in readme
        assert "byte-for-byte media integrity" in readme
        assert "compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata" in readme
        assert "Command Roster" in readme
        assert "CLIFF_START_HERE.cmd" in readme
        assert "launchers/" in readme
        assert "If opened inside an extracted pack, they open packaged proof docs instead of trying to rebuild the app." in readme
        assert "START_FRANK_CREATE_DEMO.cmd" in readme
        assert "CHECK_FRANK_CREATE.cmd" in readme
        assert "VERIFY_CLIFF_PACK.cmd" in readme
        assert "BUILD_FRANK_CREATE_READINESS_PACK.cmd" in readme
        assert "STOP_FRANK_CREATE.cmd" in readme
        assert "call-brief/frank-create-call-brief-latest.md" in readme
        assert "provider-readiness/frank-create-provider-readiness-latest.md" in readme
        assert "activation-checklist/frank-create-activation-checklist-latest.md" in readme
        assert "brand-context/frank-create-brand-context-latest.md" in readme
        assert "handoff-review/frank-create-review-board-latest.png" in readme
        assert "sync/frank-create-sync-manifest-latest.json" in readme
        sync_manifest = json.loads(archive.read("sync/frank-create-sync-manifest-latest.json").decode("utf-8-sig"))
        assert sync_manifest["schema_version"] == "frank-create.sync.v1"
        assert sync_manifest["sync_contract"]["tables"]["assets"] == "frank_create_assets"
        assert sync_manifest["session"]["name"] == "Frank Body Demo Studio"
        assert sync_manifest["counts"]["approved_assets"] >= 1
        assert sync_manifest["counts"]["reference_assets"] >= 1
        brand_context_markdown = archive.read("brand-context/frank-create-brand-context-latest.md").decode("utf-8-sig")
        brand_context_json = json.loads(archive.read("brand-context/frank-create-brand-context-latest.json").decode("utf-8-sig"))
        assert "Frank Create Brand Context Brief" in brand_context_markdown
        assert "Prompt-guided target" in brand_context_markdown
        assert "Future LoRA target" in brand_context_markdown
        assert "Do Not Train On" in brand_context_markdown
        assert brand_context_json["summary"]["reference_asset_count"] == 1
        assert brand_context_json["training_recommendation"]["lora"]
        provider_readiness_markdown = archive.read("provider-readiness/frank-create-provider-readiness-latest.md").decode(
            "utf-8-sig"
        )
        assert "Frank Create Provider Readiness" in provider_readiness_markdown
        assert "## Mocked Live-Path Coverage" in provider_readiness_markdown
        assert "Recraft V4.1 Pro (recraft)" not in provider_readiness_markdown
        assert "FLUX 1.1 Pro Ultra (replicate)" in provider_readiness_markdown
        assert "send edit sources as inline data" in provider_readiness_markdown
        assert "server-side Replicate token path" in provider_readiness_markdown
        assert "Mocked image edit creates review assets" not in provider_readiness_markdown
        activation_markdown = archive.read("activation-checklist/frank-create-activation-checklist-latest.md").decode(
            "utf-8-sig"
        )
        activation_json = json.loads(
            archive.read("activation-checklist/frank-create-activation-checklist-latest.json").decode("utf-8-sig")
        )
        assert "Frank Create Production Unlock Checklist" in activation_markdown
        assert "Paste rotated live provider keys" in activation_markdown
        assert "Install one full local checkpoint" in activation_markdown
        assert "Rotate the exposed Replicate token" in activation_markdown
        assert "No provider secret values are returned" in activation_markdown
        assert activation_json["status"] == "action_needed"
        assert len(activation_json["steps"]) == 4
        assert activation_json["steps"][0]["key"] == "server-provider-keys"
        assert "OPENAI_API_KEY" in json.dumps(activation_json)
        assert "server-side-openai-secret" not in json.dumps(activation_json)
        assert "FRANK_CREATE_CALL_DAY.md" in readme
        assert "current QA screenshots" in readme
        assert "blank provider-key template" in readme
        assert "local launcher wrappers" in readme
        assert "nested handoffs/ ZIP" in readme
        assert "handoff-review/frank-create-review-board-latest.png" in names
        top_level_review_board = archive.read("handoff-review/frank-create-review-board-latest.png")
        assert top_level_review_board.startswith(b"\x89PNG\r\n\x1a\n")
        handoff_name = next(name for name in names if name.startswith("handoffs/") and name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(archive.read(handoff_name))) as handoff_archive:
            handoff_names = set(handoff_archive.namelist())
            assert "review/frank-create-review-board.png" in handoff_names
            handoff_manifest = json.loads(handoff_archive.read("frank-create-handoff.json").decode("utf-8-sig"))
            sidecar_name = next(
                name for name in handoff_names if name.startswith("workflows/") and name.endswith(".json")
            )
            workflow_sidecar = json.loads(handoff_archive.read(sidecar_name).decode("utf-8-sig"))
        assert handoff_manifest["review_board"]["archive_path"] == "review/frank-create-review-board.png"
        assert handoff_manifest["review_board"]["approved_asset_count"] >= 1
        assert workflow_sidecar["workflow_bridge"]["raw_canvas_load_status"] in {"api_prompt_attached", "receipt_only"}
        assert workflow_sidecar["workflow_bridge"]["comfy_node_types"]
        assert "frankAssetId=" in workflow_sidecar["workflow_bridge"]["raw_canvas_url"]


def test_capture_readiness_screenshots_skips_when_npx_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(routes.shutil, "which", lambda name: None)

    receipt = routes._capture_readiness_screenshots(tmp_path, "http://127.0.0.1:8190")

    assert receipt["status"] == "skipped"
    assert receipt["captured"] == []
    assert "npx was not found" in receipt["notes"][0]


def test_capture_readiness_screenshots_refreshes_canonical_surfaces(tmp_path, monkeypatch):
    calls = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, cwd, capture_output, text, timeout, check):
        calls.append(command)
        Path(command[-1]).write_bytes(b"png")
        return Completed()

    monkeypatch.setattr(routes.shutil, "which", lambda name: "npx.cmd" if name == "npx.cmd" else None)
    monkeypatch.setattr(routes.subprocess, "run", fake_run)
    monkeypatch.setattr(routes, "_latest_approved_image_asset_id", lambda: "asset-receipt-proof")

    receipt = routes._capture_readiness_screenshots(tmp_path, "http://127.0.0.1:8190/")

    assert receipt["status"] == "captured"
    assert receipt["issue_count"] == 0
    assert [capture["file"] for capture in receipt["captured"]] == list(routes.READINESS_SCREENSHOT_NAMES)
    assert len(calls) == 8
    assert all(command[:3] == ["npx.cmd", "playwright", "screenshot"] for command in calls)
    assert "http://127.0.0.1:8190/?mode=video-lab" in calls[2]
    assert "http://127.0.0.1:8190/?provider_audit=1" in calls[3]
    assert "--wait-for-selector=[aria-label='Provider adapter audit']" in calls[3]
    assert "http://127.0.0.1:8190/graph" in calls[4]
    assert "http://127.0.0.1:8190/comfy/" in calls[6]
    assert "http://127.0.0.1:8190/comfy/?frankAssetId=asset-receipt-proof" in calls[7]
    assert "--wait-for-selector=[aria-label='Frank raw canvas workflow receipt']" in calls[7]


def test_readiness_handoff_zip_validation_rejects_missing_reference_media(tmp_path):
    broken = tmp_path / "broken-handoff.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "media_integrity": {"sha256": "a" * 64, "file_size_bytes": 3},
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "media_integrity": {"sha256": "b" * 64, "file_size_bytes": 3},
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", b"png")

    with pytest.raises(ValueError, match="reference media"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_requires_media_integrity(tmp_path):
    broken = tmp_path / "broken-integrity-handoff.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [{"id": "asset-approved"}],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "media_integrity": {"sha256": "b" * 64, "file_size_bytes": 3},
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", b"png")
        archive.writestr("references/ref.png", b"png")

    with pytest.raises(ValueError, match="approved media integrity"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_rejects_integrity_mismatch(tmp_path):
    broken = tmp_path / "broken-integrity-mismatch-handoff.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "archive_path": "approved/approved.png",
                            "workflow_sidecar_path": "approved/approved.workflow.json",
                            "media_integrity": {"sha256": "a" * 64, "file_size_bytes": 3},
                            "workflow_provenance": {
                                "engine": "frank_renderer",
                                "workflow_key": "frank-local-masked-edit",
                                "masked_edit": True,
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "archive_path": "references/ref.png",
                            "media_integrity": {"sha256": "b" * 64, "file_size_bytes": 3},
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", b"real-approved-bytes")
        archive.writestr("approved/approved.workflow.json", "{}")
        archive.writestr("references/ref.png", b"ref")

    with pytest.raises(ValueError, match="approved media integrity mismatch"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_requires_workflow_provenance(tmp_path):
    broken = tmp_path / "broken-workflow-handoff.zip"
    approved_bytes = b"png"
    reference_bytes = b"png"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "archive_path": "approved/approved.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                                "file_size_bytes": len(approved_bytes),
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "archive_path": "references/ref.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "file_size_bytes": len(reference_bytes),
                            },
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", approved_bytes)
        archive.writestr("references/ref.png", reference_bytes)

    with pytest.raises(ValueError, match="approved workflow provenance"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_allows_non_masked_approved_workflow(tmp_path):
    broken = tmp_path / "non-masked-approved-workflow-handoff.zip"
    approved_bytes = b"png"
    reference_bytes = b"png"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "archive_path": "approved/approved.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                                "file_size_bytes": len(approved_bytes),
                            },
                            "workflow_provenance": {
                                "engine": "frank_renderer",
                                "workflow_key": "frank-local-variant-renderer",
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "archive_path": "references/ref.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "file_size_bytes": len(reference_bytes),
                            },
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", approved_bytes)
        archive.writestr("references/ref.png", reference_bytes)

    with pytest.raises(ValueError, match="approved workflow_sidecar_path"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_requires_workflow_bridge_sidecar(tmp_path):
    broken = tmp_path / "broken-workflow-bridge-handoff.zip"
    approved_bytes = b"png"
    reference_bytes = b"ref"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "archive_path": "approved/approved.png",
                            "workflow_sidecar_path": "workflows/asset-approved-workflow.json",
                            "media_integrity": {
                                "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                                "file_size_bytes": len(approved_bytes),
                            },
                            "workflow_provenance": {
                                "engine": "frank_renderer",
                                "workflow_key": "frank-local-masked-edit-renderer",
                                "masked_edit": True,
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "archive_path": "references/ref.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "file_size_bytes": len(reference_bytes),
                            },
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", approved_bytes)
        archive.writestr("references/ref.png", reference_bytes)
        archive.writestr(
            "workflows/asset-approved-workflow.json",
            json.dumps(
                {
                    "asset_id": "asset-approved",
                    "workflow_provenance": {
                        "engine": "frank_renderer",
                        "workflow_key": "frank-local-masked-edit-renderer",
                    },
                }
            ),
        )

    with pytest.raises(ValueError, match="workflow bridge metadata"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_requires_review_board(tmp_path):
    broken = tmp_path / "broken-review-board-handoff.zip"
    approved_bytes = b"png"
    reference_bytes = b"ref"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "archive_path": "approved/approved.png",
                            "workflow_sidecar_path": "workflows/asset-approved-workflow.json",
                            "media_integrity": {
                                "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                                "file_size_bytes": len(approved_bytes),
                            },
                            "workflow_provenance": {
                                "engine": "frank_renderer",
                                "workflow_key": "frank-local-masked-edit-renderer",
                                "masked_edit": True,
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "archive_path": "references/ref.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "file_size_bytes": len(reference_bytes),
                            },
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", approved_bytes)
        archive.writestr("references/ref.png", reference_bytes)
        archive.writestr(
            "workflows/asset-approved-workflow.json",
            json.dumps(
                {
                    "asset_id": "asset-approved",
                    "workflow_provenance": {
                        "engine": "frank_renderer",
                        "workflow_key": "frank-local-masked-edit-renderer",
                    },
                    "workflow_bridge": {
                        "asset_id": "asset-approved",
                        "can_open_raw_canvas": True,
                        "raw_canvas_load_status": "receipt_only",
                        "comfy_node_types": ["FrankCreateMaskedEdit", "SaveImage"],
                        "raw_canvas_url": "/comfy/?frankAssetId=asset-approved",
                        "workflow_receipt_url": "/api/frank/assets/asset-approved/workflow",
                    },
                }
            ),
        )

    with pytest.raises(ValueError, match="review board"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_requires_channel_exports(tmp_path):
    broken = tmp_path / "broken-channel-exports-handoff.zip"
    approved_bytes = b"approved"
    reference_bytes = b"reference"
    review_board_bytes = _test_png_bytes(size=(1280, 860))
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("HANDOFF_SPEC.md", "# Frank Create Handoff Spec")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "counts": {"channel_export_sets": 0, "channel_export_files": 0},
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "archive_path": "approved/approved.png",
                            "workflow_sidecar_path": "workflows/asset-approved-workflow.json",
                            "media_integrity": {
                                "sha256": hashlib.sha256(approved_bytes).hexdigest(),
                                "file_size_bytes": len(approved_bytes),
                            },
                            "workflow_provenance": {
                                "engine": "frank_renderer",
                                "workflow_key": "frank-local-masked-edit-renderer",
                                "masked_edit": True,
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "archive_path": "references/ref.png",
                            "media_integrity": {
                                "sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "file_size_bytes": len(reference_bytes),
                            },
                        }
                    ],
                    "review_board": {
                        "archive_path": "review/frank-create-review-board.png",
                        "approved_asset_count": 1,
                        "width": 1280,
                        "height": 860,
                    },
                    "channel_exports": {},
                }
            ),
        )
        archive.writestr("approved/approved.png", approved_bytes)
        archive.writestr("references/ref.png", reference_bytes)
        archive.writestr("review/frank-create-review-board.png", review_board_bytes)
        archive.writestr(
            "workflows/asset-approved-workflow.json",
            json.dumps(
                {
                    "asset_id": "asset-approved",
                    "workflow_provenance": {
                        "engine": "frank_renderer",
                        "workflow_key": "frank-local-masked-edit-renderer",
                    },
                    "workflow_bridge": {
                        "asset_id": "asset-approved",
                        "can_open_raw_canvas": True,
                        "raw_canvas_load_status": "receipt_only",
                        "comfy_node_types": ["FrankCreateMaskedEdit", "SaveImage"],
                        "raw_canvas_url": "/comfy/?frankAssetId=asset-approved",
                        "workflow_receipt_url": "/api/frank/assets/asset-approved/workflow",
                    },
                }
            ),
        )

    with pytest.raises(ValueError, match="channel export"):
        routes._validate_readiness_handoff_zip(broken)


def test_readiness_handoff_zip_validation_requires_director_spec_sheet(tmp_path):
    broken = tmp_path / "broken-spec-handoff.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr(
            "frank-create-handoff.json",
            json.dumps(
                {
                    "approved_assets": [
                        {
                            "id": "asset-approved",
                            "media_integrity": {"sha256": "a" * 64, "file_size_bytes": 3},
                            "workflow_provenance": {
                                "engine": "frank_renderer",
                                "workflow_key": "frank-local-masked-edit-renderer",
                            },
                        }
                    ],
                    "reference_assets": [
                        {
                            "id": "asset-reference",
                            "media_integrity": {"sha256": "b" * 64, "file_size_bytes": 3},
                        }
                    ],
                }
            ),
        )
        archive.writestr("approved/approved.png", b"png")
        archive.writestr("references/ref.png", b"png")

    with pytest.raises(ValueError, match="HANDOFF_SPEC.md"):
        routes._validate_readiness_handoff_zip(broken)


def test_shareable_pack_hygiene_scans_nested_handoff_text(tmp_path):
    handoff = tmp_path / "handoff.zip"
    with zipfile.ZipFile(handoff, "w") as archive:
        archive.writestr("README.md", "handoff")
        archive.writestr("provider_keys.env", "OPENAI_API_KEY=server-side-openai-secret")

    receipt = routes._shareable_pack_hygiene_receipt(
        [{"kind": "zip", "path": handoff, "archive_name": "handoffs/frank-body-demo-studio-handoff.zip"}]
    )

    assert receipt["status"] == "blocked"
    assert receipt["issue_count"] >= 1
    assert any(issue["reason"] == "secret-looking file name" for issue in receipt["issues"])
    assert any(issue["reason"] == "provider-token-shaped value" for issue in receipt["issues"])


def test_demo_doctor_fails_when_seeded_media_files_are_missing(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))

    session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Missing reference",
            "file_path": "input/frank_create/missing-reference.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Missing starter",
            "file_path": "output/frank_create/missing-starter.png",
            "media_type": "image",
            "approval_status": "review",
        }
    )

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is False
    assert doctor["status"] == "needs_attention"
    assert doctor["summary"]["missingMediaFileCount"] == 2
    assert checks["asset_files"]["status"] == "fail"
    assert "2 media files are missing" in checks["asset_files"]["detail"]
    assert "Reset demo data" in checks["asset_files"]["action"]


def test_demo_doctor_prefers_seeded_demo_session_over_empty_scratch_session(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    (tmp_path / "input" / "frank_create" / "product.png").write_bytes(b"reference")
    _write_test_png(tmp_path / "output" / "frank_create" / "starter.png")

    demo_session = store.create_session({"name": "Frank Body Demo Studio", "mode": "image"})
    store.create_asset(
        {
            "session_id": demo_session["id"],
            "kind": "reference",
            "title": "Product reference",
            "file_path": "input/frank_create/product.png",
            "media_type": "image",
        }
    )
    store.create_asset(
        {
            "session_id": demo_session["id"],
            "kind": "candidate",
            "title": "Starter image",
            "file_path": "output/frank_create/starter.png",
            "media_type": "image",
            "approval_status": "approved",
        }
    )
    _add_approved_masked_asset(store, demo_session, tmp_path)
    scratch_session = store.create_session({"name": "Frank Create Workflow Smoke", "mode": "image", "status": "active"})
    with store._connect() as conn:
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", ("2999-01-01T00:00:00+00:00", scratch_session["id"]))

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is True
    assert doctor["summary"]["activeSessionCount"] == 2
    assert doctor["summary"]["outputAssetCount"] == 2
    assert doctor["summary"]["imageOutputAssetCount"] == 2
    assert doctor["summary"]["demoCurated"] is False
    assert checks["demo_session"]["detail"] == "Frank Body Demo Studio is active."
    assert checks["starter_assets"]["status"] == "ready"
    assert checks["cliff_pack"]["status"] == "ready"


def test_demo_doctor_flags_empty_store_as_needing_attention(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "frank_create")
    monkeypatch.setattr(routes, "_STORE", store)

    doctor = routes._demo_doctor_response()
    checks = {check["key"]: check for check in doctor["checks"]}

    assert doctor["readyForDemo"] is False
    assert doctor["status"] == "needs_attention"
    assert checks["demo_session"]["status"] == "fail"
    assert "Reset demo data" in checks["demo_session"]["action"]


def test_prompt_remix_response_returns_three_frank_directions():
    result = routes._prompt_remix_response(
        {
            "prompt": "Coffee scrub product shot on a pink bathroom counter",
            "preset_key": "product-shot-lab",
            "frank_body_mode": True,
        }
    )

    assert len(result["variants"]) == 3
    assert {variant["key"] for variant in result["variants"]} == {"clean", "lifestyle", "campaign"}
    assert all("Coffee scrub product shot" in variant["prompt"] for variant in result["variants"])
    assert any("Frank Body" in variant["prompt"] for variant in result["variants"])
    assert "sk-" not in str(result)


def test_comfy_brand_boot_script_clears_stock_missing_model_workflow():
    script = routes._comfy_brand_boot_script()

    assert "v1-5-pruned-emaonly-fp16.safetensors" in script
    assert "clearStockStarterWorkflow" in script
    assert "graph.clear()" in script
    assert "dismissStockStarterAlerts" in script


def test_comfy_canvas_compat_returns_empty_userdata_for_canvas_referer():
    request = SimpleNamespace(
        method="GET",
        path="/api/userdata",
        headers={"Referer": "http://127.0.0.1:8190/comfy/"},
        rel_url=SimpleNamespace(query={}),
    )

    response = routes._comfy_canvas_compat_preflight(request)

    assert response.status == 200
    assert response.text == "[]"


def test_comfy_canvas_compat_ignores_non_canvas_userdata_requests():
    request = SimpleNamespace(
        method="GET",
        path="/api/userdata",
        headers={},
        rel_url=SimpleNamespace(query={}),
    )

    assert routes._comfy_canvas_compat_preflight(request) is None


def test_normalize_jobs_payload_sets_numeric_limit():
    payload = {"jobs": [{"id": "one"}], "pagination": {"offset": 0, "limit": None, "total": 1}}

    normalized = routes._normalize_jobs_payload(payload)

    assert normalized["pagination"]["limit"] == 1


def test_comfy_prefix_redirect_preserves_root_api_path():
    redirect = routes._comfy_prefix_redirect("system_stats")

    assert redirect.location == "/system_stats"
    assert redirect.status == 307


@pytest.mark.asyncio
async def test_comfy_websocket_handles_prefixed_canvas_route(aiohttp_client):
    prompt_server = FakePromptServer()
    route_table = web.RouteTableDef()

    @route_table.get("/comfy/ws")
    async def websocket_handler(request):
        return await routes._comfy_websocket(request, prompt_server)

    app = web.Application()
    app.add_routes(route_table)
    client = await aiohttp_client(app)

    ws = await client.ws_connect("/comfy/ws?clientId=frank-canvas")
    initial = await ws.receive_json()

    assert initial["type"] == "status"
    assert initial["data"]["sid"] == "frank-canvas"
    assert "frank-canvas" in prompt_server.sockets

    await ws.send_json({"type": "feature_flags", "data": {"frank_graph": True}})
    feature_response = await ws.receive_json()

    assert feature_response["type"] == "feature_flags"
    assert prompt_server.sockets_metadata["frank-canvas"]["feature_flags"] == {"frank_graph": True}

    await ws.close()
