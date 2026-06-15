import requests
import base64
from io import BytesIO

import pytest
from custom_nodes.frank_create import provider_adapters
from custom_nodes.frank_create.inference import MissingProviderKey, require_provider_key
from custom_nodes.frank_create.models import get_model
from custom_nodes.frank_create.provider_adapters import run_live_provider_turn
from custom_nodes.frank_create.store import FrankCreateStore
from PIL import Image


def _turn(store, model_id="google-nb-pro"):
    session = store.create_session({"name": "Provider failure QA"})
    model = get_model(model_id)
    return store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": model["provider"],
            "model": model["id"],
            "prompt": "Clean product image.",
            "status": "queued",
        }
    )


def _png_bytes(width=32, height=24):
    buffer = BytesIO()
    Image.new("RGB", (width, height), (248, 230, 230)).save(buffer, "PNG")
    return buffer.getvalue()


def test_live_provider_runners_are_limited_to_three_key_app_boundary():
    assert provider_adapters.provider_runner_keys() == {"google", "openai", "replicate"}


def test_provider_key_gate_ignores_placeholder_env_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "YOUR_KEY_HERE")

    try:
        require_provider_key("openai-gpt-image-2")
    except MissingProviderKey as exc:
        assert exc.env_vars == ["OPENAI_API_KEY"]
    else:
        raise AssertionError("Expected placeholder provider key to be treated as missing")

    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai")
    assert require_provider_key("openai-gpt-image-2") == "server-side-openai"


def test_live_provider_runner_redacts_secret_values_from_uncaught_errors(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store)
    model = get_model("google-nb-pro")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-secret-123")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-456")

    def failing_runner(*_args):
        raise RuntimeError("request failed https://example.test/v1?key=AIza-secret-123 with Bearer sk-secret-456")

    monkeypatch.setattr(provider_adapters, "_provider_runners", lambda: {"google": failing_runner})

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"count": 1}},
        model,
        {"prompt": "Clean product image."},
    )

    assert assets == []
    assert updated_turn["status"] == "failed"
    assert "AIza-secret-123" not in updated_turn["error_json"]
    assert "sk-secret-456" not in updated_turn["error_json"]
    assert "[redacted]" in updated_turn["error_json"]


def test_google_adapter_redacts_secret_values_from_caught_request_errors(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store)
    model = get_model("google-nb-pro")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-secret-123")

    def failing_post(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("GET https://google.test?key=AIza-secret-123 failed")

    monkeypatch.setattr(provider_adapters.requests, "post", failing_post)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1}, "reference_asset_ids": []},
        model,
        {"prompt": "Clean product image."},
    )

    assert assets == []
    assert updated_turn["status"] == "failed"
    assert "AIza-secret-123" not in updated_turn["error_json"]
    assert "key=[redacted]" in updated_turn["error_json"]


def test_google_adapter_uses_current_v1beta_endpoint_and_header_key(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="google-nb-2")
    model = get_model("google-nb-2")
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(b"google-output").decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        captured["headers"] = kwargs.get("headers")
        captured["body"] = kwargs.get("json")
        return FakeResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "1:1", "image_size": "4K", "count": 1}, "reference_asset_ids": []},
        model,
        {"prompt": "Clean product image."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent"
    assert captured["params"] is None
    assert captured["headers"]["x-goog-api-key"] == "server-side-google"
    assert captured["body"]["generationConfig"]["imageConfig"] == {
        "aspectRatio": "1:1",
        "imageSize": "4K",
    }
    assert "seed" not in captured["body"]


def test_google_edit_adapter_sends_source_image_as_inline_data(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source_path = media_root / "input" / "frank_create" / "source.png"
    source_path.parent.mkdir(parents=True)
    source_bytes = _png_bytes(41, 31)
    source_path.write_bytes(source_bytes)
    output_bytes = _png_bytes(53, 47)

    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "Google edit path QA"})
    source_asset = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Source pack shot",
            "media_type": "image",
            "provider": "upload",
            "model": "uploaded",
            "file_path": "input/frank_create/source.png",
            "preview_url": "/api/view?filename=source.png&subfolder=frank_create&type=input",
            "width": 41,
            "height": 31,
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "edit",
            "provider": "google",
            "model": "google-nb-pro",
            "prompt": "Keep the label sharp and add pink bathroom tile.",
            "source_asset_id": source_asset["id"],
            "status": "queued",
        }
    )
    model = get_model("google-nb-pro")
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(output_bytes).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["body"] = kwargs.get("json")
        return FakeResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {
            "kind": "edit",
            "settings": {"aspect_ratio": "4:5", "image_size": "4K", "count": 1},
            "edit_source_asset_id": source_asset["id"],
            "reference_asset_ids": [],
        },
        model,
        {"prompt": "Keep the label sharp and add pink bathroom tile."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert assets[0]["provider"] == "google"
    assert assets[0]["model"] == "google-nb-pro"
    assert assets[0]["source_asset_id"] == source_asset["id"]
    assert assets[0]["width"] == 53
    assert assets[0]["height"] == 47
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image:generateContent"
    assert captured["headers"] == {"x-goog-api-key": "server-side-google", "Content-Type": "application/json"}
    parts = captured["body"]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/png"
    assert parts[0]["inlineData"]["data"] == base64.b64encode(source_bytes).decode("ascii")
    assert parts[-1]["text"] == "Keep the label sharp and add pink bathroom tile."
    assert "thinkingConfig" not in captured["body"]["generationConfig"]


def test_google_adapter_retries_minimal_payload_when_generation_config_is_rejected(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="google-nb-pro")
    model = get_model("google-nb-pro")
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")
    image_bytes = _png_bytes(29, 31)
    captured_bodies = []

    class BadConfigResponse:
        status_code = 400

        def json(self):
            return {
                "error": {
                    "code": 400,
                    "message": (
                        'Invalid JSON payload received. Unknown name "responseModalities" at '
                        "'generation_config': Cannot find field. Invalid JSON payload received. "
                        'Unknown name "responseFormat" at '
                        "'generation_config': Cannot find field. Invalid JSON payload received. "
                        'Unknown name "thinkingConfig" at '
                        "'generation_config': Cannot find field. Invalid JSON payload received. "
                        'Unknown name "seed": Cannot find field.'
                    ),
                    "status": "INVALID_ARGUMENT",
                }
            }

    class GoodMinimalResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(image_bytes).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(_url, **kwargs):
        captured_bodies.append(kwargs.get("json"))
        return BadConfigResponse() if len(captured_bodies) == 1 else GoodMinimalResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "4:5", "image_size": "4K", "count": 1}, "reference_asset_ids": []},
        model,
        {"prompt": "Clean product image."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert len(captured_bodies) == 2
    assert "generationConfig" in captured_bodies[0]
    assert "seed" not in captured_bodies[0]
    assert "generationConfig" not in captured_bodies[1]
    assert captured_bodies[1]["contents"][0]["parts"] == captured_bodies[0]["contents"][0]["parts"]


def test_google_adapter_retries_minimal_payload_when_generation_config_values_are_rejected(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="google-nb-pro")
    model = get_model("google-nb-pro")
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")
    image_bytes = _png_bytes(31, 29)
    captured_bodies = []

    class BadConfigValueResponse:
        status_code = 400

        def json(self):
            return {
                "error": {
                    "code": 400,
                    "message": (
                        "Invalid value at 'generation_config.response_format.image.aspect_ratio' "
                        '(type.googleapis.com/google.ai.generativelanguage.v1beta.ImageResponseFormat.AspectRatio), "1:1"\n'
                        "Invalid value at 'generation_config.response_format.image.image_size' "
                        '(type.googleapis.com/google.ai.generativelanguage.v1beta.ImageResponseFormat.ImageSize), "1K"'
                    ),
                    "status": "INVALID_ARGUMENT",
                }
            }

    class GoodMinimalResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(image_bytes).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    def fake_post(_url, **kwargs):
        captured_bodies.append(kwargs.get("json"))
        return BadConfigValueResponse() if len(captured_bodies) == 1 else GoodMinimalResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1}, "reference_asset_ids": []},
        model,
        {"prompt": "Clean product image."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert len(captured_bodies) == 2
    assert "generationConfig" in captured_bodies[0]
    assert "generationConfig" not in captured_bodies[1]


def test_live_provider_image_asset_records_downloaded_dimensions(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("GOOGLE_API_KEY", "server-side-google")
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="google-nb-pro")
    model = get_model("google-nb-pro")
    image_bytes = _png_bytes(37, 29)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(image_bytes).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    monkeypatch.setattr(provider_adapters.requests, "post", lambda *_args, **_kwargs: FakeResponse())

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1}, "reference_asset_ids": []},
        model,
        {"prompt": "Clean product image."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert assets[0]["width"] == 37
    assert assets[0]["height"] == 29


@pytest.mark.skip(reason="legacy Ideogram provider is outside the three-key app boundary")
def test_ideogram_v4_adapter_uses_multipart_text_prompt_and_loops_count(tmp_path, monkeypatch):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="ideogram-v4-quality")
    model = get_model("ideogram-v4-quality")
    monkeypatch.setenv("IDEOGRAM_API_KEY", "server-side-ideogram")
    captured_posts = []

    class FakePostResponse:
        status_code = 200

        def __init__(self, index):
            self.index = index

        def json(self):
            return {
                "response_type": "url",
                "created": "2026-06-08T00:00:00Z",
                "data": [
                    {
                        "prompt": "Clean product image.",
                        "resolution": "1792x2240",
                        "is_image_safe": True,
                        "seed": self.index,
                        "url": f"https://ideogram.test/output-{self.index}.png",
                    }
                ],
            }

    class FakeGetResponse:
        headers = {"content-type": "image/png"}
        content = b"ideogram-output"

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured_posts.append(
            {
                "url": url,
                "headers": kwargs.get("headers"),
                "files": kwargs.get("files"),
                "json": kwargs.get("json"),
                "data": kwargs.get("data"),
            }
        )
        return FakePostResponse(len(captured_posts))

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", lambda *_args, **_kwargs: FakeGetResponse())

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "4:5", "image_size": "2K", "count": 3}, "reference_asset_ids": []},
        model,
        {"prompt": "Clean product image."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 3
    assert len(captured_posts) == 3
    for post in captured_posts:
        assert post["url"] == "https://api.ideogram.ai/v1/ideogram-v4/generate"
        assert post["headers"] == {"Api-Key": "server-side-ideogram"}
        assert post["json"] is None
        assert post["data"] is None
        assert post["files"] == {
            "text_prompt": (None, "Clean product image."),
            "resolution": (None, "1792x2240"),
            "rendering_speed": (None, "DEFAULT"),
        }


def test_provider_request_preview_redacts_prompt_and_declares_auth_shape():
    openai = provider_adapters.build_provider_request_preview(
        get_model("openai-gpt-image-2"),
        "generate",
        {"aspect_ratio": "1:1", "image_size": "4096", "count": 2},
    )
    google = provider_adapters.build_provider_request_preview(
        get_model("google-nb-pro"),
        "generate",
        {"aspect_ratio": "4:5", "image_size": "4K", "count": 1},
    )
    replicate = provider_adapters.build_provider_request_preview(
        get_model("flux-1-1-pro-ultra"),
        "generate",
        {"aspect_ratio": "4:5", "image_size": "4MP", "count": 1},
    )

    assert openai["endpoint"] == "https://api.openai.com/v1/images/generations"
    assert openai["auth"] == "Authorization bearer header"
    assert openai["body_preview"]["prompt"] == "<composed prompt>"
    assert google["endpoint"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image:generateContent"
    assert google["body_preview"]["contents"][0]["parts"][0]["text"] == "<composed prompt>"
    assert replicate["endpoint"] == "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro-ultra/predictions"
    assert replicate["auth"] == "REPLICATE_API_TOKEN bearer header"
    assert replicate["body_preview"]["input"]["prompt"] == "<composed prompt>"
    assert "server-side" not in str(openai)
    assert "server-side" not in str(google)
    assert "server-side" not in str(replicate)


@pytest.mark.skip(reason="legacy Recraft provider is outside the three-key app boundary")
def test_recraft_generation_adapter_creates_review_assets(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("RECRAFT_API_KEY", "server-side-recraft")

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="recraft-v4-pro")
    model = get_model("recraft-v4-pro")
    captured = {}

    class FakePostResponse:
        status_code = 200

        def json(self):
            return {"data": [{"url": "https://recraft.test/output-1.png"}, {"url": "https://recraft.test/output-2.png"}]}

    class FakeGetResponse:
        headers = {"content-type": "image/png"}
        content = _png_bytes(40, 50)

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return FakePostResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", lambda *_args, **_kwargs: FakeGetResponse())

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "16:9", "image_size": "4MP", "count": 2}, "reference_asset_ids": []},
        model,
        {"prompt": "Design-grade Frank Body product campaign."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 2
    assert {asset["provider"] for asset in assets} == {"recraft"}
    assert [asset["width"] for asset in assets] == [40, 40]
    assert captured["url"] == "https://external.api.recraft.ai/v1/images/generations"
    assert captured["headers"] == {"Authorization": "Bearer server-side-recraft", "Content-Type": "application/json"}
    assert captured["json"] == {
        "prompt": "Design-grade Frank Body product campaign.",
        "model": "recraftv4_1_pro",
        "n": 2,
        "size": "2688x1536",
    }


@pytest.mark.skip(reason="legacy fal.ai provider is outside the three-key app boundary")
def test_fal_flux_direct_adapter_creates_review_assets(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("FAL_KEY", "server-side-fal")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "server-side-replicate")

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="flux-1-1-pro-ultra")
    model = get_model("flux-1-1-pro-ultra")
    captured = {}

    class FakePostResponse:
        status_code = 200

        def json(self):
            return {"images": [{"url": "https://fal.test/flux-1.png"}, {"url": "https://fal.test/flux-2.png"}]}

    class FakeGetResponse:
        headers = {"content-type": "image/png"}
        content = _png_bytes(64, 48)

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return FakePostResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", lambda *_args, **_kwargs: FakeGetResponse())

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "4:5", "image_size": "4MP", "count": 2}, "reference_asset_ids": []},
        model,
        {"prompt": "Photoreal Frank Body product scene."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 2
    assert {asset["provider"] for asset in assets} == {"fal"}
    assert [asset["height"] for asset in assets] == [48, 48]
    assert captured["url"] == "https://fal.run/fal-ai/flux-pro/v1.1-ultra"
    assert captured["headers"] == {"Authorization": "Key server-side-fal", "Content-Type": "application/json"}
    assert captured["json"] == {
        "prompt": "Photoreal Frank Body product scene.",
        "num_images": 2,
        "aspect_ratio": "4:5",
        "raw": False,
        "enable_safety_checker": True,
        "output_format": "png",
    }


def test_replicate_flux_fallback_loops_requested_variant_count(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("REPLICATE_API_TOKEN", "server-side-replicate")

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    turn = _turn(store, model_id="flux-1-1-pro-ultra")
    model = get_model("flux-1-1-pro-ultra")
    captured_posts = []

    class FakePostResponse:
        status_code = 200

        def __init__(self, index):
            self.index = index

        def json(self):
            return {"status": "succeeded", "output": f"https://replicate.test/flux-{self.index}.png"}

    class FakeGetResponse:
        headers = {"content-type": "image/png"}
        content = _png_bytes(24, 24)

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured_posts.append({"url": url, "headers": kwargs.get("headers"), "json": kwargs.get("json")})
        return FakePostResponse(len(captured_posts))

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", lambda *_args, **_kwargs: FakeGetResponse())

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {"settings": {"aspect_ratio": "4:5", "image_size": "4MP", "count": 3}, "reference_asset_ids": []},
        model,
        {"prompt": "Photoreal product campaign."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 3
    assert len(captured_posts) == 3
    assert [post["json"]["input"]["seed"] for post in captured_posts] == [42, 43, 44]
    expected_auth_header = f"Bearer {'server-side-replicate'}"
    for post in captured_posts:
        assert post["url"] == "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro-ultra/predictions"
        assert post["headers"]["Authorization"] == expected_auth_header
        assert post["headers"]["Prefer"] == "wait=60"
        assert post["json"]["input"]["prompt"] == "Photoreal product campaign."
        assert post["json"]["input"]["aspect_ratio"] == "4:5"


@pytest.mark.skip(reason="legacy xAI video provider is outside the three-key app boundary")
@pytest.mark.skip(reason="legacy xAI provider is outside the three-key app boundary")
def test_xai_video_adapter_creates_image_to_video_asset(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source_path = media_root / "output" / "frank_create" / "source.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source-png")
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("XAI_API_KEY", "server-side-xai")

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "xAI Video QA", "mode": "video"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved source",
            "media_type": "image",
            "file_path": "output/frank_create/source.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "video",
            "provider": "xai",
            "model": "grok-imagine-quality",
            "prompt": "Subtle product rotation and texture shimmer.",
            "status": "queued",
        }
    )
    captured = {"post": None, "polls": []}

    class FakePostResponse:
        status_code = 200

        def json(self):
            return {"request_id": "video-request-123"}

    class FakePollResponse:
        status_code = 200

        def json(self):
            return {"status": "done", "video": {"url": "https://xai.test/video.mp4"}}

    class FakeVideoResponse:
        headers = {"content-type": "video/mp4"}
        content = b"mp4-output"

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["post"] = {"url": url, "headers": kwargs.get("headers"), "json": kwargs.get("json")}
        return FakePostResponse()

    def fake_get(url, **kwargs):
        if url == "https://api.x.ai/v1/videos/video-request-123":
            captured["polls"].append({"url": url, "headers": kwargs.get("headers")})
            return FakePollResponse()
        if url == "https://xai.test/video.mp4":
            return FakeVideoResponse()
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", fake_get)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {
            "kind": "video",
            "settings": {"aspect_ratio": "16:9", "image_size": "2K", "count": 1, "duration": 6},
            "source_asset_id": source["id"],
            "reference_asset_ids": [],
        },
        get_model("grok-imagine-quality"),
        {"prompt": "Subtle product rotation and texture shimmer."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert assets[0]["kind"] == "video"
    assert assets[0]["media_type"] == "video"
    assert assets[0]["provider"] == "xai"
    assert assets[0]["file_path"].endswith(".mp4")
    assert (media_root / assets[0]["file_path"]).read_bytes() == b"mp4-output"
    assert captured["post"]["url"] == "https://api.x.ai/v1/videos/generations"
    assert captured["post"]["headers"] == {"Authorization": "Bearer server-side-xai", "Content-Type": "application/json"}
    assert captured["post"]["json"]["model"] == "grok-imagine-video"
    assert captured["post"]["json"]["prompt"] == "Subtle product rotation and texture shimmer."
    assert captured["post"]["json"]["duration"] == 6
    assert captured["post"]["json"]["image"]["url"].startswith("data:image/png;base64,")
    assert captured["polls"] == [
        {"url": "https://api.x.ai/v1/videos/video-request-123", "headers": {"Authorization": "Bearer server-side-xai"}}
    ]


@pytest.mark.skip(reason="legacy Runway provider is outside the three-key app boundary")
def test_runway_gen45_video_adapter_creates_image_to_video_asset(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source_path = media_root / "output" / "frank_create" / "source.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(_png_bytes(40, 30))
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("RUNWAYML_API_SECRET", "server-side-runway")

    model = get_model("runway-gen45-video")
    preview = provider_adapters.build_provider_request_preview(
        model,
        "video",
        {"aspect_ratio": "16:9", "image_size": "720p", "count": 1, "duration": 5},
    )
    assert preview["endpoint"] == "https://api.dev.runwayml.com/v1/image_to_video"
    assert preview["auth"] == "Authorization bearer header + X-Runway-Version"
    assert preview["body_preview"]["model"] == "gen4.5"
    assert preview["body_preview"]["promptImage"] == "<source image data url>"
    assert preview["body_preview"]["promptText"] == "<composed prompt>"
    assert preview["body_preview"]["ratio"] == "1280:720"
    assert preview["body_preview"]["duration"] == 5

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "Runway Video QA", "mode": "video"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved source",
            "media_type": "image",
            "file_path": "output/frank_create/source.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "video",
            "provider": "runway",
            "model": "runway-gen45-video",
            "prompt": "Subtle product tilt, glossy texture catchlight, Frank pink set.",
            "status": "queued",
        }
    )
    captured = {"post": None, "polls": []}

    class FakePostResponse:
        status_code = 200

        def json(self):
            return {"id": "runway-task-123"}

    class FakePollResponse:
        status_code = 200

        def json(self):
            return {"status": "SUCCEEDED", "output": ["https://runway.test/video.mp4"]}

    class FakeVideoResponse:
        headers = {"content-type": "video/mp4"}
        content = b"runway-mp4-output"

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["post"] = {"url": url, "headers": kwargs.get("headers"), "json": kwargs.get("json")}
        return FakePostResponse()

    def fake_get(url, **kwargs):
        if url == "https://api.dev.runwayml.com/v1/tasks/runway-task-123":
            captured["polls"].append({"url": url, "headers": kwargs.get("headers")})
            return FakePollResponse()
        if url == "https://runway.test/video.mp4":
            return FakeVideoResponse()
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", fake_get)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {
            "kind": "video",
            "settings": {"aspect_ratio": "16:9", "image_size": "720p", "count": 1, "duration": 5},
            "source_asset_id": source["id"],
            "reference_asset_ids": [],
        },
        model,
        {"prompt": "Subtle product tilt, glossy texture catchlight, Frank pink set."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert assets[0]["kind"] == "video"
    assert assets[0]["media_type"] == "video"
    assert assets[0]["provider"] == "runway"
    assert assets[0]["model"] == "runway-gen45-video"
    assert assets[0]["file_path"].endswith(".mp4")
    assert (media_root / assets[0]["file_path"]).read_bytes() == b"runway-mp4-output"
    assert captured["post"]["url"] == "https://api.dev.runwayml.com/v1/image_to_video"
    assert captured["post"]["headers"] == {
        "Authorization": "Bearer server-side-runway",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }
    assert captured["post"]["json"]["model"] == "gen4.5"
    assert captured["post"]["json"]["promptText"] == "Subtle product tilt, glossy texture catchlight, Frank pink set."
    assert captured["post"]["json"]["ratio"] == "1280:720"
    assert captured["post"]["json"]["duration"] == 5
    assert captured["post"]["json"]["promptImage"].startswith("data:image/png;base64,")
    assert captured["polls"] == [
        {
            "url": "https://api.dev.runwayml.com/v1/tasks/runway-task-123",
            "headers": {"Authorization": "Bearer server-side-runway", "X-Runway-Version": "2024-11-06"},
        }
    ]


@pytest.mark.skip(reason="legacy xAI image provider is outside the three-key app boundary")
@pytest.mark.skip(reason="legacy xAI provider is outside the three-key app boundary")
def test_xai_edit_adapter_sends_source_image_and_creates_review_asset(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source_path = media_root / "output" / "frank_create" / "source.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(_png_bytes(21, 22))
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("XAI_API_KEY", "server-side-xai")

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "xAI Edit QA"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Source",
            "media_type": "image",
            "file_path": "output/frank_create/source.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "edit",
            "provider": "xai",
            "model": "grok-imagine-quality",
            "prompt": "Clean the product label and keep packaging honest.",
            "status": "queued",
        }
    )
    captured = {}

    class FakePostResponse:
        status_code = 200

        def json(self):
            return {"data": [{"url": "https://xai.test/edit-output.png"}]}

    class FakeGetResponse:
        headers = {"content-type": "image/png"}
        content = _png_bytes(31, 32)

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return FakePostResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)
    monkeypatch.setattr(provider_adapters.requests, "get", lambda *_args, **_kwargs: FakeGetResponse())

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {
            "kind": "edit",
            "settings": {"aspect_ratio": "1:1", "image_size": "2K", "count": 1},
            "edit_source_asset_id": source["id"],
            "reference_asset_ids": [],
        },
        get_model("grok-imagine-quality"),
        {"prompt": "Clean the product label and keep packaging honest."},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert assets[0]["provider"] == "xai"
    assert assets[0]["width"] == 31
    assert assets[0]["height"] == 32
    assert captured["url"] == "https://api.x.ai/v1/images/edits"
    assert captured["headers"] == {"Authorization": "Bearer server-side-xai", "Content-Type": "application/json"}
    assert captured["json"]["model"] == "grok-imagine-image-quality"
    assert captured["json"]["prompt"] == "Clean the product label and keep packaging honest."
    assert captured["json"]["size"] == "2K"
    assert captured["json"]["image"]["type"] == "image_url"
    assert captured["json"]["image"]["url"].startswith("data:image/png;base64,")


def test_openai_masked_edit_attaches_mask_file_separately(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source_path = media_root / "input" / "frank_create" / "source.png"
    mask_path = media_root / "input" / "frank_create" / "mask.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source-png")
    mask_path.write_bytes(b"mask-png")
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai")

    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "Masked edit QA"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Source",
            "file_path": "input/frank_create/source.png",
        }
    )
    mask = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "mask",
            "title": "Mask",
            "file_path": "input/frank_create/mask.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "masked_edit",
            "provider": "openai",
            "model": "openai-gpt-image-2",
            "prompt": "Retouch only the masked edge.",
            "status": "queued",
        }
    )
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {"data": [{"b64_json": base64.b64encode(b"masked-output").decode("ascii")}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["files"] = [(name, file_tuple[0], file_tuple[2]) for name, file_tuple in kwargs.get("files", [])]
        return FakeResponse()

    monkeypatch.setattr(provider_adapters.requests, "post", fake_post)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {
            "kind": "masked_edit",
            "settings": {"aspect_ratio": "1:1", "image_size": "1024", "count": 1},
            "edit_source_asset_id": source["id"],
            "mask_asset_id": mask["id"],
            "reference_asset_ids": [],
        },
        get_model("openai-gpt-image-2"),
        {"prompt": "Retouch only the masked edge.", "mask_asset_id": mask["id"]},
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert captured["url"] == "https://api.openai.com/v1/images/edits"
    assert captured["data"]["model"] == "gpt-image-2"
    assert ("image[]", "source.png", "image/png") in captured["files"]
    assert ("mask", "mask.png", "image/png") in captured["files"]


def test_openai_edit_fails_when_source_asset_is_not_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-side-openai")
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "Missing source edit QA"})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "edit",
            "provider": "openai",
            "model": "openai-gpt-image-2",
            "prompt": "Clean the label edge.",
            "status": "queued",
        }
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Provider request should not be sent without a readable edit source")

    monkeypatch.setattr(provider_adapters.requests, "post", fail_if_called)

    updated_turn, assets = run_live_provider_turn(
        store,
        turn,
        {
            "kind": "edit",
            "settings": {"aspect_ratio": "1:1", "image_size": "1024", "count": 1},
            "edit_source_asset_id": "asset-does-not-exist",
            "reference_asset_ids": [],
        },
        get_model("openai-gpt-image-2"),
        {"prompt": "Clean the label edge."},
    )

    assert assets == []
    assert updated_turn["status"] == "failed"
    assert "readable source asset" in updated_turn["error_json"]
