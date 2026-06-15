from urllib.parse import urlencode

import numpy as np
import torch
from PIL import Image

from .local_image import _compose_variant


class FrankCreateVariantNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "preset_key": ("STRING", {"default": "product-shot-lab"}),
                "width": ("INT", {"default": 1024, "min": 256, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1024, "min": 256, "max": 4096, "step": 64}),
                "variant_index": ("INT", {"default": 0, "min": 0, "max": 99}),
                "edit_mode": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "image": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "render"
    CATEGORY = "Frank Create"
    DESCRIPTION = "Creates a Frank Body product-image variant inside the Comfy queue."

    def render(self, prompt, preset_key, width, height, variant_index, edit_mode, image=None):
        base_image = _tensor_to_pil(image) if image is not None else None
        output = _compose_variant(
            base_image=base_image,
            dimensions=(int(width), int(height)),
            preset_key=preset_key or "product-shot-lab",
            prompt=prompt or "",
            variant_index=int(variant_index),
            edit_mode=bool(edit_mode),
        )
        return (_pil_to_tensor(output),)


def build_frank_variant_prompt(
    prompt_text,
    turn_id,
    preset_key,
    width,
    height,
    variant_index,
    reference_file_path=None,
    edit_mode=False,
):
    variant_node_id = "2" if reference_file_path else "1"
    save_node_id = "3" if reference_file_path else "2"
    prompt = {}

    if reference_file_path:
        prompt["1"] = {
            "class_type": "LoadImage",
            "inputs": {"image": _load_image_name(reference_file_path)},
        }

    variant_inputs = {
        "prompt": prompt_text or "",
        "preset_key": preset_key or "product-shot-lab",
        "width": int(width),
        "height": int(height),
        "variant_index": int(variant_index),
        "edit_mode": bool(edit_mode),
    }
    if reference_file_path:
        variant_inputs["image"] = ["1", 0]

    prompt[variant_node_id] = {
        "class_type": "FrankCreateVariant",
        "inputs": variant_inputs,
    }
    prompt[save_node_id] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": [variant_node_id, 0],
            "filename_prefix": f"frank_create/{_safe_prefix(turn_id)}_{int(variant_index):02d}",
        },
    }
    return prompt


def build_checkpoint_diffusion_prompt(
    prompt_text,
    turn_id,
    checkpoint_name,
    width,
    height,
    variant_index,
    negative_prompt=None,
):
    safe_seed = 424242 + int(variant_index)
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint_name},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text or "",
                "clip": ["1", 1],
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt
                or "warped packaging, unreadable label, extra lids, distorted product, plastic skin, low quality, blurry",
                "clip": ["1", 1],
            },
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": 1,
            },
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": safe_seed,
                "steps": 24,
                "cfg": 6.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2],
            },
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["6", 0],
                "filename_prefix": f"frank_create/{_safe_prefix(turn_id)}_diffusion_{int(variant_index):02d}",
            },
        },
    }


def build_checkpoint_img2img_prompt(
    prompt_text,
    turn_id,
    checkpoint_name,
    width,
    height,
    variant_index,
    reference_file_path,
    negative_prompt=None,
    denoise=0.48,
):
    safe_seed = 525252 + int(variant_index)
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint_name},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": _load_image_name(reference_file_path)},
        },
        "3": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["2", 0],
                "upscale_method": "lanczos",
                "width": int(width),
                "height": int(height),
                "crop": "center",
            },
        },
        "4": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["3", 0],
                "vae": ["1", 2],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text or "",
                "clip": ["1", 1],
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt
                or "changed product silhouette, unreadable label, extra lids, distorted packaging, blurry, low quality",
                "clip": ["1", 1],
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": safe_seed,
                "steps": 22,
                "cfg": 5.8,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": float(denoise),
                "model": ["1", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["4", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["1", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": f"frank_create/{_safe_prefix(turn_id)}_img2img_{int(variant_index):02d}",
            },
        },
    }


def build_checkpoint_inpaint_prompt(
    prompt_text,
    turn_id,
    checkpoint_name,
    width,
    height,
    variant_index,
    reference_file_path,
    mask_file_path,
    negative_prompt=None,
    denoise=0.64,
):
    safe_seed = 626262 + int(variant_index)
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint_name},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": _load_image_name(reference_file_path)},
        },
        "3": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["2", 0],
                "upscale_method": "lanczos",
                "width": int(width),
                "height": int(height),
                "crop": "center",
            },
        },
        "4": {
            "class_type": "LoadImageMask",
            "inputs": {
                "image": _load_image_name(mask_file_path),
                "channel": "red",
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text or "",
                "clip": ["1", 1],
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt
                or "changed unmasked product, unreadable label outside mask, extra lids, distorted packaging, blurry, low quality",
                "clip": ["1", 1],
            },
        },
        "7": {
            "class_type": "InpaintModelConditioning",
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "pixels": ["3", 0],
                "vae": ["1", 2],
                "mask": ["4", 0],
                "noise_mask": True,
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "seed": safe_seed,
                "steps": 24,
                "cfg": 5.6,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": float(denoise),
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["7", 2],
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["1", 2],
            },
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": f"frank_create/{_safe_prefix(turn_id)}_inpaint_{int(variant_index):02d}",
            },
        },
    }


def extract_saved_images(history, prompt_id):
    root = history or {}
    entry = root.get(prompt_id, root) if isinstance(root, dict) else {}
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    images = []
    for output in outputs.values():
        for image in output.get("images", []) if isinstance(output, dict) else []:
            image_type = image.get("type") or "output"
            subfolder = image.get("subfolder") or ""
            filename = image.get("filename")
            if not filename:
                continue
            folder = f"{subfolder}/" if subfolder else ""
            images.append(
                {
                    "filename": filename,
                    "file_path": f"{image_type}/{folder}{filename}",
                    "preview_url": _view_url(filename, subfolder, image_type),
                }
            )
    return images


def _tensor_to_pil(image):
    tensor = image[0].detach().cpu().clamp(0, 1)
    array = (tensor.numpy() * 255.0).round().astype(np.uint8)
    return Image.fromarray(array, "RGB").convert("RGBA")


def _pil_to_tensor(image):
    array = np.asarray(image.convert("RGB")).astype(np.float32) / 255.0
    return torch.from_numpy(array)[None,]


def _load_image_name(file_path):
    normalized = str(file_path or "").replace("\\", "/")
    if normalized.startswith("input/"):
        return normalized[len("input/") :]
    return normalized


def _safe_prefix(value):
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value or "turn"))
    return clean.strip("_") or "turn"


def _view_url(filename, subfolder, image_type):
    params = {"filename": filename, "type": image_type}
    if subfolder:
        params["subfolder"] = subfolder
    return f"/api/view?{urlencode(params)}"
