import os
from pathlib import Path

CHECKPOINT_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth"}
DEFAULT_MIN_CHECKPOINT_BYTES = 100 * 1024 * 1024
LOCAL_MODEL_SUBDIRS = ("checkpoints", "loras", "vae", "controlnet")


LAUNCH_MODELS = [
    {
        "id": "frank-local-comfy",
        "label": "Frank Local Comfy Studio",
        "short_label": "Local Comfy",
        "provider": "local",
        "provider_model": "frank-local-comfy",
        "env_vars": [],
        "status": "ready",
        "badge": "Ready",
        "max_resolution_label": "4K",
        "description": "Local Comfy-backed product variants, edits, masked retouch demos, crops, export prep, and storyboard motion without API keys.",
        "capabilities": {"generation": True, "edit": True, "masked_edit": True, "video": True},
        "allowed_aspect_ratios": ["1:1", "4:5", "3:4", "16:9", "9:16", "3:2", "2:3"],
        "allowed_image_sizes": ["1K", "2K", "4K"],
        "reference_image_limit": 8,
        "cost_label": "local",
    },
    {
        "id": "google-nb-pro",
        "label": "Gemini 3 Pro Image / Nano Banana Pro",
        "short_label": "Nano Banana Pro",
        "provider": "google",
        "provider_model": "gemini-3-pro-image",
        "provider_api_version": "v1beta",
        "env_vars": ["GOOGLE_API_KEY"],
        "status": "ready",
        "badge": "4K",
        "max_resolution_label": "4K",
        "description": "Frank Body beauty/editorial generation and broad edits.",
        "capabilities": {"generation": True, "edit": True, "masked_edit": False, "video": False},
        "allowed_aspect_ratios": ["1:1", "4:5", "3:4", "16:9", "9:16"],
        "allowed_image_sizes": ["1K", "2K", "4K"],
        "reference_image_limit": 14,
        "cost_label": "premium",
    },
    {
        "id": "google-nb-2",
        "label": "Gemini 3.1 Flash Image / NB 2",
        "short_label": "NB 2",
        "provider": "google",
        "provider_model": "gemini-3.1-flash-image",
        "provider_api_version": "v1beta",
        "env_vars": ["GOOGLE_API_KEY"],
        "status": "ready",
        "badge": "4K",
        "max_resolution_label": "4K",
        "description": "Fast 4K ideation rounds and cheaper prompt exploration.",
        "capabilities": {"generation": True, "edit": True, "masked_edit": False, "video": False},
        "allowed_aspect_ratios": ["1:1", "4:5", "3:4", "16:9", "9:16"],
        "allowed_image_sizes": ["1K", "2K", "4K"],
        "reference_image_limit": 14,
        "cost_label": "fast",
    },
    {
        "id": "openai-gpt-image-2",
        "label": "OpenAI gpt-image-2",
        "short_label": "gpt-image-2",
        "provider": "openai",
        "provider_model": "gpt-image-2",
        "env_vars": ["OPENAI_API_KEY"],
        "status": "ready",
        "badge": "4K",
        "max_resolution_label": "4K",
        "description": "High-fidelity generation, edits, and masked inpainting.",
        "capabilities": {"generation": True, "edit": True, "masked_edit": True, "video": False},
        "allowed_aspect_ratios": ["1:1", "4:5", "3:4", "16:9", "9:16"],
        "allowed_image_sizes": ["1024", "2048", "4096"],
        "reference_image_limit": 10,
        "cost_label": "premium",
    },
    {
        "id": "flux-1-1-pro-ultra",
        "label": "FLUX 1.1 Pro Ultra",
        "short_label": "FLUX Ultra",
        "provider": "replicate",
        "provider_model": "black-forest-labs/flux-1.1-pro-ultra",
        "env_vars": ["REPLICATE_API_TOKEN"],
        "status": "ready",
        "badge": "4MP",
        "max_resolution_label": "4MP",
        "description": "Photorealism, 4MP output, and Frank LoRA experiments through Replicate when approved.",
        "capabilities": {"generation": True, "edit": False, "masked_edit": False, "video": False},
        "allowed_aspect_ratios": ["1:1", "4:5", "3:4", "16:9", "9:16"],
        "allowed_image_sizes": ["1MP", "4MP"],
        "reference_image_limit": 4,
        "cost_label": "photo",
        "lora_candidate": True,
    },
]


BACKLOG_MODELS = []


PROMPT_PRESETS = [
    {
        "key": "product-shot-lab",
        "label": "Product Shot Lab",
        "description": "Clean product image for PDP, retouching, and channel crops.",
        "prompt": "Product-first composition, clean label, honest skin-care texture, Frank pink accent, channel-ready negative space.",
    },
    {
        "key": "clean-ecom",
        "label": "Clean Ecom",
        "description": "White or softly tinted commerce image with crisp packaging.",
        "prompt": "Clean Ecom structure: centered product, readable label, soft realistic shadow, no visual clutter, high conversion PDP finish.",
    },
    {
        "key": "fb-lifestyle",
        "label": "FB Lifestyle",
        "description": "Bathroom, beach, or bedroom moment with Frank warmth.",
        "prompt": "Frank lifestyle scene: warm real-world bathroom or body-care set, tactile surfaces, cheeky confidence, natural skin-care mess kept polished.",
    },
    {
        "key": "fb-model-image",
        "label": "FB Model Image",
        "description": "Beauty/editorial body-care concept with inclusive casting.",
        "prompt": "Beauty editorial structure: confident body-care model moment, warm direct flash, tactile product use, inclusive casting, no plastic retouching.",
    },
    {
        "key": "campaign-variants",
        "label": "Campaign Variants",
        "description": "Creative rounds from one approved product direction.",
        "prompt": "Campaign variant structure: keep product recognizable, push set styling, leave channel-ready headline space, make the Frank Body attitude sharper.",
    },
    {
        "key": "product-texture",
        "label": "Product Texture",
        "description": "Macro scrub, foam, and skin-care texture exploration.",
        "prompt": "Macro texture direction: coffee scrub grains, creamy body-care texture, tactile swipes, high detail, delicious but skin-care appropriate.",
    },
    {
        "key": "retail-mock",
        "label": "Retail Mock",
        "description": "Packaging, shelf, display, and typography-heavy exploration.",
        "prompt": "Retail mockup structure: packaging readable, shelf/display context, brand block clear, campaign headline space, sharp typography.",
    },
]


FRANK_BODY_STYLE_GUIDANCE = """Frank Body visual language:
- warm off-white, Frank pink, cherry red, coffee brown, and off-black palette
- cheeky but director-ready body-care attitude
- tactile coffee/body-scrub textures, glossy skin-care detail, warm flash, editorial realism
- packaging labels must stay clean, legible, and plausible
- avoid warped logos, extra lids, plastic skin, over-airbrushed bodies, muddy coffee spills, and generic spa stock-photo styling"""


def get_visible_models():
    return [dict(model) for model in LAUNCH_MODELS]


def get_backlog_models():
    return [dict(model) for model in BACKLOG_MODELS]


def get_prompt_presets():
    return [dict(preset) for preset in PROMPT_PRESETS]


def get_local_engine_status():
    checkpoint_entries = _local_checkpoint_entries()
    checkpoints = [entry["name"] for entry in checkpoint_entries["valid"]]
    ignored_checkpoints = checkpoint_entries["ignored"]
    diffusion_ready = bool(checkpoints)
    model_root = _preferred_model_root()
    checkpoint_dir = model_root / "checkpoints"
    lora_dir = model_root / "loras"
    minimum_size_mb = _minimum_checkpoint_mb_label()
    return {
        "active_engine": "checkpoint_diffusion" if diffusion_ready else "frank_renderer",
        "diffusion_ready": diffusion_ready,
        "checkpoint_count": len(checkpoints),
        "checkpoints": checkpoints[:20],
        "ignored_checkpoints": ignored_checkpoints[:20],
        "minimum_checkpoint_mb": minimum_size_mb,
        "model_root": str(model_root),
        "checkpoint_dir": str(checkpoint_dir),
        "setup_readme": str(model_root / "FRANK_CREATE_MODELS_README.txt"),
        "setup_steps": [
            f"Put a full SDXL-style .safetensors checkpoint in {checkpoint_dir} for Local Comfy txt2img, reference/edit img2img, and masked inpaint workflows.",
            f"Files smaller than {minimum_size_mb} MB are treated as incomplete downloads/placeholders.",
            "Keep LoRA files in the loras folder when Frank-specific open-model training is approved.",
            "Use the raw Comfy canvas for FLUX or custom loader workflows until a curated FLUX app workflow is added.",
            "Run Demo Doctor again after adding model files; the Frank renderer remains available as fallback.",
        ],
        "recommended_checkpoints": [
            {
                "label": "SDXL 1.0 Base or an approved SDXL product checkpoint",
                "use": "Best first local checkpoint for campaign/image rounds, reference-guided edits, and masked retouching through built-in Comfy txt2img/img2img/inpaint workflows.",
                "folder": str(checkpoint_dir),
            },
            {
                "label": "Frank-approved SDXL LoRA",
                "use": "Later brand-tuning layer for open models after the image set and rights are approved.",
                "folder": str(lora_dir),
            },
        ],
        "note": (
            f"{len(checkpoints)} local diffusion checkpoint(s) detected. Local Comfy rounds use checkpoint txt2img for prompt-only work, checkpoint img2img for reference/edit work, and checkpoint inpaint for masked edits."
            if diffusion_ready
            else (
                "No usable diffusion checkpoint detected. Local Comfy uses the Frank renderer until a full checkpoint is installed."
                if ignored_checkpoints
                else "No diffusion checkpoint detected. Local Comfy uses the Frank renderer until a checkpoint is installed."
            )
        ),
    }


def get_preferred_checkpoint():
    checkpoints = _local_checkpoint_names()
    return checkpoints[0] if checkpoints else None


def prepare_local_engine_folders():
    model_root = _preferred_model_root()
    created_dirs = []
    for subdir in LOCAL_MODEL_SUBDIRS:
        path = model_root / subdir
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            created_dirs.append(str(path))

    readme_path = model_root / "FRANK_CREATE_MODELS_README.txt"
    readme_path.write_text(_local_engine_readme(model_root), encoding="utf-8")
    return {
        "created_dirs": created_dirs,
        "readme_path": str(readme_path),
        "localEngine": get_local_engine_status(),
    }


def get_model(model_id):
    for model in LAUNCH_MODELS + BACKLOG_MODELS:
        if model["id"] == model_id:
            return dict(model)
    raise KeyError(f"Unknown model: {model_id}")


def get_prompt_preset(preset_key):
    if not preset_key:
        return None
    for preset in PROMPT_PRESETS:
        if preset["key"] == preset_key:
            return dict(preset)
    return None


def compose_frank_prompt(prompt, frank_body_mode=False, preset_key=None, brand_kit=None):
    prompt = (prompt or "").strip()
    if not frank_body_mode:
        return prompt

    preset = get_prompt_preset(preset_key)
    if brand_kit:
        parts = [
            "Frank Body brand kit:",
            (brand_kit.get("style_guidance") or FRANK_BODY_STYLE_GUIDANCE).strip(),
        ]
        negative_prompt = (brand_kit.get("negative_prompt") or "").strip()
        reference_notes = (brand_kit.get("reference_notes") or "").strip()
        if negative_prompt:
            parts.append(f"Negative guardrails: {negative_prompt}")
        if reference_notes:
            parts.append(f"Reference guidance: {reference_notes}")
    else:
        parts = [FRANK_BODY_STYLE_GUIDANCE]
    if preset:
        parts.append(f"{preset['label']} preset: {preset['prompt']}")
    if prompt:
        parts.append(f"User brief: {prompt}")
    return "\n\n".join(parts)


def _local_checkpoint_names():
    return [entry["name"] for entry in _local_checkpoint_entries()["valid"]]


def _local_checkpoint_entries():
    roots = _local_checkpoint_dirs()

    valid = {}
    ignored = {}
    minimum_size = _minimum_checkpoint_bytes()
    minimum_size_mb = _minimum_checkpoint_mb_label(minimum_size)
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in CHECKPOINT_SUFFIXES:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                entry = {
                    "name": path.name,
                    "path": str(path),
                    "size_bytes": size,
                }
                if size >= minimum_size:
                    valid[path.name] = entry
                else:
                    ignored[path.name] = {
                        **entry,
                        "reason": f"smaller than {minimum_size_mb} MB",
                    }
    return {
        "valid": [valid[name] for name in sorted(valid)],
        "ignored": [ignored[name] for name in sorted(ignored)],
    }


def _minimum_checkpoint_bytes():
    raw = os.environ.get("FRANK_CREATE_MIN_CHECKPOINT_BYTES")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            return DEFAULT_MIN_CHECKPOINT_BYTES
    return DEFAULT_MIN_CHECKPOINT_BYTES


def _minimum_checkpoint_mb_label(byte_count=None):
    byte_count = _minimum_checkpoint_bytes() if byte_count is None else int(byte_count)
    return max(1, int((byte_count + (1024 * 1024) - 1) / (1024 * 1024)))


def _local_checkpoint_dirs():
    env_root = os.environ.get("FRANK_CREATE_MODEL_ROOT")
    if env_root:
        root = Path(env_root)
        return [root / "checkpoints", root]

    try:
        import folder_paths

        paths = [Path(path) for path in folder_paths.get_folder_paths("checkpoints")]
        return paths or [Path.cwd() / "models" / "checkpoints"]
    except Exception:
        return [Path.cwd() / "models" / "checkpoints"]


def _preferred_model_root():
    env_root = os.environ.get("FRANK_CREATE_MODEL_ROOT")
    if env_root:
        return Path(env_root)

    checkpoint_dirs = _local_checkpoint_dirs()
    if checkpoint_dirs:
        first = checkpoint_dirs[0]
        return first.parent if first.name.lower() == "checkpoints" else first

    return Path.cwd() / "models"


def _local_engine_readme(model_root):
    checkpoint_dir = model_root / "checkpoints"
    lora_dir = model_root / "loras"
    return "\n".join(
        [
            "Frank Create local model folders",
            "",
            f"Checkpoint folder: {checkpoint_dir}",
            f"LoRA folder: {lora_dir}",
            "",
            "Use this when you want full local Comfy diffusion instead of only the Frank renderer fallback.",
            "For the one-click Frank Local Comfy workflow, start with a full SDXL-style .safetensors checkpoint for txt2img, reference/edit img2img, and masked inpaint.",
            f"Frank Create ignores checkpoint-looking files smaller than {_minimum_checkpoint_mb_label()} MB because they are usually placeholders or incomplete downloads.",
            "Use the raw Comfy canvas for FLUX or custom loader workflows until a curated FLUX app workflow is added.",
            "Place approved open-model LoRA files in the loras folder after the image set and rights are approved.",
            "After copying model files, restart Frank Create or run Demo Doctor again.",
            "Do not store API keys in this folder.",
            "",
        ]
    )
