import os

import pytest

from custom_nodes.frank_create.inference import (
    MissingProviderKey,
    UnsupportedModelCapability,
    build_provider_payload,
    build_turn_payload,
    require_provider_key,
)
from custom_nodes.frank_create.models import (
    compose_frank_prompt,
    get_local_engine_status,
    get_preferred_checkpoint,
    get_visible_models,
    prepare_local_engine_folders,
)
from custom_nodes.frank_create.provider_adapters import (
    build_google_request,
    build_openai_generation_request,
    build_provider_request_preview,
    provider_runner_keys,
)


def test_visible_model_registry_includes_launch_models_with_capabilities():
    models = get_visible_models()
    ids = [model["id"] for model in models]

    assert ids == [
        "frank-local-comfy",
        "google-nb-pro",
        "google-nb-2",
        "openai-gpt-image-2",
        "flux-1-1-pro-ultra",
    ]
    assert {model["provider"] for model in models} == {"local", "google", "openai", "replicate"}
    assert {
        env_var for model in models for env_var in model.get("env_vars", [])
    } == {"GOOGLE_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN"}

    local = next(model for model in models if model["id"] == "frank-local-comfy")
    assert local["capabilities"]["video"] is True
    assert local["capabilities"]["masked_edit"] is True
    assert all("future" not in (model.get("description") or "").lower() for model in models)

    nano_banana_pro = next(model for model in models if model["id"] == "google-nb-pro")
    assert nano_banana_pro["provider_model"] == "gemini-3-pro-image"
    assert nano_banana_pro["provider_api_version"] == "v1beta"
    assert nano_banana_pro["allowed_image_sizes"] == ["1K", "2K", "4K"]

    nano_banana_2 = next(model for model in models if model["id"] == "google-nb-2")
    assert nano_banana_2["provider_model"] == "gemini-3.1-flash-image"
    assert nano_banana_2["provider_api_version"] == "v1beta"
    assert nano_banana_2["badge"] == "4K"
    assert nano_banana_2["max_resolution_label"] == "4K"
    assert nano_banana_2["allowed_image_sizes"] == ["1K", "2K", "4K"]


def test_local_engine_status_reports_frank_renderer_without_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(tmp_path / "models"))

    status = get_local_engine_status()

    assert status["active_engine"] == "frank_renderer"
    assert status["diffusion_ready"] is False
    assert status["checkpoint_count"] == 0
    assert status["ignored_checkpoints"] == []
    assert status["minimum_checkpoint_mb"] == 100
    assert status["checkpoint_dir"].endswith("models" + os.sep + "checkpoints")
    assert status["setup_readme"].endswith("FRANK_CREATE_MODELS_README.txt")
    assert any("SDXL-style .safetensors checkpoint" in step for step in status["setup_steps"])
    assert any("raw Comfy canvas for FLUX" in step for step in status["setup_steps"])
    assert any("Run Demo Doctor again" in step for step in status["setup_steps"])
    assert status["recommended_checkpoints"][0]["label"].startswith("SDXL")
    assert "No diffusion checkpoint" in status["note"]


def test_local_engine_status_detects_local_checkpoints(tmp_path, monkeypatch):
    model_root = tmp_path / "models"
    checkpoint_dir = model_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "frank-test.safetensors").write_bytes(b"fake-model")
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("FRANK_CREATE_MIN_CHECKPOINT_BYTES", "1")

    status = get_local_engine_status()

    assert status["diffusion_ready"] is True
    assert status["active_engine"] == "checkpoint_diffusion"
    assert status["checkpoint_count"] == 1
    assert status["checkpoints"] == ["frank-test.safetensors"]
    assert status["ignored_checkpoints"] == []
    assert "checkpoint txt2img" in status["note"]
    assert "checkpoint img2img" in status["note"]
    assert "checkpoint inpaint" in status["note"]
    assert get_preferred_checkpoint() == "frank-test.safetensors"


def test_local_engine_status_ignores_tiny_checkpoint_placeholders(tmp_path, monkeypatch):
    model_root = tmp_path / "models"
    checkpoint_dir = model_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "broken-download.safetensors").write_bytes(b"not-a-real-model")
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("FRANK_CREATE_MIN_CHECKPOINT_BYTES", "1000")

    status = get_local_engine_status()

    assert status["diffusion_ready"] is False
    assert status["active_engine"] == "frank_renderer"
    assert status["checkpoint_count"] == 0
    assert status["checkpoints"] == []
    assert status["ignored_checkpoints"][0]["name"] == "broken-download.safetensors"
    assert status["ignored_checkpoints"][0]["reason"] == "smaller than 1 MB"
    assert "No usable diffusion checkpoint" in status["note"]
    assert get_preferred_checkpoint() is None


def test_prepare_local_engine_folders_creates_model_dirs_and_readme(tmp_path, monkeypatch):
    model_root = tmp_path / "models"
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(model_root))

    result = prepare_local_engine_folders()

    assert (model_root / "checkpoints").is_dir()
    assert (model_root / "loras").is_dir()
    assert (model_root / "vae").is_dir()
    assert (model_root / "controlnet").is_dir()
    readme = model_root / "FRANK_CREATE_MODELS_README.txt"
    assert readme.exists()
    text = readme.read_text(encoding="utf-8")
    assert "Checkpoint folder" in text
    assert "full SDXL-style .safetensors checkpoint" in text
    assert "reference/edit img2img" in text
    assert "masked inpaint" in text
    assert "ignores checkpoint-looking files smaller" in text
    assert "raw Comfy canvas for FLUX" in text
    assert "Do not store API keys" in text
    assert result["readme_path"] == str(readme)
    assert result["localEngine"]["checkpoint_dir"] == str(model_root / "checkpoints")


def test_frank_body_mode_is_opt_in_prompt_layer():
    plain = compose_frank_prompt(
        "Create a body scrub product shot.",
        frank_body_mode=False,
        preset_key="clean-ecom",
    )
    styled = compose_frank_prompt(
        "Create a body scrub product shot.",
        frank_body_mode=True,
        preset_key="clean-ecom",
    )

    assert plain == "Create a body scrub product shot."
    assert "Frank Body visual language" in styled
    assert "Clean Ecom" in styled
    assert "Create a body scrub product shot." in styled


def test_frank_body_mode_accepts_local_brand_kit_context():
    styled = compose_frank_prompt(
        "Create a coffee scrub campaign image.",
        frank_body_mode=True,
        preset_key="campaign-variants",
        brand_kit={
            "style_guidance": "Use the approved FrankHub cherry-red accent and tactile coffee scrub macro language.",
            "negative_prompt": "No beige spa stock sets, no warped labels.",
            "reference_notes": "Prioritize the latest body scrub pack shots and bathroom shelf references.",
        },
    )

    assert "Frank Body brand kit" in styled
    assert "FrankHub cherry-red accent" in styled
    assert "No beige spa stock sets" in styled
    assert "latest body scrub pack shots" in styled
    assert "Campaign Variants" in styled
    assert "Create a coffee scrub campaign image." in styled


def test_provider_key_lookup_stays_server_side(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(MissingProviderKey):
        require_provider_key("openai-gpt-image-2")

    monkeypatch.setenv("OPENAI_API_KEY", "server-side-only")

    assert require_provider_key("openai-gpt-image-2") == "server-side-only"


def test_provider_payload_maps_shared_request_without_leaking_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")

    payload = build_provider_payload(
        model_id="google-nb-pro",
        prompt="Warm campaign image.",
        settings={"aspect_ratio": "1:1", "image_size": "4K", "count": 2, "thinking": "high"},
        reference_assets=["input/frank_create/ref.png"],
        edit_source_asset_id=None,
    )

    assert payload["provider"] == "google"
    assert payload["model"] == "gemini-3-pro-image"
    assert payload["settings"]["image_size"] == "4K"
    assert payload["reference_assets"] == ["input/frank_create/ref.png"]
    assert "server-side-google" not in str(payload)


def test_turn_payload_uses_supplied_brand_kit_when_frank_mode_enabled():
    payload = build_turn_payload(
        {
            "model": "frank-local-comfy",
            "kind": "generate",
            "prompt": "Coffee scrub product hero.",
            "frank_body_mode": True,
            "preset_key": "product-shot-lab",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [],
        },
        brand_kit={
            "style_guidance": "Use FrankHub pink tile references and real coffee scrub texture.",
            "negative_prompt": "No plastic skin, no generic spa props.",
            "reference_notes": "Prefer approved packaging references.",
        },
    )

    assert "FrankHub pink tile references" in payload["prompt"]
    assert "No plastic skin" in payload["prompt"]
    assert "Coffee scrub product hero." in payload["prompt"]


def test_google_request_uses_inline_refs_and_response_format_image_config(tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"fake-png-bytes")

    body = build_google_request(
        "Warm campaign image.",
        {"id": "google-nb-pro", "provider_model": "gemini-3-pro-image"},
        {"aspect_ratio": "4:5", "image_size": "4K", "thinking": "high"},
        [ref],
    )
    flash_body = build_google_request(
        "Warm campaign image.",
        {"id": "google-nb-2", "provider_model": "gemini-3.1-flash-image"},
        {"aspect_ratio": "4:5", "image_size": "4K", "thinking": "high"},
        [ref],
    )

    parts = body["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/png"
    assert parts[-1]["text"] == "Warm campaign image."
    assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert body["generationConfig"]["imageConfig"] == {"aspectRatio": "4:5", "imageSize": "4K"}
    assert "responseFormat" not in body["generationConfig"]
    assert "thinkingConfig" not in body["generationConfig"]
    assert "seed" not in body
    assert flash_body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "HIGH", "includeThoughts": False}


def test_provider_request_builders_map_shared_settings():
    settings = {"aspect_ratio": "16:9", "image_size": "2K", "count": 3}

    openai = build_openai_generation_request("Prompt", {"provider_model": "gpt-image-2"}, settings)
    replicate_preview = build_provider_request_preview(
        {"provider": "replicate", "provider_model": "black-forest-labs/flux-1.1-pro-ultra"},
        settings=settings,
    )

    assert openai["model"] == "gpt-image-2"
    assert openai["size"] == "2048x1152"
    assert replicate_preview["endpoint"] == "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro-ultra/predictions"
    assert replicate_preview["auth"] == "REPLICATE_API_TOKEN bearer header"
    assert replicate_preview["body_preview"]["input"]["num_outputs"] == 3
    assert replicate_preview["body_preview"]["input"]["aspect_ratio"] == "16:9"


def test_all_visible_ready_api_models_have_registered_live_adapters():
    ready_api_providers = {
        model["provider"]
        for model in get_visible_models()
        if model["provider"] != "local" and model["status"] == "ready"
    }

    assert ready_api_providers.issubset(provider_runner_keys())


def test_turn_payload_rejects_unsupported_model_settings_before_key_lookup(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(UnsupportedModelCapability, match="google-nb-2 does not support image size 8K"):
        build_turn_payload(
            {
                "model": "google-nb-2",
                "kind": "generate",
                "prompt": "Fast idea.",
                "settings": {"aspect_ratio": "1:1", "image_size": "8K", "count": 1},
            }
        )

    with pytest.raises(UnsupportedModelCapability, match="flux-1-1-pro-ultra does not support image size 8K"):
        build_turn_payload(
            {
                "model": "flux-1-1-pro-ultra",
                "kind": "generate",
                "prompt": "Experimental idea.",
                "settings": {"aspect_ratio": "4:5", "image_size": "8K", "count": 1},
            }
        )


def test_turn_payload_rejects_reference_count_above_model_limit(monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)

    with pytest.raises(UnsupportedModelCapability, match="flux-1-1-pro-ultra supports at most 4 reference images"):
        build_turn_payload(
            {
                "model": "flux-1-1-pro-ultra",
                "kind": "generate",
                "prompt": "Use too many references.",
                "settings": {"aspect_ratio": "1:1", "image_size": "4MP", "count": 1},
                "reference_asset_ids": ["a", "b", "c", "d", "e"],
            }
        )


def test_turn_payload_requires_source_for_edits_before_key_lookup(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(UnsupportedModelCapability, match="openai-gpt-image-2 edit requires a source asset"):
        build_turn_payload(
            {
                "model": "openai-gpt-image-2",
                "kind": "edit",
                "prompt": "Clean the label edge.",
                "settings": {"aspect_ratio": "1:1", "image_size": "1024", "count": 1},
            }
        )


def test_turn_payload_requires_source_and_mask_for_masked_edits_before_key_lookup(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(UnsupportedModelCapability, match="openai-gpt-image-2 masked edit requires a source asset"):
        build_turn_payload(
            {
                "model": "openai-gpt-image-2",
                "kind": "masked_edit",
                "prompt": "Retouch only the masked label edge.",
                "settings": {"aspect_ratio": "1:1", "image_size": "1024", "count": 1},
                "mask_asset_id": "asset-mask",
            }
        )

    with pytest.raises(UnsupportedModelCapability, match="openai-gpt-image-2 masked edit requires a mask asset"):
        build_turn_payload(
            {
                "model": "openai-gpt-image-2",
                "kind": "masked_edit",
                "prompt": "Retouch only the masked label edge.",
                "settings": {"aspect_ratio": "1:1", "image_size": "1024", "count": 1},
                "edit_source_asset_id": "asset-source",
            }
        )


def test_turn_payload_rejects_non_video_models_before_key_lookup(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(UnsupportedModelCapability, match="google-nb-pro does not support video"):
        build_turn_payload(
            {
                "model": "google-nb-pro",
                "kind": "video",
                "prompt": "Make a motion board from this pick.",
                "settings": {"aspect_ratio": "16:9", "image_size": "1K", "count": 1},
                "source_asset_id": "asset-source",
            }
        )


def test_turn_payload_allows_local_video_storyboard_without_key_lookup(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    provider_payload = build_turn_payload(
        {
            "model": "frank-local-comfy",
            "kind": "video",
            "prompt": "Make a simple Frank motion board.",
            "settings": {"aspect_ratio": "16:9", "image_size": "1K", "count": 1},
        }
    )

    assert provider_payload["provider"] == "local"
    assert provider_payload["capabilities"]["video"] is True


def test_turn_payload_carries_mask_asset_for_provider_adapter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai")

    provider_payload = build_turn_payload(
        {
            "model": "openai-gpt-image-2",
            "kind": "masked_edit",
            "prompt": "Retouch only the masked label edge.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1024", "count": 1},
            "edit_source_asset_id": "asset-source",
            "mask_asset_id": "asset-mask",
        }
    )

    assert provider_payload["edit_source_asset_id"] == "asset-source"
    assert provider_payload["mask_asset_id"] == "asset-mask"
    assert "server-side-openai" not in str(provider_payload)
