import json

import pytest

from custom_nodes.frank_create.comfy_local import ComfyExecutionUnavailable, run_comfy_studio_turn
from custom_nodes.frank_create.store import FrankCreateStore


class FakePromptQueue:
    def __init__(self):
        self.items = []
        self.history = {}

    def put(self, item):
        self.items.append(item)
        _, prompt_id, _, _, _, _ = item
        workflow = item[2]
        save_node_id = next(
            (
                node_id
                for node_id, node in workflow.items()
                if isinstance(node, dict) and node.get("class_type") == "SaveImage"
            ),
            "3",
        )
        self.history[prompt_id] = {
            prompt_id: {
                "outputs": {
                    save_node_id: {
                        "images": [
                            {
                                "filename": f"{prompt_id}_00001_.png",
                                "subfolder": "frank_create",
                                "type": "output",
                            }
                        ]
                    }
                }
            }
        }

    def get_history(self, prompt_id=None, **_kwargs):
        if prompt_id:
            return self.history.get(prompt_id, {})
        return self.history


class FakeNodeReplaceManager:
    def apply_replacements(self, _prompt):
        return None


class FakePromptServer:
    def __init__(self):
        self.number = 0
        self.prompt_queue = FakePromptQueue()
        self.node_replace_manager = FakeNodeReplaceManager()


@pytest.mark.asyncio
async def test_run_comfy_studio_turn_queues_workflow_and_creates_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr("custom_nodes.frank_create.comfy_local._validate_prompt", _valid_prompt)
    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Comfy round"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "product.png",
            "file_path": "input/frank_create/product.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Clean product shot.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 2},
            "reference_asset_ids": [reference["id"]],
            "status": "running",
        }
    )

    updated_turn, assets = await run_comfy_studio_turn(
        FakePromptServer(),
        store,
        turn,
        {
            "prompt": "Clean product shot.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 2},
            "reference_asset_ids": [reference["id"]],
            "preset_key": "clean-ecom",
        },
        {"id": "frank-local-comfy", "provider": "local", "short_label": "Local Comfy"},
        timeout_seconds=0.25,
        poll_interval=0,
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 2
    assert assets[0]["provider"] == "local"
    assert assets[0]["file_path"].startswith("output/frank_create/")
    assert assets[0]["preview_url"].startswith("/api/view?")
    provenance = json.loads(assets[0]["settings_json"])["workflow_provenance"]
    assert provenance["engine"] == "frank_renderer"
    assert provenance["workflow_key"] == "frank-local-variant-renderer"
    assert provenance["comfy_node_types"] == ["LoadImage", "FrankCreateVariant", "SaveImage"]
    assert provenance["workflow_json"]["2"]["class_type"] == "FrankCreateVariant"
    assert updated_turn["output_asset_ids_json"]


@pytest.mark.asyncio
async def test_run_comfy_studio_turn_uses_checkpoint_diffusion_for_prompt_only_rounds(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    model_root = tmp_path / "models"
    checkpoint_dir = model_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "frank-sdxl.safetensors").write_bytes(b"fake-checkpoint")
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("FRANK_CREATE_MIN_CHECKPOINT_BYTES", "1")
    monkeypatch.setattr("custom_nodes.frank_create.comfy_local._validate_prompt", _valid_prompt)
    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Comfy checkpoint round"})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Frank Body coffee scrub hero shot.",
            "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
            "status": "running",
        }
    )
    prompt_server = FakePromptServer()

    updated_turn, assets = await run_comfy_studio_turn(
        prompt_server,
        store,
        turn,
        {
            "prompt": "Frank Body coffee scrub hero shot.",
            "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
            "reference_asset_ids": [],
            "preset_key": "campaign-variants",
        },
        {"id": "frank-local-comfy", "provider": "local", "short_label": "Local Comfy"},
        timeout_seconds=0.25,
        poll_interval=0,
    )

    queued_workflow = prompt_server.prompt_queue.items[0][2]
    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert queued_workflow["1"]["class_type"] == "CheckpointLoaderSimple"
    assert queued_workflow["1"]["inputs"]["ckpt_name"] == "frank-sdxl.safetensors"
    assert queued_workflow["5"]["class_type"] == "KSampler"
    assert queued_workflow["7"]["class_type"] == "SaveImage"
    provenance = json.loads(assets[0]["settings_json"])["workflow_provenance"]
    assert provenance["engine"] == "checkpoint_diffusion"
    assert provenance["workflow_key"] == "comfy-checkpoint-txt2img"
    assert provenance["checkpoint_name"] == "frank-sdxl.safetensors"
    assert provenance["comfy_node_types"] == [
        "CheckpointLoaderSimple",
        "CLIPTextEncode",
        "CLIPTextEncode",
        "EmptyLatentImage",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ]
    assert provenance["workflow_json"]["5"]["class_type"] == "KSampler"


@pytest.mark.asyncio
async def test_run_comfy_studio_turn_copies_output_source_to_input_before_queueing(tmp_path, monkeypatch):
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr("custom_nodes.frank_create.comfy_local._validate_prompt", _valid_prompt)
    source_path = tmp_path / "output" / "frank_create" / "approved.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"approved-output")
    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Comfy edit"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved output",
            "file_path": "output/frank_create/approved.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "edit",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Polish the label.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "source_asset_id": source["id"],
            "status": "running",
        }
    )
    prompt_server = FakePromptServer()

    await run_comfy_studio_turn(
        prompt_server,
        store,
        turn,
        {
            "prompt": "Polish the label.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "edit_source_asset_id": source["id"],
            "reference_asset_ids": [],
            "preset_key": "product-cleanup",
        },
        {"id": "frank-local-comfy", "provider": "local", "short_label": "Local Comfy"},
        timeout_seconds=0.25,
        poll_interval=0,
    )

    queued_workflow = prompt_server.prompt_queue.items[0][2]
    queued_image = queued_workflow["1"]["inputs"]["image"]
    assert queued_image.startswith("frank_create/comfy_refs/")
    assert queued_image.endswith("_approved.png")
    assert (tmp_path / "input" / queued_image).read_bytes() == b"approved-output"


@pytest.mark.asyncio
async def test_run_comfy_studio_turn_uses_checkpoint_img2img_for_edit_rounds(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    model_root = tmp_path / "models"
    checkpoint_dir = model_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "frank-sdxl.safetensors").write_bytes(b"fake-checkpoint")
    source_path = media_root / "output" / "frank_create" / "approved.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"approved-output")
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("FRANK_CREATE_MIN_CHECKPOINT_BYTES", "1")
    monkeypatch.setattr("custom_nodes.frank_create.comfy_local._validate_prompt", _valid_prompt)
    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Comfy checkpoint edit"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved output",
            "file_path": "output/frank_create/approved.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "edit",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Keep the pack shape and polish the label.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "source_asset_id": source["id"],
            "status": "running",
        }
    )
    prompt_server = FakePromptServer()

    updated_turn, assets = await run_comfy_studio_turn(
        prompt_server,
        store,
        turn,
        {
            "prompt": "Keep the pack shape and polish the label.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "edit_source_asset_id": source["id"],
            "reference_asset_ids": [],
            "preset_key": "product-cleanup",
        },
        {"id": "frank-local-comfy", "provider": "local", "short_label": "Local Comfy"},
        timeout_seconds=0.25,
        poll_interval=0,
    )

    queued_workflow = prompt_server.prompt_queue.items[0][2]
    queued_image = queued_workflow["2"]["inputs"]["image"]
    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert queued_workflow["1"]["class_type"] == "CheckpointLoaderSimple"
    assert queued_workflow["1"]["inputs"]["ckpt_name"] == "frank-sdxl.safetensors"
    assert queued_workflow["3"]["class_type"] == "ImageScale"
    assert queued_workflow["4"]["class_type"] == "VAEEncode"
    assert queued_workflow["7"]["class_type"] == "KSampler"
    assert queued_workflow["9"]["class_type"] == "SaveImage"
    assert queued_image.startswith("frank_create/comfy_refs/")
    assert queued_image.endswith("_approved.png")
    assert (media_root / "input" / queued_image).read_bytes() == b"approved-output"
    provenance = json.loads(assets[0]["settings_json"])["workflow_provenance"]
    assert provenance["engine"] == "checkpoint_diffusion"
    assert provenance["workflow_key"] == "comfy-checkpoint-img2img"
    assert provenance["checkpoint_name"] == "frank-sdxl.safetensors"
    assert provenance["source_asset_id"] == source["id"]
    assert provenance["comfy_node_types"] == [
        "CheckpointLoaderSimple",
        "LoadImage",
        "ImageScale",
        "VAEEncode",
        "CLIPTextEncode",
        "CLIPTextEncode",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ]


@pytest.mark.asyncio
async def test_run_comfy_studio_turn_uses_checkpoint_inpaint_for_masked_edit_rounds(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    model_root = tmp_path / "models"
    checkpoint_dir = model_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "frank-sdxl.safetensors").write_bytes(b"fake-checkpoint")
    source_path = media_root / "output" / "frank_create" / "approved.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"approved-output")
    mask_path = media_root / "output" / "frank_create" / "mask.png"
    mask_path.write_bytes(b"mask-output")
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("FRANK_CREATE_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("FRANK_CREATE_MIN_CHECKPOINT_BYTES", "1")
    monkeypatch.setattr("custom_nodes.frank_create.comfy_local._validate_prompt", _valid_prompt)
    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Comfy checkpoint mask"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved output",
            "file_path": "output/frank_create/approved.png",
        }
    )
    mask = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "mask",
            "title": "Painted mask",
            "file_path": "output/frank_create/mask.png",
            "source_asset_id": source["id"],
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "masked_edit",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Retouch only the masked label edge.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "source_asset_id": source["id"],
            "mask_asset_id": mask["id"],
            "status": "running",
        }
    )
    prompt_server = FakePromptServer()

    updated_turn, assets = await run_comfy_studio_turn(
        prompt_server,
        store,
        turn,
        {
            "kind": "masked_edit",
            "prompt": "Retouch only the masked label edge.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "edit_source_asset_id": source["id"],
            "mask_asset_id": mask["id"],
            "reference_asset_ids": [],
            "preset_key": "product-cleanup",
        },
        {"id": "frank-local-comfy", "provider": "local", "short_label": "Local Comfy"},
        timeout_seconds=0.25,
        poll_interval=0,
    )

    queued_workflow = prompt_server.prompt_queue.items[0][2]
    queued_source = queued_workflow["2"]["inputs"]["image"]
    queued_mask = queued_workflow["4"]["inputs"]["image"]
    assert updated_turn["status"] == "complete"
    assert len(assets) == 1
    assert queued_workflow["1"]["class_type"] == "CheckpointLoaderSimple"
    assert queued_workflow["4"]["class_type"] == "LoadImageMask"
    assert queued_workflow["7"]["class_type"] == "InpaintModelConditioning"
    assert queued_workflow["8"]["class_type"] == "KSampler"
    assert queued_workflow["10"]["class_type"] == "SaveImage"
    assert queued_source.startswith("frank_create/comfy_refs/")
    assert queued_mask.startswith("frank_create/comfy_refs/")
    assert (media_root / "input" / queued_source).read_bytes() == b"approved-output"
    assert (media_root / "input" / queued_mask).read_bytes() == b"mask-output"
    provenance = json.loads(assets[0]["settings_json"])["workflow_provenance"]
    assert provenance["engine"] == "checkpoint_diffusion"
    assert provenance["workflow_key"] == "comfy-checkpoint-inpaint"
    assert provenance["checkpoint_name"] == "frank-sdxl.safetensors"
    assert provenance["source_asset_id"] == source["id"]
    assert provenance["mask_asset_id"] == mask["id"]
    assert provenance["masked_edit"] is True
    assert provenance["comfy_node_types"] == [
        "CheckpointLoaderSimple",
        "LoadImage",
        "ImageScale",
        "LoadImageMask",
        "CLIPTextEncode",
        "CLIPTextEncode",
        "InpaintModelConditioning",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ]


@pytest.mark.asyncio
async def test_run_comfy_studio_turn_raises_when_prompt_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "custom_nodes.frank_create.comfy_local._validate_prompt",
        lambda *_args, **_kwargs: (False, {"type": "bad_prompt"}, [], {}),
    )
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user")
    session = store.create_session({"name": "Comfy round"})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Clean product shot.",
            "status": "running",
        }
    )

    with pytest.raises(ComfyExecutionUnavailable):
        await run_comfy_studio_turn(
            FakePromptServer(),
            store,
            turn,
            {"prompt": "Clean product shot.", "settings": {"count": 1}},
            {"id": "frank-local-comfy", "provider": "local", "short_label": "Local Comfy"},
            timeout_seconds=0.25,
            poll_interval=0,
        )


async def _valid_prompt(_prompt_id, _prompt, _partial_execution_targets):
    return True, None, ["3"], {}
