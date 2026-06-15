import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_BRAND_KIT = {
    "style_guidance": (
        "Warm off-white, Frank pink, cherry red, coffee brown, and off-black palette. "
        "Cheeky but director-ready body-care attitude. Tactile coffee/body-scrub textures, "
        "glossy skin-care detail, warm flash, editorial realism, and packaging that stays clean."
    ),
    "negative_prompt": (
        "Avoid warped logos, extra lids, plastic skin, over-airbrushed bodies, muddy coffee spills, "
        "generic beige spa stock-photo styling, and unreadable packaging labels."
    ),
    "reference_notes": (
        "Use approved Frank Body pack shots first, then lifestyle/body-care references. "
        "Keep source product identity more important than style experiments."
    ),
    "sync_status": "local",
    "remote_id": None,
}


def brand_kit_path(root_dir):
    return Path(root_dir) / "brand_kit.json"


def load_brand_kit(root_dir):
    path = brand_kit_path(root_dir)
    if not path.exists():
        return dict(DEFAULT_BRAND_KIT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_BRAND_KIT)
    return normalize_brand_kit(data)


def save_brand_kit(root_dir, payload):
    path = brand_kit_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    brand_kit = normalize_brand_kit(payload)
    brand_kit["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.write_text(json.dumps(brand_kit, indent=2, sort_keys=True), encoding="utf-8")
    return brand_kit


def normalize_brand_kit(payload):
    payload = payload or {}
    normalized = dict(DEFAULT_BRAND_KIT)
    for key in ("style_guidance", "negative_prompt", "reference_notes", "sync_status", "remote_id", "updated_at"):
        if key in payload:
            normalized[key] = _clean_text(payload.get(key)) if key not in {"remote_id"} else payload.get(key)
    if not normalized.get("sync_status"):
        normalized["sync_status"] = "local"
    return normalized


def _clean_text(value):
    return str(value or "").strip()
