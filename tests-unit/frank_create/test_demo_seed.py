import json

from PIL import Image

from custom_nodes.frank_create.demo_seed import (
    NANO_BANANA_DEMO_FILENAMES,
    NANO_BANANA_EDIT_PROOF_FILENAME,
    reset_and_seed_demo,
)
from custom_nodes.frank_create.store import FrankCreateStore


def test_reset_and_seed_demo_falls_back_to_local_candidate_images(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user")

    result = reset_and_seed_demo(store)

    session = result["session"]
    assets = store.list_assets(session_id=session["id"])
    references = [asset for asset in assets if asset["kind"] == "reference"]
    masks = [asset for asset in assets if asset["kind"] == "mask"]
    candidates = [asset for asset in assets if asset["kind"] == "candidate"]
    videos = [asset for asset in assets if asset["media_type"] == "video"]
    turns = store.list_turns(session_id=session["id"])
    output_ids = json.loads(turns[0]["output_asset_ids_json"])
    turn_reference_ids = json.loads(turns[0]["reference_asset_ids_json"])

    assert session["name"] == "Frank Body Demo Studio"
    assert len(references) == 1
    assert references[0]["title"] == "Frank Body Coffee Scrub Reference"
    assert references[0]["preview_url"].startswith("/api/view?")
    assert (media_root / "input" / "frank_create" / "frank-body-coffee-scrub-reference.png").exists()
    assert len(masks) == 1
    assert masks[0]["source_asset_id"] == result["assets"][0]["id"]
    assert (media_root / "input" / "frank_create" / "frank-body-coffee-scrub-mask.png").exists()
    assert len(candidates) == 5
    assert len(videos) == 1
    assert result["video_assets"][0]["id"] == videos[0]["id"]
    assert videos[0]["kind"] == "video"
    assert videos[0]["approval_status"] == "approved"
    assert videos[0]["favorite"] is True
    assert videos[0]["source_asset_id"] == result["assets"][1]["id"]
    assert json.loads(videos[0]["reference_asset_ids_json"]) == [references[0]["id"]]
    assert len(result["assets"]) == 5
    assert turn_reference_ids == [references[0]["id"]]
    assert output_ids == [asset["id"] for asset in result["assets"] if asset["turn_id"] == turns[0]["id"]]
    assert all(asset["provider"] == "local" for asset in candidates)
    assert all(asset["model"] == "frank-local-comfy" for asset in candidates)
    assert all(asset["preview_url"].startswith("/api/view?") for asset in candidates)
    assert all(json.loads(asset["reference_asset_ids_json"]) == [references[0]["id"]] for asset in candidates)
    approved = [asset for asset in candidates if asset["approval_status"] == "approved"]
    assert len(approved) == 1
    seed_pick = [asset for asset in approved if asset["notes"] == "Approved. Hot. Seed pick for Cliff demo."][0]
    assert seed_pick["favorite"] is True
    masked = [asset for asset in candidates if asset["source_asset_id"] == result["assets"][0]["id"]][0]
    assert masked["approval_status"] == "review"
    assert masked["favorite"] is False
    assert masked["notes"] == "Masked retouch proof for Cliff demo."
    provenance = json.loads(masked["settings_json"])["workflow_provenance"]
    assert provenance["workflow_key"] == "frank-local-masked-edit-renderer"
    assert provenance["mask_asset_id"] == masks[0]["id"]
    for asset in candidates:
        relative = asset["file_path"].replace("output/", "")
        assert (media_root / "output" / relative).exists()
    video_relative = videos[0]["file_path"].replace("output/", "")
    assert (media_root / "output" / video_relative).exists()


def test_reset_and_seed_demo_uses_cached_nano_banana_images_when_available(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    seed_dir = media_root / "input" / "frank_create"
    seed_dir.mkdir(parents=True)
    for index, filename in enumerate([*NANO_BANANA_DEMO_FILENAMES, NANO_BANANA_EDIT_PROOF_FILENAME]):
        Image.new("RGB", (128 + index, 96 + index), (255, 183, 166)).save(seed_dir / filename, "JPEG")
    monkeypatch.setenv("FRANK_CREATE_MEDIA_ROOT", str(media_root))
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user")

    result = reset_and_seed_demo(store)

    session = result["session"]
    assets = store.list_assets(session_id=session["id"])
    references = [asset for asset in assets if asset["kind"] == "reference"]
    masks = [asset for asset in assets if asset["kind"] == "mask"]
    candidates = [asset for asset in assets if asset["kind"] == "candidate"]
    videos = [asset for asset in assets if asset["media_type"] == "video"]
    turns = store.list_turns(session_id=session["id"])
    generate_turn = turns[0]
    edit_turn = turns[1]
    generate_ids = json.loads(generate_turn["output_asset_ids_json"])
    edit_ids = json.loads(edit_turn["output_asset_ids_json"])

    assert len(references) == 1
    assert len(masks) == 0
    assert len(videos) == 0
    assert len(candidates) == 5
    assert len(result["assets"]) == 5
    assert result["video_assets"] == []
    assert generate_turn["provider"] == "google"
    assert generate_turn["model"] == "google-nb-pro"
    assert generate_turn["status"] == "complete"
    assert generate_turn["frank_body_mode"] == 1
    assert edit_turn["provider"] == "google"
    assert edit_turn["kind"] == "edit"
    assert edit_turn["source_asset_id"] == result["assets"][0]["id"]
    assert generate_ids == [asset["id"] for asset in result["assets"][:4]]
    assert edit_ids == [result["assets"][4]["id"]]
    assert all(asset["provider"] == "google" for asset in candidates)
    assert all(asset["model"] == "google-nb-pro" for asset in candidates)
    assert all(asset["preview_url"].startswith("/api/view?") for asset in candidates)
    assert all(json.loads(asset["reference_asset_ids_json"]) == [references[0]["id"]] for asset in candidates)
    approved = [asset for asset in candidates if asset["approval_status"] == "approved"]
    assert len(approved) == 1
    assert approved[0]["favorite"] is True
    assert approved[0]["notes"] == "Approved. Hot. Live Nano Banana Pro seed pick for Cliff demo."
    edit_asset = result["assets"][4]
    assert edit_asset["source_asset_id"] == result["assets"][0]["id"]
    assert edit_asset["notes"] == "Nano Banana Pro edit proof for Cliff demo."
    assert (media_root / edit_asset["file_path"]).exists()
