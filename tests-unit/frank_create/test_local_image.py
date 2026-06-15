import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from custom_nodes.frank_create.local_image import (
    create_asset_channel_set_pack,
    create_export_pack,
    create_session_review_board,
    create_session_handoff_pack,
    dimensions_for,
    run_local_video_storyboard,
    run_local_studio_turn,
)
from custom_nodes.frank_create.models import get_model
from custom_nodes.frank_create.store import FrankCreateStore


def test_dimensions_for_aspect_and_size():
    assert dimensions_for("16:9", "2K") == (2048, 1152)
    assert dimensions_for("4:5", "1K") == (819, 1024)


def test_local_studio_turn_creates_assets_and_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    Image.new("RGB", (320, 420), (255, 183, 166)).save(tmp_path / "input" / "frank_create" / "product.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Local round"})
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
            "prompt": "Clean product shot",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 2},
            "reference_asset_ids": [reference["id"]],
            "status": "running",
        }
    )

    updated_turn, assets = run_local_studio_turn(
        store,
        turn,
        {
            "prompt": "Clean product shot",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 2},
            "reference_asset_ids": [reference["id"]],
            "preset_key": "clean-ecom",
        },
        get_model("frank-local-comfy"),
    )

    assert updated_turn["status"] == "complete"
    assert len(assets) == 2
    assert Path(tmp_path / assets[0]["file_path"]).exists()
    assert assets[0]["preview_url"].startswith("/api/view?")


def test_local_studio_turn_renders_simulated_frank_body_product_scene(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    product = Image.new("RGBA", (480, 680), (255, 250, 248, 0))
    draw = ImageDraw.Draw(product)
    draw.rounded_rectangle((148, 54, 332, 606), radius=26, fill=(255, 255, 255, 255), outline=(63, 42, 45, 255), width=5)
    draw.rounded_rectangle((172, 84, 308, 148), radius=14, fill=(255, 226, 218, 255), outline=(196, 17, 47, 255), width=3)
    draw.text((202, 98), "frank", fill=(63, 42, 45, 255))
    draw.text((202, 122), "body", fill=(63, 42, 45, 255))
    for index in range(26):
        x = 178 + (index * 31) % 124
        y = 336 + (index * 47) % 164
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(91, 58, 51, 180))
    product.save(tmp_path / "input" / "frank_create" / "frank-scrub-ref.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Local realistic round"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "frank-scrub-ref.png",
            "file_path": "input/frank_create/frank-scrub-ref.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Create a Frank Body coffee scrub product image on a warm pink bathroom set.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "status": "running",
        }
    )

    _updated_turn, assets = run_local_studio_turn(
        store,
        turn,
        {
            "prompt": "Create a Frank Body coffee scrub product image on a warm pink bathroom set.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "preset_key": "product-shot-lab",
        },
        get_model("frank-local-comfy"),
    )

    output = Image.open(tmp_path / assets[0]["file_path"]).convert("RGBA")
    settings = json.loads(assets[0]["settings_json"])
    provenance = settings["workflow_provenance"]
    coffee_pixels = 0
    cherry_pixels = 0
    glossy_pixels = 0
    for red, green, blue, alpha in output.getdata():
        if alpha < 200:
            continue
        if red < 120 and green < 95 and blue < 90:
            coffee_pixels += 1
        if red > 150 and green < 70 and blue < 90:
            cherry_pixels += 1
        if red > 245 and green > 238 and blue > 232:
            glossy_pixels += 1

    assert provenance["visual_treatment"] == "simulated_frank_body_product_photography"
    assert provenance["demo_realism"] == "high_fidelity_local_mock"
    assert provenance["placeholder_art"] is False
    package_body = output.getpixel((output.width // 2, round(output.height * 0.36)))[:3]
    assert package_body[0] > 225
    assert package_body[1] > 218
    assert package_body[2] > 212
    assert coffee_pixels > output.width * output.height * 0.035
    assert cherry_pixels > output.width * output.height * 0.004
    assert glossy_pixels > output.width * output.height * 0.045


def test_background_remove_task_outputs_transparent_local_cutout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    product = Image.new("RGBA", (320, 420), (250, 245, 240, 255))
    draw = ImageDraw.Draw(product)
    draw.rounded_rectangle((92, 58, 228, 350), radius=24, fill=(255, 183, 166, 255), outline=(42, 42, 42, 255), width=5)
    draw.text((122, 178), "frank", fill=(42, 42, 42, 255))
    product.save(tmp_path / "input" / "frank_create" / "product-flat-bg.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Background remove"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "product-flat-bg.png",
            "file_path": "input/frank_create/product-flat-bg.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Isolate the product.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "status": "running",
        }
    )

    _updated_turn, assets = run_local_studio_turn(
        store,
        turn,
        {
            "prompt": "Isolate the product.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "preset_key": "background-remove",
        },
        get_model("frank-local-comfy"),
    )

    output = Image.open(tmp_path / assets[0]["file_path"]).convert("RGBA")
    alpha_extrema = output.getchannel("A").getextrema()
    settings = json.loads(assets[0]["settings_json"])

    assert alpha_extrema[0] == 0
    assert alpha_extrema[1] == 255
    assert settings["workflow_provenance"]["background_removed"] is True
    assert settings["workflow_provenance"]["workflow_key"] == "frank-local-background-remove-renderer"


def test_background_replace_task_records_frank_backdrop_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    product = Image.new("RGBA", (320, 420), (255, 250, 248, 255))
    draw = ImageDraw.Draw(product)
    draw.rounded_rectangle((92, 58, 228, 350), radius=24, fill=(255, 183, 166, 255), outline=(42, 42, 42, 255), width=5)
    draw.text((122, 178), "frank", fill=(42, 42, 42, 255))
    product.save(tmp_path / "input" / "frank_create" / "product-on-old-set.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Background replace"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "product-on-old-set.png",
            "file_path": "input/frank_create/product-on-old-set.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Move the product into a Frank Body lifestyle set.",
            "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "status": "running",
        }
    )

    _updated_turn, assets = run_local_studio_turn(
        store,
        turn,
        {
            "prompt": "Move the product into a Frank Body lifestyle set.",
            "settings": {"aspect_ratio": "4:5", "image_size": "1K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "preset_key": "background-replace",
        },
        get_model("frank-local-comfy"),
    )

    output = Image.open(tmp_path / assets[0]["file_path"]).convert("RGBA")
    alpha_extrema = output.getchannel("A").getextrema()
    sampled_colors = {
        output.getpixel((round(output.width * x), round(output.height * y)))[:3]
        for x, y in ((0.1, 0.1), (0.88, 0.14), (0.18, 0.84), (0.82, 0.82))
    }
    settings = json.loads(assets[0]["settings_json"])
    provenance = settings["workflow_provenance"]

    assert alpha_extrema == (255, 255)
    assert len(sampled_colors) >= 3
    assert provenance["background_replaced"] is True
    assert provenance["workflow_key"] == "frank-local-background-replace-renderer"
    assert provenance["comfy_node_types"] == ["FrankCreateBackgroundReplace", "SaveImage"]


def test_local_studio_turn_supports_masked_edit_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (600, 600), (255, 250, 248, 255)).save(tmp_path / "output" / "frank_create" / "source.png")
    mask = Image.new("L", (600, 600), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle((190, 190, 410, 410), fill=255)
    mask.save(tmp_path / "output" / "frank_create" / "mask.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Masked edit"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Source",
            "file_path": "output/frank_create/source.png",
            "media_type": "image",
        }
    )
    mask_asset = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "mask",
            "title": "Mask",
            "file_path": "output/frank_create/mask.png",
            "media_type": "image",
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
            "status": "running",
        }
    )

    updated_turn, assets = run_local_studio_turn(
        store,
        turn,
        {
            "prompt": "Retouch only the masked label edge.",
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "edit_source_asset_id": source["id"],
            "mask_asset_id": mask_asset["id"],
            "preset_key": "product-cleanup",
        },
        get_model("frank-local-comfy"),
    )

    assert updated_turn["status"] == "complete"
    assert assets[0]["source_asset_id"] == source["id"]
    assert Path(tmp_path / assets[0]["file_path"]).exists()
    settings = json.loads(assets[0]["settings_json"])
    provenance = settings["workflow_provenance"]
    assert provenance["workflow_key"] == "frank-local-masked-edit-renderer"
    assert provenance["masked_edit"] is True
    assert provenance["mask_asset_id"] == mask_asset["id"]
    assert provenance["comfy_node_types"] == ["FrankCreateMaskedEdit", "SaveImage"]


def test_local_video_storyboard_creates_gif_asset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (640, 640), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "source.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Video lab", "mode": "video"})
    source = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved source",
            "file_path": "output/frank_create/source.png",
            "media_type": "image",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "video",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Six second PDP motion loop",
            "settings": {"aspect_ratio": "16:9", "image_size": "1K"},
            "source_asset_id": source["id"],
            "status": "running",
        }
    )

    updated_turn, assets = run_local_video_storyboard(
        store,
        turn,
        {
            "prompt": "Six second PDP motion loop",
            "settings": {"aspect_ratio": "16:9", "image_size": "1K"},
            "source_asset_id": source["id"],
        },
        get_model("frank-local-comfy"),
    )

    assert updated_turn["status"] == "complete"
    assert assets[0]["media_type"] == "video"
    assert assets[0]["kind"] == "video"
    assert assets[0]["source_asset_id"] == source["id"]
    assert assets[0]["file_path"].endswith(".gif")
    assert (tmp_path / assets[0]["file_path"]).exists()
    settings = json.loads(assets[0]["settings_json"])
    provenance = settings["workflow_provenance"]
    assert provenance["workflow_key"] == "frank-local-video-storyboard"
    assert provenance["comfy_node_types"] == ["FrankCreateVideoStoryboard", "SaveAnimatedImage"]


def test_export_pack_creates_image_and_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (900, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "candidate.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    asset = store.create_asset(
        {
            "title": "Candidate",
            "kind": "candidate",
            "file_path": "output/frank_create/candidate.png",
            "preview_url": "/api/view?filename=candidate.png&type=output&subfolder=frank_create",
        }
    )

    payload = create_export_pack(store, {"asset_id": asset["id"], "preset": "instagram-story", "metadata": {"app": "test"}})

    assert Path(payload["file_path"]).exists()
    assert payload["file_path"].endswith(".zip")
    assert payload["metadata"]["width"] == 1080
    assert payload["metadata"]["height"] == 1920
    assert len(payload["metadata"]["media_integrity"]["sha256"]) == 64
    assert payload["metadata"]["media_integrity"]["file_size_bytes"] > 0
    assert Path(payload["metadata"]["metadata_file"]).exists()
    assert Path(payload["metadata"]["image_file"]).exists()
    with ZipFile(payload["file_path"]) as archive:
        names = set(archive.namelist())
        readme = archive.read("README.md").decode("utf-8")
        spec = archive.read("EXPORT_SPEC.md").decode("utf-8")
        metadata = json.loads(archive.read(f"{asset['id']}-instagram-story.json"))
    assert f"{asset['id']}-instagram-story.jpg" in names
    assert f"{asset['id']}-instagram-story.json" in names
    assert "EXPORT_SPEC.md" in names
    assert "Frank Create export pack" in readme
    assert "Frank Create Export Spec" in spec
    assert "| Intended use | instagram-story |" in spec
    assert "| Output size | 1080 x 1920 |" in spec
    assert "| Approval | review |" in spec
    assert f"| Asset ID | {asset['id']} |" in spec
    assert "- Preset: instagram-story" in readme
    assert "- Dimensions: 1080 x 1920" in readme
    assert f"- Asset: Candidate ({asset['id']})" in readme
    assert "- Workflow: Not set (Not set)" in readme
    assert f"- Image: {asset['id']}-instagram-story.jpg" in readme
    assert f"- Metadata: {asset['id']}-instagram-story.json" in readme
    assert "- SHA-256:" in readme
    assert metadata["media_integrity"]["sha256"] == payload["metadata"]["media_integrity"]["sha256"]


def test_channel_set_pack_creates_all_image_presets_and_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (900, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "candidate.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    asset = store.create_asset(
        {
            "title": "Channel candidate",
            "kind": "candidate",
            "file_path": "output/frank_create/candidate.png",
            "preview_url": "/api/view?filename=candidate.png&type=output&subfolder=frank_create",
            "prompt": "Clean Frank Body channel set.",
            "settings": {
                "aspect_ratio": "1:1",
                "image_size": "2K",
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-variant-renderer",
                },
            },
        }
    )

    payload = create_asset_channel_set_pack(store, {"asset_id": asset["id"], "metadata": {"app": "test"}})

    assert Path(payload["file_path"]).exists()
    assert payload["preset"] == "channel-set"
    assert payload["metadata"]["preset_count"] == 7
    assert payload["metadata"]["presets"] == [
        "pdp",
        "email-hero",
        "instagram-feed",
        "instagram-story",
        "paid-social",
        "transparent-png",
        "high-res-master",
    ]

    with ZipFile(payload["file_path"]) as archive:
      names = set(archive.namelist())
      manifest = json.loads(archive.read("frank-create-channel-set.json"))
      readme = archive.read("README.md").decode("utf-8")
      spec = archive.read("CHANNEL_SPEC.md").decode("utf-8")

    assert "README.md" in names
    assert "CHANNEL_SPEC.md" in names
    assert "video-storyboard" not in str(names)
    assert "pdp/asset-channel-candidate-pdp.jpg" not in names
    assert f"pdp/{asset['id']}-pdp.jpg" in names
    assert f"pdp/{asset['id']}-pdp.json" in names
    assert f"transparent-png/{asset['id']}-transparent-png.png" in names
    assert f"high-res-master/{asset['id']}-high-res-master.png" in names
    assert manifest["asset_id"] == asset["id"]
    assert manifest["preset"] == "channel-set"
    assert manifest["exports"]["pdp"]["width"] == 1600
    assert manifest["exports"]["pdp"]["height"] == 2000
    assert len(manifest["exports"]["pdp"]["media_integrity"]["sha256"]) == 64
    assert manifest["exports"]["pdp"]["media_integrity"]["file_size_bytes"] > 0
    assert manifest["exports"]["transparent-png"]["format"] == "png"
    assert manifest["asset_context"]["prompt"] == "Clean Frank Body channel set."
    assert manifest["asset_context"]["workflow_provenance"]["workflow_key"] == "frank-local-variant-renderer"
    assert manifest["workflow_bridge"]["asset_id"] == asset["id"]
    assert manifest["workflow_bridge"]["workflow_key"] == "frank-local-variant-renderer"
    assert manifest["workflow_bridge"]["raw_canvas_url"] == f"/comfy/?frankAssetId={asset['id']}"
    assert manifest["workflow_bridge"]["workflow_receipt_url"] == f"/api/frank/assets/{asset['id']}/workflow"
    assert manifest["workflow_bridge"]["can_open_raw_canvas"] is True
    assert manifest["workflow_bridge"]["can_load_comfy_api_prompt"] is False
    assert manifest["workflow_bridge"]["raw_canvas_load_status"] == "receipt_only"
    assert manifest["workflow_bridge"]["comfy_node_types"] == ["FrankCreateVariant", "SaveImage"]
    assert "Frank Create channel set" in readme
    assert "Frank Create Channel Spec" in spec
    assert "| pdp | 1600 x 2000 | jpg |" in spec
    assert "| instagram-story | 1080 x 1920 | jpg |" in spec
    assert "| high-res-master | 4096 x 4096 | png |" in spec
    assert "Clean Frank Body channel set." in spec
    assert "- Presets: 7" in readme
    assert "- Workflow: frank-local-variant-renderer (frank_renderer)" in readme
    assert f"- Raw Comfy: /comfy/?frankAssetId={asset['id']}" in readme
    assert f"- Workflow receipt: /api/frank/assets/{asset['id']}/workflow" in readme
    assert "- Raw Comfy load: receipt_only" in readme
    assert "- Comfy nodes: FrankCreateVariant, SaveImage" in readme
    assert "- pdp: 1600 x 2000 jpg" in readme
    assert "- transparent-png: 900 x 900 png" in readme
    assert "- Manifest: frank-create-channel-set.json" in readme
    assert "Integrity" in readme


def test_high_res_master_export_records_upscale_and_enhance_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (900, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "candidate.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    asset = store.create_asset(
        {
            "title": "Upscale candidate",
            "kind": "candidate",
            "file_path": "output/frank_create/candidate.png",
            "preview_url": "/api/view?filename=candidate.png&type=output&subfolder=frank_create",
        }
    )

    payload = create_export_pack(store, {"asset_id": asset["id"], "preset": "high-res-master", "metadata": {"app": "test"}})

    with ZipFile(payload["file_path"]) as archive:
        metadata = json.loads(archive.read(f"{asset['id']}-high-res-master.json"))

    assert payload["metadata"]["width"] == 4096
    assert payload["metadata"]["height"] == 4096
    assert metadata["upscaled"] is True
    assert metadata["enhanced"] is True
    assert metadata["source_width"] == 900
    assert metadata["source_height"] == 900
    assert metadata["scale_factor"] > 4.5
    assert metadata["export_context"]["workflow_key"] == "high-res-master"


def test_export_pack_metadata_includes_asset_and_turn_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (320, 420), (255, 244, 240, 255)).save(tmp_path / "input" / "frank_create" / "ref.png")
    Image.new("RGBA", (900, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "candidate.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Export metadata QA"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Reference",
            "file_path": "input/frank_create/ref.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Create a Frank Body body scrub shot.",
            "settings": {"aspect_ratio": "4:5", "image_size": "2K", "count": 4},
            "reference_asset_ids": [reference["id"]],
            "frank_body_mode": True,
            "preset_key": "campaign-variants",
            "status": "complete",
        }
    )
    asset = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": turn["id"],
            "title": "Campaign candidate",
            "kind": "candidate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Create a Frank Body body scrub shot.",
            "settings": {
                "aspect_ratio": "4:5",
                "image_size": "2K",
                "count": 4,
                "workflow_provenance": {
                    "engine": "checkpoint_diffusion",
                    "workflow_key": "comfy-checkpoint-txt2img",
                    "checkpoint_name": "frank-sdxl.safetensors",
                    "authorization": "Bearer sk-secret-export-12345678901234567890",
                    "comfy_node_types": ["CheckpointLoaderSimple", "KSampler", "SaveImage"],
                    "workflow_json": {
                        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "frank-sdxl.safetensors"}},
                        "2": {"class_type": "SaveImage", "inputs": {"api_key": "sk-secret-export-12345678901234567890"}},
                    },
                },
            },
            "reference_asset_ids": [reference["id"]],
            "file_path": "output/frank_create/candidate.png",
            "notes": "Use this for email.",
        }
    )

    payload = create_export_pack(store, {"asset_id": asset["id"], "preset": "email-hero", "metadata": {"app": "test"}})

    with ZipFile(payload["file_path"]) as archive:
        metadata = json.loads(archive.read(f"{asset['id']}-email-hero.json"))

    assert metadata["asset_context"]["prompt"] == "Create a Frank Body body scrub shot."
    assert metadata["asset_context"]["settings"]["aspect_ratio"] == "4:5"
    assert metadata["asset_context"]["workflow_provenance"]["engine"] == "checkpoint_diffusion"
    assert metadata["asset_context"]["workflow_provenance"]["workflow_key"] == "comfy-checkpoint-txt2img"
    assert metadata["asset_context"]["workflow_provenance"]["checkpoint_name"] == "frank-sdxl.safetensors"
    assert metadata["asset_context"]["workflow_provenance"]["authorization"] == "[server-side secret]"
    assert metadata["asset_context"]["workflow_provenance"]["workflow_json"]["2"]["inputs"]["api_key"] == "[server-side secret]"
    assert metadata["asset_context"]["workflow_provenance"]["comfy_node_types"] == [
        "CheckpointLoaderSimple",
        "KSampler",
        "SaveImage",
    ]
    assert metadata["asset_context"]["reference_asset_ids"] == [reference["id"]]
    assert metadata["asset_context"]["notes"] == "Use this for email."
    assert metadata["turn_context"]["preset_key"] == "campaign-variants"
    assert metadata["turn_context"]["frank_body_mode"] is True
    assert metadata["export_context"]["preset"] == "email-hero"
    assert metadata["export_context"]["width"] == 2400
    assert metadata["export_context"]["height"] == 1350
    assert metadata["workflow_bridge"] == {
        "asset_id": asset["id"],
        "workflow_key": "comfy-checkpoint-txt2img",
        "engine": "checkpoint_diffusion",
        "can_open_raw_canvas": True,
        "can_load_comfy_api_prompt": True,
        "raw_canvas_load_status": "api_prompt_attached",
        "comfy_node_types": ["CheckpointLoaderSimple", "KSampler", "SaveImage"],
        "raw_canvas_url": f"/comfy/?frankAssetId={asset['id']}",
        "workflow_receipt_url": f"/api/frank/assets/{asset['id']}/workflow",
    }
    assert "sk-secret-export" not in json.dumps(metadata)
    with ZipFile(payload["file_path"]) as archive:
        readme = archive.read("README.md").decode("utf-8")
    assert "- Workflow: comfy-checkpoint-txt2img (checkpoint_diffusion)" in readme
    assert f"- Raw Comfy: /comfy/?frankAssetId={asset['id']}" in readme
    assert f"- Workflow receipt: /api/frank/assets/{asset['id']}/workflow" in readme
    assert "- Raw Comfy load: api_prompt_attached" in readme
    assert "- Comfy nodes: CheckpointLoaderSimple, KSampler, SaveImage" in readme


def test_export_pack_metadata_includes_project_and_brief_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (900, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "candidate.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    project = store.create_project({"name": "Coffee Scrub Launch", "client": "Frank Body"})
    brief = store.create_brief(
        {
            "project_id": project["id"],
            "title": "Coffee Scrub PDP Refresh",
            "product_name": "Original Coffee Scrub",
            "task_type": "product-shot-lab",
            "channel": "PDP",
            "tone": "Cheeky but premium",
            "prompt": "Clean Frank Body product shot.",
            "negative_prompt": "No warped label.",
        }
    )
    session = store.create_session({"name": "Export metadata QA", "project_id": project["id"], "summary": brief["title"]})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": brief["prompt"],
            "preset_key": "product-shot-lab",
            "status": "complete",
        }
    )
    asset = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": turn["id"],
            "brief_id": brief["id"],
            "title": "Campaign candidate",
            "kind": "candidate",
            "file_path": "output/frank_create/candidate.png",
            "prompt": brief["prompt"],
        }
    )

    payload = create_export_pack(store, {"asset_id": asset["id"], "preset": "email-hero", "metadata": {"app": "test"}})

    with ZipFile(payload["file_path"]) as archive:
        metadata = json.loads(archive.read(f"{asset['id']}-email-hero.json"))

    assert metadata["project_context"]["name"] == "Coffee Scrub Launch"
    assert metadata["project_context"]["client"] == "Frank Body"
    assert metadata["brief_context"]["title"] == "Coffee Scrub PDP Refresh"
    assert metadata["brief_context"]["product_name"] == "Original Coffee Scrub"
    assert metadata["brief_context"]["negative_prompt"] == "No warped label."
    assert payload["metadata"]["project_context"]["id"] == project["id"]
    assert payload["metadata"]["brief_context"]["id"] == brief["id"]


def test_transparent_png_export_removes_flat_background(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    image = Image.new("RGB", (320, 320), (255, 183, 166))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((104, 70, 216, 250), radius=10, fill=(245, 238, 231), outline=(55, 38, 42), width=4)
    draw.rectangle((132, 92, 188, 132), fill=(255, 248, 245), outline=(196, 17, 47), width=2)
    image.save(tmp_path / "output" / "frank_create" / "flat-bg-product.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    asset = store.create_asset(
        {
            "title": "Flat background product",
            "kind": "candidate",
            "file_path": "output/frank_create/flat-bg-product.png",
            "preview_url": "/api/view?filename=flat-bg-product.png&type=output&subfolder=frank_create",
        }
    )

    payload = create_export_pack(store, {"asset_id": asset["id"], "preset": "transparent-png", "metadata": {"app": "test"}})
    output = Image.open(payload["metadata"]["image_file"]).convert("RGBA")

    assert payload["metadata"]["background_removed"] is True
    assert output.getpixel((0, 0))[3] == 0
    assert output.getpixel((160, 160))[3] == 255


def test_export_pack_creates_video_storyboard_zip_without_rasterizing_gif(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    gif_path = tmp_path / "output" / "frank_create" / "storyboard.gif"
    Image.new("RGBA", (320, 180), (255, 183, 166, 255)).save(gif_path, "GIF")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Video export QA", "mode": "video"})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "video",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Subtle product push-in",
            "settings": {"aspect_ratio": "16:9", "image_size": "1K", "count": 1},
            "frank_body_mode": False,
            "preset_key": "video-lab",
            "status": "complete",
        }
    )
    asset = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": turn["id"],
            "title": "Motion storyboard",
            "kind": "video",
            "media_type": "video",
            "provider": "local",
            "model": "frank-local-comfy",
            "file_path": "output/frank_create/storyboard.gif",
            "preview_url": "/api/view?filename=storyboard.gif&type=output&subfolder=frank_create",
            "prompt": "Subtle product push-in",
            "settings": {"aspect_ratio": "16:9", "image_size": "1K", "count": 1},
            "approval_status": "approved",
        }
    )

    payload = create_export_pack(store, {"asset_id": asset["id"], "preset": "video-storyboard", "metadata": {"app": "test"}})

    assert Path(payload["file_path"]).exists()
    assert payload["metadata"]["media_type"] == "video"
    assert payload["metadata"]["storyboard_file"].endswith("storyboard.gif")
    with ZipFile(payload["file_path"]) as archive:
        names = set(archive.namelist())
        metadata = json.loads(archive.read(f"{asset['id']}-video-storyboard.json"))
        gif_bytes = archive.read(f"{asset['id']}-video-storyboard.gif")
        readme = archive.read("README.md").decode("utf-8")
        spec = archive.read("EXPORT_SPEC.md").decode("utf-8")

    assert f"{asset['id']}-video-storyboard.gif" in names
    assert "README.md" in names
    assert "EXPORT_SPEC.md" in names
    assert metadata["asset_id"] == asset["id"]
    assert metadata["media_type"] == "video"
    assert metadata["asset_context"]["prompt"] == "Subtle product push-in"
    assert metadata["asset_context"]["settings"]["aspect_ratio"] == "16:9"
    assert metadata["turn_context"]["preset_key"] == "video-lab"
    assert metadata["export_context"]["preset"] == "video-storyboard"
    assert metadata["export_context"]["format"] == ".gif"
    assert len(metadata["media_integrity"]["sha256"]) == 64
    assert metadata["media_integrity"]["file_size_bytes"] == len(gif_bytes)
    assert gif_bytes.startswith(b"GIF8")
    assert "Frank Create export pack" in readme
    assert "Frank Create Export Spec" in spec
    assert "| Media type | video |" in spec
    assert "| Intended use | video-storyboard |" in spec
    assert "| Output size | 320 x 180 |" in spec
    assert "- Media type: video" in readme
    assert "- Preset: video-storyboard" in readme
    assert "- Dimensions: 320 x 180" in readme
    assert f"- Storyboard: {asset['id']}-video-storyboard.gif" in readme
    assert "- SHA-256:" in readme
    assert f"- Metadata: {asset['id']}-video-storyboard.json" in readme


def test_session_handoff_pack_includes_approved_assets_references_and_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (700, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "approved.png")
    Image.new("RGBA", (700, 900), (255, 226, 218, 255)).save(tmp_path / "output" / "frank_create" / "masked-proof.png")
    Image.new("RGBA", (320, 420), (255, 244, 240, 255)).save(tmp_path / "input" / "frank_create" / "ref.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Cliff Handoff"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Coffee scrub ref",
            "file_path": "input/frank_create/ref.png",
        }
    )
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Make it pop",
            "settings": {"aspect_ratio": "4:5", "image_size": "2K", "count": 1},
            "reference_asset_ids": [reference["id"]],
            "status": "complete",
        }
    )
    approved = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": turn["id"],
            "kind": "candidate",
            "title": "Approved. Hot.",
            "file_path": "output/frank_create/approved.png",
            "prompt": "Make it pop",
            "settings": {
                "aspect_ratio": "4:5",
                "image_size": "2K",
                "count": 1,
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-variant-renderer",
                    "comfy_node_types": ["LoadImage", "FrankCreateVariant", "SaveImage"],
                },
            },
            "reference_asset_ids": [reference["id"]],
            "approval_status": "approved",
            "notes": "This is the direction.",
        }
    )
    masked_turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "masked_edit",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": "Retouch only the label.",
            "settings": {"aspect_ratio": "1:1", "image_size": "2K", "count": 1},
            "source_asset_id": approved["id"],
            "reference_asset_ids": [reference["id"]],
            "status": "complete",
        }
    )
    masked_proof = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": masked_turn["id"],
            "kind": "candidate",
            "title": "Masked retouch proof",
            "file_path": "output/frank_create/masked-proof.png",
            "prompt": "Retouch only the label.",
            "settings": {
                "aspect_ratio": "1:1",
                "image_size": "2K",
                "count": 1,
                "workflow_provenance": {
                    "engine": "frank_renderer",
                    "workflow_key": "frank-local-masked-edit-renderer",
                    "masked_edit": True,
                    "comfy_node_types": ["LoadImage", "FrankCreateMaskedEdit", "SaveImage"],
                },
            },
            "source_asset_id": approved["id"],
            "reference_asset_ids": [reference["id"]],
            "approval_status": "review",
            "notes": "Masked proof stays in review.",
        }
    )

    payload = create_session_handoff_pack(store, {"session_id": session["id"], "summary": "Client review pack"})

    assert payload["asset_id"] == approved["id"]
    assert payload["preset"] == "session-handoff"
    assert payload["metadata"]["asset_count"] == 1
    assert payload["metadata"]["reference_count"] == 1
    with ZipFile(payload["file_path"]) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("frank-create-handoff.json"))
        readme = archive.read("README.md").decode("utf-8")
        spec = archive.read("HANDOFF_SPEC.md").decode("utf-8")
        review_board = Image.open(archive.open("review/frank-create-review-board.png"))
        sidecar_names = [name for name in names if name.startswith("workflows/")]

    assert "README.md" in names
    assert "HANDOFF_SPEC.md" in names
    assert "- Workflows: frank-local-variant-renderer (frank_renderer)" in readme
    assert "Frank Create Handoff Spec" in spec
    assert "- review/: visual review board for the approved round" in readme
    assert "- channel-exports/: channel-ready derivatives for approved image assets" in readme
    assert "| Approved assets | 1 |" in spec
    assert "| Reference images | 1 |" in spec
    assert "| Channel export sets | 1 |" in spec
    assert "| Approved. Hot. | pdp, email-hero, instagram-feed, instagram-story, paid-social, transparent-png, high-res-master |" in spec
    assert "| Approved. Hot. | image | approved | frank-local-variant-renderer |" in spec
    assert "Client review pack" in spec
    assert "- workflows/: standalone workflow provenance JSON for approved and proof assets" in readme
    assert any(name.startswith("channel-exports/approved-hot/") for name in names)
    assert any(name.startswith("approved/approved-hot") for name in names)
    assert any(name.startswith("references/coffee-scrub-ref") for name in names)
    assert manifest["summary"] == "Client review pack"
    assert manifest["counts"]["channel_export_sets"] == 1
    assert manifest["counts"]["channel_export_files"] == 7
    assert manifest["review_board"]["archive_path"] == "review/frank-create-review-board.png"
    assert manifest["review_board"]["approved_asset_count"] == 1
    assert manifest["review_board"]["reference_asset_count"] == 1
    assert manifest["review_board"]["width"] >= 1200
    assert manifest["review_board"]["height"] >= 800
    assert review_board.format == "PNG"
    assert review_board.size == (manifest["review_board"]["width"], manifest["review_board"]["height"])
    assert manifest["approved_assets"][0]["notes"] == "This is the direction."
    assert manifest["approved_assets"][0]["settings"]["aspect_ratio"] == "4:5"
    assert manifest["approved_assets"][0]["workflow_provenance"]["engine"] == "frank_renderer"
    assert manifest["approved_assets"][0]["workflow_provenance"]["workflow_key"] == "frank-local-variant-renderer"
    assert manifest["approved_assets"][0]["workflow_provenance"]["comfy_node_types"] == [
        "LoadImage",
        "FrankCreateVariant",
        "SaveImage",
    ]
    workflow_sidecar_path = manifest["approved_assets"][0]["workflow_sidecar_path"]
    assert workflow_sidecar_path in names
    assert workflow_sidecar_path.startswith("workflows/")
    assert workflow_sidecar_path in sidecar_names
    with ZipFile(payload["file_path"]) as archive:
        workflow_sidecar = json.loads(archive.read(workflow_sidecar_path))
    assert workflow_sidecar
    assert workflow_sidecar["asset_id"] == approved["id"]
    assert workflow_sidecar["asset_title"] == "Approved. Hot."
    assert workflow_sidecar["workflow_provenance"]["workflow_key"] == "frank-local-variant-renderer"
    assert workflow_sidecar["settings"]["aspect_ratio"] == "4:5"
    assert workflow_sidecar["prompt"] == "Make it pop"
    assert manifest["approved_assets"][0]["archive_path"] in names
    assert manifest["approved_assets"][0]["archive_path"].startswith("approved/")
    assert manifest["approved_assets"][0]["channel_export_count"] == 7
    assert len(manifest["approved_assets"][0]["media_integrity"]["sha256"]) == 64
    assert manifest["approved_assets"][0]["media_integrity"]["file_size_bytes"] > 0
    channel_exports = manifest["channel_exports"][approved["id"]]
    assert channel_exports["asset_id"] == approved["id"]
    assert channel_exports["preset_count"] == 7
    assert channel_exports["exports"]["pdp"]["width"] == 1600
    assert channel_exports["exports"]["pdp"]["height"] == 2000
    assert channel_exports["exports"]["instagram-story"]["width"] == 1080
    assert channel_exports["exports"]["instagram-story"]["height"] == 1920
    assert channel_exports["exports"]["transparent-png"]["format"] == "png"
    assert channel_exports["exports"]["high-res-master"]["format"] == "png"
    assert channel_exports["exports"]["high-res-master"]["width"] == 3186
    assert channel_exports["exports"]["high-res-master"]["height"] == 4096
    for preset, export in channel_exports["exports"].items():
        assert export["image_file"] in names
        assert export["metadata_file"] in names
        assert export["image_file"].startswith(f"channel-exports/approved-hot/{preset}/")
        assert len(export["media_integrity"]["sha256"]) == 64
        assert export["media_integrity"]["file_size_bytes"] > 0
    with ZipFile(payload["file_path"]) as archive:
        pdp_image = Image.open(BytesIO(archive.read(channel_exports["exports"]["pdp"]["image_file"])))
        story_image = Image.open(BytesIO(archive.read(channel_exports["exports"]["instagram-story"]["image_file"])))
    assert pdp_image.size == (1600, 2000)
    assert story_image.size == (1080, 1920)
    assert manifest["reference_assets"][0]["archive_path"] in names
    assert manifest["reference_assets"][0]["archive_path"].startswith("references/")
    assert len(manifest["reference_assets"][0]["media_integrity"]["sha256"]) == 64
    assert manifest["reference_assets"][0]["media_integrity"]["file_size_bytes"] > 0
    assert manifest["turns"][0]["reference_asset_ids"] == [reference["id"]]
    assert manifest["counts"]["proof_assets"] == 1
    assert manifest["proof_assets"][0]["id"] == masked_proof["id"]
    assert manifest["proof_assets"][0]["approval_status"] == "review"
    assert manifest["proof_assets"][0]["archive_path"].startswith("proofs/")
    assert manifest["proof_assets"][0]["archive_path"] in names
    proof_sidecar_path = manifest["proof_assets"][0]["workflow_sidecar_path"]
    assert proof_sidecar_path.startswith("workflows/")
    assert proof_sidecar_path in names
    with ZipFile(payload["file_path"]) as archive:
        proof_sidecar = json.loads(archive.read(proof_sidecar_path))
    assert proof_sidecar["asset_id"] == masked_proof["id"]
    assert proof_sidecar["workflow_provenance"]["workflow_key"] == "frank-local-masked-edit-renderer"


def test_session_review_board_returns_png_for_approved_assets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "input" / "frank_create").mkdir(parents=True)
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (700, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "approved.png")
    Image.new("RGBA", (320, 420), (255, 244, 240, 255)).save(tmp_path / "input" / "frank_create" / "ref.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Direct review board"})
    reference = store.create_asset(
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
            "title": "Approved direct board shot",
            "file_path": "output/frank_create/approved.png",
            "approval_status": "approved",
            "notes": "Lead this with the review board.",
        }
    )

    board = create_session_review_board(store, session["id"])
    image = Image.open(BytesIO(board["bytes"]))

    assert board["metadata"]["archive_path"] == "review/frank-create-review-board.png"
    assert board["metadata"]["approved_asset_count"] == 1
    assert board["metadata"]["reference_asset_count"] == 1
    assert board["metadata"]["width"] >= 1200
    assert board["metadata"]["height"] >= 800
    assert image.format == "PNG"
    assert image.size == (board["metadata"]["width"], board["metadata"]["height"])


def test_session_handoff_pack_includes_project_and_brief_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (700, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "approved.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    project = store.create_project(
        {
            "name": "Coffee Scrub Launch",
            "client": "Frank Body",
            "sync_status": "synced",
            "remote_id": "frankhub-project-1",
        }
    )
    brief = store.create_brief(
        {
            "project_id": project["id"],
            "title": "Coffee Scrub Campaign",
            "product_name": "Original Coffee Scrub",
            "task_type": "campaign-variants",
            "channel": "Paid social",
            "tone": "Cheeky but premium",
            "prompt": "Make it pop",
            "negative_prompt": "No warped label.",
            "sync_status": "pending",
            "remote_id": "frankhub-brief-1",
        }
    )
    session = store.create_session({"name": "Cliff Handoff", "project_id": project["id"], "summary": brief["title"]})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "local",
            "model": "frank-local-comfy",
            "prompt": brief["prompt"],
            "preset_key": "campaign-variants",
            "status": "complete",
        }
    )
    approved = store.create_asset(
        {
            "session_id": session["id"],
            "turn_id": turn["id"],
            "brief_id": brief["id"],
            "kind": "candidate",
            "title": "Approved. Hot.",
            "file_path": "output/frank_create/approved.png",
            "prompt": brief["prompt"],
            "approval_status": "approved",
        }
    )

    payload = create_session_handoff_pack(store, {"session_id": session["id"], "summary": "Client review pack"})

    with ZipFile(payload["file_path"]) as archive:
        manifest = json.loads(archive.read("frank-create-handoff.json"))
        readme = archive.read("README.md").decode("utf-8")

    assert payload["metadata"]["project_id"] == project["id"]
    assert payload["metadata"]["brief_id"] == brief["id"]
    assert manifest["project"]["name"] == "Coffee Scrub Launch"
    assert manifest["project"]["sync_status"] == "synced"
    assert manifest["project"]["remote_id"] == "frankhub-project-1"
    assert manifest["brief"]["title"] == "Coffee Scrub Campaign"
    assert manifest["brief"]["channel"] == "Paid social"
    assert manifest["brief"]["sync_status"] == "pending"
    assert manifest["brief"]["remote_id"] == "frankhub-brief-1"
    assert manifest["approved_assets"][0]["brief_id"] == brief["id"]
    assert "Coffee Scrub Launch" in readme
    assert "Coffee Scrub Campaign" in readme
    assert approved["id"] in manifest["counts"]["approved_asset_ids"]


def test_session_handoff_pack_counts_approved_images_and_videos(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (700, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "approved.png")
    Image.new("RGBA", (320, 180), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "motion.gif", "GIF")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Mixed handoff"})
    image = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "media_type": "image",
            "title": "Approved image",
            "file_path": "output/frank_create/approved.png",
            "approval_status": "approved",
        }
    )
    video = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "video",
            "media_type": "video",
            "title": "Approved motion",
            "file_path": "output/frank_create/motion.gif",
            "approval_status": "approved",
        }
    )

    payload = create_session_handoff_pack(store, {"session_id": session["id"]})

    assert payload["asset_id"] == image["id"]
    assert payload["metadata"]["asset_count"] == 2
    assert payload["metadata"]["image_count"] == 1
    assert payload["metadata"]["video_count"] == 1
    with ZipFile(payload["file_path"]) as archive:
        names = set(archive.namelist())
        readme = archive.read("README.md").decode("utf-8")
        manifest = json.loads(archive.read("frank-create-handoff.json"))

    assert any(name.endswith(f"{image['id']}.png") for name in names)
    assert any(name.endswith(f"{video['id']}.gif") for name in names)
    assert "- Approved images: 1" in readme
    assert "- Approved videos: 1" in readme
    assert [asset["media_type"] for asset in manifest["approved_assets"]] == ["image", "video"]


def test_session_handoff_pack_rejects_missing_approved_media(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Broken handoff"})
    approved = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved missing output",
            "file_path": "output/frank_create/missing-approved.png",
            "approval_status": "approved",
        }
    )

    try:
        create_session_handoff_pack(store, {"session_id": session["id"]})
    except FileNotFoundError as exc:
        message = str(exc)
        assert "approved asset media is unavailable" in message
        assert approved["id"] in message
        assert "missing-approved.png" in message
    else:
        raise AssertionError("handoff pack should reject missing approved media")


def test_session_handoff_pack_rejects_missing_reference_media(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))
    (tmp_path / "output" / "frank_create").mkdir(parents=True)
    Image.new("RGBA", (700, 900), (255, 183, 166, 255)).save(tmp_path / "output" / "frank_create" / "approved.png")

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "Broken reference handoff"})
    reference = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Missing coffee ref",
            "file_path": "input/frank_create/missing-ref.png",
        }
    )
    store.create_asset(
        {
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Approved output",
            "file_path": "output/frank_create/approved.png",
            "approval_status": "approved",
            "reference_asset_ids": [reference["id"]],
        }
    )

    try:
        create_session_handoff_pack(store, {"session_id": session["id"]})
    except FileNotFoundError as exc:
        message = str(exc)
        assert "reference asset media is unavailable" in message
        assert reference["id"] in message
        assert "missing-ref.png" in message
    else:
        raise AssertionError("handoff pack should reject missing reference media")


def test_session_handoff_pack_requires_an_approved_asset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(tmp_path))

    store = FrankCreateStore(db_path=tmp_path / "user" / "frank_create.db", root_dir=tmp_path / "user" / "frank_create")
    session = store.create_session({"name": "No approvals yet"})

    try:
        create_session_handoff_pack(store, {"session_id": session["id"]})
    except LookupError as exc:
        assert "Approve at least one asset" in str(exc)
    else:
        raise AssertionError("handoff pack should require an approved asset")
