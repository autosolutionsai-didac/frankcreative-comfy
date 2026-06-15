from pathlib import Path

import torch
from PIL import Image

from custom_nodes.frank_create.comfy_workflow import (
    FrankCreateVariantNode,
    build_checkpoint_diffusion_prompt,
    build_checkpoint_img2img_prompt,
    build_checkpoint_inpaint_prompt,
    build_frank_variant_prompt,
    extract_saved_images,
)


def test_build_frank_variant_prompt_uses_reference_when_present():
    prompt = build_frank_variant_prompt(
        prompt_text="Clean PDP product shot.",
        turn_id="turn-123",
        preset_key="clean-ecom",
        width=1024,
        height=1024,
        variant_index=2,
        reference_file_path="input/frank_create/product.png",
    )

    assert prompt["1"] == {
        "class_type": "LoadImage",
        "inputs": {"image": "frank_create/product.png"},
    }
    assert prompt["2"]["class_type"] == "FrankCreateVariant"
    assert prompt["2"]["inputs"]["image"] == ["1", 0]
    assert prompt["2"]["inputs"]["prompt"] == "Clean PDP product shot."
    assert prompt["2"]["inputs"]["variant_index"] == 2
    assert prompt["3"] == {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["2", 0],
            "filename_prefix": "frank_create/turn-123_02",
        },
    }


def test_build_frank_variant_prompt_supports_prompt_only_round():
    prompt = build_frank_variant_prompt(
        prompt_text="Warm bathroom lifestyle shot.",
        turn_id="turn-123",
        preset_key="fb-lifestyle",
        width=768,
        height=1024,
        variant_index=1,
    )

    assert "LoadImage" not in {node["class_type"] for node in prompt.values()}
    assert prompt["1"]["class_type"] == "FrankCreateVariant"
    assert prompt["1"]["inputs"]["width"] == 768
    assert prompt["2"]["inputs"]["images"] == ["1", 0]


def test_build_checkpoint_diffusion_prompt_uses_standard_comfy_nodes():
    prompt = build_checkpoint_diffusion_prompt(
        prompt_text="Frank Body coffee scrub hero shot.",
        turn_id="turn-456",
        checkpoint_name="sdxl.safetensors",
        width=1024,
        height=1280,
        variant_index=3,
    )

    assert prompt["1"] == {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sdxl.safetensors"},
    }
    assert prompt["2"]["class_type"] == "CLIPTextEncode"
    assert prompt["2"]["inputs"]["clip"] == ["1", 1]
    assert prompt["2"]["inputs"]["text"] == "Frank Body coffee scrub hero shot."
    assert prompt["4"] == {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 1280, "batch_size": 1},
    }
    assert prompt["5"]["class_type"] == "KSampler"
    assert prompt["5"]["inputs"]["model"] == ["1", 0]
    assert prompt["6"]["class_type"] == "VAEDecode"
    assert prompt["7"]["inputs"]["filename_prefix"] == "frank_create/turn-456_diffusion_03"


def test_build_checkpoint_img2img_prompt_uses_stock_comfy_edit_nodes():
    prompt = build_checkpoint_img2img_prompt(
        prompt_text="Keep the pack shape, polish the label, add pink bathroom light.",
        turn_id="turn-edit-1",
        checkpoint_name="frank-sdxl.safetensors",
        width=1024,
        height=1024,
        variant_index=1,
        reference_file_path="input/frank_create/comfy_refs/source.png",
        denoise=0.42,
    )

    assert prompt["1"] == {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "frank-sdxl.safetensors"},
    }
    assert prompt["2"] == {
        "class_type": "LoadImage",
        "inputs": {"image": "frank_create/comfy_refs/source.png"},
    }
    assert prompt["3"]["class_type"] == "ImageScale"
    assert prompt["3"]["inputs"] == {
        "image": ["2", 0],
        "upscale_method": "lanczos",
        "width": 1024,
        "height": 1024,
        "crop": "center",
    }
    assert prompt["4"] == {
        "class_type": "VAEEncode",
        "inputs": {"pixels": ["3", 0], "vae": ["1", 2]},
    }
    assert prompt["7"]["class_type"] == "KSampler"
    assert prompt["7"]["inputs"]["denoise"] == 0.42
    assert prompt["7"]["inputs"]["latent_image"] == ["4", 0]
    assert prompt["8"]["class_type"] == "VAEDecode"
    assert prompt["9"]["inputs"]["filename_prefix"] == "frank_create/turn-edit-1_img2img_01"


def test_build_checkpoint_inpaint_prompt_uses_stock_comfy_mask_nodes():
    prompt = build_checkpoint_inpaint_prompt(
        prompt_text="Retouch only the masked label edge.",
        turn_id="turn-mask-1",
        checkpoint_name="frank-sdxl.safetensors",
        width=1024,
        height=1024,
        variant_index=0,
        reference_file_path="input/frank_create/comfy_refs/source.png",
        mask_file_path="input/frank_create/comfy_refs/mask.png",
        denoise=0.64,
    )

    assert prompt["1"]["class_type"] == "CheckpointLoaderSimple"
    assert prompt["2"] == {
        "class_type": "LoadImage",
        "inputs": {"image": "frank_create/comfy_refs/source.png"},
    }
    assert prompt["3"]["class_type"] == "ImageScale"
    assert prompt["4"] == {
        "class_type": "LoadImageMask",
        "inputs": {"image": "frank_create/comfy_refs/mask.png", "channel": "red"},
    }
    assert prompt["7"]["class_type"] == "InpaintModelConditioning"
    assert prompt["7"]["inputs"] == {
        "positive": ["5", 0],
        "negative": ["6", 0],
        "pixels": ["3", 0],
        "vae": ["1", 2],
        "mask": ["4", 0],
        "noise_mask": True,
    }
    assert prompt["8"]["class_type"] == "KSampler"
    assert prompt["8"]["inputs"]["denoise"] == 0.64
    assert prompt["8"]["inputs"]["positive"] == ["7", 0]
    assert prompt["8"]["inputs"]["negative"] == ["7", 1]
    assert prompt["8"]["inputs"]["latent_image"] == ["7", 2]
    assert prompt["10"]["inputs"]["filename_prefix"] == "frank_create/turn-mask-1_inpaint_00"


def test_extract_saved_images_from_comfy_history():
    outputs = extract_saved_images(
        {
            "prompt-1": {
                "outputs": {
                    "3": {
                        "images": [
                            {"filename": "turn-123_01_00001_.png", "subfolder": "frank_create", "type": "output"}
                        ]
                    }
                }
            }
        },
        "prompt-1",
    )

    assert outputs == [
        {
            "filename": "turn-123_01_00001_.png",
            "file_path": "output/frank_create/turn-123_01_00001_.png",
            "preview_url": "/api/view?filename=turn-123_01_00001_.png&type=output&subfolder=frank_create",
        }
    ]


def test_frank_create_variant_node_outputs_image_tensor(tmp_path, monkeypatch):
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input").mkdir()
    Image.new("RGB", (240, 320), (248, 230, 230)).save(tmp_path / "input" / "product.png")

    source = torch.ones((1, 320, 240, 3), dtype=torch.float32)
    output = FrankCreateVariantNode().render(
        prompt="Clean product shot.",
        preset_key="clean-ecom",
        width=512,
        height=512,
        variant_index=0,
        edit_mode=False,
        image=source,
    )[0]

    assert tuple(output.shape) == (1, 512, 512, 3)
    assert float(output.max()) <= 1.0
    assert float(output.min()) >= 0.0
