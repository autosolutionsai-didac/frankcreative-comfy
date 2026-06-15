import os
import re

from .models import compose_frank_prompt, get_model


PROVIDER_KEY_PLACEHOLDER_VALUES = {
    "...",
    "<key>",
    "<paste-key>",
    "<paste key>",
    "<your-key>",
    "<your key>",
    "change-me",
    "changeme",
    "example",
    "paste key",
    "paste-key",
    "replace-me",
    "replace_me",
    "todo",
    "your-api-key",
    "your-key",
    "your_key",
    "your_key_here",
}


class MissingProviderKey(RuntimeError):
    def __init__(self, model_id, env_vars):
        env_label = " or ".join(env_vars)
        super().__init__(f"{env_label} is required for {model_id}")
        self.model_id = model_id
        self.env_vars = env_vars


class UnsupportedModelCapability(ValueError):
    pass


def require_provider_key(model_id):
    model = get_model(model_id)
    env_vars = model.get("env_vars", [])
    if not env_vars:
        return None
    for env_var in env_vars:
        value = os.environ.get(env_var)
        if _provider_key_value_is_real(value):
            return value
    raise MissingProviderKey(model_id, env_vars)


def _provider_key_value_is_real(value):
    if value is None:
        return False
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if normalized in PROVIDER_KEY_PLACEHOLDER_VALUES:
        return False
    if normalized.startswith("your_") or normalized.startswith("your-"):
        return False
    if normalized.startswith("paste ") or normalized.startswith("replace "):
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    return True


def build_provider_payload(
    model_id,
    prompt,
    settings=None,
    reference_assets=None,
    edit_source_asset_id=None,
    mask_asset_id=None,
):
    model = get_model(model_id)
    require_provider_key(model_id)

    normalized_settings = dict(settings or {})
    return {
        "provider": model["provider"],
        "model": model["provider_model"],
        "model_id": model["id"],
        "prompt": prompt,
        "settings": normalized_settings,
        "reference_assets": list(reference_assets or []),
        "edit_source_asset_id": edit_source_asset_id,
        "mask_asset_id": mask_asset_id,
        "capabilities": dict(model["capabilities"]),
    }


def build_turn_payload(payload, reference_assets=None, brand_kit=None):
    model_id = payload.get("model") or payload.get("model_id")
    if not model_id:
        raise ValueError("model is required")

    kind = payload.get("kind", "generate")
    model = get_model(model_id)
    settings = payload.get("settings", {}) or {}
    _validate_model_request(model, kind, settings, payload)
    if kind == "edit" and not model["capabilities"].get("edit"):
        raise UnsupportedModelCapability(f"{model_id} does not support edit")
    if kind == "masked_edit" and not model["capabilities"].get("masked_edit"):
        raise UnsupportedModelCapability(f"{model_id} does not support masked edit")

    prompt = compose_frank_prompt(
        payload.get("prompt", ""),
        frank_body_mode=bool(payload.get("frank_body_mode", False)),
        preset_key=payload.get("preset_key"),
        brand_kit=brand_kit,
    )
    return build_provider_payload(
        model_id=model_id,
        prompt=prompt,
        settings=settings,
        reference_assets=reference_assets or [],
        edit_source_asset_id=payload.get("edit_source_asset_id"),
        mask_asset_id=payload.get("mask_asset_id"),
    )


def _validate_model_request(model, kind, settings, payload):
    model_id = model["id"]
    if kind == "generate" and not model["capabilities"].get("generation"):
        raise UnsupportedModelCapability(f"{model_id} does not support generation")
    if kind == "video" and not model["capabilities"].get("video"):
        raise UnsupportedModelCapability(f"{model_id} does not support video")

    allowed_aspects = model.get("allowed_aspect_ratios") or []
    aspect_ratio = settings.get("aspect_ratio")
    if aspect_ratio and allowed_aspects and aspect_ratio not in allowed_aspects:
        raise UnsupportedModelCapability(f"{model_id} does not support aspect ratio {aspect_ratio}")

    allowed_sizes = model.get("allowed_image_sizes") or []
    image_size = settings.get("image_size")
    if image_size and allowed_sizes and image_size not in allowed_sizes:
        raise UnsupportedModelCapability(f"{model_id} does not support image size {image_size}")

    try:
        count = int(settings.get("count") or 1)
    except (TypeError, ValueError) as exc:
        raise UnsupportedModelCapability(f"{model_id} requires a numeric image count") from exc
    if count < 1 or count > 4:
        raise UnsupportedModelCapability(f"{model_id} supports 1 to 4 images per request")

    reference_ids = payload.get("reference_asset_ids") or []
    reference_limit = int(model.get("reference_image_limit") or 0)
    if len(reference_ids) > reference_limit:
        raise UnsupportedModelCapability(f"{model_id} supports at most {reference_limit} reference images")

    if kind == "edit":
        if not model["capabilities"].get("edit"):
            raise UnsupportedModelCapability(f"{model_id} does not support edit")
        if not (payload.get("edit_source_asset_id") or payload.get("source_asset_id")):
            raise UnsupportedModelCapability(f"{model_id} edit requires a source asset")

    if kind == "masked_edit":
        if not model["capabilities"].get("masked_edit"):
            raise UnsupportedModelCapability(f"{model_id} does not support masked edit")
        if not (payload.get("edit_source_asset_id") or payload.get("source_asset_id")):
            raise UnsupportedModelCapability(f"{model_id} masked edit requires a source asset")
        if not payload.get("mask_asset_id"):
            raise UnsupportedModelCapability(f"{model_id} masked edit requires a mask asset")
