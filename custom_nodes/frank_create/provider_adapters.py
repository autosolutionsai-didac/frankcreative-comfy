import base64
import mimetypes
import os
import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

from .inference import require_provider_key
from .local_image import dimensions_for, _output_dir, _resolve_media_path, _view_url


class ProviderAdapterError(RuntimeError):
    pass


PROVIDER_SECRET_ENV_VARS = (
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "REPLICATE_API_TOKEN",
)

SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:key|api_key|api-key|token|access_token|access-token|client_secret|client-secret)=)[^&\s\"']+"
)
BEARER_SECRET_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:api[_-]?key|token|access[_-]?token|client[_-]?secret|authorization)\s*[:=]\s*)[^\s,;\"']+"
)


def provider_runner_keys():
    return set(_provider_runners().keys())


def _provider_runners():
    return {
        "google": _run_google_turn,
        "openai": _run_openai_turn,
        "replicate": _run_replicate_flux_turn,
    }


def run_live_provider_turn(store, turn, payload, model, provider_payload):
    runners = _provider_runners()
    runner = runners.get(model["provider"])
    if not runner:
        updated_turn = store.update_turn(
            turn["id"],
            {
                "status": "blocked",
                "error": {
                    "code": "adapter_not_ready",
                    "message": f"{model['provider']} adapter is registered but not live yet.",
                },
            },
        )
        return updated_turn, []

    try:
        return runner(store, turn, payload, model, provider_payload)
    except Exception as exc:
        updated_turn = store.update_turn(
            turn["id"],
            {"status": "failed", "error": {"code": "provider_error", "message": _safe_error_message(exc)}},
        )
        return updated_turn, []


def build_google_request(prompt, model, settings, image_paths, include_generation_config=True):
    parts = []
    for path in image_paths:
        parts.append({"inlineData": _inline_data(path)})
    parts.append({"text": prompt})

    request = {"contents": [{"role": "user", "parts": parts}]}
    if include_generation_config:
        generation_config = {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": settings.get("aspect_ratio", "1:1"),
                "imageSize": settings.get("image_size", "1K"),
            },
        }
        if model.get("provider_model") == "gemini-3.1-flash-image" and settings.get("thinking") == "high":
            generation_config["thinkingConfig"] = {
                "thinkingLevel": "HIGH",
                "includeThoughts": False,
            }
        request["generationConfig"] = generation_config

    return request


def build_openai_generation_request(prompt, model, settings):
    return {
        "model": model["provider_model"],
        "prompt": prompt,
        "n": max(1, min(int(settings.get("count") or 1), 4)),
        "size": _size_for_settings(settings),
    }


def build_replicate_flux_generation_request(prompt, settings):
    return {
        "input": {
            "prompt": prompt,
            "num_outputs": max(1, min(int(settings.get("count") or 1), 4)),
            "aspect_ratio": settings.get("aspect_ratio", "1:1"),
            "output_format": "png",
        }
    }


def build_provider_request_preview(model, kind="generate", settings=None):
    """Build a no-spend, no-secret preview of the live adapter request shape."""
    settings = dict(settings or {})
    prompt = "<composed prompt>"
    provider = model["provider"]

    if provider == "local":
        return {
            "method": "LOCAL",
            "endpoint": "ComfyUI prompt queue or Frank local fallback",
            "auth": "none",
            "content_type": "workflow/json",
            "body_preview": {
                "model": model["provider_model"],
                "kind": kind,
                "settings": settings,
            },
        }

    if provider == "google":
        return {
            "method": "POST",
            "endpoint": _google_generate_url(model),
            "auth": "x-goog-api-key header",
            "content_type": "application/json",
            "body_preview": _scrub_preview_body(build_google_request(prompt, model, settings, [])),
        }

    if provider == "openai":
        if kind in {"edit", "masked_edit"}:
            files = ["image[]"]
            if kind == "masked_edit":
                files.append("mask")
            return {
                "method": "POST",
                "endpoint": "https://api.openai.com/v1/images/edits",
                "auth": "Authorization bearer header",
                "content_type": "multipart/form-data",
                "body_preview": {
                    "model": model["provider_model"],
                    "prompt": prompt,
                    "n": str(max(1, min(int(settings.get("count") or 1), 4))),
                    "size": _size_for_settings(settings),
                    "files": files,
                },
            }
        return {
            "method": "POST",
            "endpoint": "https://api.openai.com/v1/images/generations",
            "auth": "Authorization bearer header",
            "content_type": "application/json",
            "body_preview": _scrub_preview_body(build_openai_generation_request(prompt, model, settings)),
        }

    if provider == "replicate":
        return {
            "method": "POST",
            "endpoint": f"https://api.replicate.com/v1/models/{model['provider_model']}/predictions",
            "auth": "REPLICATE_API_TOKEN bearer header",
            "content_type": "application/json",
            "body_preview": _scrub_preview_body(build_replicate_flux_generation_request(prompt, settings)),
        }

    raise ProviderAdapterError(f"{provider} adapter is not registered.")


def _run_google_turn(store, turn, payload, model, provider_payload):
    api_key = require_provider_key(model["id"])
    settings = payload.get("settings") or {}
    count = max(1, min(int(settings.get("count") or 1), 4))
    if payload.get("kind") == "edit" and not _source_path_for_payload(store, payload):
        raise ProviderAdapterError("Edit requires a readable source asset.")
    image_paths = _image_paths_for_payload(store, payload)
    outputs = []
    errors = []
    url = _google_generate_url(model)

    for index in range(count):
        body = build_google_request(provider_payload["prompt"], model, settings, image_paths)
        try:
            response, data = _post_google_generate(url, api_key, body)
            if response.status_code >= 400 and _is_google_generation_config_error(data):
                response, data = _post_google_generate(url, api_key, _minimal_google_request(body))
        except Exception as exc:
            errors.append(_safe_error_message(exc))
            continue

        if response.status_code >= 400 or data.get("error"):
            errors.append(_error_message(data, response.status_code, "Google"))
            continue

        image_part = _first_image_part(data)
        if not image_part:
            errors.append("Google returned no image part.")
            continue

        outputs.append(_bytes_output(base64.b64decode(image_part["data"]), image_part["mimeType"], f"google_{index + 1:02d}"))

    return _finish_provider_outputs(store, turn, payload, model, provider_payload, outputs, errors)


def _post_google_generate(url, api_key, body):
    response = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=180,
    )
    try:
        data = response.json()
    except Exception:
        data = {}
    return response, data


def _google_generate_url(model):
    api_version = model.get("provider_api_version") or "v1"
    return f"https://generativelanguage.googleapis.com/{api_version}/models/{model['provider_model']}:generateContent"


def _minimal_google_request(body):
    return {"contents": body.get("contents") or []}


def _is_google_generation_config_error(data):
    error = data.get("error") if isinstance(data, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    text = str(message or "")
    unknown_field_error = (
        "Invalid JSON payload" in text
        and "Cannot find field" in text
        and any(
            field in text
            for field in (
                '"responseModalities"',
                '"responseFormat"',
                '"thinkingConfig"',
                '"imageConfig"',
                '"seed"',
            )
        )
    )
    invalid_config_value = (
        "Invalid value at" in text
        and any(
            path in text
            for path in (
                "generation_config.response_format",
                "generation_config.image_config",
                "generation_config.thinking_config",
            )
        )
    )
    return unknown_field_error or invalid_config_value


def _run_openai_turn(store, turn, payload, model, provider_payload):
    api_key = require_provider_key(model["id"])
    settings = payload.get("settings") or {}
    image_paths = _image_paths_for_payload(store, payload)
    headers = {"Authorization": f"Bearer {api_key}"}

    if payload.get("kind") in {"edit", "masked_edit"}:
        if not _source_path_for_payload(store, payload):
            raise ProviderAdapterError("Edit requires a readable source asset.")
        data = {
            "model": model["provider_model"],
            "prompt": provider_payload["prompt"],
            "n": str(max(1, min(int(settings.get("count") or 1), 4))),
            "size": _size_for_settings(settings),
        }
        files = [("image[]", (Path(path).name, Path(path).open("rb"), mimetypes.guess_type(str(path))[0] or "image/png")) for path in image_paths[:10]]
        mask_path = _mask_path_for_payload(store, payload)
        if payload.get("kind") == "masked_edit":
            if not mask_path:
                raise ProviderAdapterError("Masked edit requires a readable mask asset.")
            files.append(("mask", (Path(mask_path).name, Path(mask_path).open("rb"), mimetypes.guess_type(str(mask_path))[0] or "image/png")))
        try:
            response = requests.post("https://api.openai.com/v1/images/edits", headers=headers, data=data, files=files, timeout=180)
        finally:
            for _, file_tuple in files:
                file_tuple[1].close()
    else:
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={**headers, "Content-Type": "application/json"},
            json=build_openai_generation_request(provider_payload["prompt"], model, settings),
            timeout=180,
        )

    data = _json_or_error(response, "OpenAI")
    outputs = _outputs_from_openai_like(data, "openai")
    return _finish_provider_outputs(store, turn, payload, model, provider_payload, outputs, [])


def _run_replicate_flux_turn(store, turn, payload, model, provider_payload):
    api_key = require_provider_key(model["id"])
    settings = payload.get("settings") or {}
    count = max(1, min(int(settings.get("count") or 1), 4))
    outputs = []
    for index in range(count):
        body = {
            "input": {
                "prompt": provider_payload["prompt"],
                "aspect_ratio": settings.get("aspect_ratio", "1:1"),
                "output_format": "png",
                "safety_tolerance": 2,
                "raw": False,
                "seed": 42 + index,
            }
        }
        response = requests.post(
            "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro-ultra/predictions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait=60",
            },
            json=body,
            timeout=120,
        )
        data = _json_or_error(response, "Replicate")
        if data.get("status") not in {"succeeded", "failed", "canceled"} and data.get("urls", {}).get("get"):
            data = _poll_replicate(api_key, data["urls"]["get"])
        if data.get("status") in {"failed", "canceled"}:
            raise ProviderAdapterError(data.get("error") or f"Replicate request {data.get('status')}")
        outputs.extend(_outputs_from_replicate(data, "replicate"))
    return _finish_provider_outputs(store, turn, payload, model, provider_payload, outputs, [])


def _finish_provider_outputs(store, turn, payload, model, provider_payload, outputs, errors):
    output_assets = []
    for index, output in enumerate(outputs):
        raw, mime, label = _materialize_output(output)
        ext = _extension_for_mime(mime)
        filename = f"{turn['id']}_{label or model['provider']}_{index + 1:02d}.{ext}"
        output_path = _output_dir() / "frank_create" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)
        media_type = "video" if mime.startswith("video/") else "image"
        width, height = _media_dimensions(raw, mime)
        asset_kind = "video" if media_type == "video" else "candidate"
        asset_title = (
            f"{model.get('short_label') or model['label']} / Motion {index + 1:02d}"
            if media_type == "video"
            else f"{model.get('short_label') or model['label']} / Candidate {index + 1:02d}"
        )

        asset = store.create_asset(
            {
                "session_id": turn["session_id"],
                "turn_id": turn["id"],
                "kind": asset_kind,
                "title": asset_title,
                "media_type": media_type,
                "provider": model["provider"],
                "model": model["id"],
                "prompt": provider_payload["prompt"],
                "settings": payload.get("settings") or {},
                "source_asset_id": payload.get("edit_source_asset_id") or payload.get("source_asset_id"),
                "reference_asset_ids": payload.get("reference_asset_ids", []),
                "file_path": f"output/frank_create/{filename}",
                "preview_url": _view_url(filename, "frank_create", "output"),
                "width": width,
                "height": height,
                "approval_status": "review",
                "sync_status": "local",
            }
        )
        output_assets.append(asset)

    if output_assets:
        updated_turn = store.update_turn(
            turn["id"],
            {"status": "complete", "output_asset_ids": [asset["id"] for asset in output_assets]},
        )
        return updated_turn, output_assets

    updated_turn = store.update_turn(
        turn["id"],
        {
            "status": "failed",
            "error": {
                "code": "provider_error",
                "message": _safe_error_message("\n".join(errors)) if errors else "No image output.",
            },
        },
    )
    return updated_turn, []


def _scrub_preview_body(value):
    if isinstance(value, dict):
        scrubbed = {}
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if normalized_key in {"prompt", "text", "text_prompt"}:
                scrubbed[key] = "<composed prompt>"
            elif normalized_key in {"inlineData", "inlinedata"}:
                scrubbed[key] = {"mimeType": "image/png", "data": "<reference image bytes>"}
            elif normalized_key in {"image", "mask"} and isinstance(nested, str):
                scrubbed[key] = "<media file>"
            else:
                scrubbed[key] = _scrub_preview_body(nested)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_preview_body(item) for item in value]
    return value


def _image_paths_for_payload(store, payload):
    ids = []
    if payload.get("edit_source_asset_id") or payload.get("source_asset_id"):
        ids.append(payload.get("edit_source_asset_id") or payload.get("source_asset_id"))
    ids.extend(payload.get("reference_asset_ids", []))

    assets = store.list_assets()
    by_id = {asset["id"]: asset for asset in assets}
    paths = []
    for asset_id in ids:
        asset = by_id.get(asset_id)
        if not asset:
            continue
        path = _resolve_media_path(asset.get("file_path") or "")
        if path and path.exists():
            paths.append(path)
    return paths


def _source_path_for_payload(store, payload):
    source_asset_id = payload.get("edit_source_asset_id") or payload.get("source_asset_id")
    if not source_asset_id:
        return None
    path = _asset_path_for_id(store, source_asset_id)
    return path if path and path.exists() else None


def _mask_path_for_payload(store, payload):
    mask_asset_id = payload.get("mask_asset_id")
    if not mask_asset_id:
        return None
    path = _asset_path_for_id(store, mask_asset_id)
    return path if path and path.exists() else None


def _asset_path_for_id(store, asset_id):
    for asset in store.list_assets():
        if asset["id"] != asset_id:
            continue
        return _resolve_media_path(asset.get("file_path") or "")
    return None


def _outputs_from_openai_like(data, label):
    outputs = []
    for item in data.get("data") or []:
        if item.get("b64_json"):
            outputs.append(_bytes_output(base64.b64decode(item["b64_json"]), "image/png", label))
        elif item.get("url"):
            outputs.append(_url_output(item["url"], label))
    return outputs


def _outputs_from_replicate(data, label):
    output = data.get("output")
    if not output:
        return []
    if isinstance(output, str):
        return [_url_output(output, label)]
    outputs = []
    for item in output:
        if isinstance(item, str):
            outputs.append(_url_output(item, label))
        elif isinstance(item, dict) and item.get("url"):
            outputs.append(_url_output(item["url"], label))
    return outputs


def _poll_replicate(api_key, url):
    deadline = time.time() + 240
    while time.time() < deadline:
        response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        data = _json_or_error(response, "Replicate")
        if data.get("status") in {"succeeded", "failed", "canceled"}:
            return data
        time.sleep(3)
    raise ProviderAdapterError("Replicate request timed out.")


def _first_image_part(data):
    candidates = data.get("candidates") or []
    for candidate in candidates:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and (inline.get("mimeType") or inline.get("mime_type") or "").startswith("image/"):
                return {
                    "mimeType": inline.get("mimeType") or inline.get("mime_type"),
                    "data": inline.get("data"),
                }
    return None


def _json_or_error(response, provider):
    try:
        data = response.json()
    except Exception as exc:
        raise ProviderAdapterError(f"{provider} returned non-JSON response ({response.status_code})") from exc
    if response.status_code >= 400 or data.get("error"):
        raise ProviderAdapterError(_error_message(data, response.status_code, provider))
    return data


def _error_message(data, status_code, provider):
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return _safe_error_message(error.get("message") or f"{provider} request failed ({status_code})")
    if isinstance(error, str):
        return _safe_error_message(error)
    return f"{provider} request failed ({status_code})"


def _safe_error_message(error):
    text = str(error)
    for env_var in PROVIDER_SECRET_ENV_VARS:
        secret = os.environ.get(env_var)
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[redacted]")
    text = SECRET_QUERY_RE.sub(lambda match: f"{match.group(1)}[redacted]", text)
    text = BEARER_SECRET_RE.sub("Bearer [redacted]", text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}[redacted]", text)
    return text


def _inline_data(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return {"mimeType": mime, "data": base64.b64encode(Path(path).read_bytes()).decode("ascii")}


def _bytes_output(raw, mime, label):
    return {"kind": "bytes", "bytes": raw, "mime": mime, "label": label}


def _url_output(url, label):
    return {"kind": "url", "url": url, "label": label}


def _materialize_output(output):
    if output["kind"] == "bytes":
        return output["bytes"], output["mime"], output["label"]
    response = requests.get(output["url"], timeout=180)
    response.raise_for_status()
    mime = response.headers.get("content-type", "").split(";")[0] or _mime_from_url(output["url"])
    return response.content, mime, output["label"]


def _media_dimensions(raw, mime):
    if not str(mime or "").startswith("image/"):
        return None, None
    try:
        with Image.open(BytesIO(raw)) as image:
            return image.width, image.height
    except Exception:
        return None, None


def _mime_from_url(url):
    suffix = Path(urlparse(url).path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".png": "image/png",
        ".gif": "image/gif",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
    }.get(suffix, "image/png")


def _extension_for_mime(mime):
    return {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/png": "png",
        "image/gif": "gif",
        "video/mp4": "mp4",
        "video/webm": "webm",
    }.get(mime, "png")


def _size_for_settings(settings, max_edge=4096):
    width, height = dimensions_for(settings.get("aspect_ratio", "1:1"), settings.get("image_size", "1K"))
    scale = min(1.0, max_edge / max(width, height))
    width = max(64, round(width * scale))
    height = max(64, round(height * scale))
    return f"{width}x{height}"

