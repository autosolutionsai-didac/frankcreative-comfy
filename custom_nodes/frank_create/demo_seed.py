from PIL import Image, ImageDraw

from .local_image import _input_dir, _view_url, run_local_studio_turn, run_local_video_storyboard
from .models import get_model
from .store import FrankCreateStore


DEMO_SETTINGS = {"aspect_ratio": "1:1", "image_size": "2K", "count": 4}
DEMO_MASKED_EDIT_SETTINGS = {"aspect_ratio": "1:1", "image_size": "2K", "count": 1}
DEMO_VIDEO_SETTINGS = {"aspect_ratio": "16:9", "image_size": "1K", "duration": 4}
DEMO_REFERENCE_FILENAME = "frank-body-coffee-scrub-reference.png"
DEMO_MASK_FILENAME = "frank-body-coffee-scrub-mask.png"
NANO_BANANA_MODEL = "google-nb-pro"
NANO_BANANA_PROVIDER = "google"
NANO_BANANA_DEMO_SETTINGS = {"aspect_ratio": "1:1", "image_size": "1K", "count": 4}
NANO_BANANA_DEMO_FILENAMES = (
    "frank-body-nano-banana-seed-01.jpg",
    "frank-body-nano-banana-seed-02.jpg",
    "frank-body-nano-banana-seed-03.jpg",
    "frank-body-nano-banana-seed-04.jpg",
)
NANO_BANANA_EDIT_PROOF_FILENAME = "frank-body-nano-banana-edit-proof.jpg"
NANO_BANANA_DEMO_PROMPT = (
    "Generate one single square ecommerce product photograph for Frank Body Original Coffee Scrub on a soft pink "
    "studio counter with warm coffee scrub texture, honest packaging edges, and clean director-ready lighting. "
    "No collage, no grid, no split screen, no duplicate panels."
)
NANO_BANANA_EDIT_PROMPT = (
    "Create one refined edit proof from the approved Frank Body product shot: keep the packaging honest, improve "
    "the product lighting, and preserve the soft pink ecommerce art direction."
)


def reset_and_seed_demo(store=None, create_assets=True):
    store = store or FrankCreateStore()
    result = store.reset_demo_state()
    assets = []
    mask_assets = []
    video_assets = []
    reference = None
    turn = result["turn"]

    if create_assets:
        reference = _create_demo_reference_asset(store, result["session"]["id"])
        cached_seed = _seed_cached_nano_banana_demo(store, result["session"]["id"], turn, reference)
        if cached_seed:
            turn, assets = cached_seed
        else:
            turn, assets = run_local_studio_turn(
                store,
                turn,
                {
                    "prompt": turn["prompt"],
                    "settings": DEMO_SETTINGS,
                    "preset_key": "product-shot-lab",
                    "reference_asset_ids": [reference["id"]],
                },
                get_model("frank-local-comfy"),
            )
            assets = _approve_seed_pick(store, assets)
            if assets:
                masked_assets, mask_assets = _create_demo_masked_edit(store, result["session"]["id"], assets[0], reference)
                if masked_assets:
                    assets = [assets[0], *masked_assets, *assets[1:]]
                video_source = masked_assets[0] if masked_assets else assets[0]
                video_assets = _create_demo_motion_storyboard(store, result["session"]["id"], video_source, reference)

    return {**result, "turn": turn, "reference": reference, "assets": assets, "mask_assets": mask_assets, "video_assets": video_assets}


def _approve_seed_pick(store, assets):
    if not assets:
        return assets
    seed_pick = store.update_asset(
        assets[0]["id"],
        {
            "approval_status": "approved",
            "favorite": True,
            "notes": "Approved. Hot. Seed pick for Cliff demo.",
        },
    )
    return [seed_pick] + assets[1:]


def _seed_cached_nano_banana_demo(store, session_id, turn, reference):
    seed_paths = [_input_dir() / "frank_create" / filename for filename in NANO_BANANA_DEMO_FILENAMES]
    edit_path = _input_dir() / "frank_create" / NANO_BANANA_EDIT_PROOF_FILENAME
    if not all(path.exists() for path in [*seed_paths, edit_path]):
        return None

    reference_ids = [reference["id"]] if reference else []
    updated_turn = store.update_turn(
        turn["id"],
        {
            "provider": NANO_BANANA_PROVIDER,
            "model": NANO_BANANA_MODEL,
            "prompt": NANO_BANANA_DEMO_PROMPT,
            "settings": NANO_BANANA_DEMO_SETTINGS,
            "reference_asset_ids": reference_ids,
            "frank_body_mode": True,
            "preset_key": "product-shot-lab",
            "status": "complete",
        },
    )

    generate_assets = [
        _create_cached_nano_banana_asset(
            store,
            session_id,
            updated_turn["id"],
            filename,
            index=index,
            prompt=NANO_BANANA_DEMO_PROMPT,
            reference_ids=reference_ids,
            approved=index == 1,
        )
        for index, filename in enumerate(NANO_BANANA_DEMO_FILENAMES, start=1)
    ]
    updated_turn = store.update_turn(updated_turn["id"], {"output_asset_ids": [asset["id"] for asset in generate_assets]})

    edit_turn = store.create_turn(
        {
            "session_id": session_id,
            "kind": "edit",
            "provider": NANO_BANANA_PROVIDER,
            "model": NANO_BANANA_MODEL,
            "prompt": NANO_BANANA_EDIT_PROMPT,
            "settings": {"aspect_ratio": "1:1", "image_size": "1K", "count": 1},
            "source_asset_id": generate_assets[0]["id"],
            "reference_asset_ids": reference_ids,
            "frank_body_mode": True,
            "preset_key": "product-cleanup",
            "status": "complete",
        }
    )
    edit_asset = _create_cached_nano_banana_asset(
        store,
        session_id,
        edit_turn["id"],
        NANO_BANANA_EDIT_PROOF_FILENAME,
        index=1,
        prompt=NANO_BANANA_EDIT_PROMPT,
        reference_ids=reference_ids,
        source_asset_id=generate_assets[0]["id"],
        title="Nano Banana Pro Edit Proof",
        notes="Nano Banana Pro edit proof for Cliff demo.",
    )
    store.update_turn(edit_turn["id"], {"output_asset_ids": [edit_asset["id"]]})
    return updated_turn, [*generate_assets, edit_asset]


def _create_cached_nano_banana_asset(
    store,
    session_id,
    turn_id,
    filename,
    *,
    index,
    prompt,
    reference_ids,
    approved=False,
    source_asset_id=None,
    title=None,
    notes=None,
):
    image_path = _input_dir() / "frank_create" / filename
    with Image.open(image_path) as image:
        width, height = image.size
    return store.create_asset(
        {
            "session_id": session_id,
            "turn_id": turn_id,
            "kind": "candidate",
            "title": title or f"Nano Banana Pro Product Shot {index:02d}",
            "media_type": "image",
            "provider": NANO_BANANA_PROVIDER,
            "model": NANO_BANANA_MODEL,
            "prompt": prompt,
            "settings": {
                "aspect_ratio": "1:1",
                "image_size": "1K",
                "workflow_provenance": {
                    "workflow_key": "google-nano-banana-live-seed",
                    "cached_live_output": True,
                    "source": "GOOGLE_API_KEY generated demo output",
                },
            },
            "source_asset_id": source_asset_id,
            "reference_asset_ids": reference_ids,
            "file_path": f"input/frank_create/{filename}",
            "preview_url": _view_url(filename, "frank_create", "input"),
            "width": width,
            "height": height,
            "favorite": approved,
            "approval_status": "approved" if approved else "review",
            "notes": notes
            or (
                "Approved. Hot. Live Nano Banana Pro seed pick for Cliff demo."
                if approved
                else "Live Nano Banana Pro product candidate for Cliff demo."
            ),
            "sync_status": "local",
        }
    )


def _create_demo_reference_asset(store, session_id):
    image_path = _input_dir() / "frank_create" / DEMO_REFERENCE_FILENAME
    image_path.parent.mkdir(parents=True, exist_ok=True)
    _draw_demo_product_reference().save(image_path, "PNG")
    return store.create_asset(
        {
            "session_id": session_id,
            "kind": "reference",
            "title": "Frank Body Coffee Scrub Reference",
            "media_type": "image",
            "file_path": f"input/frank_create/{DEMO_REFERENCE_FILENAME}",
            "preview_url": _view_url(DEMO_REFERENCE_FILENAME, "frank_create", "input"),
            "approval_status": "review",
            "sync_status": "local",
        }
    )


def _create_demo_masked_edit(store, session_id, source_asset, reference):
    mask = _create_demo_mask_asset(store, session_id, source_asset)
    turn = store.create_turn(
        {
            "session_id": session_id,
            "kind": "masked_edit",
            "model": "frank-local-comfy",
            "provider": "local",
            "prompt": "Retouch only the masked Frank Body label area; keep the product truth and packaging edges honest.",
            "settings": DEMO_MASKED_EDIT_SETTINGS,
            "source_asset_id": source_asset["id"],
            "reference_asset_ids": [reference["id"]] if reference else [],
            "preset_key": "product-cleanup",
            "status": "queued",
        }
    )
    _, masked_assets = run_local_studio_turn(
        store,
        turn,
        {
            "prompt": turn["prompt"],
            "settings": DEMO_MASKED_EDIT_SETTINGS,
            "edit_source_asset_id": source_asset["id"],
            "mask_asset_id": mask["id"],
            "reference_asset_ids": [reference["id"]] if reference else [],
            "preset_key": "product-cleanup",
        },
        get_model("frank-local-comfy"),
    )
    if masked_assets:
        masked_assets[0] = store.update_asset(
            masked_assets[0]["id"],
            {
                "approval_status": "review",
                "favorite": False,
                "notes": "Masked retouch proof for Cliff demo.",
            },
        )
    return masked_assets, [mask]


def _create_demo_mask_asset(store, session_id, source_asset):
    image_path = _input_dir() / "frank_create" / DEMO_MASK_FILENAME
    image_path.parent.mkdir(parents=True, exist_ok=True)
    _draw_demo_mask().save(image_path, "PNG")
    return store.create_asset(
        {
            "session_id": session_id,
            "kind": "mask",
            "title": "Frank Body Label Retouch Mask",
            "media_type": "image",
            "source_asset_id": source_asset["id"],
            "file_path": f"input/frank_create/{DEMO_MASK_FILENAME}",
            "preview_url": _view_url(DEMO_MASK_FILENAME, "frank_create", "input"),
            "approval_status": "review",
            "sync_status": "local",
        }
    )


def _create_demo_motion_storyboard(store, session_id, source_asset, reference):
    turn = store.create_turn(
        {
            "session_id": session_id,
            "kind": "video",
            "model": "frank-local-comfy",
            "provider": "local",
            "prompt": "Make a short Frank Body PDP motion board: product hero, coffee texture sweep, final packshot hold.",
            "settings": DEMO_VIDEO_SETTINGS,
            "source_asset_id": source_asset["id"],
            "reference_asset_ids": [reference["id"]] if reference else [],
            "preset_key": "video-lab",
            "status": "queued",
        }
    )
    _, storyboard_assets = run_local_video_storyboard(
        store,
        turn,
        {
            "prompt": turn["prompt"],
            "settings": DEMO_VIDEO_SETTINGS,
            "source_asset_id": source_asset["id"],
            "reference_asset_ids": [reference["id"]] if reference else [],
        },
        get_model("frank-local-comfy"),
    )
    if storyboard_assets:
        store.update_asset(
            storyboard_assets[0]["id"],
            {
                "approval_status": "approved",
                "favorite": True,
                "notes": "Approved motion board for the Cliff demo.",
            },
        )
    return storyboard_assets


def _draw_demo_product_reference():
    image = Image.new("RGBA", (900, 1200), (255, 250, 248, 0))
    draw = ImageDraw.Draw(image)

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((252, 116, 668, 1100), radius=58, fill=(63, 42, 45, 54))
    image.alpha_composite(shadow, (30, 34))

    pack = (236, 82, 660, 1082)
    draw.rounded_rectangle(pack, radius=58, fill=(255, 255, 255, 255), outline=(63, 42, 45, 255), width=7)
    draw.line((270, 134, 626, 126), fill=(63, 42, 45, 76), width=3)
    draw.line((274, 1034, 622, 1028), fill=(63, 42, 45, 72), width=3)
    draw.rounded_rectangle((264, 132, 632, 292), radius=34, fill=(255, 226, 218, 255), outline=(196, 17, 47, 218), width=5)
    draw.text((324, 164), "frank", fill=(63, 42, 45, 255))
    draw.text((324, 218), "body", fill=(63, 42, 45, 255))

    draw.rectangle((292, 360, 604, 367), fill=(63, 42, 45, 255))
    draw.text((302, 416), "original", fill=(91, 58, 51, 255))
    draw.text((302, 482), "coffee", fill=(63, 42, 45, 255))
    draw.text((302, 548), "scrub", fill=(63, 42, 45, 255))
    draw.text((302, 626), "body exfoliator", fill=(91, 58, 51, 255))
    draw.text((302, 678), "with robusta coffee", fill=(91, 58, 51, 230))

    for index in range(88):
        x = 300 + (index * 41) % 296
        y = 748 + (index * 59) % 210
        radius = 4 + index % 10
        alpha = 118 + (index * 13) % 112
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(91, 58, 51, alpha))

    draw.rounded_rectangle((308, 968, 592, 1018), radius=24, fill=(255, 183, 166, 255))
    draw.text((372, 984), "frank body", fill=(63, 42, 45, 255))
    return image


def _draw_demo_mask():
    image = Image.new("L", (900, 1200), 0)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((286, 156, 650, 1048), radius=44, fill=26)
    draw.rounded_rectangle((278, 154, 586, 260), radius=24, fill=255)
    draw.ellipse((318, 166, 410, 250), fill=255)
    draw.ellipse((430, 166, 552, 250), fill=255)
    return image
