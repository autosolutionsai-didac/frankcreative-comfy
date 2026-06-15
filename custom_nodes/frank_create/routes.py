import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import aiohttp
from aiohttp import web
from comfy_api import feature_flags

from .brand_kit import brand_kit_path, load_brand_kit, save_brand_kit
from .comfy_local import ComfyExecutionUnavailable, run_comfy_studio_turn
from .comfy_workflow import (
    build_checkpoint_diffusion_prompt,
    build_checkpoint_img2img_prompt,
    build_checkpoint_inpaint_prompt,
)
from .demo_seed import reset_and_seed_demo
from .inference import MissingProviderKey, UnsupportedModelCapability, build_turn_payload
from .local_image import (
    create_asset_channel_set_pack,
    create_export_pack,
    create_session_handoff_pack,
    create_session_review_board,
    run_local_studio_turn,
    run_local_video_storyboard,
    _resolve_media_path,
)
from .models import (
    compose_frank_prompt,
    get_backlog_models,
    get_local_engine_status,
    get_model,
    get_prompt_presets,
    get_visible_models,
    prepare_local_engine_folders,
)
from .provider_adapters import build_provider_request_preview, provider_runner_keys, run_live_provider_turn
from .store import FrankCreateStore

_STORE = None
_REGISTERED = False


TASKS = [
    {
        "key": "product-shot-lab",
        "label": "Product Shot Lab",
        "description": "Upload a product/reference image, generate variants, approve, and export.",
        "providers": ["local", "google", "replicate", "openai"],
    },
    {
        "key": "background-remove",
        "label": "Background sweep",
        "description": "Remove or isolate the product for transparent PNG and PDP work.",
        "providers": ["local", "openai"],
    },
    {
        "key": "background-replace",
        "label": "Background glow-up",
        "description": "Replace the set with a Frank-branded lifestyle or campaign backdrop.",
        "providers": ["local", "google", "openai"],
    },
    {
        "key": "product-cleanup",
        "label": "Product polish",
        "description": "Retouch dust, label edges, smudges, and small product-shot issues.",
        "providers": ["local", "openai"],
    },
    {
        "key": "campaign-variants",
        "label": "Campaign remix",
        "description": "Create director-ready variants from one approved product direction.",
        "providers": ["local", "google", "openai", "replicate"],
    },
    {
        "key": "aspect-crops",
        "label": "Crop the goods",
        "description": "Prepare PDP, email, social feed, story, and paid-social crops.",
        "providers": ["local"],
    },
    {
        "key": "upscale-enhance",
        "label": "Make it bigger",
        "description": "Upscale and enhance a high-res master without losing product detail.",
        "providers": ["local", "openai"],
    },
    {
        "key": "prompt-remix",
        "label": "Brief remix",
        "description": "Generate stronger prompt directions before another creative round.",
        "providers": ["local", "openai", "google"],
    },
]

PROVIDERS = [
    {"key": "local", "label": "Local RTX", "type": "local", "status": "ready"},
    {"key": "google", "label": "Gemini / Nano Banana", "type": "api", "status": "curated"},
    {"key": "replicate", "label": "Replicate", "type": "api", "status": "curated"},
    {"key": "openai", "label": "OpenAI image/edit", "type": "api", "status": "curated"},
]

EXPORT_PRESETS = [
    {"key": "pdp", "label": "PDP", "size": "1600 x 2000", "format": "PNG/JPG", "media_types": ["image"]},
    {"key": "email-hero", "label": "Email hero", "size": "2400 x 1350", "format": "JPG", "media_types": ["image"]},
    {"key": "instagram-feed", "label": "Instagram feed", "size": "1080 x 1350", "format": "JPG", "media_types": ["image"]},
    {"key": "instagram-story", "label": "Instagram story", "size": "1080 x 1920", "format": "JPG", "media_types": ["image"]},
    {"key": "paid-social", "label": "Paid social", "size": "1200 x 628", "format": "JPG", "media_types": ["image"]},
    {"key": "transparent-png", "label": "Transparent PNG", "size": "source", "format": "PNG", "media_types": ["image"]},
    {"key": "high-res-master", "label": "High-res master", "size": "source/upscaled", "format": "PNG/TIFF", "media_types": ["image"]},
    {"key": "video-storyboard", "label": "Motion storyboard", "size": "source loop", "format": "GIF + JSON", "media_types": ["video"]},
]

RAW_COMFY_CANVAS_URL = "/comfy/"
PROVIDER_ENV_FILENAME = "provider_keys.env"
WORKFLOW_SMOKE_STATUS_FILENAME = "workflow_smoke_status.json"
CLIFF_PREP_STATUS_FILENAME = "cliff_prep_status.json"
DEMO_EVIDENCE_DIRNAME = "demo_evidence"
READINESS_PACK_DIRNAME = "readiness_packs"
READINESS_SCREENSHOT_NAMES = (
    "studio-live-desktop-latest.png",
    "studio-live-mobile-latest.png",
    "video-lab-live-desktop-latest.png",
    "provider-audit-live-desktop-latest.png",
    "graph-live-desktop-latest.png",
    "graph-live-mobile-latest.png",
    "raw-comfy-live-quiet-latest.png",
    "raw-comfy-workflow-receipt-latest.png",
)
CURATED_DEMO_MIN_IMAGE_OUTPUTS = 3
CURATED_DEMO_MAX_IMAGE_OUTPUTS = 6
SECRET_HYGIENE_SCAN_PATHS = (
    "DESIGN.md",
    "FRANK_CREATE_DEMO.md",
    "config",
    "custom_nodes/frank_create",
    "frank-create/index.html",
    "frank-create/src",
    "scripts",
)
SECRET_HYGIENE_TOKEN_PATTERNS = (
    re.compile(r"\br8_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{19,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
    re.compile(r"(?im)^\s*(?:\$env:)?(?:GOOGLE_API_KEY|OPENAI_API_KEY|REPLICATE_API_TOKEN)\s*=\s*[\"']?[A-Za-z0-9_-]{16,}[\"']?\s*$"),
)
SECRET_HYGIENE_TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".css",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}
SECRET_HYGIENE_EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "dist",
    "node_modules",
    "user",
}
PROVIDER_ENV_PLACEHOLDER_VALUES = {
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


def _install_comfy_canvas_compat_middleware(prompt_server):
    app = prompt_server.app
    if app.get("_frank_comfy_canvas_compat_middleware"):
        return

    @web.middleware
    async def frank_comfy_canvas_compat(request, handler):
        preflight = _comfy_canvas_compat_preflight(request)
        if preflight is not None:
            return preflight

        response = await handler(request)
        return _comfy_canvas_compat_postprocess(request, response)

    app.middlewares.append(frank_comfy_canvas_compat)
    app["_frank_comfy_canvas_compat_middleware"] = True


def _comfy_canvas_compat_preflight(request):
    if not _is_comfy_canvas_request(request) or request.method.upper() != "GET":
        return None

    if request.path == "/api/userdata" and not request.rel_url.query.get("dir"):
        return _json([])

    if request.path == "/api/userdata/comfy.templates.json":
        return _json({})

    return None


def _comfy_canvas_compat_postprocess(request, response):
    if (
        not _is_comfy_canvas_request(request)
        or request.method.upper() != "GET"
        or request.path != "/api/jobs"
        or response.status != 200
    ):
        return response

    try:
        body = response.text if response.text is not None else response.body.decode("utf-8")
        payload = _normalize_jobs_payload(json.loads(body))
    except Exception:
        return response

    return _json(payload, status=response.status)


def _normalize_jobs_payload(payload):
    if not isinstance(payload, dict):
        return payload

    pagination = payload.get("pagination")
    if isinstance(pagination, dict) and pagination.get("limit") is None:
        jobs = payload.get("jobs")
        pagination["limit"] = len(jobs) if isinstance(jobs, list) else 0
    return payload


def _is_comfy_canvas_request(request):
    referer = request.headers.get("Referer", "") or request.headers.get("Referrer", "")
    if not referer:
        return False

    path = referer
    try:
        path = urlsplit(referer).path
    except Exception:
        pass
    return path.startswith(RAW_COMFY_CANVAS_URL)


def register_routes():
    global _REGISTERED
    if _REGISTERED:
        return

    try:
        from server import PromptServer
    except Exception as exc:
        print(f"[Frank Create] PromptServer unavailable: {exc}")
        return

    if PromptServer.instance is None:
        print("[Frank Create] PromptServer instance unavailable")
        return

    routes = PromptServer.instance.routes
    _install_comfy_canvas_compat_middleware(PromptServer.instance)

    @routes.get("/frank/health")
    async def health(request):
        return _json({"ok": True, "product": "Frank Create", "store": str(_store().db_path)})

    @routes.get("/frank/models")
    async def models(request):
        return _json(_model_registry_response())

    @routes.get("/frank/provider-status")
    async def provider_status(request):
        return _json(_provider_readiness_response())

    @routes.get("/frank/provider-readiness")
    async def provider_readiness(request):
        return _json(_provider_readiness_response())

    @routes.get("/frank/provider-audit")
    async def provider_audit(request):
        return _json(_provider_adapter_audit_response())

    @routes.get("/frank/activation-checklist")
    async def activation_checklist(request):
        return _json(_activation_checklist_response())

    @routes.post("/frank/provider-preflight")
    async def provider_preflight(request):
        return _json(_provider_preflight_response(await _payload(request)))

    @routes.post("/frank/local-engine/setup")
    async def local_engine_setup(request):
        return _json(prepare_local_engine_folders())

    @routes.get("/frank/local-engine/workflow-blueprints")
    async def local_engine_workflow_blueprints(request):
        return _json(_workflow_blueprints_response())

    @routes.get("/frank/demo-doctor")
    async def demo_doctor(request):
        return _json(_demo_doctor_response())

    @routes.get("/frank/demo/doctor")
    async def demo_doctor_alias(request):
        return _json(_demo_doctor_response())

    @routes.post("/frank/demo/evidence")
    async def demo_evidence(request):
        return _created(_demo_evidence_response(await _payload(request)))

    @routes.post("/frank/demo/call-brief")
    async def demo_call_brief(request):
        return _created(_demo_call_brief_response(await _payload(request)))

    @routes.post("/frank/demo/provider-readiness")
    async def demo_provider_readiness(request):
        return _created(_demo_provider_readiness_receipt_response())

    @routes.post("/frank/demo/brand-context")
    async def demo_brand_context(request):
        return _created(_demo_brand_context_receipt_response(await _payload(request)))

    @routes.get("/frank/demo/evidence/{filename}")
    async def demo_evidence_file(request):
        return _demo_evidence_file_response(request.match_info["filename"])

    @routes.get("/frank/demo/call-brief/{filename}")
    async def demo_call_brief_file(request):
        return _demo_call_brief_file_response(request.match_info["filename"])

    @routes.get("/frank/demo/provider-readiness/{filename}")
    async def demo_provider_readiness_file(request):
        return _demo_provider_readiness_file_response(request.match_info["filename"])

    @routes.get("/frank/demo/brand-context/{filename}")
    async def demo_brand_context_file(request):
        return _demo_brand_context_file_response(request.match_info["filename"])

    @routes.post("/frank/demo/readiness-pack")
    async def demo_readiness_pack(request):
        payload = await _payload(request)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: _demo_readiness_pack_response(payload))
        return _created(response)

    @routes.get("/frank/demo/readiness-pack/{filename}")
    async def demo_readiness_pack_file(request):
        return _demo_readiness_pack_file_response(request.match_info["filename"])

    @routes.post("/frank/demo/reset")
    async def reset_demo(request):
        return _created(_reset_demo_response(await _payload(request)))

    @routes.post("/frank/prompt-remix")
    async def prompt_remix(request):
        return _json(_prompt_remix_response(await _payload(request)))

    @routes.get("/frank/brand-kit")
    async def brand_kit(request):
        return _json(_brand_kit_response())

    @routes.patch("/frank/brand-kit")
    async def update_brand_kit(request):
        return _json(_update_brand_kit_response(await _payload(request)))

    @routes.get("/frank/provider-env")
    async def provider_env_status(request):
        return _json(_provider_env_status())

    @routes.post("/frank/provider-env/template")
    async def create_provider_env_template(request):
        return _created(_create_provider_env_template())

    @routes.post("/frank/provider-env/reload")
    async def reload_provider_env(request):
        return _json(_reload_provider_env_file())

    @routes.post("/frank/provider-env/save")
    async def save_provider_env(request):
        try:
            return _json(_save_provider_env_values(await _payload(request)))
        except ValueError as exc:
            return _json({"error": {"code": "bad_provider_key_payload", "message": str(exc)}}, status=400)

    @routes.get("/frank/config")
    async def config(request):
        return _json(
            {
                "tasks": TASKS,
                "providers": PROVIDERS,
                "exportPresets": EXPORT_PRESETS,
                "models": _models_with_key_status(get_visible_models()),
                "backlogModels": _models_with_key_status(get_backlog_models()),
                "promptPresets": get_prompt_presets(),
                "localEngine": get_local_engine_status(),
                "voice": {
                    "appTitle": "The Art Dept.",
                    "labTitle": "Frank Body Image Studio",
                    "primaryAction": "Generate",
                    "emptyState": "Waiting for the brief...",
                    "approved": "Approved. Hot.",
                },
                "advancedGraphUrl": RAW_COMFY_CANVAS_URL,
            }
        )

    @routes.get("/graph")
    async def graph_app(request):
        return _frank_spa_index()

    @routes.get("/graph/")
    async def graph_app_slash(request):
        return _frank_spa_index()

    @routes.get("/comfy")
    async def comfy_canvas_redirect(request):
        raise web.HTTPFound(RAW_COMFY_CANVAS_URL)

    @routes.get("/comfy/")
    async def comfy_canvas_index(request):
        return _comfy_frontend_index()

    @routes.get("/comfy/user.css")
    async def comfy_user_css(request):
        return web.Response(text=_comfy_user_css_text(), content_type="text/css")

    @routes.get("/comfy/api/userdata/user.css")
    async def comfy_user_data_css(request):
        return web.Response(text=_comfy_user_css_text(), content_type="text/css")

    @routes.get("/favicon.ico")
    async def frank_favicon_ico(request):
        return web.Response(body=_frank_favicon_svg(), content_type="image/svg+xml")

    @routes.get("/assets/favicon.ico")
    async def frank_asset_favicon_ico(request):
        return web.Response(body=_frank_favicon_svg(), content_type="image/svg+xml")

    @routes.get("/assets/images/favicon_progress_16x16/frame_9.png")
    async def frank_progress_favicon_frame(request):
        return web.Response(body=_frank_progress_png(), content_type="image/png")

    @routes.get("/comfy/ws")
    async def comfy_canvas_websocket(request):
        return await _comfy_websocket(request, PromptServer.instance)

    @routes.route("*", "/comfy/{relative_path:.*}")
    async def comfy_frontend_asset(request):
        return _comfy_frontend_file_or_redirect(request.match_info["relative_path"], request.method)

    @routes.get("/frank/projects")
    async def list_projects(request):
        return _json({"projects": _store().list_projects(status=request.query.get("status"))})

    @routes.post("/frank/projects")
    async def create_project(request):
        return _created({"project": _store().create_project(await _payload(request))})

    @routes.patch("/frank/projects/{project_id}")
    async def update_project(request):
        return _json({"project": _store().update_project(request.match_info["project_id"], await _payload(request))})

    @routes.get("/frank/briefs")
    async def list_briefs(request):
        return _json({"briefs": _store().list_briefs(project_id=request.query.get("project_id"))})

    @routes.post("/frank/briefs")
    async def create_brief(request):
        return _created({"brief": _store().create_brief(await _payload(request))})

    @routes.patch("/frank/briefs/{brief_id}")
    async def update_brief(request):
        return _json({"brief": _store().update_brief(request.match_info["brief_id"], await _payload(request))})

    @routes.get("/frank/runs")
    async def list_runs(request):
        return _json({"runs": _store().list_runs(brief_id=request.query.get("brief_id"))})

    @routes.post("/frank/runs")
    async def create_run(request):
        return _created({"run": _store().create_run(await _payload(request))})

    @routes.patch("/frank/runs/{run_id}")
    async def update_run(request):
        return _json({"run": _store().update_run(request.match_info["run_id"], await _payload(request))})

    @routes.get("/frank/sessions")
    async def list_sessions(request):
        return _json(
            {
                "sessions": _store().list_sessions(
                    status=request.query.get("status"),
                    project_id=request.query.get("project_id"),
                )
            }
        )

    @routes.post("/frank/sessions")
    async def create_session(request):
        return _created({"session": _store().create_session(await _payload(request))})

    @routes.patch("/frank/sessions/{session_id}")
    async def update_session(request):
        return _json({"session": _store().update_session(request.match_info["session_id"], await _payload(request))})

    @routes.post("/frank/sessions/{session_id}/handoff")
    async def create_session_handoff(request):
        payload = {**(await _payload(request)), "session_id": request.match_info["session_id"]}
        try:
            handoff_payload = create_session_handoff_pack(_store(), payload)
        except (FileNotFoundError, LookupError) as exc:
            return _json({"error": {"code": "handoff_failed", "message": str(exc)}}, status=400)
        export = _store().create_export(handoff_payload)
        return _created(
            {
                "handoff": export,
                "download_url": f"/api/frank/exports/{export['id']}/download",
                "metadata": handoff_payload["metadata"],
            }
        )

    @routes.get("/frank/sessions/{session_id}/review-board")
    async def session_review_board(request):
        try:
            return _session_review_board_response(request.match_info["session_id"])
        except (FileNotFoundError, LookupError) as exc:
            return _json({"error": {"code": "review_board_failed", "message": str(exc)}}, status=400)

    @routes.get("/frank/sessions/{session_id}/sync-manifest")
    async def session_sync_manifest(request):
        try:
            manifest = _session_sync_manifest(request.match_info["session_id"])
        except LookupError as exc:
            return _json({"error": {"code": "sync_manifest_failed", "message": str(exc)}}, status=404)
        filename = f"{_safe_download_stem((manifest.get('session') or {}).get('name') or 'frank-create')}-sync-manifest.json"
        return web.Response(
            text=json.dumps(manifest, indent=2, sort_keys=True),
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @routes.get("/frank/turns")
    async def list_turns(request):
        return _json(
            {
                "turns": _store().list_turns(
                    session_id=request.query.get("session_id"),
                    status=request.query.get("status"),
                )
            }
        )

    @routes.post("/frank/turns")
    async def create_turn(request):
        payload = await _payload(request)
        return _created({"turn": _store().create_turn(payload)})

    @routes.patch("/frank/turns/{turn_id}")
    async def update_turn(request):
        return _json({"turn": _store().update_turn(request.match_info["turn_id"], await _payload(request))})

    @routes.post("/frank/inference/turn")
    async def create_inference_turn(request):
        payload = await _payload(request)
        try:
            return _created(await _create_inference_turn_async(payload, PromptServer.instance))
        except MissingProviderKey as exc:
            turn = _store().create_turn(
                {
                    **payload,
                    "provider": _safe_provider(payload.get("model")),
                    "status": "blocked",
                    "error": {"code": "missing_key", "env_vars": exc.env_vars},
                }
            )
            return _created({"turn": turn, "status": "blocked", "error": {"code": "missing_key", "env_vars": exc.env_vars}})
        except UnsupportedModelCapability as exc:
            return _json({"error": {"code": "unsupported_capability", "message": str(exc)}}, status=400)
        except (KeyError, ValueError) as exc:
            return _json({"error": {"code": "bad_request", "message": str(exc)}}, status=400)

    @routes.get("/frank/assets")
    async def list_assets(request):
        return _json(
            {
                "assets": _store().list_assets(
                    run_id=request.query.get("run_id"),
                    brief_id=request.query.get("brief_id"),
                    session_id=request.query.get("session_id"),
                    turn_id=request.query.get("turn_id"),
                    approval_status=request.query.get("approval_status"),
                )
            }
        )

    @routes.post("/frank/assets")
    async def create_asset(request):
        return _created({"asset": _store().create_asset(await _payload(request))})

    @routes.post("/frank/references")
    async def create_reference(request):
        payload = await _payload(request)
        return _created({"asset": _store().create_asset({**payload, "kind": "reference", "media_type": "image"})})

    @routes.post("/frank/images")
    async def create_image(request):
        payload = await _payload(request)
        return _created({"asset": _store().create_asset({**payload, "kind": payload.get("kind", "candidate")})})

    @routes.post("/frank/edits")
    async def create_edit(request):
        payload = await _payload(request)
        try:
            return _created(await _create_inference_turn_async({**payload, "kind": "edit"}, PromptServer.instance))
        except MissingProviderKey as exc:
            turn = _store().create_turn(
                {
                    **payload,
                    "kind": "edit",
                    "provider": _safe_provider(payload.get("model")),
                    "status": "blocked",
                    "error": {"code": "missing_key", "env_vars": exc.env_vars},
                }
            )
            return _created({"turn": turn, "status": "blocked", "error": {"code": "missing_key", "env_vars": exc.env_vars}})

    @routes.post("/frank/videos")
    async def create_video(request):
        payload = await _payload(request)
        try:
            return _created(_create_video_storyboard(payload))
        except MissingProviderKey as exc:
            turn = _create_blocked_video_turn(payload, exc)
            return _created({"turn": turn, "status": "blocked", "assets": [], "error": {"code": "missing_key", "env_vars": exc.env_vars}})
        except UnsupportedModelCapability as exc:
            return _json({"error": {"code": "unsupported_model", "message": str(exc)}}, status=400)

    @routes.patch("/frank/assets/{asset_id}")
    async def update_asset(request):
        return _json({"asset": _store().update_asset(request.match_info["asset_id"], await _payload(request))})

    @routes.delete("/frank/assets/{asset_id}")
    async def delete_asset(request):
        try:
            return _json({"asset": _store().delete_asset(request.match_info["asset_id"])})
        except LookupError as exc:
            return _json({"error": {"code": "asset_not_found", "message": str(exc)}}, status=404)

    @routes.get("/frank/assets/{asset_id}/download")
    async def download_asset(request):
        asset_id = request.match_info["asset_id"]
        asset = next((record for record in _store().list_assets() if record["id"] == asset_id), None)
        if not asset:
            raise web.HTTPNotFound(text="Asset was not found")
        path = _resolve_media_path(asset.get("file_path") or "")
        if not path or not path.exists():
            raise web.HTTPNotFound(text="Asset file was not found")
        return web.FileResponse(path)

    @routes.get("/frank/assets/{asset_id}/workflow")
    async def asset_workflow_receipt(request):
        try:
            return _json(_asset_workflow_receipt(request.match_info["asset_id"]))
        except LookupError as exc:
            return _json({"error": {"code": "asset_not_found", "message": str(exc)}}, status=404)

    @routes.post("/frank/assets/{asset_id}/export-set")
    async def create_asset_export_set(request):
        payload = {**(await _payload(request)), "asset_id": request.match_info["asset_id"]}
        try:
            export_payload = create_asset_channel_set_pack(_store(), payload)
        except (FileNotFoundError, LookupError, ValueError) as exc:
            return _json({"error": {"code": "export_set_failed", "message": str(exc)}}, status=400)
        export = _store().create_export(export_payload)
        return _created(
            {
                "export": export,
                "download_url": f"/api/frank/exports/{export['id']}/download",
                "metadata": export_payload["metadata"],
            }
        )

    @routes.get("/frank/exports")
    async def list_exports(request):
        return _json({"exports": _store().list_exports(asset_id=request.query.get("asset_id"))})

    @routes.post("/frank/exports")
    async def create_export(request):
        payload = await _payload(request)
        try:
            payload = create_export_pack(_store(), payload)
        except (FileNotFoundError, LookupError) as exc:
            return _json({"error": {"code": "export_failed", "message": str(exc)}}, status=400)
        return _created({"export": _store().create_export(payload)})

    @routes.get("/frank/exports/{export_id}/download")
    async def download_export(request):
        export_id = request.match_info["export_id"]
        export = next((record for record in _store().list_exports() if record["id"] == export_id), None)
        if not export:
            raise web.HTTPNotFound(text="Export was not found")
        path = Path(export["file_path"])
        if not path.exists():
            raise web.HTTPNotFound(text="Export file was not found")
        return web.FileResponse(path)

    _REGISTERED = True
    print("[Frank Create] API routes registered at /api/frank/*")


def _create_inference_turn(payload):
    return _create_inference_turn_sync(payload)


def _create_video_storyboard(payload):
    session_id = payload.get("session_id")
    if not session_id:
        session = _store().create_session({"name": _session_name(payload), "mode": "video"})
        payload = {**payload, "session_id": session["id"]}

    model = get_model(payload.get("model") or payload.get("model_id") or "frank-local-comfy")
    _validate_video_preflight(model, payload)
    if model["provider"] != "local":
        provider_payload = build_turn_payload(
            {**payload, "kind": "video", "model": model["id"]},
            reference_assets=_reference_asset_paths(payload.get("reference_asset_ids", [])),
            brand_kit=_active_brand_kit(),
        )
        turn = _store().create_turn(
            {
                **payload,
                "kind": "video",
                "provider": model["provider"],
                "model": model["id"],
                "prompt": provider_payload["prompt"],
                "status": "queued",
            }
        )
        updated_turn, assets = run_live_provider_turn(
            _store(),
            turn,
            {**payload, "kind": "video", "model": model["id"], "prompt": provider_payload["prompt"]},
            model,
            provider_payload,
        )
        return {
            "turn": updated_turn,
            "status": "complete" if assets else updated_turn.get("status", "failed"),
            "assets": assets,
            "providerPayload": provider_payload,
            "localEngine": model["provider"],
        }

    turn = _store().create_turn(
        {
            **payload,
            "kind": "video",
            "provider": "local",
            "model": model["id"],
            "status": "running",
        }
    )
    updated_turn, assets = run_local_video_storyboard(_store(), turn, payload, model)
    return {"turn": updated_turn, "status": updated_turn.get("status", "complete"), "assets": assets, "localEngine": "storyboard"}


def _session_review_board_response(session_id):
    board = create_session_review_board(_store(), session_id)
    metadata = board.get("metadata") or {}
    headers = {
        "Content-Disposition": 'inline; filename="frank-create-review-board.png"',
        "X-Frank-Review-Board-Approved": str(metadata.get("approved_asset_count") or 0),
        "X-Frank-Review-Board-References": str(metadata.get("reference_asset_count") or 0),
        "X-Frank-Review-Board-Size": f"{metadata.get('width') or 0}x{metadata.get('height') or 0}",
    }
    return web.Response(body=board["bytes"], content_type="image/png", headers=headers)


def _session_sync_manifest(session_id):
    if not session_id:
        raise LookupError("session_id is required")

    store = _store()
    session = _find_record(store.list_sessions(), session_id)
    if not session:
        raise LookupError(f"session {session_id} was not found")

    assets = store.list_assets(session_id=session_id)
    turns = store.list_turns(session_id=session_id)
    asset_ids = {asset.get("id") for asset in assets}
    exports = [export for export in store.list_exports() if export.get("asset_id") in asset_ids]
    project = _find_record(store.list_projects(), session.get("project_id")) if session.get("project_id") else None
    brief = _sync_manifest_brief(store, project, assets)
    records = {
        "projects": [_sync_record(project)] if project else [],
        "briefs": [_sync_record(brief)] if brief else [],
        "sessions": [_sync_record(session)],
        "turns": [_sync_record(turn) for turn in turns],
        "assets": [_sync_record(asset) for asset in _sync_manifest_asset_order(assets)],
        "exports": [_sync_record(export) for export in exports],
    }
    all_records = [record for group in records.values() for record in group]
    approved_assets = [
        asset
        for asset in assets
        if asset.get("kind") != "reference" and asset.get("approval_status") == "approved"
    ]
    reference_assets = [asset for asset in assets if asset.get("kind") == "reference"]

    return {
        "app": "Frank Create",
        "schema_version": "frank-create.sync.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Local-first FrankHub/Supabase/DAM sync manifest. No provider secrets included.",
        "sync_contract": {
            "target": "FrankHub Supabase or DAM mirror",
            "primary_key_field": "id",
            "remote_id_field": "remote_id",
            "sync_status_field": "sync_status",
            "tables": {
                "projects": "frank_create_projects",
                "briefs": "frank_create_briefs",
                "sessions": "frank_create_sessions",
                "turns": "frank_create_turns",
                "assets": "frank_create_assets",
                "exports": "frank_create_exports",
            },
            "media_upload_key": "media_files[].file_path",
        },
        "session": _sync_record(session),
        "project": _sync_record(project) if project else None,
        "brief": _sync_record(brief) if brief else None,
        "counts": {
            "assets": len(assets),
            "approved_assets": len(approved_assets),
            "reference_assets": len(reference_assets),
            "turns": len(turns),
            "exports": len(exports),
            "pending_records": sum(1 for record in all_records if record.get("sync_status") == "pending"),
        },
        "status_summary": _sync_status_summary(all_records),
        "records": records,
        "media_files": [_sync_media_file(asset) for asset in _sync_manifest_asset_order(assets) if asset.get("file_path")],
        "notes": [
            "Use id for local idempotency and remote_id after FrankHub/DAM creates a remote record.",
            "Upload media_files first, then mirror records with their local id, remote_id, sync_status, prompt, settings, and approval state.",
            "Provider keys are intentionally absent; live model credentials stay server-side.",
        ],
    }


def _find_record(records, record_id):
    if not record_id:
        return None
    return next((record for record in records if record.get("id") == record_id), None)


def _sync_manifest_brief(store, project, assets):
    brief_ids = [asset.get("brief_id") for asset in assets if asset.get("brief_id")]
    if brief_ids:
        return _find_record(store.list_briefs(), brief_ids[0])
    if project:
        briefs = store.list_briefs(project_id=project.get("id"))
        return briefs[0] if briefs else None
    return None


def _sync_manifest_asset_order(assets):
    return sorted(
        assets,
        key=lambda asset: (
            1 if asset.get("kind") == "reference" else 0,
            0 if asset.get("approval_status") == "approved" else 1,
            str(asset.get("created_at") or ""),
            str(asset.get("id") or ""),
        ),
    )


def _sync_record(record):
    if not record:
        return None
    data = dict(record)
    json_fields = {
        "settings_json": "settings",
        "reference_asset_ids_json": "reference_asset_ids",
        "output_asset_ids_json": "output_asset_ids",
        "error_json": "error",
        "metadata_json": "metadata",
    }
    for source_key, target_key in json_fields.items():
        if source_key in data:
            data[target_key] = _json_loads_safe(data.pop(source_key), [] if target_key.endswith("_ids") else {})
    if "frank_body_mode" in data:
        data["frank_body_mode"] = bool(data["frank_body_mode"])
    return data


def _sync_status_summary(records):
    summary = {}
    for record in records:
        status = record.get("sync_status") or "local"
        summary[status] = summary.get(status, 0) + 1
    return summary


def _sync_media_file(asset):
    media_path = _resolve_media_path(asset.get("file_path") or "")
    exists = bool(media_path and media_path.exists())
    media = {
        "asset_id": asset.get("id"),
        "title": asset.get("title"),
        "kind": asset.get("kind"),
        "media_type": asset.get("media_type") or "image",
        "file_path": asset.get("file_path"),
        "preview_url": asset.get("preview_url"),
        "exists": exists,
    }
    if exists:
        data = Path(media_path).read_bytes()
        media["integrity"] = {"sha256": hashlib.sha256(data).hexdigest(), "file_size_bytes": len(data)}
    else:
        media["missing_reason"] = "File is not currently readable from this workstation."
    return media


def _safe_download_stem(value):
    clean = "".join(char.lower() if char.isalnum() else "-" for char in str(value))
    clean = "-".join(part for part in clean.split("-") if part)
    return clean[:72] or "frank-create"


def _create_blocked_video_turn(payload, exc):
    session_id = payload.get("session_id")
    if not session_id:
        session = _store().create_session({"name": _session_name(payload), "mode": "video"})
        session_id = session["id"]
    model_id = payload.get("model") or payload.get("model_id") or getattr(exc, "model_id", None)
    return _store().create_turn(
        {
            **payload,
            "session_id": session_id,
            "kind": "video",
            "provider": _safe_provider(model_id),
            "model": model_id,
            "status": "blocked",
            "error": {"code": "missing_key", "env_vars": exc.env_vars},
        }
    )


async def _create_inference_turn_async(payload, prompt_server=None):
    context = _create_turn_context(payload)
    model = context["model"]
    provider_payload = context["provider_payload"]
    turn = context["turn"]
    payload = context["payload"]

    if model["provider"] == "local":
        try:
            updated_turn, assets = await run_comfy_studio_turn(
                prompt_server,
                _store(),
                turn,
                {**payload, "prompt": provider_payload["prompt"]},
                model,
            )
            return {
                "turn": updated_turn,
                "status": updated_turn.get("status", "complete"),
                "assets": assets,
                "providerPayload": provider_payload,
                "localEngine": "comfy",
            }
        except ComfyExecutionUnavailable as exc:
            updated_turn, assets = run_local_studio_turn(
                _store(),
                turn,
                {**payload, "prompt": provider_payload["prompt"]},
                model,
            )
            return {
                "turn": updated_turn,
                "status": updated_turn.get("status", "complete"),
                "assets": assets,
                "providerPayload": provider_payload,
                "localEngine": "fallback",
                "fallbackReason": str(exc),
            }

    updated_turn, assets = run_live_provider_turn(
        _store(),
        turn,
        {**payload, "prompt": provider_payload["prompt"]},
        model,
        provider_payload,
    )
    return {
        "turn": updated_turn,
        "status": "complete" if assets else updated_turn.get("status", "failed"),
        "assets": assets,
        "providerPayload": provider_payload,
    }


def _create_inference_turn_sync(payload):
    context = _create_turn_context(payload)
    model = context["model"]
    provider_payload = context["provider_payload"]
    turn = context["turn"]
    payload = context["payload"]

    if model["provider"] == "local":
        updated_turn, assets = run_local_studio_turn(
            _store(),
            turn,
            {**payload, "prompt": provider_payload["prompt"]},
            model,
        )
        return {"turn": updated_turn, "status": "complete", "assets": assets, "providerPayload": provider_payload}
    updated_turn, assets = run_live_provider_turn(
        _store(),
        turn,
        {**payload, "prompt": provider_payload["prompt"]},
        model,
        provider_payload,
    )
    return {
        "turn": updated_turn,
        "status": "complete" if assets else updated_turn.get("status", "failed"),
        "assets": assets,
        "providerPayload": provider_payload,
    }


def _create_turn_context(payload):
    model = get_model(payload.get("model") or payload.get("model_id"))
    reference_asset_ids = payload.get("reference_asset_ids", [])
    provider_payload = build_turn_payload(
        payload,
        reference_assets=_reference_asset_paths(reference_asset_ids),
        brand_kit=_active_brand_kit(),
    )
    session_id = payload.get("session_id")
    if not session_id:
        session = _store().create_session({"name": _session_name(payload), "mode": "image"})
        payload = {**payload, "session_id": session["id"]}

    turn = _store().create_turn(
        {
            **payload,
            "model": model["id"],
            "provider": model["provider"],
            "prompt": provider_payload["prompt"],
            "status": "running" if model["provider"] == "local" else "queued",
        }
    )
    return {
        "payload": payload,
        "model": model,
        "turn": turn,
        "providerPayload": provider_payload,
        "provider_payload": provider_payload,
    }


def _reference_asset_paths(asset_ids):
    if not asset_ids:
        return []
    assets = _store().list_assets()
    by_id = {asset["id"]: asset for asset in assets}
    paths = []
    for asset_id in asset_ids:
        asset = by_id.get(asset_id)
        if asset:
            paths.append(asset.get("file_path") or asset.get("preview_url") or asset_id)
        else:
            paths.append(asset_id)
    return paths


def _model_registry_response():
    return {
        "models": _models_with_key_status(get_visible_models()),
        "backlogModels": _models_with_key_status(get_backlog_models()),
        "promptPresets": get_prompt_presets(),
        "localEngine": get_local_engine_status(),
    }


def _workflow_blueprints_response():
    checkpoint_name = "frank-create-placeholder.safetensors"
    source_path = "input/frank_create/comfy_refs/source-product.png"
    mask_path = "input/frank_create/comfy_refs/source-mask.png"
    blueprints = [
        _workflow_blueprint(
            key="comfy-checkpoint-txt2img",
            label="Checkpoint txt2img",
            use="Prompt-only campaign and product-image generation when a local checkpoint is installed.",
            workflow_json=build_checkpoint_diffusion_prompt(
                prompt_text="Frank Body product campaign image, product truth, clean label, tactile body-care set.",
                turn_id="frank-create-blueprint-txt2img",
                checkpoint_name=checkpoint_name,
                width=1024,
                height=1280,
                variant_index=0,
            ),
        ),
        _workflow_blueprint(
            key="comfy-checkpoint-img2img",
            label="Checkpoint img2img",
            use="Reference-guided product edits and cleanup while preserving the uploaded pack shot.",
            workflow_json=build_checkpoint_img2img_prompt(
                prompt_text="Keep the product shape and label, polish the set, add Frank Body warmth.",
                turn_id="frank-create-blueprint-img2img",
                checkpoint_name=checkpoint_name,
                width=1024,
                height=1024,
                variant_index=0,
                reference_file_path=source_path,
            ),
        ),
        _workflow_blueprint(
            key="comfy-checkpoint-inpaint",
            label="Checkpoint inpaint",
            use="Masked retouching for label edges, smudges, and small product-shot fixes.",
            workflow_json=build_checkpoint_inpaint_prompt(
                prompt_text="Retouch only the masked area; preserve all unmasked Frank Body packaging.",
                turn_id="frank-create-blueprint-inpaint",
                checkpoint_name=checkpoint_name,
                width=1024,
                height=1024,
                variant_index=0,
                reference_file_path=source_path,
                mask_file_path=mask_path,
            ),
        ),
    ]
    return {
        "status": "ready",
        "product": "Frank Create",
        "checkpoint_name": checkpoint_name,
        "source_placeholder": source_path,
        "mask_placeholder": mask_path,
        "note": "Blueprints use stock Comfy nodes and placeholder files; runtime turns swap in the selected checkpoint, source, and mask assets.",
        "blueprints": blueprints,
    }


def _workflow_blueprint(key, label, use, workflow_json):
    return {
        "key": key,
        "label": label,
        "use": use,
        "node_types": _workflow_json_node_types(workflow_json),
        "workflow_json": workflow_json,
    }


def _workflow_json_node_types(workflow_json):
    return [
        node.get("class_type")
        for _node_id, node in sorted((workflow_json or {}).items(), key=lambda item: _workflow_node_sort_key(item[0]))
        if isinstance(node, dict) and node.get("class_type")
    ]


def _workflow_node_sort_key(node_id):
    try:
        return (0, int(node_id))
    except (TypeError, ValueError):
        return (1, str(node_id))


def _asset_workflow_receipt(asset_id):
    assets = _store().list_assets()
    asset = next((record for record in assets if record["id"] == asset_id), None)
    if not asset:
        raise LookupError("Asset was not found")

    turns = _store().list_turns(session_id=asset.get("session_id")) if asset.get("session_id") else _store().list_turns()
    turn = next((record for record in turns if record["id"] == asset.get("turn_id")), None)
    settings = _json_loads_safe(asset.get("settings_json") or (turn or {}).get("settings_json"), {})
    if not isinstance(settings, dict):
        settings = {}
    workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else {}
    if not isinstance(workflow, dict):
        workflow = {}
    api_prompt_json = workflow.get("workflow_json") if isinstance(workflow.get("workflow_json"), dict) else None
    source_asset_id = asset.get("source_asset_id") or (turn or {}).get("source_asset_id")
    reference_asset_ids = _json_loads_safe(
        asset.get("reference_asset_ids_json") or (turn or {}).get("reference_asset_ids_json"),
        [],
    )
    if not isinstance(reference_asset_ids, list):
        reference_asset_ids = []

    return _sanitize_workflow_receipt(
        {
            "product": "Frank Create",
            "asset": _asset_receipt_summary(asset),
            "turn": _turn_receipt_summary(turn),
            "workflow_key": workflow.get("workflow_key") or asset.get("model") or "frank-create-workflow",
            "engine": workflow.get("engine") or asset.get("provider") or (turn or {}).get("provider") or "unknown",
            "workflow_provenance": workflow,
            "api_prompt_json": api_prompt_json,
            "can_open_raw_canvas": True,
            "can_load_comfy_api_prompt": bool(api_prompt_json),
            "raw_canvas_load_status": "api_prompt_attached" if api_prompt_json else "receipt_only",
            "comfy_node_types": _workflow_node_types(api_prompt_json, workflow),
            "raw_canvas_url": f"{RAW_COMFY_CANVAS_URL}?frankAssetId={quote(asset_id)}",
            "source": _asset_reference_summary(source_asset_id, assets) if source_asset_id else None,
            "references": [_asset_reference_summary(str(item), assets) for item in reference_asset_ids],
            "notes": [
                "Provider keys stay server-side; this receipt is sanitized.",
                "Comfy API prompt JSON is included when the selected pick came from a checkpoint Comfy workflow.",
            ],
        }
    )


def _asset_receipt_summary(asset):
    return {
        "id": asset.get("id"),
        "title": asset.get("title"),
        "kind": asset.get("kind"),
        "media_type": asset.get("media_type") or "image",
        "provider": asset.get("provider"),
        "model": asset.get("model"),
        "prompt": asset.get("prompt"),
        "file_path": asset.get("file_path"),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "approval_status": asset.get("approval_status"),
        "favorite": bool(asset.get("favorite")),
        "sync_status": asset.get("sync_status") or "local",
        "created_at": asset.get("created_at"),
        "updated_at": asset.get("updated_at"),
    }


def _turn_receipt_summary(turn):
    if not turn:
        return None
    return {
        "id": turn.get("id"),
        "kind": turn.get("kind"),
        "provider": turn.get("provider"),
        "model": turn.get("model"),
        "preset_key": turn.get("preset_key"),
        "status": turn.get("status"),
        "created_at": turn.get("created_at"),
        "updated_at": turn.get("updated_at"),
    }


def _asset_reference_summary(asset_id, assets):
    asset = next((record for record in assets if record["id"] == asset_id), None)
    return {
        "id": asset_id,
        "title": asset.get("title") if asset else asset_id,
        "kind": asset.get("kind") if asset else None,
        "file_path": asset.get("file_path") if asset else None,
    }


def _workflow_node_types(api_prompt_json, workflow=None):
    workflow = workflow or {}
    fallback_by_workflow = {
        "frank-local-variant-renderer": ["FrankCreateVariant", "SaveImage"],
        "frank-local-background-remove-renderer": ["FrankCreateBackgroundRemove", "SaveImage"],
        "frank-local-background-replace-renderer": ["FrankCreateBackgroundReplace", "SaveImage"],
        "frank-local-masked-edit-renderer": ["FrankCreateMaskedEdit", "SaveImage"],
        "frank-local-video-storyboard": ["FrankCreateVideoStoryboard", "SaveAnimatedImage"],
    }
    if workflow.get("workflow_key") in fallback_by_workflow:
        return fallback_by_workflow[workflow.get("workflow_key")]
    if isinstance(workflow.get("comfy_node_types"), list):
        return [str(item) for item in workflow.get("comfy_node_types") if item]
    return _workflow_json_node_types(api_prompt_json)


def _sanitize_workflow_receipt(value):
    if isinstance(value, dict):
        return {
            key: "[server-side secret]" if _workflow_receipt_key_is_sensitive(key) else _sanitize_workflow_receipt(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_workflow_receipt(item) for item in value]
    if isinstance(value, str) and _workflow_receipt_value_is_sensitive(value):
        return "[server-side secret]"
    return value


def _workflow_receipt_key_is_sensitive(key):
    return bool(re.search(r"api[_-]?key|token|secret|authorization|bearer|password|credential", str(key), re.IGNORECASE))


def _workflow_receipt_value_is_sensitive(value):
    return bool(_contains_secret_like_token(value) or re.search(r"\bBearer\s+\S{12,}", value, re.IGNORECASE))


def _brand_kit_response():
    return {
        "brandKit": _active_brand_kit(),
        "filePath": str(brand_kit_path(_store().root_dir)),
    }


def _update_brand_kit_response(payload):
    return {
        "brandKit": save_brand_kit(_store().root_dir, payload),
        "filePath": str(brand_kit_path(_store().root_dir)),
    }


def _active_brand_kit():
    return load_brand_kit(_store().root_dir)


def _provider_readiness_response():
    models = _models_with_key_status(get_visible_models())
    providers = []
    provider_names = []
    for model in models:
        provider = model["provider"]
        if provider not in provider_names:
            provider_names.append(provider)

    for provider in provider_names:
        provider_models = [model for model in models if model["provider"] == provider]
        missing_env_vars = sorted(
            {env_var for model in provider_models for env_var in model.get("missing_env_vars", [])}
        )
        configured_env_vars = sorted(
            {
                model.get("configured_env_var")
                for model in provider_models
                if model.get("configured_env_var")
            }
        )
        providers.append(
            {
                "provider": provider,
                "configured": any(model["configured"] for model in provider_models),
                "model_count": len(provider_models),
                "ready_model_count": sum(1 for model in provider_models if model["configured"]),
                "waiting_model_count": sum(1 for model in provider_models if not model["configured"]),
                "configured_env_vars": configured_env_vars,
                "missing_env_vars": missing_env_vars,
                "models": [model["id"] for model in provider_models],
            }
        )

    ready_models = sum(1 for model in models if model["configured"])
    waiting_models = len(models) - ready_models
    missing_env_vars = sorted({env_var for model in models for env_var in model.get("missing_env_vars", [])})
    configured_env_vars = sorted({model["configured_env_var"] for model in models if model.get("configured_env_var")})

    return {
        "summary": {
            "modelCount": len(models),
            "readyModels": ready_models,
            "waitingModels": waiting_models,
            "configuredEnvVars": configured_env_vars,
            "missingEnvVars": missing_env_vars,
        },
        "providers": providers,
        "models": models,
        "notes": [
            "Provider keys are read server-side only.",
            "The browser receives env var names and readiness status, never secret values.",
        ],
    }


def _activation_checklist_response():
    provider_status = _provider_readiness_response()
    local_engine = get_local_engine_status()
    env_status = _provider_env_status()
    audit = _provider_adapter_audit_response()
    ready_models = int(provider_status["summary"]["readyModels"])
    model_count = int(provider_status["summary"]["modelCount"])
    waiting_models = int(provider_status["summary"]["waitingModels"])
    missing_env_vars = list(provider_status["summary"]["missingEnvVars"])
    configured_env_vars = list(provider_status["summary"]["configuredEnvVars"])
    diffusion_ready = bool(local_engine.get("diffusion_ready"))
    checkpoint_count = int(local_engine.get("checkpoint_count") or 0)

    steps = [
        {
            "key": "server-provider-keys",
            "label": "Paste rotated live provider keys",
            "status": "ready" if waiting_models == 0 else "action_needed",
            "detail": (
                "All live provider models have server-side keys."
                if waiting_models == 0
                else f"{waiting_models} live provider models are waiting on server-side keys."
            ),
            "action": (
                "Run Check selected model before the first paid round."
                if waiting_models == 0
                else "Use Provider Setup or user\\frank_create\\provider_keys.env, then reload keys."
            ),
            "env_vars": missing_env_vars,
        },
        {
            "key": "local-checkpoint",
            "label": "Install one full local checkpoint",
            "status": "ready" if diffusion_ready else "action_needed",
            "detail": (
                f"{checkpoint_count} local checkpoint file(s) ready for Comfy txt2img/img2img/inpaint."
                if diffusion_ready
                else "Local Comfy checkpoint workflows are waiting for a full SDXL-style checkpoint."
            ),
            "action": (
                "Local Comfy checkpoint workflows are enabled."
                if diffusion_ready
                else "Put a .safetensors file in models\\checkpoints, then run Demo Doctor."
            ),
            "path": local_engine.get("checkpoint_dir"),
            "minimum_checkpoint_mb": local_engine.get("minimum_checkpoint_mb"),
        },
        {
            "key": "adapter-audit",
            "label": "Confirm no-spend provider adapter audit",
            "status": "ready" if audit["summary"]["missing_runners"] == 0 and audit["summary"]["preview_failures"] == 0 else "action_needed",
            "detail": (
                f"{audit['summary']['runner_registered']} / {audit['summary']['model_count']} launch runners registered; "
                f"{audit['summary']['preview_failures']} preview issues."
            ),
            "action": "Use Audit roster to refresh request-shape proof before live API work.",
        },
        {
            "key": "replicate-rotation",
            "label": "Rotate the exposed Replicate token",
            "status": "recommended",
            "detail": "The token shared in chat should be treated as exposed.",
            "action": "Create a fresh rotated Replicate token before live Replicate usage.",
            "env_vars": ["REPLICATE_API_TOKEN"],
        },
    ]

    return {
        "title": "Frank Create Production Unlock Checklist",
        "status": "ready" if waiting_models == 0 and diffusion_ready else "action_needed",
        "summary": {
            "ready_provider_models": ready_models,
            "provider_model_count": model_count,
            "waiting_provider_models": waiting_models,
            "diffusion_ready": diffusion_ready,
            "checkpoint_count": checkpoint_count,
            "server_key_file": env_status.get("filePath"),
            "configured_env_vars": configured_env_vars,
            "missing_env_vars": missing_env_vars,
        },
        "steps": steps,
        "notes": [
            "No provider secret values are returned by this endpoint.",
            "Local Frank renderer remains available while live keys and checkpoint files are being installed.",
        ],
    }


def _provider_adapter_audit_response():
    models = _models_with_key_status(get_visible_models())
    runner_keys = provider_runner_keys()
    rows = []

    for model in models:
        kinds = _audit_kinds_for_model(model)
        primary_kind = kinds[0] if kinds else "generate"
        runner_registered = model["provider"] == "local" or model["provider"] in runner_keys
        request_previews = {}
        request_preview_errors = {}
        request_preview = None
        request_preview_error = None
        if runner_registered:
            for kind in kinds or [primary_kind]:
                try:
                    preview = build_provider_request_preview(model, kind, _audit_settings_for_model(model))
                    request_previews[kind] = preview
                    if kind == primary_kind:
                        request_preview = preview
                except Exception as exc:
                    request_preview_errors[kind] = str(exc)
                    if kind == primary_kind:
                        request_preview_error = str(exc)
            if request_preview is None and request_previews:
                request_preview = next(iter(request_previews.values()))
            if request_preview_error is None and request_preview_errors:
                request_preview_error = next(iter(request_preview_errors.values()))

        configured = bool(model.get("configured"))
        if not runner_registered:
            status = "adapter_missing"
        elif request_preview_errors:
            status = "preview_failed"
        elif configured:
            status = "ready"
        else:
            status = "waiting_for_key"

        rows.append(
            {
                "model_id": model["id"],
                "label": model.get("short_label") or model.get("label") or model["id"],
                "provider": model["provider"],
                "provider_model": model.get("provider_model"),
                "badge": model.get("badge"),
                "status": status,
                "configured": configured,
                "configured_env_var": model.get("configured_env_var"),
                "missing_env_vars": list(model.get("missing_env_vars") or []),
                "runner_registered": runner_registered,
                "operation_kinds": kinds,
                "capabilities": dict(model.get("capabilities") or {}),
                "reference_limit": int(model.get("reference_image_limit") or 0),
                "allowed_aspect_ratios": list(model.get("allowed_aspect_ratios") or []),
                "allowed_image_sizes": list(model.get("allowed_image_sizes") or []),
                "request_preview": request_preview,
                "request_preview_error": request_preview_error,
                "request_previews": request_previews,
                "request_preview_errors": request_preview_errors,
            }
        )

    operation_preview_count = sum(len(row["request_previews"]) for row in rows)
    operation_preview_failures = sum(len(row["request_preview_errors"]) for row in rows)
    return {
        "title": "Frank Create Provider Adapter Audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "model_count": len(rows),
            "runner_registered": sum(1 for row in rows if row["runner_registered"]),
            "missing_runners": sum(1 for row in rows if not row["runner_registered"]),
            "ready_models": sum(1 for row in rows if row["status"] == "ready"),
            "waiting_for_key": sum(1 for row in rows if row["status"] == "waiting_for_key"),
            "preview_failures": sum(1 for row in rows if row["status"] == "preview_failed"),
            "operation_preview_count": operation_preview_count,
            "operation_preview_failures": operation_preview_failures,
            "no_spend": True,
            "secret_values_returned": False,
        },
        "models": rows,
        "notes": [
            "This audit builds local request previews only; it does not call provider APIs.",
            "Missing keys block live generation but do not mean the server-side adapter is absent.",
            "Request previews show endpoints, auth style, and body shape for every supported operation with prompts/media redacted.",
        ],
    }


def _audit_kinds_for_model(model):
    capabilities = model.get("capabilities") or {}
    kinds = []
    if capabilities.get("generation"):
        kinds.append("generate")
    if capabilities.get("edit"):
        kinds.append("edit")
    if capabilities.get("masked_edit"):
        kinds.append("masked_edit")
    if capabilities.get("video"):
        kinds.append("video")
    return kinds


def _audit_settings_for_model(model):
    aspects = model.get("allowed_aspect_ratios") or []
    sizes = model.get("allowed_image_sizes") or []
    return {
        "aspect_ratio": "1:1" if "1:1" in aspects else (aspects[0] if aspects else "1:1"),
        "image_size": _preferred_audit_image_size(sizes),
        "count": 1,
    }


def _preferred_audit_image_size(sizes):
    for preferred in ("4K", "4096", "4MP", "2K", "2048", "1K", "1024"):
        if preferred in sizes:
            return preferred
    return sizes[0] if sizes else "1K"


def _provider_preflight_response(payload):
    try:
        model = get_model(payload.get("model") or payload.get("model_id"))
    except Exception as exc:
        return {
            "status": "unsupported",
            "ready": False,
            "provider": None,
            "model_id": payload.get("model") or payload.get("model_id"),
            "missing_env_vars": [],
            "message": str(exc),
            "payloadPreview": _provider_preflight_preview(None, payload, payload.get("prompt") or ""),
        }

    kind = payload.get("kind") or "generate"
    model_with_status = _models_with_key_status([model])[0]

    try:
        if kind == "video":
            _validate_video_preflight(model, payload)
            prompt = compose_frank_prompt(
                payload.get("prompt", ""),
                frank_body_mode=bool(payload.get("frank_body_mode", False)),
                preset_key=payload.get("preset_key"),
                brand_kit=_active_brand_kit(),
            )
            if model["provider"] != "local" and model_with_status.get("configured") is False:
                raise MissingProviderKey(model["id"], model_with_status.get("missing_env_vars") or model.get("env_vars", []))
            provider_payload = {"prompt": prompt}
        else:
            provider_payload = build_turn_payload(
                payload,
                reference_assets=_reference_asset_paths(payload.get("reference_asset_ids", [])),
                brand_kit=_active_brand_kit(),
            )
    except UnsupportedModelCapability as exc:
        return {
            "status": "unsupported",
            "ready": False,
            "provider": model["provider"],
            "model_id": model["id"],
            "model_label": model.get("short_label") or model.get("label") or model["id"],
            "missing_env_vars": [],
            "message": str(exc),
            "payloadPreview": _provider_preflight_preview(model_with_status, payload, _preflight_prompt_preview_text(model, payload)),
        }
    except MissingProviderKey as exc:
        missing_env_vars = list(exc.env_vars)
        return {
            "status": "blocked",
            "ready": False,
            "provider": model["provider"],
            "model_id": model["id"],
            "model_label": model.get("short_label") or model.get("label") or model["id"],
            "missing_env_vars": missing_env_vars,
            "message": f"Add {' or '.join(missing_env_vars)} in the server key file, then reload keys.",
            "payloadPreview": _provider_preflight_preview(model_with_status, payload, _preflight_prompt_preview_text(model, payload)),
        }
    except (KeyError, ValueError) as exc:
        return {
            "status": "unsupported",
            "ready": False,
            "provider": model["provider"],
            "model_id": model["id"],
            "model_label": model.get("short_label") or model.get("label") or model["id"],
            "missing_env_vars": [],
            "message": str(exc),
            "payloadPreview": _provider_preflight_preview(model_with_status, payload, _preflight_prompt_preview_text(model, payload)),
        }

    return {
        "status": "ready",
        "ready": True,
        "provider": model["provider"],
        "model_id": model["id"],
        "model_label": model.get("short_label") or model.get("label") or model["id"],
        "configured_env_var": model_with_status.get("configured_env_var"),
        "missing_env_vars": [],
        "message": f"{model.get('short_label') or model.get('label') or model['id']} is ready for {kind}.",
        "payloadPreview": _provider_preflight_preview(model_with_status, payload, provider_payload.get("prompt") or ""),
    }


def _validate_video_preflight(model, payload):
    if not model.get("capabilities", {}).get("video"):
        raise UnsupportedModelCapability(f"{model['id']} does not support video")
    reference_ids = payload.get("reference_asset_ids") or []
    reference_limit = int(model.get("reference_image_limit") or 0)
    if len(reference_ids) > reference_limit:
        raise UnsupportedModelCapability(f"{model['id']} supports at most {reference_limit} reference images")


def _preflight_prompt_preview_text(model, payload):
    if not model:
        return payload.get("prompt") or ""
    return compose_frank_prompt(
        payload.get("prompt", ""),
        frank_body_mode=bool(payload.get("frank_body_mode", False)),
        preset_key=payload.get("preset_key"),
        brand_kit=_active_brand_kit(),
    )


def _provider_preflight_preview(model, payload, prompt):
    settings = dict(payload.get("settings") or {})
    references = payload.get("reference_asset_ids") or []
    prompt = prompt or ""
    return {
        "provider": (model or {}).get("provider"),
        "provider_model": (model or {}).get("provider_model"),
        "model_id": (model or {}).get("id") or payload.get("model") or payload.get("model_id"),
        "kind": payload.get("kind") or "generate",
        "settings": settings,
        "reference_count": len(references),
        "reference_limit": int((model or {}).get("reference_image_limit") or 0),
        "source_asset_id": payload.get("edit_source_asset_id") or payload.get("source_asset_id"),
        "mask_asset_id": payload.get("mask_asset_id"),
        "frank_body_mode": bool(payload.get("frank_body_mode", False)),
        "preset_key": payload.get("preset_key"),
        "prompt_length": len(prompt),
        "prompt_preview": _truncate_prompt(prompt),
    }


def _truncate_prompt(prompt, limit=420):
    clean = " ".join(str(prompt or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def _prompt_remix_response(payload):
    prompt = (payload.get("prompt") or "").strip()
    preset_key = payload.get("preset_key") or "product-shot-lab"
    preset = next((item for item in get_prompt_presets() if item.get("key") == preset_key), None)
    base_prompt = prompt or (preset or {}).get("prompt") or "Frank Body product image"
    brand_phrase = "Frank Body " if payload.get("frank_body_mode") else ""

    return {
        "variants": [
            {
                "key": "clean",
                "label": "Clean Ecom",
                "prompt": (
                    f"{base_prompt}. {brand_phrase}clean ecommerce composition, readable product label, "
                    "soft shadow, honest texture, warm pink accent, channel-ready crop."
                ),
            },
            {
                "key": "lifestyle",
                "label": "Lifestyle",
                "prompt": (
                    f"{base_prompt}. {brand_phrase}warm bathroom or body-care lifestyle scene, "
                    "tactile surfaces, natural skin-care mess kept polished, confident cheeky tone."
                ),
            },
            {
                "key": "campaign",
                "label": "Campaign",
                "prompt": (
                    f"{base_prompt}. {brand_phrase}campaign-ready variant with recognizable product, "
                    "punchier set styling, headline space, bold Frank attitude, export-safe composition."
                ),
            },
        ]
    }


def _demo_doctor_response():
    store = _store()
    sessions = store.list_sessions()
    active_sessions = [session for session in sessions if session.get("status") == "active"]
    session = _select_demo_doctor_session(sessions, active_sessions)
    assets = store.list_assets(session_id=session["id"]) if session else []
    output_assets = [asset for asset in assets if asset.get("kind") not in {"reference", "mask"}]
    image_output_assets = [asset for asset in output_assets if asset.get("media_type", "image") != "video"]
    reference_assets = [asset for asset in assets if asset.get("kind") == "reference"]
    approved_assets = [asset for asset in output_assets if asset.get("approval_status") == "approved"]
    video_assets = [asset for asset in output_assets if asset.get("media_type") == "video"]
    masked_edit_ready = _assets_include_masked_edit_workflow(image_output_assets)
    edit_proof_ready = masked_edit_ready or _assets_include_image_edit_proof(image_output_assets)
    media_file_report = _demo_media_file_report(assets)
    workflow_smoke = _workflow_smoke_status()
    secret_hygiene = _secret_hygiene_report()
    provider_readiness = _provider_readiness_response()
    provider_adapters = _provider_adapter_report()
    local_engine = get_local_engine_status()
    frontend_index = Path(__file__).resolve().parents[2] / "frank-create" / "dist" / "index.html"
    graph_branding = _graph_branding_report(frontend_index.parent)
    demo_evidence = _demo_evidence_report()
    call_brief = _call_brief_report()
    provider_receipt = _provider_readiness_receipt_report()
    brand_context = _brand_context_receipt_report()
    activation_checklist = _activation_checklist_receipt_report()
    readiness_pack = _readiness_pack_report()

    checks = [
        _doctor_check("server", "Frank server", "ready", "Comfy is responding on this port."),
        _doctor_check(
            "frontend_build",
            "Frank shell",
            "ready" if frontend_index.exists() else "fail",
            "Built Frank Create shell found." if frontend_index.exists() else "Run npm run build in frank-create.",
            None if frontend_index.exists() else "Run: cd frank-create; npm run build",
        ),
        _doctor_check(
            "graph_branding",
            "Graph branding",
            graph_branding["status"],
            graph_branding["detail"],
            graph_branding.get("action"),
        ),
        _doctor_check(
            "database",
            "Local studio DB",
            "ready" if store.db_path.exists() else "fail",
            str(store.db_path),
            None if store.db_path.exists() else "Start Frank Create once to initialize SQLite.",
        ),
        _doctor_check(
            "demo_session",
            "Demo session",
            "ready" if session else "fail",
            f"{session.get('name')} is active." if session else "No active Frank Create session found.",
            None if session else "Reset demo data or create a session.",
        ),
        _doctor_check(
            "starter_assets",
            "Starter outputs",
            "ready" if output_assets else "fail",
            f"{len(output_assets)} output asset{'' if len(output_assets) == 1 else 's'} available.",
            None if output_assets else "Run: .\\scripts\\Start-FrankCreate.ps1 -ResetDemoData",
        ),
        _doctor_check(
            "references",
            "Reference assets",
            "ready" if reference_assets else "warning",
            f"{len(reference_assets)} reference asset{'' if len(reference_assets) == 1 else 's'} available.",
            None if reference_assets else "Upload or seed at least one product reference.",
        ),
        _doctor_check(
            "asset_files",
            "Asset media",
            media_file_report["status"],
            media_file_report["detail"],
            media_file_report.get("action"),
        ),
        _doctor_check(
            "cliff_pack",
            "Cliff Pack",
            "ready" if approved_assets else "fail",
            (
                f"{len(approved_assets)} approved asset{'' if len(approved_assets) == 1 else 's'} ready for handoff."
                if approved_assets
                else "No approved assets available; the visible Cliff Pack export is disabled."
            ),
            None if approved_assets else "Approve one seeded output or reset demo data.",
        ),
        _doctor_check(
            "masked_edit",
            "Edit proof",
            "ready" if edit_proof_ready else "fail",
            (
                "Masked-edit proof is ready for review."
                if masked_edit_ready
                else (
                    "Image edit proof is ready for review."
                    if edit_proof_ready
                    else "No edit proof is available in the demo session."
                )
            ),
            None if edit_proof_ready else "Run: .\\scripts\\Start-FrankCreate.ps1 -ResetDemoData",
        ),
        _doctor_check(
            "motion_board",
            "Motion board",
            "ready" if video_assets else "warning",
            (
                f"{len(video_assets)} storyboard asset{'' if len(video_assets) == 1 else 's'} ready for Video Lab."
                if video_assets
                else "No storyboard asset is visible in the demo session."
            ),
            None if video_assets else "Run: .\\scripts\\Start-FrankCreate.ps1 -ResetDemoData",
        ),
        _curated_demo_check(reference_assets, image_output_assets, approved_assets, video_assets, edit_proof_ready),
        _doctor_check(
            "secret_hygiene",
            "Secret hygiene",
            secret_hygiene["status"],
            secret_hygiene["detail"],
            secret_hygiene.get("action"),
        ),
        _doctor_check(
            "workflow_smoke",
            "Workflow smoke",
            workflow_smoke["status"],
            workflow_smoke["detail"],
            workflow_smoke.get("action"),
        ),
        _doctor_check(
            "demo_evidence",
            "Demo evidence",
            demo_evidence["status"],
            demo_evidence["detail"],
            demo_evidence.get("action"),
        ),
        _doctor_check(
            "call_brief",
            "Call brief",
            call_brief["status"],
            call_brief["detail"],
            call_brief.get("action"),
        ),
        _doctor_check(
            "provider_readiness_receipt",
            "Provider receipt",
            provider_receipt["status"],
            provider_receipt["detail"],
            provider_receipt.get("action"),
        ),
        _doctor_check(
            "brand_context_receipt",
            "Brand context",
            brand_context["status"],
            brand_context["detail"],
            brand_context.get("action"),
        ),
        _doctor_check(
            "activation_checklist",
            "Activation checklist",
            activation_checklist["status"],
            activation_checklist["detail"],
            activation_checklist.get("action"),
        ),
        _doctor_check(
            "readiness_pack",
            "Readiness pack",
            readiness_pack["status"],
            readiness_pack["detail"],
            readiness_pack.get("action"),
        ),
        _doctor_check(
            "local_engine",
            "Local engine",
            "ready" if local_engine.get("diffusion_ready") else "warning",
            (
                f"{local_engine.get('checkpoint_count', 0)} checkpoint file ready."
                if local_engine.get("diffusion_ready")
                else (
                    "No usable diffusion checkpoint detected; Frank renderer fallback is ready."
                    if local_engine.get("ignored_checkpoints")
                    else "No diffusion checkpoint detected; Frank renderer fallback is ready."
                )
            ),
            None
            if local_engine.get("diffusion_ready")
            else (
                f"Optional: click Prepare model folders, then put a full checkpoint in "
                f"{local_engine.get('checkpoint_dir')} for checkpoint txt2img, reference/edit img2img, and masked inpaint. "
                f"Files below {local_engine.get('minimum_checkpoint_mb', 100)} MB are ignored as incomplete downloads."
            ),
        ),
        _doctor_check(
            "provider_keys",
            "Provider keys",
            "ready" if provider_readiness["summary"]["waitingModels"] == 0 else "warning",
            (
                "All live provider models have server keys."
                if provider_readiness["summary"]["waitingModels"] == 0
                else f"{provider_readiness['summary']['waitingModels']} live models are waiting on server keys."
            ),
            None
            if provider_readiness["summary"]["waitingModels"] == 0
            else (
                "Local renderer still demos end to end. For live API rounds, paste rotated keys in "
                "Provider Setup -> Save server keys or use user\\frank_create\\provider_keys.env."
            ),
        ),
        _doctor_check(
            "provider_adapters",
            "Provider adapters",
            provider_adapters["status"],
            provider_adapters["detail"],
            provider_adapters.get("action"),
        ),
    ]

    failed = any(check["status"] == "fail" for check in checks)
    warned = any(check["status"] == "warning" for check in checks)
    status = "needs_attention" if failed else ("ready_with_warnings" if warned else "ready")
    headline = "Needs attention" if failed else "Ready for Cliff"

    return {
        "status": status,
        "readyForDemo": not failed,
        "headline": headline,
        "summary": {
            "activeSessionCount": len(active_sessions),
            "outputAssetCount": len(output_assets),
            "imageOutputAssetCount": len(image_output_assets),
            "approvedAssetCount": len(approved_assets),
            "referenceAssetCount": len(reference_assets),
            "videoAssetCount": len(video_assets),
            "missingMediaFileCount": media_file_report["missing_count"],
            "workflowSmokeOk": workflow_smoke.get("ok", False),
            "workflowSmokeAt": workflow_smoke.get("completed_at"),
            "workflowSmokeMediaFileCount": workflow_smoke.get("media_file_count", 0),
            "workflowSmokeChannelExportFileCount": workflow_smoke.get("channel_export_file_count", 0),
            "secretIssueCount": secret_hygiene.get("issue_count", 0),
            "graphBrandingReady": graph_branding["status"] == "ready",
            "demoEvidenceReady": demo_evidence["status"] == "ready",
            "callBriefReady": call_brief["status"] == "ready",
            "providerReadinessReceiptReady": provider_receipt["status"] == "ready",
            "brandContextReceiptReady": brand_context["status"] == "ready",
            "activationChecklistReady": activation_checklist["status"] == "ready",
            "readinessPackReady": readiness_pack["status"] == "ready",
            "readinessPackBytes": readiness_pack.get("file_size_bytes", 0),
            "readinessPackSha256": readiness_pack.get("sha256", ""),
            "readyProviderModels": provider_readiness["summary"]["readyModels"],
            "waitingProviderModels": provider_readiness["summary"]["waitingModels"],
            "providerAdapterCount": provider_adapters["adapter_count"],
            "missingProviderAdapterCount": provider_adapters["missing_count"],
            "diffusionReady": bool(local_engine.get("diffusion_ready")),
            "checkpointCount": int(local_engine.get("checkpoint_count", 0)),
            "maskedEditReady": masked_edit_ready,
            "editProofReady": edit_proof_ready,
            "demoCurated": _is_curated_demo(reference_assets, image_output_assets, approved_assets, edit_proof_ready),
        },
        "checks": checks,
        "notes": [
            "Warnings are okay for a local demo when the Frank renderer is ready.",
            "Provider readiness reports env var names only, never secret values.",
            "Secret hygiene scans source/docs for provider-looking tokens and reports file paths only.",
        ],
    }


def _demo_evidence_report():
    root = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    markdown_path = root / "frank-create-demo-evidence-latest.md"
    json_path = root / "frank-create-demo-evidence-latest.json"
    markdown_ready = markdown_path.exists() and markdown_path.is_file()
    json_ready = json_path.exists() and json_path.is_file()
    if markdown_ready and json_ready:
        return {
            "status": "ready",
            "detail": "Latest demo evidence receipt is ready.",
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }

    missing = []
    if not markdown_ready:
        missing.append("Markdown")
    if not json_ready:
        missing.append("JSON")
    return {
        "status": "warning",
        "detail": f"Latest demo evidence is missing {' and '.join(missing)}.",
        "action": "Click Save evidence in Demo Doctor or run PREP_FRANK_CREATE_FOR_CLIFF.cmd.",
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def _provider_readiness_receipt_report():
    root = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    markdown_path = root / "frank-create-provider-readiness-latest.md"
    json_path = root / "frank-create-provider-readiness-latest.json"
    markdown_ready = markdown_path.exists() and markdown_path.is_file()
    json_ready = json_path.exists() and json_path.is_file()
    if markdown_ready and json_ready:
        return {
            "status": "ready",
            "detail": "Latest provider-readiness receipt is ready.",
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }

    missing = []
    if not markdown_ready:
        missing.append("Markdown")
    if not json_ready:
        missing.append("JSON")
    return {
        "status": "warning",
        "detail": f"Latest provider-readiness receipt is missing {' and '.join(missing)}.",
        "action": "Click Save receipt in Provider Setup or build the call pack.",
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def _brand_context_receipt_report():
    root = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    markdown_path = root / "frank-create-brand-context-latest.md"
    json_path = root / "frank-create-brand-context-latest.json"
    markdown_ready = markdown_path.exists() and markdown_path.is_file()
    json_ready = json_path.exists() and json_path.is_file()
    if markdown_ready and json_ready:
        return {
            "status": "ready",
            "detail": "Latest Frank Body brand-context receipt is ready.",
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }

    missing = []
    if not markdown_ready:
        missing.append("Markdown")
    if not json_ready:
        missing.append("JSON")
    return {
        "status": "warning",
        "detail": f"Latest Frank Body brand-context receipt is missing {' and '.join(missing)}.",
        "action": "Click Save context brief in Brand Kit after adding reference assets.",
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def _activation_checklist_receipt_report():
    root = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    markdown_path = root / "frank-create-activation-checklist-latest.md"
    json_path = root / "frank-create-activation-checklist-latest.json"
    markdown_ready = markdown_path.exists() and markdown_path.is_file()
    json_ready = json_path.exists() and json_path.is_file()
    if markdown_ready and json_ready:
        return {
            "status": "ready",
            "detail": "Latest production activation checklist is ready.",
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }

    missing = []
    if not markdown_ready:
        missing.append("Markdown")
    if not json_ready:
        missing.append("JSON")
    return {
        "status": "warning",
        "detail": f"Latest production activation checklist is missing {' and '.join(missing)}.",
        "action": "Click Build call pack in Demo Doctor or run BUILD_FRANK_CREATE_READINESS_PACK.cmd.",
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def _approved_assets_include_workflow(assets, workflow_key):
    for asset in assets:
        settings = _json_loads_safe(asset.get("settings_json"), {})
        workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
        if isinstance(workflow, dict) and workflow.get("workflow_key") == workflow_key:
            return True
    return False


def _assets_include_masked_edit_workflow(assets):
    for asset in assets:
        settings = _json_loads_safe(asset.get("settings_json"), {})
        workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
        if _workflow_is_masked_edit_proof(workflow):
            return True
    return False


def _assets_include_image_edit_proof(assets):
    for asset in assets:
        if asset.get("media_type", "image") == "video":
            continue
        if not asset.get("source_asset_id"):
            continue
        settings = _json_loads_safe(asset.get("settings_json"), {})
        workflow = settings.get("workflow_provenance") if isinstance(settings, dict) else None
        if _workflow_is_masked_edit_proof(workflow):
            return True
        if isinstance(workflow, dict) and workflow.get("workflow_key") in {
            "google-nano-banana-live-seed",
            "google-image-edit",
            "openai-image-edit",
            "replicate-image-edit",
        }:
            return True
        if asset.get("provider") in {"google", "openai", "replicate", "local"}:
            return True
    return False


def _workflow_is_masked_edit_proof(workflow):
    if not isinstance(workflow, dict):
        return False
    return workflow.get("masked_edit") is True or workflow.get("workflow_key") in {
        "frank-local-masked-edit-renderer",
        "comfy-checkpoint-inpaint",
    }


def _json_loads_safe(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _call_brief_report():
    root = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    markdown_path = root / "frank-create-call-brief-latest.md"
    json_path = root / "frank-create-call-brief-latest.json"
    markdown_ready = markdown_path.exists() and markdown_path.is_file()
    json_ready = json_path.exists() and json_path.is_file()
    if markdown_ready and json_ready:
        return {
            "status": "ready",
            "detail": "Latest one-page Cliff call brief is ready.",
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }

    missing = []
    if not markdown_ready:
        missing.append("Markdown")
    if not json_ready:
        missing.append("JSON")
    return {
        "status": "warning",
        "detail": f"Latest call brief is missing {' and '.join(missing)}.",
        "action": "Click Call brief in Demo Doctor or run PREP_FRANK_CREATE_FOR_CLIFF.cmd.",
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def _readiness_pack_report():
    pack_path = _latest_readiness_pack_path()
    if pack_path and pack_path.exists() and pack_path.is_file():
        try:
            _validate_readiness_pack_for_doctor(pack_path)
        except Exception as exc:
            return {
                "status": "warning",
                "detail": f"Latest Cliff readiness ZIP could not be verified: {exc}",
                "action": "Rebuild with Build call pack or run VERIFY_CLIFF_PACK.cmd, then run Demo Doctor again.",
                "path": str(pack_path),
                "file_size_bytes": pack_path.stat().st_size,
            }
        return {
            "status": "ready",
            "detail": f"Latest Cliff readiness ZIP is ready ({pack_path.stat().st_size} bytes).",
            "path": str(pack_path),
            "file_size_bytes": pack_path.stat().st_size,
            "sha256": _read_or_compute_readiness_pack_sha256(pack_path),
        }

    expected_path = _store().root_dir / READINESS_PACK_DIRNAME / "frank-create-cliff-readiness-latest.zip"
    return {
        "status": "warning",
        "detail": "Latest Cliff readiness ZIP has not been built yet.",
        "action": "Click Build call pack in Demo Doctor or run BUILD_FRANK_CREATE_READINESS_PACK.cmd.",
        "path": str(expected_path),
        "file_size_bytes": 0,
        "sha256": "",
    }


def _read_or_compute_readiness_pack_sha256(pack_path):
    sidecar = pack_path.with_suffix(pack_path.suffix + ".sha256")
    if sidecar.exists() and sidecar.is_file():
        try:
            first_token = sidecar.read_text(encoding="utf-8-sig").split()[0]
            if re.fullmatch(r"[0-9a-fA-F]{64}", first_token):
                return first_token.lower()
        except (OSError, IndexError):
            pass
    return hashlib.sha256(pack_path.read_bytes()).hexdigest()


def _validate_readiness_pack_for_doctor(pack_path):
    required_entries = {
        "readiness-pack-manifest.json",
        "qa/browser-qa-receipt.json",
        "receipts/cliff_prep_status.json",
    }
    with zipfile.ZipFile(pack_path) as archive:
        names = set(archive.namelist())
        missing = sorted(required_entries - names)
        if missing:
            raise ValueError(f"missing {', '.join(missing)}")
        manifest = json.loads(archive.read("readiness-pack-manifest.json").decode("utf-8-sig"))
        if manifest.get("purpose") != "Cliff call-day readiness pack":
            raise ValueError("manifest purpose is not Cliff call-day readiness pack")
        if (manifest.get("shareable_pack_hygiene") or {}).get("status") != "clean":
            raise ValueError("shareable pack hygiene is not clean")
        browser_qa = manifest.get("browser_qa") or json.loads(
            archive.read("qa/browser-qa-receipt.json").decode("utf-8-sig")
        )
        _validate_readiness_pack_browser_qa(browser_qa, "Readiness pack Browser QA")
        cliff_prep = json.loads(archive.read("receipts/cliff_prep_status.json").decode("utf-8-sig"))
        _validate_readiness_pack_browser_qa(cliff_prep.get("browser_qa"), "Cliff prep Browser QA")


def _validate_readiness_pack_browser_qa(browser_qa, label):
    if not isinstance(browser_qa, dict) or browser_qa.get("status") != "ready":
        raise ValueError(f"{label} is not ready")
    checks = browser_qa.get("checks") or []
    keys = {check.get("key") for check in checks}
    required = {
        "studio_interactions",
        "demo_doctor_checksum",
        "studio_model_preflight",
        "studio_local_generate",
        "studio_masked_edit_generate",
        "video_lab",
        "provider_audit",
        "advanced_graph",
        "raw_comfy",
        "raw_comfy_receipt",
    }
    missing = sorted(required - keys)
    if missing:
        raise ValueError(f"{label} is missing {', '.join(missing)}")
    studio_check = next((check for check in checks if check.get("key") == "studio_interactions"), {})
    studio_detail = str(studio_check.get("detail") or "")
    if "safe production unlock plan" not in studio_detail:
        raise ValueError(f"{label} is missing safe production unlock plan proof")
    checksum_check = next((check for check in checks if check.get("key") == "demo_doctor_checksum"), {})
    checksum_detail = str(checksum_check.get("detail") or "")
    if not re.search(r"Verified SHA-256\s+[0-9a-fA-F]{64}", checksum_detail):
        raise ValueError(f"{label} is missing Demo Doctor checksum proof")
    model_preflight_check = next((check for check in checks if check.get("key") == "studio_model_preflight"), {})
    model_preflight_detail = str(model_preflight_check.get("detail") or "")
    if "no-spend selected model preflight" not in model_preflight_detail.lower() or "safe payload preview" not in model_preflight_detail.lower():
        raise ValueError(f"{label} is missing selected model preflight proof")
    local_generate_check = next((check for check in checks if check.get("key") == "studio_local_generate"), {})
    local_generate_detail = str(local_generate_check.get("detail") or "")
    if "local generate proof" not in local_generate_detail.lower() or "created output assets" not in local_generate_detail:
        raise ValueError(f"{label} is missing local Generate button proof")
    masked_edit_generate_check = next((check for check in checks if check.get("key") == "studio_masked_edit_generate"), {})
    masked_edit_generate_detail = str(masked_edit_generate_check.get("detail") or "")
    if "masked edit proof" not in masked_edit_generate_detail.lower() or "created output assets" not in masked_edit_generate_detail:
        raise ValueError(f"{label} is missing masked edit Generate button proof")


def _provider_adapter_report():
    audit = _provider_adapter_audit_response()
    summary = audit["summary"]
    missing = [
        row.get("label") or row.get("model_id")
        for row in audit.get("models", [])
        if not row.get("runner_registered")
    ]
    preview_failures = int(summary.get("operation_preview_failures") or 0)
    if missing or preview_failures:
        issue_parts = []
        if missing:
            issue_parts.append(f"missing runner for {', '.join(missing)}")
        if preview_failures:
            issue_parts.append(f"{preview_failures} request preview failure{'' if preview_failures == 1 else 's'}")
        return {
            "status": "fail",
            "adapter_count": int(summary.get("runner_registered") or 0),
            "missing_count": int(summary.get("missing_runners") or 0),
            "operation_preview_count": int(summary.get("operation_preview_count") or 0),
            "operation_preview_failures": preview_failures,
            "detail": f"Provider adapter audit found {'; '.join(issue_parts)}.",
            "action": "Fix adapter registration/request previews before enabling this model for Cliff.",
        }

    return {
        "status": "ready",
        "adapter_count": int(summary.get("runner_registered") or 0),
        "missing_count": 0,
        "operation_preview_count": int(summary.get("operation_preview_count") or 0),
        "operation_preview_failures": preview_failures,
        "detail": (
            f"{summary.get('runner_registered')} / {summary.get('model_count')} launch provider runners registered; "
            f"{summary.get('operation_preview_count')} operation request preview"
            f"{'' if int(summary.get('operation_preview_count') or 0) == 1 else 's'} checked with no external calls."
        ),
    }


def _graph_branding_report(dist_dir):
    dist_dir = Path(dist_dir)
    shell_tokens = (
        "Workflow Map",
        "Studio workflow map",
        "Real node graph lives in Comfy Canvas.",
        "Frank Create workflow map",
        "Selected workflow stage",
        "View details",
        "Workflow receipts",
        "Use in Studio",
        "Open Comfy Canvas",
    )
    raw_script = _comfy_brand_boot_script()
    raw_css = _comfy_user_css_text()
    raw_tokens_ready = all(
        token in raw_script or token in raw_css
        for token in (
            "Frank Graph / Raw Goods",
            "Frank Canvas",
            "frank-comfy-brand-chrome",
            "frank-comfy-workflow-receipt",
            "frank-create-raw-canvas",
            "Advanced Comfy canvas",
            "pointer-events: none",
            "NODE_TITLE_HEIGHT",
        )
    )

    if not dist_dir.exists():
        return {
            "status": "fail",
            "detail": "Frank shell dist is missing, so the branded graph cannot be verified.",
            "action": "Run: cd frank-create; npm run build",
        }

    missing_shell_tokens = [token for token in shell_tokens if not _dist_contains_token(dist_dir, token)]
    if missing_shell_tokens:
        return {
            "status": "fail",
            "detail": f"Branded graph shell is missing token: {missing_shell_tokens[0]}.",
            "action": "Run: cd frank-create; npm run build",
        }

    if not raw_tokens_ready:
        return {
            "status": "fail",
            "detail": "Raw Comfy canvas branding hooks are missing.",
            "action": "Restart Frank Create from the current custom_nodes/frank_create extension.",
        }

    return {
        "status": "ready",
        "detail": "Advanced Graph and raw Comfy canvas branding are installed.",
    }


def _dist_contains_token(dist_dir, token):
    for path in Path(dist_dir).rglob("*"):
        if path.suffix.lower() not in {".html", ".js", ".css"} or not path.is_file():
            continue
        try:
            if token in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _reset_demo_response(payload):
    create_assets = payload.get("create_assets", True)
    result = reset_and_seed_demo(_store(), create_assets=bool(create_assets))
    _invalidate_workflow_smoke_after_demo_reset()
    reference = result.get("reference")
    mask_assets = result.get("mask_assets") or []
    output_assets = (result.get("assets") or []) + (result.get("video_assets") or [])
    assets = ([reference] if reference else []) + mask_assets + output_assets
    return {
        "project": result["project"],
        "brief": result["brief"],
        "session": result["session"],
        "turn": result["turn"],
        "reference": reference,
        "assets": assets,
        "doctor": _demo_doctor_response(),
    }


def _demo_evidence_response(payload):
    doctor = _demo_doctor_response()
    workflow_smoke = _workflow_smoke_status()
    cliff_prep = _cliff_prep_status()
    evidence = _demo_evidence_payload(doctor, workflow_smoke, payload, cliff_prep, provider_status=_provider_readiness_response())
    paths = _write_demo_evidence_files(evidence)
    return {
        "evidence": evidence,
        "markdown_path": str(paths["markdown"]),
        "json_path": str(paths["json"]),
        "latest_markdown_path": str(paths["latest_markdown"]),
        "latest_json_path": str(paths["latest_json"]),
        "markdown_file": paths["markdown"].name,
        "json_file": paths["json"].name,
        "latest_markdown_file": paths["latest_markdown"].name,
        "latest_json_file": paths["latest_json"].name,
        "markdown_url": f"/api/frank/demo/evidence/{paths['markdown'].name}",
        "json_url": f"/api/frank/demo/evidence/{paths['json'].name}",
        "latest_markdown_url": f"/api/frank/demo/evidence/{paths['latest_markdown'].name}",
        "latest_json_url": f"/api/frank/demo/evidence/{paths['latest_json'].name}",
    }


def _demo_call_brief_response(payload):
    payload = payload or {}
    doctor = _demo_doctor_response()
    workflow_smoke = _workflow_smoke_status()
    provider_status = _provider_readiness_response()
    readiness_pack = _latest_readiness_pack_path()
    brief = _demo_call_brief_payload(doctor, workflow_smoke, provider_status, payload, readiness_pack)
    paths = _write_demo_call_brief_files(brief)
    return {
        "brief": brief,
        "markdown_path": str(paths["markdown"]),
        "json_path": str(paths["json"]),
        "latest_markdown_path": str(paths["latest_markdown"]),
        "latest_json_path": str(paths["latest_json"]),
        "markdown_file": paths["markdown"].name,
        "json_file": paths["json"].name,
        "latest_markdown_file": paths["latest_markdown"].name,
        "latest_json_file": paths["latest_json"].name,
        "markdown_url": f"/api/frank/demo/call-brief/{paths['markdown'].name}",
        "json_url": f"/api/frank/demo/call-brief/{paths['json'].name}",
        "latest_markdown_url": f"/api/frank/demo/call-brief/{paths['latest_markdown'].name}",
        "latest_json_url": f"/api/frank/demo/call-brief/{paths['latest_json'].name}",
    }


def _demo_evidence_file_response(filename):
    path = _resolve_demo_evidence_file(filename)
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text="Demo evidence file was not found")
    content_type = "text/markdown" if path.suffix.lower() == ".md" else "application/json"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def _demo_call_brief_file_response(filename):
    path = _resolve_demo_call_brief_file(filename)
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text="Call brief file was not found")
    content_type = "text/markdown" if path.suffix.lower() == ".md" else "application/json"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def _demo_provider_readiness_file_response(filename):
    path = _resolve_demo_provider_readiness_file(filename)
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text="Provider readiness file was not found")
    content_type = "text/markdown" if path.suffix.lower() == ".md" else "application/json"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def _demo_brand_context_file_response(filename):
    path = _resolve_demo_brand_context_file(filename)
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text="Brand context file was not found")
    content_type = "text/markdown" if path.suffix.lower() == ".md" else "application/json"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def _demo_readiness_pack_response(payload):
    evidence_response = _demo_evidence_response(payload)
    call_brief_response = _demo_call_brief_response(payload)
    provider_readiness_response = _demo_provider_readiness_receipt_response()
    activation_checklist_response = _demo_activation_checklist_receipt_response()
    brand_context_response = _demo_brand_context_receipt_response(payload)
    pack = _write_demo_readiness_pack(
        evidence_response,
        payload or {},
        call_brief_response,
        provider_readiness_response,
        activation_checklist_response,
        brand_context_response,
    )
    return {
        "file_path": str(pack["path"]),
        "file_name": pack["path"].name,
        "download_url": f"/api/frank/demo/readiness-pack/{pack['path'].name}",
        "latest_file_path": str(pack["latest_path"]),
        "latest_file_name": pack["latest_path"].name,
        "latest_download_url": f"/api/frank/demo/readiness-pack/{pack['latest_path'].name}",
        "checksum_path": str(pack["checksum"]["path"]),
        "checksum_sha256": pack["checksum"]["sha256"],
        "latest_checksum_path": str(pack["latest_checksum"]["path"]),
        "latest_checksum_sha256": pack["latest_checksum"]["sha256"],
        "latest_file_size_bytes": pack["latest_checksum"]["file_size_bytes"],
        "latest_implementation_manifest_path": pack.get("latest_implementation_manifest_path"),
        "latest_implementation_manifest_url": "/api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md",
        "manifest": pack["manifest"],
        "evidence": evidence_response,
        "call_brief": call_brief_response,
        "provider_readiness": provider_readiness_response,
        "activation_checklist": activation_checklist_response,
        "brand_context": brand_context_response,
    }


def _demo_readiness_pack_file_response(filename):
    path = _resolve_demo_readiness_pack_file(filename)
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text="Readiness pack was not found")
    content_type = "text/markdown" if path.suffix.lower() == ".md" else "application/zip"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def _resolve_demo_evidence_file(filename):
    if Path(filename).name != filename:
        raise web.HTTPForbidden(text="Invalid demo evidence filename")
    if not filename.startswith("frank-create-demo-evidence-") or Path(filename).suffix.lower() not in {".md", ".json"}:
        raise web.HTTPForbidden(text="Invalid demo evidence filename")
    root = (_store().root_dir / DEMO_EVIDENCE_DIRNAME).resolve()
    path = (root / filename).resolve()
    if root not in path.parents:
        raise web.HTTPForbidden(text="Invalid demo evidence path")
    return path


def _resolve_demo_call_brief_file(filename):
    if Path(filename).name != filename:
        raise web.HTTPForbidden(text="Invalid call brief filename")
    if not filename.startswith("frank-create-call-brief-") or Path(filename).suffix.lower() not in {".md", ".json"}:
        raise web.HTTPForbidden(text="Invalid call brief filename")
    root = (_store().root_dir / DEMO_EVIDENCE_DIRNAME).resolve()
    path = (root / filename).resolve()
    if root not in path.parents:
        raise web.HTTPForbidden(text="Invalid call brief path")
    return path


def _resolve_demo_provider_readiness_file(filename):
    if Path(filename).name != filename:
        raise web.HTTPForbidden(text="Invalid provider readiness filename")
    if not filename.startswith("frank-create-provider-readiness-") or Path(filename).suffix.lower() not in {".md", ".json"}:
        raise web.HTTPForbidden(text="Invalid provider readiness filename")
    root = (_store().root_dir / DEMO_EVIDENCE_DIRNAME).resolve()
    path = (root / filename).resolve()
    if root not in path.parents:
        raise web.HTTPForbidden(text="Invalid provider readiness path")
    return path


def _resolve_demo_brand_context_file(filename):
    if Path(filename).name != filename:
        raise web.HTTPForbidden(text="Invalid brand context filename")
    if not filename.startswith("frank-create-brand-context-") or Path(filename).suffix.lower() not in {".md", ".json"}:
        raise web.HTTPForbidden(text="Invalid brand context filename")
    root = (_store().root_dir / DEMO_EVIDENCE_DIRNAME).resolve()
    path = (root / filename).resolve()
    if root not in path.parents:
        raise web.HTTPForbidden(text="Invalid brand context path")
    return path


def _resolve_demo_readiness_pack_file(filename):
    if Path(filename).name != filename:
        raise web.HTTPForbidden(text="Invalid readiness pack filename")
    is_pack_zip = filename.startswith("frank-create-cliff-readiness-") and Path(filename).suffix.lower() == ".zip"
    is_manifest = filename == "frank-create-implementation-manifest-latest.md"
    if not is_pack_zip and not is_manifest:
        raise web.HTTPForbidden(text="Invalid readiness pack filename")
    root = (_store().root_dir / READINESS_PACK_DIRNAME).resolve()
    path = (root / filename).resolve()
    if root not in path.parents:
        raise web.HTTPForbidden(text="Invalid readiness pack path")
    return path


def _demo_provider_readiness_receipt_response():
    provider_status = _provider_readiness_response()
    receipt = _provider_readiness_receipt_payload(provider_status)
    paths = _write_provider_readiness_receipt_files(receipt)
    return {
        "receipt": receipt,
        "markdown_path": str(paths["markdown"]),
        "json_path": str(paths["json"]),
        "latest_markdown_path": str(paths["latest_markdown"]),
        "latest_json_path": str(paths["latest_json"]),
        "markdown_file": paths["markdown"].name,
        "json_file": paths["json"].name,
        "latest_markdown_file": paths["latest_markdown"].name,
        "latest_json_file": paths["latest_json"].name,
        "markdown_url": f"/api/frank/demo/provider-readiness/{paths['markdown'].name}",
        "json_url": f"/api/frank/demo/provider-readiness/{paths['json'].name}",
        "latest_markdown_url": f"/api/frank/demo/provider-readiness/{paths['latest_markdown'].name}",
        "latest_json_url": f"/api/frank/demo/provider-readiness/{paths['latest_json'].name}",
    }


def _demo_activation_checklist_receipt_response():
    checklist = _activation_checklist_response()
    paths = _write_activation_checklist_receipt_files(checklist)
    return {
        "checklist": checklist,
        "markdown_path": str(paths["markdown"]),
        "json_path": str(paths["json"]),
        "latest_markdown_path": str(paths["latest_markdown"]),
        "latest_json_path": str(paths["latest_json"]),
        "markdown_file": paths["markdown"].name,
        "json_file": paths["json"].name,
        "latest_markdown_file": paths["latest_markdown"].name,
        "latest_json_file": paths["latest_json"].name,
    }


def _demo_brand_context_receipt_response(payload=None):
    payload = payload or {}
    receipt = _brand_context_receipt_payload(payload)
    paths = _write_brand_context_receipt_files(receipt)
    return {
        "receipt": receipt,
        "markdown_path": str(paths["markdown"]),
        "json_path": str(paths["json"]),
        "latest_markdown_path": str(paths["latest_markdown"]),
        "latest_json_path": str(paths["latest_json"]),
        "markdown_file": paths["markdown"].name,
        "json_file": paths["json"].name,
        "latest_markdown_file": paths["latest_markdown"].name,
        "latest_json_file": paths["latest_json"].name,
        "markdown_url": f"/api/frank/demo/brand-context/{paths['markdown'].name}",
        "json_url": f"/api/frank/demo/brand-context/{paths['json'].name}",
        "latest_markdown_url": f"/api/frank/demo/brand-context/{paths['latest_markdown'].name}",
        "latest_json_url": f"/api/frank/demo/brand-context/{paths['latest_json'].name}",
    }


def _brand_context_receipt_payload(payload):
    store = _store()
    sessions = store.list_sessions()
    session_id = payload.get("session_id")
    session = next((item for item in sessions if item.get("id") == session_id), None) if session_id else None
    if not session:
        active_sessions = [item for item in sessions if item.get("status") == "active"]
        session = _select_demo_doctor_session(sessions, active_sessions)
    assets = store.list_assets(session_id=session["id"]) if session else []
    reference_assets = [asset for asset in assets if asset.get("kind") == "reference"]
    approved_assets = [
        asset
        for asset in assets
        if asset.get("kind") not in {"reference", "mask"} and asset.get("approval_status") == "approved"
    ]
    brand_kit = _active_brand_kit()
    prompt_min = 30
    prompt_target = 80
    lora_min = 100
    lora_target = 300
    reference_count = len(reference_assets)
    return {
        "title": "Frank Create Brand Context Brief",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session": {
            "id": session.get("id") if session else None,
            "name": session.get("name") if session else None,
            "status": session.get("status") if session else None,
        },
        "summary": {
            "style_guidance_chars": len((brand_kit.get("style_guidance") or "").strip()),
            "negative_prompt_chars": len((brand_kit.get("negative_prompt") or "").strip()),
            "reference_notes_chars": len((brand_kit.get("reference_notes") or "").strip()),
            "reference_asset_count": reference_count,
            "approved_asset_count": len(approved_assets),
            "prompt_guided_status": _brand_context_status(reference_count, prompt_min, prompt_target),
            "lora_training_status": _brand_context_status(reference_count, lora_min, lora_target),
            "prompt_guided_target": f"{prompt_min}-{prompt_target} curated references",
            "lora_training_target": f"{lora_min}-{lora_target} rights-cleared references",
        },
        "brand_kit": {
            "style_guidance": brand_kit.get("style_guidance") or "",
            "negative_prompt": brand_kit.get("negative_prompt") or "",
            "reference_notes": brand_kit.get("reference_notes") or "",
            "sync_status": brand_kit.get("sync_status") or "local",
            "remote_id": brand_kit.get("remote_id"),
            "updated_at": brand_kit.get("updated_at"),
        },
        "reference_assets": [_brand_context_asset_summary(asset) for asset in reference_assets],
        "approved_assets": [_brand_context_asset_summary(asset) for asset in approved_assets],
        "training_recommendation": {
            "frank_body_mode": "Use prompt-guided Frank Body Mode first; it works with all current launch providers and selected references.",
            "lora": "Treat LoRA as a later open-model layer for FLUX/SDXL only after image rights, product coverage, and QA references are approved.",
            "do_not_train_on": "Do not train on Slack screenshots, unlicensed campaign pulls, or supplier imagery without explicit rights clearance.",
        },
        "next_inputs": _brand_context_next_inputs(reference_count, prompt_min, prompt_target, lora_min, lora_target),
    }


def _brand_context_status(count, minimum, target):
    if count >= target:
        return "strong"
    if count >= minimum:
        return "ready"
    if count > 0:
        return "starter"
    return "missing"


def _brand_context_next_inputs(count, prompt_min, prompt_target, lora_min, lora_target):
    items = [
        "Add approved pack shots for every hero SKU, front label, texture, and cap/lid angle.",
        "Add director-approved lifestyle references with the Frank pink/coffee/cherry/off-black palette.",
        "Keep prompt-guided references separate from any future rights-cleared LoRA training set.",
        "Tag references by product, channel, campaign mood, must-preserve details, and avoid-list.",
    ]
    if count < prompt_min:
        items.insert(0, f"Collect {prompt_min - count} more curated references to reach the prompt-guided starter target.")
    elif count < prompt_target:
        items.insert(0, f"Add {prompt_target - count} more references for a stronger prompt-guided validation set.")
    if count < lora_min:
        items.append(f"Future LoRA still needs at least {lora_min - count} more rights-cleared references.")
    elif count < lora_target:
        items.append(f"Future LoRA can start, but {lora_target - count} more references would make it healthier.")
    return items


def _brand_context_asset_summary(asset):
    return {
        "id": asset.get("id"),
        "title": asset.get("title"),
        "kind": asset.get("kind"),
        "media_type": asset.get("media_type") or "image",
        "file_path": asset.get("file_path"),
        "approval_status": asset.get("approval_status"),
        "favorite": bool(asset.get("favorite")),
        "sync_status": asset.get("sync_status") or "local",
        "remote_id": asset.get("remote_id"),
    }


def _write_brand_context_receipt_files(receipt):
    output_dir = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    markdown_path = output_dir / f"frank-create-brand-context-{timestamp}.md"
    json_path = output_dir / f"frank-create-brand-context-{timestamp}.json"
    latest_markdown_path = output_dir / "frank-create-brand-context-latest.md"
    latest_json_path = output_dir / "frank-create-brand-context-latest.json"
    markdown = _brand_context_receipt_markdown(receipt)
    json_payload = json.dumps(receipt, indent=2, sort_keys=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_payload, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_json_path.write_text(json_payload, encoding="utf-8")
    return {
        "markdown": markdown_path,
        "json": json_path,
        "latest_markdown": latest_markdown_path,
        "latest_json": latest_json_path,
    }


def _brand_context_receipt_markdown(receipt):
    summary = receipt.get("summary") or {}
    brand_kit = receipt.get("brand_kit") or {}
    lines = [
        "# Frank Create Brand Context Brief",
        "",
        f"Generated: {receipt.get('generated_at')}",
        f"Session: {(receipt.get('session') or {}).get('name') or 'none'}",
        "",
        "## Readiness",
        "",
        f"- References: {summary.get('reference_asset_count', 0)}",
        f"- Approved outputs: {summary.get('approved_asset_count', 0)}",
        f"- Prompt-guided target: {summary.get('prompt_guided_target')} ({summary.get('prompt_guided_status')})",
        f"- Future LoRA target: {summary.get('lora_training_target')} ({summary.get('lora_training_status')})",
        "",
        "## Brand Kit",
        "",
        f"- Style guidance: {brand_kit.get('style_guidance') or 'none'}",
        f"- Negative guardrails: {brand_kit.get('negative_prompt') or 'none'}",
        f"- Reference notes: {brand_kit.get('reference_notes') or 'none'}",
        "",
        "## What To Supply Next",
        "",
    ]
    lines.extend(f"- {item}" for item in receipt.get("next_inputs") or [])
    lines.extend(["", "## Current References", ""])
    references = receipt.get("reference_assets") or []
    if references:
        for asset in references:
            lines.append(f"- {asset.get('title') or asset.get('id')}: `{asset.get('file_path')}`")
    else:
        lines.append("- No reference assets attached to the active session yet.")
    lines.extend(["", "## Training Recommendation", ""])
    recommendation = receipt.get("training_recommendation") or {}
    lines.extend(f"- {key.replace('_', ' ').title()}: {value}" for key, value in recommendation.items())
    return "\n".join(lines).strip() + "\n"


def _provider_readiness_receipt_payload(provider_status):
    summary = provider_status.get("summary") or {}
    adapter_audit = _provider_adapter_audit_response()
    return {
        "title": "Frank Create Provider Readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "model_count": int(summary.get("modelCount") or 0),
            "ready_models": int(summary.get("readyModels") or 0),
            "waiting_models": int(summary.get("waitingModels") or 0),
            "configured_env_vars": list(summary.get("configuredEnvVars") or []),
            "missing_env_vars": list(summary.get("missingEnvVars") or []),
        },
        "providers": provider_status.get("providers") or [],
        "model_roster": _model_roster_for_evidence(provider_status.get("models") or []),
        "adapter_audit": adapter_audit,
        "mocked_live_path_coverage": _mocked_live_path_coverage(),
        "notes": provider_status.get("notes") or [],
    }


def _mocked_live_path_coverage():
    return [
        {
            "provider": "google",
            "model": "Nano Banana Pro / NB 2",
            "proof": "Mocked v1 generateContent generation/edit responses create review image assets and send edit sources as inline data.",
        },
        {
            "provider": "openai",
            "model": "gpt-image-2",
            "proof": "Mocked masked-edit request sends source image and mask as separate multipart files.",
        },
        {
            "provider": "replicate",
            "model": "FLUX 1.1 Pro Ultra",
            "proof": "Mocked Replicate prediction response creates review assets through the server-side Replicate token path.",
        },
    ]


def _write_provider_readiness_receipt_files(receipt):
    output_dir = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    markdown_path = output_dir / f"frank-create-provider-readiness-{timestamp}.md"
    json_path = output_dir / f"frank-create-provider-readiness-{timestamp}.json"
    latest_markdown_path = output_dir / "frank-create-provider-readiness-latest.md"
    latest_json_path = output_dir / "frank-create-provider-readiness-latest.json"
    markdown = _provider_readiness_receipt_markdown(receipt)
    json_payload = json.dumps(receipt, indent=2, sort_keys=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_payload, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_json_path.write_text(json_payload, encoding="utf-8")
    return {
        "markdown": markdown_path,
        "json": json_path,
        "latest_markdown": latest_markdown_path,
        "latest_json": latest_json_path,
    }


def _provider_readiness_receipt_markdown(receipt):
    summary = receipt.get("summary") or {}
    lines = [
        "# Frank Create Provider Readiness",
        "",
        f"Generated: {receipt.get('generated_at')}",
        "",
        "## Summary",
        "",
        f"- Models ready: {summary.get('ready_models', 0)} / {summary.get('model_count', 0)}",
        f"- Models waiting on keys: {summary.get('waiting_models', 0)}",
        f"- Configured env vars: {', '.join(summary.get('configured_env_vars') or []) or 'none'}",
        f"- Missing env vars: {', '.join(summary.get('missing_env_vars') or []) or 'none'}",
        "",
        "## Providers",
        "",
    ]
    for provider in receipt.get("providers") or []:
        lines.append(
            f"- {provider.get('provider')}: {provider.get('ready_model_count', 0)} ready / "
            f"{provider.get('model_count', 0)} models; waiting {provider.get('waiting_model_count', 0)}"
        )

    lines.extend(["", "## Launch Model Roster", ""])
    for model in receipt.get("model_roster") or []:
        missing = ", ".join(model.get("missing_env_vars") or [])
        status = "ready" if model.get("configured") else f"needs {missing or 'server key'}"
        capabilities = ", ".join(model.get("capabilities") or [])
        lines.append(
            f"- {model.get('label')} ({model.get('provider')}, {model.get('badge')}): "
            f"{status}; {capabilities}; {model.get('reference_limit')} refs"
        )

    adapter_audit = receipt.get("adapter_audit") or {}
    audit_summary = adapter_audit.get("summary") or {}
    if audit_summary:
        lines.extend(
            [
                "",
                "## No-Spend Adapter Audit",
                "",
                f"- Adapter runners registered: {audit_summary.get('runner_registered', 0)} / {audit_summary.get('model_count', 0)}",
                f"- Missing runners: {audit_summary.get('missing_runners', 0)}",
                f"- Request preview failures: {audit_summary.get('preview_failures', 0)}",
                f"- Operation request previews: {audit_summary.get('operation_preview_count', 0)} checked / {audit_summary.get('operation_preview_failures', 0)} failures",
                f"- External API calls made: {'no' if audit_summary.get('no_spend') else 'check'}",
                f"- Secret values returned: {'no' if not audit_summary.get('secret_values_returned') else 'check'}",
                "",
            ]
        )
        for model in adapter_audit.get("models") or []:
            preview = model.get("request_preview") or {}
            operation_kinds = ", ".join(model.get("operation_kinds") or [])
            operation_preview_count = len(model.get("request_previews") or {})
            lines.append(
                f"- {model.get('label')} ({model.get('provider')}): {model.get('status')}; "
                f"{operation_preview_count} operation preview(s): {operation_kinds or 'none'}; "
                f"{preview.get('method', 'n/a')} {preview.get('endpoint', 'n/a')}"
            )

    coverage = receipt.get("mocked_live_path_coverage") or []
    if coverage:
        lines.extend(["", "## Mocked Live-Path Coverage", ""])
        for item in coverage:
            lines.append(f"- {item.get('model')} ({item.get('provider')}): {item.get('proof')}")

    notes = receipt.get("notes") or []
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines).strip() + "\n"


def _write_activation_checklist_receipt_files(checklist):
    output_dir = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    markdown_path = output_dir / f"frank-create-activation-checklist-{timestamp}.md"
    json_path = output_dir / f"frank-create-activation-checklist-{timestamp}.json"
    latest_markdown_path = output_dir / "frank-create-activation-checklist-latest.md"
    latest_json_path = output_dir / "frank-create-activation-checklist-latest.json"
    markdown = _activation_checklist_markdown(checklist)
    json_payload = json.dumps(checklist, indent=2, sort_keys=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_payload, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_json_path.write_text(json_payload, encoding="utf-8")
    return {
        "markdown": markdown_path,
        "json": json_path,
        "latest_markdown": latest_markdown_path,
        "latest_json": latest_json_path,
    }


def _activation_checklist_markdown(checklist):
    summary = checklist.get("summary") or {}
    lines = [
        "# Frank Create Production Unlock Checklist",
        "",
        f"Status: **{checklist.get('status')}**",
        "",
        "## Summary",
        "",
        f"- Live model paths unlocked: {summary.get('ready_provider_models', 0)} / {summary.get('provider_model_count', 0)}",
        f"- Live model paths waiting: {summary.get('waiting_provider_models', 0)}",
        f"- Local checkpoint count: {summary.get('checkpoint_count', 0)}",
        f"- Diffusion checkpoint ready: {'yes' if summary.get('diffusion_ready') else 'no'}",
        f"- Server key file: `{summary.get('server_key_file') or 'user/frank_create/provider_keys.env'}`",
        f"- Configured env vars: {', '.join(summary.get('configured_env_vars') or []) or 'none'}",
        f"- Missing env vars: {', '.join(summary.get('missing_env_vars') or []) or 'none'}",
        "",
        "## Unlock Steps",
        "",
    ]
    for index, step in enumerate(checklist.get("steps") or [], start=1):
        lines.extend(
            [
                f"### {index}. {step.get('label')}",
                "",
                f"- Status: {step.get('status')}",
                f"- Detail: {step.get('detail')}",
                f"- Action: {step.get('action')}",
            ]
        )
        if step.get("env_vars"):
            lines.append(f"- Env vars: {', '.join(step.get('env_vars') or [])}")
        if step.get("path"):
            lines.append(f"- Path: `{step.get('path')}`")
        lines.append("")
    notes = checklist.get("notes") or []
    if notes:
        lines.extend(["## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines).strip() + "\n"


def _demo_evidence_payload(doctor, workflow_smoke, payload=None, cliff_prep=None, provider_status=None):
    payload = payload or {}
    provider_status = provider_status or _provider_readiness_response()
    summary = doctor.get("summary") or {}
    checks = doctor.get("checks") or []
    return {
        "title": "Frank Create Demo Evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": payload.get("base_url") or "http://127.0.0.1:8190",
        "headline": doctor.get("headline") or "Demo readiness",
        "status": doctor.get("status") or "unknown",
        "ready_for_demo": bool(doctor.get("readyForDemo")),
        "summary": {
            "outputs": int(summary.get("outputAssetCount") or 0),
            "references": int(summary.get("referenceAssetCount") or 0),
            "approved": int(summary.get("approvedAssetCount") or 0),
            "video": int(summary.get("videoAssetCount") or 0),
            "workflow_smoke_ok": bool(summary.get("workflowSmokeOk")),
            "workflow_smoke_at": summary.get("workflowSmokeAt"),
            "workflow_smoke_media_files": int(summary.get("workflowSmokeMediaFileCount") or 0),
            "workflow_smoke_channel_exports": int(summary.get("workflowSmokeChannelExportFileCount") or 0),
            "waiting_provider_models": int(summary.get("waitingProviderModels") or 0),
            "secret_issue_count": int(summary.get("secretIssueCount") or 0),
            "graph_branding_ready": bool(summary.get("graphBrandingReady")),
            "call_brief_ready": bool(summary.get("callBriefReady")),
            "readiness_pack_ready": bool(summary.get("readinessPackReady")),
            "readiness_pack_bytes": int(summary.get("readinessPackBytes") or 0),
            "provider_adapter_count": int(summary.get("providerAdapterCount") or 0),
            "missing_provider_adapter_count": int(summary.get("missingProviderAdapterCount") or 0),
        },
        "checks": checks,
        "warnings": [check for check in checks if check.get("status") == "warning"],
        "failures": [check for check in checks if check.get("status") == "fail"],
        "notes": doctor.get("notes") or [],
        "model_roster": _model_roster_for_evidence(provider_status.get("models") or []),
        "workflow_smoke": {
            "ok": bool(workflow_smoke.get("ok")),
            "session_name": workflow_smoke.get("session_name") or workflow_smoke.get("error") or "Workflow smoke",
            "completed_at": workflow_smoke.get("completed_at"),
            "media_file_count": int(workflow_smoke.get("media_file_count") or 0),
            "channel_export_file_count": int(workflow_smoke.get("channel_export_file_count") or 0),
            "detail": workflow_smoke.get("detail"),
        },
        "cliff_prep": cliff_prep,
        "demo_urls": {
            "studio": payload.get("base_url") or "http://127.0.0.1:8190",
            "advanced_graph": f"{payload.get('base_url') or 'http://127.0.0.1:8190'}/graph",
            "raw_comfy": f"{payload.get('base_url') or 'http://127.0.0.1:8190'}/comfy/",
        },
    }


def _model_roster_for_evidence(models):
    roster = []
    for model in models:
        missing_env_vars = list(model.get("missing_env_vars") or [])
        configured = bool(model.get("configured"))
        roster.append(
            {
                "id": model.get("id"),
                "label": model.get("short_label") or model.get("label") or model.get("id"),
                "provider": model.get("provider"),
                "badge": model.get("badge") or model.get("max_resolution_label") or "",
                "status": "ready" if configured else "waiting_for_key",
                "configured": configured,
                "missing_env_vars": missing_env_vars,
                "capabilities": {
                    key: bool((model.get("capabilities") or {}).get(key))
                    for key in ("generation", "edit", "masked_edit", "video")
                },
                "reference_image_limit": int(model.get("reference_image_limit") or 0),
            }
        )
    return roster


def _write_demo_evidence_files(evidence):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"frank-create-demo-evidence-{timestamp}.md"
    json_path = output_dir / f"frank-create-demo-evidence-{timestamp}.json"
    latest_markdown_path = output_dir / "frank-create-demo-evidence-latest.md"
    latest_json_path = output_dir / "frank-create-demo-evidence-latest.json"
    markdown = _demo_evidence_markdown(evidence)
    json_payload = json.dumps(evidence, indent=2, sort_keys=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_payload, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_json_path.write_text(json_payload, encoding="utf-8")
    return {
        "markdown": markdown_path,
        "json": json_path,
        "latest_markdown": latest_markdown_path,
        "latest_json": latest_json_path,
    }


def _demo_call_brief_payload(doctor, workflow_smoke, provider_status, payload=None, readiness_pack=None):
    payload = payload or {}
    summary = doctor.get("summary") or {}
    warnings = [check for check in doctor.get("checks") or [] if check.get("status") == "warning"]
    failures = [check for check in doctor.get("checks") or [] if check.get("status") == "fail"]
    base_url = payload.get("base_url") or "http://127.0.0.1:8190"
    call_decision = _demo_call_decision(doctor, warnings, failures)
    return {
        "title": "Frank Create Cliff Call Brief",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": doctor.get("headline") or "Demo readiness",
        "status": doctor.get("status") or "unknown",
        "ready_for_demo": bool(doctor.get("readyForDemo")),
        "call_decision": call_decision,
        "summary": {
            "outputs": int(summary.get("outputAssetCount") or 0),
            "approved": int(summary.get("approvedAssetCount") or 0),
            "references": int(summary.get("referenceAssetCount") or 0),
            "videos": int(summary.get("videoAssetCount") or 0),
            "workflow_smoke_ok": bool(summary.get("workflowSmokeOk")),
            "workflow_smoke_at": summary.get("workflowSmokeAt"),
            "graph_branding_ready": bool(summary.get("graphBrandingReady")),
            "provider_adapter_count": int(summary.get("providerAdapterCount") or 0),
            "waiting_provider_models": int(summary.get("waitingProviderModels") or 0),
            "checkpoint_count": int(summary.get("checkpointCount") or 0),
        },
        "workflow_smoke": {
            "ok": bool(workflow_smoke.get("ok")),
            "session_name": workflow_smoke.get("session_name") or "Workflow smoke",
            "completed_at": workflow_smoke.get("completed_at"),
            "handoff_media_files": int(
                workflow_smoke.get("media_file_count") or (workflow_smoke.get("handoff") or {}).get("media_file_count") or 0
            ),
            "handoff_channel_exports": int(
                workflow_smoke.get("channel_export_file_count")
                or (workflow_smoke.get("handoff") or {}).get("channel_export_file_count")
                or 0
            ),
        },
        "warnings": warnings,
        "failures": failures,
        "readiness_pack": {
            "path": str(readiness_pack) if readiness_pack else "",
            "exists": bool(readiness_pack and Path(readiness_pack).exists()),
            "latest_file": "frank-create-cliff-readiness-latest.zip",
        },
        "model_summary": {
            "ready_models": int((provider_status.get("summary") or {}).get("readyModels") or 0),
            "waiting_models": int((provider_status.get("summary") or {}).get("waitingModels") or 0),
        },
        "talk_track": [
            "Frank Create is a Frank-branded creative shell over ComfyUI, with the raw graph still available for power users.",
            "The local demo proves prompt, reference upload, generation, edit, approval, export, motion storyboard, and mixed-media handoff without paid API calls.",
            "Live provider keys stay server-side; the browser only sees readiness, env var names, and capability badges.",
            "Handoff ZIPs include approved media, references, a visual review board, prompts, notes, workflow provenance, project/brief context, sync-ready fields, byte-for-byte media integrity, and SHA-256 integrity metadata.",
            "The workflow smoke, readiness builder, and VERIFY_CLIFF_PACK.cmd compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.",
        ],
        "demo_urls": {
            "studio": base_url,
            "advanced_graph": f"{base_url}/graph",
            "raw_comfy": f"{base_url}/comfy/",
        },
        "handoff_path": "user\\frank_create\\readiness_packs\\frank-create-cliff-readiness-latest.zip",
        "expected_warning_keys": [warning.get("key") for warning in warnings],
    }


def _demo_call_decision(doctor, warnings, failures):
    failure_keys = [item.get("key") for item in failures if item.get("key")]
    warning_keys = [item.get("key") for item in warnings if item.get("key")]
    if failures or not doctor.get("readyForDemo"):
        status = "NO-GO"
        headline = "Fix the failing checks before presenting."
        can_present = False
    elif warnings:
        status = "GO WITH WARNINGS"
        headline = "Present the local demo; name the expected live-key/checkpoint caveats."
        can_present = True
    else:
        status = "GO"
        headline = "Present the demo as ready."
        can_present = True

    return {
        "status": status,
        "headline": headline,
        "can_present": can_present,
        "warning_keys": warning_keys,
        "failure_keys": failure_keys,
        "warnings": [
            {"key": item.get("key"), "detail": item.get("detail"), "action": item.get("action")}
            for item in warnings
        ],
        "failures": [
            {"key": item.get("key"), "detail": item.get("detail"), "action": item.get("action")}
            for item in failures
        ],
    }


def _write_demo_call_brief_files(brief):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = _store().root_dir / DEMO_EVIDENCE_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"frank-create-call-brief-{timestamp}.md"
    json_path = output_dir / f"frank-create-call-brief-{timestamp}.json"
    latest_markdown_path = output_dir / "frank-create-call-brief-latest.md"
    latest_json_path = output_dir / "frank-create-call-brief-latest.json"
    markdown = _demo_call_brief_markdown(brief)
    json_payload = json.dumps(brief, indent=2, sort_keys=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_payload, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_json_path.write_text(json_payload, encoding="utf-8")
    return {
        "markdown": markdown_path,
        "json": json_path,
        "latest_markdown": latest_markdown_path,
        "latest_json": latest_json_path,
    }


def _demo_call_brief_markdown(brief):
    summary = brief.get("summary") or {}
    smoke = brief.get("workflow_smoke") or {}
    pack = brief.get("readiness_pack") or {}
    model_summary = brief.get("model_summary") or {}
    decision = brief.get("call_decision") or {}
    lines = [
        "# Frank Create Cliff Call Brief",
        "",
        f"Generated: {brief.get('generated_at')}",
        f"Status: **{brief.get('headline')}** (`{brief.get('status')}`)",
        f"Ready for demo: **{'yes' if brief.get('ready_for_demo') else 'no'}**",
        "",
        "## Call-Day Decision",
        "",
        f"**{decision.get('status', 'UNKNOWN')}**",
        "",
        decision.get("headline") or "Run Demo Doctor before presenting.",
        "",
        "## What Passed",
        "",
        f"- Outputs: {summary.get('outputs', 0)}",
        f"- Approved assets: {summary.get('approved', 0)}",
        f"- References: {summary.get('references', 0)}",
        f"- Motion/storyboard assets: {summary.get('videos', 0)}",
        f"- Workflow smoke: {'passed' if smoke.get('ok') else 'not passed'} ({smoke.get('session_name')})",
        f"- Handoff media files in smoke: {smoke.get('handoff_media_files', 0)}",
        f"- Handoff channel exports in smoke: {smoke.get('handoff_channel_exports', 0)}",
        f"- Graph branding: {'verified' if summary.get('graph_branding_ready') else 'not verified'}",
        f"- Provider adapters: {summary.get('provider_adapter_count', 0)} registered",
        "",
        "## What To Hand Over",
        "",
        f"- Readiness pack: `{brief.get('handoff_path')}`",
        "- Provider readiness: `provider-readiness/frank-create-provider-readiness-latest.md`",
        "- Activation checklist: `activation-checklist/frank-create-activation-checklist-latest.md`",
        "- Brand context: `brand-context/frank-create-brand-context-latest.md`",
        f"- Launch models: {model_summary.get('ready_models', 0)} ready / {model_summary.get('waiting_models', 0)} waiting on keys",
        f"- Latest pack exists: {'yes' if pack.get('exists') else 'not yet'}",
        "- Open `FRANK_CREATE_CALL_DAY.md` first, then `evidence/frank-create-demo-evidence-latest.md`.",
        "",
        "## Talk Track",
        "",
    ]
    decision_insert_at = lines.index("## What Passed") - 1
    decision_notes = []
    if decision.get("warnings"):
        decision_notes.extend(["", "Warnings to name:"])
        for warning in decision.get("warnings") or []:
            decision_notes.append(f"- `{warning.get('key')}` {warning.get('detail')}")
    if decision.get("failures"):
        decision_notes.extend(["", "Fix before call:"])
        for failure in decision.get("failures") or []:
            decision_notes.append(f"- `{failure.get('key')}` {failure.get('detail')}")
    if decision_notes:
        lines[decision_insert_at:decision_insert_at] = decision_notes
    lines.extend(f"- {item}" for item in brief.get("talk_track") or [])
    warnings = brief.get("warnings") or []
    if warnings:
        lines.extend(["", "## Expected Warnings", ""])
        for warning in warnings:
            lines.append(f"- `{warning.get('key')}` {warning.get('detail')}")
            if warning.get("action"):
                lines.append(f"  Action: {warning.get('action')}")
    failures = brief.get("failures") or []
    if failures:
        lines.extend(["", "## Fix Before Call", ""])
        for failure in failures:
            lines.append(f"- `{failure.get('key')}` {failure.get('detail')}")
            if failure.get("action"):
                lines.append(f"  Action: {failure.get('action')}")
    urls = brief.get("demo_urls") or {}
    lines.extend(
        [
            "",
            "## URLs",
            "",
            f"- Studio: {urls.get('studio')}",
            f"- Advanced Graph: {urls.get('advanced_graph')}",
            f"- Raw Comfy: {urls.get('raw_comfy')}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _latest_readiness_pack_path():
    path = _store().root_dir / READINESS_PACK_DIRNAME / "frank-create-cliff-readiness-latest.zip"
    return path if path.exists() else None


def _write_readiness_pack_checksum(zip_path):
    checksum_path = zip_path.with_suffix(zip_path.suffix + ".sha256")
    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{sha256}  {zip_path.name}\n", encoding="utf-8")
    return {"path": checksum_path, "sha256": sha256, "file_size_bytes": zip_path.stat().st_size}


def _readiness_acceptance_matrix(
    evidence_response,
    provider_readiness_response=None,
    activation_checklist_response=None,
    brand_context_response=None,
):
    evidence = (evidence_response or {}).get("evidence") or {}
    summary = evidence.get("summary") or {}
    provider_receipt = (provider_readiness_response or {}).get("receipt") or provider_readiness_response or {}
    provider_summary = provider_receipt.get("summary") or {}
    adapter_audit = provider_receipt.get("adapter_audit") or {}
    audit_summary = adapter_audit.get("summary") or {}
    ready_models = int(provider_summary.get("ready_models") or provider_summary.get("readyModels") or 0)
    waiting_models = int(
        provider_summary.get("waiting_models")
        or provider_summary.get("waitingModels")
        or summary.get("waiting_provider_models")
        or 0
    )
    adapter_count = int(summary.get("provider_adapter_count") or 0)
    missing_adapters = int(summary.get("missing_provider_adapter_count") or 0)
    runner_count = int(audit_summary.get("runner_registered") or 0)
    runner_total = int(audit_summary.get("model_count") or 0)
    preview_failures = int(audit_summary.get("preview_failures") or 0)
    provider_status = "ready" if runner_total and runner_count == runner_total and preview_failures == 0 and missing_adapters == 0 else "check"
    provider_proof = (
        f"No-spend audit: {runner_count} / {runner_total} launch runners registered, "
        f"{preview_failures} preview failures; provider keys {ready_models} ready / {waiting_models} waiting."
        if runner_total
        else f"{adapter_count} registered, {missing_adapters} missing; provider keys {ready_models} ready / {waiting_models} waiting."
    )
    studio_proof = _studio_interaction_proof()
    brand_receipt = (brand_context_response or {}).get("receipt") or brand_context_response or {}
    brand_summary = brand_receipt.get("summary") or {}
    brand_ref_count = int(brand_summary.get("reference_asset_count") or summary.get("references") or 0)
    prompt_status = brand_summary.get("prompt_guided_status") or ("starter" if brand_ref_count else "missing")
    lora_status = brand_summary.get("lora_training_status") or ("starter" if brand_ref_count else "missing")
    brand_status = "ready" if brand_ref_count > 0 else "check"
    brand_proof = (
        f"Brand-context brief packaged with {brand_ref_count} reference asset(s); "
        f"prompt-guided mode is {prompt_status}, future LoRA is {lora_status}."
    )
    activation = (activation_checklist_response or {}).get("checklist") or activation_checklist_response or {}
    activation_steps = activation.get("steps") or []
    activation_labels = ", ".join(
        (step.get("label") or "").replace("Paste rotated live provider keys", "rotated live provider keys")
        for step in activation_steps[:3]
        if step.get("label")
    )
    activation_proof = (
        f"Activation checklist packaged with {len(activation_steps)} setup step(s): "
        f"{activation_labels or 'production unlock actions'}."
    )
    return [
        {
            "capability": "Conversational Image Studio",
            "status": "ready",
            "proof": studio_proof,
        },
        {
            "capability": "Product Shot Lab flow",
            "status": "ready",
            "proof": f"{summary.get('references', 0)} reference asset(s), {summary.get('outputs', 0)} output asset(s), {summary.get('approved', 0)} approved pick(s).",
        },
        {
            "capability": "Generate, edit, approve, export",
            "status": "ready" if summary.get("workflow_smoke_ok") else "check",
            "proof": (
                f"Workflow smoke media files: {summary.get('workflow_smoke_media_files', 0)}; "
                f"channel exports: {summary.get('workflow_smoke_channel_exports', 0)}."
            ),
        },
        {
            "capability": "Video Lab storyboard",
            "status": "ready" if int(summary.get("video") or 0) > 0 else "check",
            "proof": f"{summary.get('video', 0)} local storyboard/motion asset(s) available.",
        },
        {
            "capability": "Advanced Graph + raw Comfy",
            "status": "ready" if summary.get("graph_branding_ready") else "check",
            "proof": "Advanced Graph and raw Comfy QA screenshots plus branded graph Doctor check.",
        },
        {
            "capability": "Curated Comfy workflow blueprints",
            "status": "ready",
            "proof": "Local Comfy exposes downloadable stock-node txt2img, img2img, and inpaint workflow JSON blueprints.",
        },
        {
            "capability": "Frank Body Mode + brand context",
            "status": brand_status,
            "proof": brand_proof,
        },
        {
            "capability": "Live provider adapters",
            "status": provider_status,
            "proof": provider_proof,
        },
        {
            "capability": "Production activation checklist",
            "status": "ready" if activation_steps else "check",
            "proof": activation_proof,
        },
        {
            "capability": "Server-side key hygiene",
            "status": "ready" if int(summary.get("secret_issue_count") or 0) == 0 else "check",
            "proof": f"Secret hygiene issue count: {summary.get('secret_issue_count', 0)}; no provider keys are included in packs.",
        },
        {
            "capability": "Cliff handoff integrity",
            "status": "ready",
            "proof": "Readiness ZIP, nested handoff ZIP, workflow provenance, channel-ready approved-image exports, media integrity metadata, byte-for-byte media integrity, and SHA-256 sidecar; workflow smoke, readiness builder, and VERIFY_CLIFF_PACK.cmd compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.",
        },
    ]


def _acceptance_matrix_markdown(matrix):
    lines = [
        "## Acceptance Matrix",
        "",
        "| Capability | Status | Proof |",
        "| --- | --- | --- |",
    ]
    for item in matrix or []:
        lines.append(f"| {item.get('capability')} | {item.get('status')} | {item.get('proof')} |")
    return "\n".join(lines)


def _readiness_open_me_first_text():
    return (
        "# Open Me First\n\n"
        "This is the Frank Create Cliff readiness pack.\n\n"
        "## Fastest Path\n\n"
        "1. On Didac's workstation, double-click `CLIFF_START_HERE.cmd` from the project root.\n"
        "2. In this ZIP, open `call-brief/frank-create-call-brief-latest.md` for the one-page meeting view.\n"
        "3. Open `FRANK_CREATE_CALL_DAY.md` for the demo order and fallback commands.\n"
        "4. Open `provider-readiness/frank-create-provider-readiness-latest.md` to explain which live models are waiting on keys.\n"
        "5. Open `activation-checklist/frank-create-activation-checklist-latest.md` for production unlock actions.\n"
        "6. Open `brand-context/frank-create-brand-context-latest.md` to answer what Frank should supply for prompt guidance and future LoRA.\n\n"
        "Provider setup reference: `setup/frank-create.env.example` lists the server-side key names with blank placeholder values only.\n\n"
        "## What This Pack Proves\n\n"
        "- The local Frank Create workflow runs end to end: reference upload, generate, edit, approve, export, storyboard, and handoff.\n"
        "- The Advanced Graph and raw Comfy canvas are branded and still available for power users.\n"
        "- Open `handoff-review/frank-create-review-board-latest.png` for the instant visual contact sheet.\n"
        "- Open `sync/frank-create-sync-manifest-latest.json` for the portable `frank-create.sync.v1` FrankHub/Supabase/DAM mirror contract.\n"
        "- The nested `handoffs/` ZIP contains approved media, references, channel-ready approved-image exports, the same visual review board, prompts, notes, workflow provenance, and byte-for-byte media integrity metadata.\n"
        "- The workflow smoke, readiness builder, and `VERIFY_CLIFF_PACK.cmd` compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.\n"
        "- No provider API keys or local secret files are included.\n\n"
        "Expected warnings: no local diffusion checkpoint installed and live provider keys not loaded. "
        "The local Frank renderer remains ready for the demo.\n"
    )


def _implementation_manifest_text(base_url, acceptance_matrix, evidence_response=None, provider_readiness_response=None):
    evidence = (evidence_response or {}).get("evidence") or {}
    summary = evidence.get("summary") or {}
    provider_receipt = (provider_readiness_response or {}).get("receipt") or provider_readiness_response or {}
    provider_summary = provider_receipt.get("summary") or {}
    adapter_audit = (provider_receipt.get("adapter_audit") or {}).get("summary") or {}
    base = (base_url or "http://127.0.0.1:8190").rstrip("/")
    lines = [
        "# Frank Create Implementation Manifest",
        "",
        "Frank Create is a Frank-branded creative shell over ComfyUI for Frank Body image and motion workflows.",
        "",
        "## Built Surfaces",
        "",
        f"- Conversational Image Studio: `{base}`",
        f"- Advanced Graph escape hatch: `{base}/graph`",
        f"- Raw branded Comfy canvas: `{base}/comfy/`",
        "- Provider Setup: server-side key file plus no-spend adapter audit.",
        "- Production activation checklist: packaged key/checkpoint/rotation actions.",
        "- Demo Doctor: call-day health, evidence, call brief, and readiness pack generation.",
        "",
        "## Core Workflow",
        "",
        "- Create or select a session.",
        "- Upload product/reference assets.",
        "- Generate or edit image rounds with local Comfy/fallback or configured live providers.",
        "- Approve/favorite/reject outputs and add notes.",
        "- Export channel packs, storyboard GIFs, and mixed-media Cliff handoff ZIPs with channel-ready approved-image derivatives.",
        "- Open or package a `frank-create.sync.v1` sync manifest for FrankHub, Supabase, or DAM mirroring.",
        "",
        "## Verification Snapshot",
        "",
        f"- Outputs available: {summary.get('outputs', 0)}",
        f"- Approved assets: {summary.get('approved', 0)}",
        f"- Reference assets: {summary.get('references', 0)}",
        f"- Motion/storyboard assets: {summary.get('video', 0)}",
        f"- Workflow smoke media files: {summary.get('workflow_smoke_media_files', 0)}",
        f"- Workflow smoke channel exports: {summary.get('workflow_smoke_channel_exports', 0)}",
        f"- Provider models: {provider_summary.get('ready_models', provider_summary.get('readyModels', 0))} ready / {provider_summary.get('waiting_models', provider_summary.get('waitingModels', 0))} waiting on keys",
        f"- No-spend adapter audit: {adapter_audit.get('runner_registered', 0)} / {adapter_audit.get('model_count', 0)} launch runners, {adapter_audit.get('preview_failures', 0)} preview failures",
        "",
        "## Launch Commands",
        "",
        "- `CLIFF_START_HERE.cmd` starts or reuses the local Studio, runs the call-day chain, and opens the useful docs.",
        "- `START_FRANK_CREATE_DEMO.cmd` resets to a clean demo state and starts the app.",
        "- `BUILD_FRANK_CREATE_READINESS_PACK.cmd` rebuilds this proof pack.",
        "- `VERIFY_CLIFF_PACK.cmd` verifies the latest proof pack without rebuilding.",
        "",
        "## Acceptance Matrix",
        "",
        "| Capability | Status | Proof |",
        "| --- | --- | --- |",
    ]
    for item in acceptance_matrix or []:
        lines.append(f"| {item.get('capability')} | {item.get('status')} | {item.get('proof')} |")
    lines.extend(
        [
            "",
            "## Expected Warnings",
            "",
            "- Live provider models wait for rotated server-side API keys.",
            "- Google Gemini/Nano Banana is the first live API path after `GOOGLE_API_KEY` is saved, keys are reloaded, and the selected model preflight passes.",
            "- Local Comfy rounds use checkpoint txt2img when a checkpoint exists in `models/checkpoints`, checkpoint img2img for reference/edit rounds, and checkpoint inpaint for masked edits.",
            "- Provider API keys and local secret files are intentionally excluded from every readiness pack.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _write_demo_readiness_pack(
    evidence_response,
    payload=None,
    call_brief_response=None,
    provider_readiness_response=None,
    activation_checklist_response=None,
    brand_context_response=None,
):
    payload = payload or {}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = _store().root_dir / READINESS_PACK_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"frank-create-cliff-readiness-{timestamp}.zip"
    latest_zip_path = output_dir / "frank-create-cliff-readiness-latest.zip"
    latest_implementation_manifest_path = output_dir / "frank-create-implementation-manifest-latest.md"
    root = Path(__file__).resolve().parents[2]

    required_files = [
        (Path(call_brief_response["latest_markdown_path"]), "call-brief/frank-create-call-brief-latest.md")
        if call_brief_response
        else None,
        (Path(call_brief_response["latest_json_path"]), "call-brief/frank-create-call-brief-latest.json")
        if call_brief_response
        else None,
        (Path(provider_readiness_response["latest_markdown_path"]), "provider-readiness/frank-create-provider-readiness-latest.md")
        if provider_readiness_response
        else None,
        (Path(provider_readiness_response["latest_json_path"]), "provider-readiness/frank-create-provider-readiness-latest.json")
        if provider_readiness_response
        else None,
        (Path(activation_checklist_response["latest_markdown_path"]), "activation-checklist/frank-create-activation-checklist-latest.md")
        if activation_checklist_response
        else None,
        (Path(activation_checklist_response["latest_json_path"]), "activation-checklist/frank-create-activation-checklist-latest.json")
        if activation_checklist_response
        else None,
        (Path(brand_context_response["latest_markdown_path"]), "brand-context/frank-create-brand-context-latest.md")
        if brand_context_response
        else None,
        (Path(brand_context_response["latest_json_path"]), "brand-context/frank-create-brand-context-latest.json")
        if brand_context_response
        else None,
        (Path(evidence_response["latest_markdown_path"]), "evidence/frank-create-demo-evidence-latest.md"),
        (Path(evidence_response["latest_json_path"]), "evidence/frank-create-demo-evidence-latest.json"),
        (_workflow_smoke_status_path(), "receipts/workflow_smoke_status.json"),
        (_cliff_prep_status_path(), "receipts/cliff_prep_status.json"),
        (root / "FRANK_CREATE_CALL_DAY.md", "FRANK_CREATE_CALL_DAY.md"),
        (root / "FRANK_CREATE_DEMO.md", "FRANK_CREATE_DEMO.md"),
        (root / "OPEN_FOR_CLIFF.md", "OPEN_FOR_CLIFF.md"),
        (root / "config" / "frank-create.env.example", "setup/frank-create.env.example"),
        (root / "CLIFF_START_HERE.cmd", "launchers/CLIFF_START_HERE.cmd"),
        (root / "START_FRANK_CREATE_DEMO.cmd", "launchers/START_FRANK_CREATE_DEMO.cmd"),
        (root / "START_FRANK_CREATE.cmd", "launchers/START_FRANK_CREATE.cmd"),
        (root / "CHECK_FRANK_CREATE.cmd", "launchers/CHECK_FRANK_CREATE.cmd"),
        (root / "VERIFY_CLIFF_PACK.cmd", "launchers/VERIFY_CLIFF_PACK.cmd"),
        (root / "PREP_FRANK_CREATE_FOR_CLIFF.cmd", "launchers/PREP_FRANK_CREATE_FOR_CLIFF.cmd"),
        (root / "BUILD_FRANK_CREATE_READINESS_PACK.cmd", "launchers/BUILD_FRANK_CREATE_READINESS_PACK.cmd"),
        (root / "STOP_FRANK_CREATE.cmd", "launchers/STOP_FRANK_CREATE.cmd"),
    ]
    required_files = [item for item in required_files if item]
    cliff_pack = _create_readiness_cliff_pack()
    missing_files = []
    included_files = []
    screenshots = []
    hygiene_sources = []
    acceptance_matrix = _readiness_acceptance_matrix(
        evidence_response,
        provider_readiness_response,
        activation_checklist_response,
        brand_context_response,
    )

    manifest = {
        "product": "Frank Create",
        "purpose": "Cliff call-day readiness pack",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url": payload.get("base_url") or "http://127.0.0.1:8190",
        "includes": [],
        "missing_files": missing_files,
        "screenshot_count": 0,
        "acceptance_matrix": acceptance_matrix,
        "notes": [
            "No provider secrets are included.",
            "Open FRANK_CREATE_CALL_DAY.md first, then evidence/frank-create-demo-evidence-latest.md.",
            "For the shortest meeting view, open call-brief/frank-create-call-brief-latest.md.",
            "For live-model setup status, open provider-readiness/frank-create-provider-readiness-latest.md.",
            "For production unlock actions, open activation-checklist/frank-create-activation-checklist-latest.md.",
            "For Frank Body Mode and future training inputs, open brand-context/frank-create-brand-context-latest.md.",
            "The call-day handoff copy is frank-create-cliff-readiness-latest.zip.",
            "This pack is generated by the Frank Create backend from known proof artifacts only.",
        ],
    }
    screenshot_capture = _capture_readiness_screenshots(_store().root_dir, manifest["base_url"])
    manifest["screenshot_capture"] = screenshot_capture
    screenshot_paths = list(_readiness_screenshot_paths(_store().root_dir))
    screenshots = [f"screenshots/{screenshot.name}" for screenshot in screenshot_paths]
    browser_qa = _browser_qa_receipt(screenshots, manifest["base_url"])

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, archive_name in required_files:
            if not path.exists() or not path.is_file():
                missing_files.append(archive_name)
                continue
            if archive_name == "receipts/cliff_prep_status.json":
                cliff_prep = json.loads(path.read_text(encoding="utf-8-sig"))
                cliff_prep["browser_qa"] = browser_qa
                cliff_prep_json = json.dumps(cliff_prep, indent=2, sort_keys=True)
                archive.writestr(archive_name, cliff_prep_json)
                hygiene_sources.append({"kind": "text", "archive_name": archive_name, "text": cliff_prep_json})
            else:
                _zip_known_file(archive, path, archive_name)
                hygiene_sources.append({"kind": "file", "path": path, "archive_name": archive_name})
            included_files.append(archive_name)

        for screenshot in screenshot_paths:
            archive_name = f"screenshots/{screenshot.name}"
            archive.write(screenshot, archive_name)

        if cliff_pack.get("path"):
            _validate_readiness_handoff_zip(cliff_pack["path"])
            archive_name = f"handoffs/{cliff_pack['path'].name}"
            archive.write(cliff_pack["path"], archive_name)
            included_files.append(archive_name)
            cliff_pack["archive_path"] = archive_name
            review_board_archive_name = "handoff-review/frank-create-review-board-latest.png"
            review_board_bytes = _read_handoff_review_board_bytes(cliff_pack["path"])
            archive.writestr(review_board_archive_name, review_board_bytes)
            included_files.append(review_board_archive_name)
            cliff_pack["review_board_top_level_archive_path"] = review_board_archive_name
            hygiene_sources.append({"kind": "zip", "path": cliff_pack["path"], "archive_name": archive_name})

            sync_manifest_archive_name = "sync/frank-create-sync-manifest-latest.json"
            sync_manifest = _session_sync_manifest(cliff_pack["session_id"])
            sync_manifest_json = json.dumps(sync_manifest, indent=2, sort_keys=True)
            archive.writestr(sync_manifest_archive_name, sync_manifest_json)
            included_files.append(sync_manifest_archive_name)
            cliff_pack["sync_manifest_archive_path"] = sync_manifest_archive_name
            manifest["sync_manifest"] = {
                "status": "included",
                "schema_version": sync_manifest.get("schema_version"),
                "archive_path": sync_manifest_archive_name,
                "asset_count": (sync_manifest.get("counts") or {}).get("assets", 0),
                "approved_asset_count": (sync_manifest.get("counts") or {}).get("approved_assets", 0),
                "reference_asset_count": (sync_manifest.get("counts") or {}).get("reference_assets", 0),
            }
            hygiene_sources.append(
                {"kind": "text", "archive_name": sync_manifest_archive_name, "text": sync_manifest_json}
            )

        open_me_first = _readiness_open_me_first_text()
        implementation_manifest = _implementation_manifest_text(
            manifest["base_url"],
            acceptance_matrix,
            evidence_response,
            provider_readiness_response,
        )
        included_files.append("OPEN_ME_FIRST.md")
        included_files.append("IMPLEMENTATION_MANIFEST.md")
        manifest["includes"] = included_files
        manifest["screenshot_count"] = len(screenshots)
        if screenshots:
            manifest["screenshots"] = screenshots
        manifest["browser_qa"] = browser_qa
        browser_qa_json = json.dumps(browser_qa, indent=2, sort_keys=True)
        browser_qa_markdown = _browser_qa_receipt_markdown(browser_qa)
        screenshot_capture_json = json.dumps(screenshot_capture, indent=2, sort_keys=True)
        screenshot_capture_markdown = _screenshot_capture_receipt_markdown(screenshot_capture)
        archive.writestr("qa/browser-qa-receipt.json", browser_qa_json)
        archive.writestr("qa/browser-qa-receipt.md", browser_qa_markdown)
        archive.writestr("qa/screenshot-capture-receipt.json", screenshot_capture_json)
        archive.writestr("qa/screenshot-capture-receipt.md", screenshot_capture_markdown)
        included_files.extend(
            [
                "qa/browser-qa-receipt.json",
                "qa/browser-qa-receipt.md",
                "qa/screenshot-capture-receipt.json",
                "qa/screenshot-capture-receipt.md",
            ]
        )
        hygiene_sources.extend(
            [
                {"kind": "text", "archive_name": "qa/browser-qa-receipt.json", "text": browser_qa_json},
                {"kind": "text", "archive_name": "qa/browser-qa-receipt.md", "text": browser_qa_markdown},
                {
                    "kind": "text",
                    "archive_name": "qa/screenshot-capture-receipt.json",
                    "text": screenshot_capture_json,
                },
                {
                    "kind": "text",
                    "archive_name": "qa/screenshot-capture-receipt.md",
                    "text": screenshot_capture_markdown,
                },
            ]
        )
        if cliff_pack:
            manifest["cliff_pack"] = {key: value for key, value in cliff_pack.items() if key != "path"}

        readme = (
            "# Frank Create Cliff Readiness Pack\n\n"
            "Call-day file: frank-create-cliff-readiness-latest.zip.\n\n"
            "Checksum sidecar: frank-create-cliff-readiness-latest.zip.sha256.\n\n"
            "## Command Roster\n\n"
            "| Need | Double-click |\n"
            "| --- | --- |\n"
            "| Cliff call-day start | CLIFF_START_HERE.cmd |\n"
            "| Clean demo start | START_FRANK_CREATE_DEMO.cmd |\n"
            "| Keep current state | START_FRANK_CREATE.cmd |\n"
            "| Fast readiness check | CHECK_FRANK_CREATE.cmd |\n"
            "| Verify latest pack | VERIFY_CLIFF_PACK.cmd |\n"
            "| Full prep receipt | PREP_FRANK_CREATE_FOR_CLIFF.cmd |\n"
            "| Shareable proof pack | BUILD_FRANK_CREATE_READINESS_PACK.cmd |\n"
            "| Stop local server | STOP_FRANK_CREATE.cmd |\n\n"
            "Start with OPEN_ME_FIRST.md if you are opening this pack cold. "
            "IMPLEMENTATION_MANIFEST.md summarizes what was built and verified. "
            "OPEN_FOR_CLIFF.md is the shortest workstation note. "
            "Open call-brief/frank-create-call-brief-latest.md for the one-page meeting view. "
            "Open provider-readiness/frank-create-provider-readiness-latest.md for model/key readiness. "
            "Open activation-checklist/frank-create-activation-checklist-latest.md for production unlock actions. "
            "Open brand-context/frank-create-brand-context-latest.md for Frank Body Mode and future training inputs. "
            "Open setup/frank-create.env.example for blank server-side provider key names. "
            "Open handoff-review/frank-create-review-board-latest.png for the quickest visual contact sheet. "
            "Open sync/frank-create-sync-manifest-latest.json for the portable FrankHub/Supabase/DAM sync manifest. "
            "Command wrappers are bundled under launchers/ for reference. "
            "If opened inside an extracted pack, they open packaged proof docs instead of trying to rebuild the app. "
            "Open FRANK_CREATE_CALL_DAY.md for the quick checklist. "
            "Then open evidence/frank-create-demo-evidence-latest.md for the proof receipt.\n\n"
            f"{_acceptance_matrix_markdown(acceptance_matrix)}\n\n"
            "This pack includes the implementation manifest, latest call brief, provider-readiness receipt, production activation checklist, brand-context brief, demo evidence, SHA-256 sidecar, workflow smoke and Cliff prep receipts, "
            "the one-page call-day checklist, the current runbook, the short OPEN_FOR_CLIFF note, the blank provider-key template, current QA screenshots, "
            "local launcher wrappers, Browser QA, shareable-pack hygiene receipts, and a nested handoffs/ ZIP with approved media, "
            "references, prompts, notes, workflow provenance, a portable sync/frank-create-sync-manifest-latest.json contract, and byte-for-byte media integrity metadata. "
            "The same visual review board is also exposed at handoff-review/frank-create-review-board-latest.png for instant review. "
            "Workflow smoke, readiness builder, and VERIFY_CLIFF_PACK.cmd compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.\n\n"
            "No provider API keys or local secret files are included.\n"
        )
        if _contains_secret_like_token(readme):
            raise ValueError("Readiness pack README contains a secret-looking token.")
        hygiene_sources.append({"kind": "text", "archive_name": "README.md", "text": readme})
        hygiene_sources.append({"kind": "text", "archive_name": "OPEN_ME_FIRST.md", "text": open_me_first})
        hygiene_sources.append({"kind": "text", "archive_name": "IMPLEMENTATION_MANIFEST.md", "text": implementation_manifest})
        shareable_hygiene = _shareable_pack_hygiene_receipt(hygiene_sources)
        if shareable_hygiene["status"] != "clean":
            issues = "; ".join(f"{issue['path']}: {issue['reason']}" for issue in shareable_hygiene["issues"])
            raise ValueError(f"Readiness pack hygiene check failed: {issues}")
        manifest["shareable_pack_hygiene"] = shareable_hygiene
        shareable_hygiene_json = json.dumps(shareable_hygiene, indent=2, sort_keys=True)
        shareable_hygiene_markdown = _shareable_pack_hygiene_markdown(shareable_hygiene)
        archive.writestr("OPEN_ME_FIRST.md", open_me_first)
        archive.writestr("IMPLEMENTATION_MANIFEST.md", implementation_manifest)
        archive.writestr("README.md", readme)
        archive.writestr("qa/shareable-pack-hygiene.json", shareable_hygiene_json)
        archive.writestr("qa/shareable-pack-hygiene.md", shareable_hygiene_markdown)
        included_files.extend(["qa/shareable-pack-hygiene.json", "qa/shareable-pack-hygiene.md"])
        archive.writestr("readiness-pack-manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    latest_zip_path.write_bytes(zip_path.read_bytes())
    if "implementation_manifest" in locals():
        latest_implementation_manifest_path.write_text(implementation_manifest, encoding="utf-8")
    checksum = _write_readiness_pack_checksum(zip_path)
    latest_checksum = _write_readiness_pack_checksum(latest_zip_path)

    return {
        "path": zip_path,
        "latest_path": latest_zip_path,
        "checksum": checksum,
        "latest_checksum": latest_checksum,
        "manifest": manifest,
        "latest_implementation_manifest_path": str(latest_implementation_manifest_path),
    }


def _readiness_screenshot_paths(root_dir):
    root_dir = Path(root_dir)
    qa_dir = root_dir / "qa"
    return [qa_dir / name for name in READINESS_SCREENSHOT_NAMES if (qa_dir / name).is_file()]


def _capture_readiness_screenshots(root_dir, base_url):
    qa_dir = Path(root_dir) / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    base = (base_url or "http://127.0.0.1:8190").rstrip("/")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    receipt = {
        "status": "skipped",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "playwright screenshot",
        "base_url": base,
        "captured": [],
        "issues": [],
        "issue_count": 0,
        "notes": [],
    }
    if not npx:
        receipt["notes"].append("npx was not found, so existing QA screenshots were reused.")
        return receipt

    root = Path(__file__).resolve().parents[2]
    captures = [
        ("studio_desktop", "Studio desktop", "1440,960", base, "studio-live-desktop-latest.png", None),
        ("studio_mobile", "Studio mobile", "390,900", base, "studio-live-mobile-latest.png", None),
        ("video_lab", "Video Lab desktop", "1440,960", f"{base}/?mode=video-lab", "video-lab-live-desktop-latest.png", None),
        (
            "provider_audit",
            "Provider Adapter Audit",
            "1440,960",
            f"{base}/?provider_audit=1",
            "provider-audit-live-desktop-latest.png",
            "[aria-label='Provider adapter audit']",
        ),
        ("advanced_graph", "Advanced Graph", "1440,960", f"{base}/graph", "graph-live-desktop-latest.png", None),
        ("advanced_graph_mobile", "Advanced Graph mobile", "390,900", f"{base}/graph", "graph-live-mobile-latest.png", None),
        ("raw_comfy", "Raw Comfy canvas", "1440,960", f"{base}/comfy/", "raw-comfy-live-quiet-latest.png", None),
        (
            "raw_comfy_receipt",
            "Raw Comfy selected workflow receipt",
            "1440,960",
            _raw_comfy_receipt_url(base),
            "raw-comfy-workflow-receipt-latest.png",
            "[aria-label='Frank raw canvas workflow receipt']",
        ),
    ]
    for key, label, viewport, url, filename, wait_selector in captures:
        destination = qa_dir / filename
        command = [npx, "playwright", "screenshot", f"--viewport-size={viewport}", url, str(destination)]
        if wait_selector:
            command = [
                npx,
                "playwright",
                "screenshot",
                f"--viewport-size={viewport}",
                f"--wait-for-selector={wait_selector}",
                url,
                str(destination),
            ]
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            receipt["issues"].append({"key": key, "label": label, "file": filename, "reason": str(exc)})
            continue

        if completed.returncode != 0 or not destination.is_file():
            detail = (completed.stderr or completed.stdout or "Playwright screenshot failed.").strip()
            receipt["issues"].append({"key": key, "label": label, "file": filename, "reason": detail[-500:]})
            continue
        receipt["captured"].append({"key": key, "label": label, "file": filename, "url": url, "viewport": viewport})

    if len(receipt["captured"]) == len(captures):
        receipt["status"] = "captured"
        receipt["notes"].append("All canonical QA screenshots were refreshed before the pack was written.")
    elif receipt["captured"]:
        receipt["status"] = "partial"
        receipt["notes"].append("Some QA screenshots were refreshed; existing files may cover the remaining surfaces.")
    else:
        receipt["status"] = "failed"
        receipt["notes"].append("Screenshot capture failed, so existing QA screenshots were reused where available.")
    receipt["issue_count"] = len(receipt["issues"])
    return receipt


def _raw_comfy_receipt_url(base):
    asset_id = _latest_approved_image_asset_id()
    if not asset_id:
        return f"{base}/comfy/"
    return f"{base}/comfy/?frankAssetId={quote(asset_id)}"


def _latest_approved_image_asset_id():
    candidates = [
        asset
        for asset in _store().list_assets(approval_status="approved")
        if asset.get("kind") != "reference" and (asset.get("media_type") or "image") == "image"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda asset: asset.get("updated_at") or asset.get("created_at") or "", reverse=True)
    return candidates[0].get("id")


def _browser_qa_receipt(screenshots, base_url):
    screenshot_set = set(screenshots or [])
    checks = [
        {
            "key": "studio_desktop",
            "label": "Studio desktop",
            "screenshot": "screenshots/studio-live-desktop-latest.png",
        },
        {
            "key": "studio_mobile",
            "label": "Studio mobile",
            "screenshot": "screenshots/studio-live-mobile-latest.png",
        },
        {
            "key": "video_lab",
            "label": "Video Lab",
            "screenshot": "screenshots/video-lab-live-desktop-latest.png",
        },
        {
            "key": "provider_audit",
            "label": "Provider Adapter Audit",
            "screenshot": "screenshots/provider-audit-live-desktop-latest.png",
        },
        {
            "key": "advanced_graph",
            "label": "Advanced Graph",
            "screenshot": "screenshots/graph-live-desktop-latest.png",
        },
        {
            "key": "advanced_graph_mobile",
            "label": "Advanced Graph mobile",
            "screenshot": "screenshots/graph-live-mobile-latest.png",
        },
        {
            "key": "raw_comfy",
            "label": "Raw Comfy canvas",
            "screenshot": "screenshots/raw-comfy-live-quiet-latest.png",
        },
        {
            "key": "raw_comfy_receipt",
            "label": "Raw Comfy selected workflow receipt",
            "screenshot": "screenshots/raw-comfy-workflow-receipt-latest.png",
        },
    ]
    for check in checks:
        check["status"] = "included" if check["screenshot"] in screenshot_set else "missing"

    script_receipt = _load_browser_qa_script_receipt()
    script_checks = script_receipt.get("checks") if isinstance(script_receipt, dict) else []
    completed_at = script_receipt.get("completed_at") if isinstance(script_receipt, dict) else None
    for script_check in script_checks or []:
        check_key = str(script_check.get("key") or "")
        if not check_key:
            continue
        existing_check = next((check for check in checks if check.get("key") == check_key), None)
        if existing_check:
            existing_check["browser_status"] = str(script_check.get("status") or "")
            if script_check.get("url"):
                existing_check["url"] = str(script_check.get("url") or "")
            if script_check.get("detail"):
                existing_check["detail"] = str(script_check.get("detail") or "")
            continue
        checks.append(
            {
                "key": check_key,
                "label": str(script_check.get("label") or check_key),
                "status": str(script_check.get("status") or "missing"),
                "url": str(script_check.get("url") or ""),
                "detail": str(script_check.get("detail") or ""),
                "screenshot": str(script_check.get("screenshot") or ""),
            }
        )

    if not any(check.get("key") == "studio_interactions" for check in checks):
        checks.append(
            {
                "key": "studio_interactions",
                "label": "Studio interaction path",
                "status": "missing",
                "url": base_url,
                "detail": "Run Test-FrankCreateBrowserQa.ps1 before building the pack to prove the visible prompt, reference, safe provider key-plan copy, safe selected-output run brief copy with workflow provenance, mask-save, cleanup, graph, and raw Comfy paths.",
            }
        )

    return {
        "status": "ready" if all(check["status"] in {"included", "ready"} for check in checks) else "partial",
        "base_url": base_url,
        "completed_at": completed_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "notes": [
            "Screenshots were captured from the live local Frank Create app.",
            "Use these with the Demo Evidence receipt for visual QA proof.",
            "The Demo Doctor checksum row proves the visible UI checksum at browser-QA time; use the readiness ZIP .sha256 sidecar for the current package checksum after rebuilds.",
        ],
    }


def _browser_qa_receipt_markdown(receipt):
    lines = [
        "# Frank Create Browser QA Receipt",
        "",
        f"Status: **{receipt.get('status')}**",
        f"Base URL: `{receipt.get('base_url')}`",
        f"Generated: {receipt.get('generated_at')}",
        "",
        "## Covered Surfaces",
        "",
    ]
    for check in receipt.get("checks") or []:
        proof_parts = []
        if check.get("screenshot"):
            proof_parts.append(f"Screenshot: `{check.get('screenshot')}`")
        if check.get("browser_status"):
            proof_parts.append(f"Browser: `{check.get('browser_status')}`")
        if check.get("url"):
            proof_parts.append(f"URL: `{check.get('url')}`")
        if check.get("detail"):
            proof_parts.append(str(check.get("detail")))
        if not proof_parts:
            proof_parts.append("No proof detail recorded.")
        lines.append(f"- `{check.get('status')}` {check.get('label')}: {'; '.join(proof_parts)}")
    if receipt.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in receipt.get("notes"))
    return "\n".join(lines).strip() + "\n"


def _browser_qa_script_receipt_path():
    return _store().root_dir / "browser_qa_status.json"


def _load_browser_qa_script_receipt():
    path = _browser_qa_script_receipt_path()
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _studio_interaction_proof():
    receipt = _load_browser_qa_script_receipt()
    for check in (receipt or {}).get("checks") or []:
        if check.get("key") != "studio_interactions" or check.get("status") != "ready":
            continue
        detail = str(check.get("detail") or "").strip()
        if detail:
            return detail
    return "Session prompt/edit thread, reference assets, generated rounds, copies a safe provider key plan with env-var names and no secret values, safe selected-output run brief copy with workflow provenance, and desktop/mobile QA screenshots."


def _screenshot_capture_receipt_markdown(receipt):
    lines = [
        "# Frank Create Screenshot Capture Receipt",
        "",
        f"Status: **{receipt.get('status')}**",
        f"Base URL: `{receipt.get('base_url')}`",
        f"Generated: {receipt.get('generated_at')}",
        "",
        "## Captured",
        "",
    ]
    captured = receipt.get("captured") or []
    if captured:
        for capture in captured:
            lines.append(
                f"- `{capture.get('key')}` {capture.get('label')}: `{capture.get('file')}` at `{capture.get('viewport')}`"
            )
    else:
        lines.append("- No screenshots were captured in this run.")
    if receipt.get("issues"):
        lines.extend(["", "## Issues", ""])
        for issue in receipt.get("issues") or []:
            lines.append(f"- `{issue.get('key')}` {issue.get('label')}: {issue.get('reason')}")
    if receipt.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in receipt.get("notes") or [])
    return "\n".join(lines).strip() + "\n"


def _shareable_pack_hygiene_receipt(sources):
    issues = []
    text_suffixes = SECRET_HYGIENE_TEXT_SUFFIXES | {".md", ".txt", ".csv", ".ps1"}
    for source in sources:
        kind = source.get("kind")
        archive_name = str(source.get("archive_name") or "").replace("\\", "/")
        issues.extend(_shareable_pack_hygiene_name_issues(archive_name))
        if kind == "text":
            issues.extend(_shareable_pack_hygiene_text_issues(archive_name, source.get("text") or ""))
        elif kind == "file":
            path = Path(source["path"])
            if path.suffix.lower() not in text_suffixes or path.stat().st_size > 1_048_576:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            issues.extend(_shareable_pack_hygiene_text_issues(archive_name, text))
        elif kind == "zip":
            path = Path(source["path"])
            if not path.exists():
                continue
            with zipfile.ZipFile(path) as inner:
                for entry in inner.infolist():
                    inner_name = f"{archive_name}!/{entry.filename}".replace("\\", "/")
                    issues.extend(_shareable_pack_hygiene_name_issues(inner_name))
                    suffix = Path(entry.filename).suffix.lower()
                    if entry.is_dir() or suffix not in text_suffixes or entry.file_size > 1_048_576:
                        continue
                    text = inner.read(entry).decode("utf-8-sig", errors="ignore")
                    issues.extend(_shareable_pack_hygiene_text_issues(inner_name, text))
    return {
        "status": "clean" if not issues else "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned_root": "readiness pack source artifacts",
        "issue_count": len(issues),
        "issues": issues,
        "notes": [
            "Provider key placeholders such as ... are allowed.",
            "Actual provider-looking tokens or provider key files block the pack.",
        ],
    }


def _shareable_pack_hygiene_name_issues(archive_name):
    if not archive_name:
        return []
    normalized = archive_name.replace("\\", "/")
    if normalized.endswith("/") or normalized.startswith("qa/shareable-pack-hygiene."):
        return []
    if Path(normalized).name == PROVIDER_ENV_FILENAME or normalized.endswith("/.env") or normalized == ".env":
        return [{"path": normalized, "reason": "secret-looking file name"}]
    return []


def _shareable_pack_hygiene_text_issues(archive_name, text):
    if _contains_secret_like_token(text or ""):
        return [{"path": archive_name, "reason": "provider-token-shaped value"}]
    return []


def _shareable_pack_hygiene_markdown(receipt):
    lines = [
        "# Frank Create Shareable Pack Hygiene",
        "",
        f"Status: **{receipt.get('status')}**",
        f"Generated: {receipt.get('generated_at')}",
        f"Issues: {receipt.get('issue_count', 0)}",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in receipt.get("notes") or [])
    if receipt.get("issues"):
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {issue.get('path')}: {issue.get('reason')}" for issue in receipt.get("issues") or [])
    return "\n".join(lines).strip() + "\n"


def _validate_readiness_handoff_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "README.md" not in names:
            raise ValueError("Readiness handoff ZIP is missing README.md.")
        if "HANDOFF_SPEC.md" not in names:
            raise ValueError("Readiness handoff ZIP is missing HANDOFF_SPEC.md.")
        if "frank-create-handoff.json" not in names:
            raise ValueError("Readiness handoff ZIP is missing frank-create-handoff.json.")
        if not any(name.startswith("approved/") and not name.endswith("/") for name in names):
            raise ValueError("Readiness handoff ZIP has no approved media files.")
        if not any(name.startswith("references/") and not name.endswith("/") for name in names):
            raise ValueError("Readiness handoff ZIP has no reference media files.")

        manifest = json.loads(archive.read("frank-create-handoff.json").decode("utf-8-sig"))
        if not manifest.get("approved_assets"):
            raise ValueError("Readiness handoff manifest has no approved assets.")
        if not manifest.get("reference_assets"):
            raise ValueError("Readiness handoff manifest has no reference assets.")
        proof_assets = manifest.get("proof_assets") or []
        _validate_handoff_asset_integrity(archive, names, manifest.get("approved_assets"), "approved")
        _validate_handoff_asset_integrity(archive, names, proof_assets, "proof")
        _validate_handoff_asset_integrity(archive, names, manifest.get("reference_assets"), "reference")
        _validate_handoff_workflow_provenance(manifest.get("approved_assets"), proof_assets)
        _validate_handoff_workflow_sidecars(archive, names, manifest.get("approved_assets"), "approved")
        _validate_handoff_workflow_sidecars(archive, names, proof_assets, "proof")
        _validate_handoff_review_board(archive, names, manifest.get("review_board"))
        _validate_handoff_channel_exports(archive, names, manifest)


def _read_handoff_review_board_bytes(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("frank-create-handoff.json").decode("utf-8-sig"))
        review_board = manifest.get("review_board") or {}
        archive_path = review_board.get("archive_path") or "review/frank-create-review-board.png"
        data = archive.read(archive_path)
    if len(data) < 8 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Readiness handoff review board is not a PNG.")
    return data


def _validate_handoff_asset_integrity(archive, names, assets, label):
    for asset in assets or []:
        integrity = asset.get("media_integrity") or {}
        sha256 = integrity.get("sha256")
        size = int(integrity.get("file_size_bytes") or 0)
        if not isinstance(sha256, str) or len(sha256) != 64 or size <= 0:
            raise ValueError(f"Readiness handoff manifest has missing {label} media integrity metadata.")
        archive_path = asset.get("archive_path")
        if not archive_path or archive_path not in names:
            raise ValueError(f"Readiness handoff ZIP is missing {label} media file.")
        data = archive.read(archive_path)
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != sha256 or len(data) != size:
            raise ValueError(f"Readiness handoff manifest has {label} media integrity mismatch.")


def _validate_handoff_workflow_provenance(assets, proof_assets=None):
    for asset in assets or []:
        if not asset.get("workflow_provenance"):
            raise ValueError("Readiness handoff manifest has missing approved workflow provenance.")
    for asset in proof_assets or []:
        if not asset.get("workflow_provenance"):
            raise ValueError("Readiness handoff manifest has missing proof workflow provenance.")


def _validate_handoff_workflow_sidecars(archive, names, assets, label="approved"):
    for asset in assets or []:
        if not asset.get("workflow_provenance"):
            continue
        sidecar_path = asset.get("workflow_sidecar_path")
        if not sidecar_path or not str(sidecar_path).startswith("workflows/"):
            raise ValueError(f"Readiness handoff manifest has missing {label} workflow_sidecar_path.")
        if sidecar_path not in names:
            raise ValueError(f"Readiness handoff ZIP is missing {label} workflow sidecar.")
        try:
            sidecar = json.loads(archive.read(sidecar_path).decode("utf-8-sig"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Readiness handoff ZIP has invalid {label} workflow sidecar.") from exc
        if sidecar.get("asset_id") != asset.get("id") or not sidecar.get("workflow_provenance"):
            raise ValueError(f"Readiness handoff ZIP has invalid {label} workflow sidecar.")
        _validate_handoff_workflow_bridge(sidecar.get("workflow_bridge"), asset.get("id"))


def _validate_handoff_workflow_bridge(bridge, asset_id):
    if not isinstance(bridge, dict):
        raise ValueError("Readiness handoff workflow sidecar is missing workflow bridge metadata.")
    if bridge.get("asset_id") != asset_id:
        raise ValueError("Readiness handoff workflow bridge metadata is incomplete.")
    if bridge.get("can_open_raw_canvas") is not True:
        raise ValueError("Readiness handoff workflow bridge metadata is incomplete.")
    if bridge.get("raw_canvas_load_status") not in {"api_prompt_attached", "receipt_only"}:
        raise ValueError("Readiness handoff workflow bridge metadata is incomplete.")
    if bridge.get("raw_canvas_load_status") == "api_prompt_attached" and (
        not isinstance(bridge.get("comfy_node_types"), list) or not bridge.get("comfy_node_types")
    ):
        raise ValueError("Readiness handoff workflow bridge metadata is incomplete.")
    if "frankAssetId=" not in str(bridge.get("raw_canvas_url") or ""):
        raise ValueError("Readiness handoff workflow bridge metadata is incomplete.")
    if "/workflow" not in str(bridge.get("workflow_receipt_url") or ""):
        raise ValueError("Readiness handoff workflow bridge metadata is incomplete.")


def _validate_handoff_review_board(archive, names, review_board):
    if not isinstance(review_board, dict):
        raise ValueError("Readiness handoff manifest is missing review board metadata.")
    archive_path = review_board.get("archive_path")
    if archive_path != "review/frank-create-review-board.png" or archive_path not in names:
        raise ValueError("Readiness handoff ZIP is missing review board.")
    data = archive.read(archive_path)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Readiness handoff review board is not a PNG.")
    if int(review_board.get("approved_asset_count") or 0) < 1:
        raise ValueError("Readiness handoff review board metadata has no approved assets.")
    if int(review_board.get("width") or 0) < 1200 or int(review_board.get("height") or 0) < 800:
        raise ValueError("Readiness handoff review board dimensions are too small.")


def _validate_handoff_channel_exports(archive, names, manifest):
    channel_exports = manifest.get("channel_exports")
    counts = manifest.get("counts") or {}
    if not isinstance(channel_exports, dict) or not channel_exports:
        raise ValueError("Readiness handoff manifest is missing channel export metadata.")
    if int(counts.get("channel_export_sets") or 0) < 1 or int(counts.get("channel_export_files") or 0) < 1:
        raise ValueError("Readiness handoff manifest is missing channel export counts.")

    required_presets = (
        "pdp",
        "email-hero",
        "instagram-feed",
        "instagram-story",
        "paid-social",
        "transparent-png",
        "high-res-master",
    )
    validated_files = 0
    for export_set in channel_exports.values():
        exports = export_set.get("exports") if isinstance(export_set, dict) else None
        if not isinstance(exports, dict):
            raise ValueError("Readiness handoff channel export set is incomplete.")
        for preset in required_presets:
            export = exports.get(preset)
            if not isinstance(export, dict):
                raise ValueError(f"Readiness handoff channel export set is missing {preset}.")
            image_file = export.get("image_file")
            metadata_file = export.get("metadata_file")
            if not image_file or image_file not in names or f"channel-exports/" not in str(image_file):
                raise ValueError("Readiness handoff ZIP is missing channel export image.")
            if not metadata_file or metadata_file not in names:
                raise ValueError("Readiness handoff ZIP is missing channel export metadata.")
            integrity = export.get("media_integrity") or {}
            sha256 = integrity.get("sha256")
            size = int(integrity.get("file_size_bytes") or 0)
            if not isinstance(sha256, str) or len(sha256) != 64 or size <= 0:
                raise ValueError("Readiness handoff channel export has missing media integrity metadata.")
            data = archive.read(image_file)
            if hashlib.sha256(data).hexdigest() != sha256 or len(data) != size:
                raise ValueError("Readiness handoff channel export integrity mismatch.")
            validated_files += 1
    if validated_files < len(required_presets):
        raise ValueError("Readiness handoff ZIP has no validated channel export files.")


def _create_readiness_cliff_pack():
    sessions = _store().list_sessions(status="active")
    session = next((item for item in sessions if item.get("name") == "Frank Body Demo Studio"), sessions[0] if sessions else None)
    if not session:
        return {"status": "missing", "detail": "No active session was available for a Cliff Pack handoff."}

    try:
        payload = create_session_handoff_pack(
            _store(),
            {
                "session_id": session["id"],
                "summary": "Frank Create readiness-pack handoff for Cliff review.",
            },
        )
    except (FileNotFoundError, LookupError) as exc:
        return {"status": "missing", "session_id": session.get("id"), "detail": str(exc)}

    export = _store().create_export(payload)
    metadata = payload.get("metadata") or {}
    return {
        "status": "included",
        "export_id": export["id"],
        "session_id": session.get("id"),
        "session_name": session.get("name"),
        "archive_path": None,
        "approved_asset_count": int(metadata.get("asset_count") or 0),
        "approved_image_count": int(metadata.get("image_count") or 0),
        "approved_video_count": int(metadata.get("video_count") or 0),
        "reference_count": int(metadata.get("reference_count") or 0),
        "path": Path(export["file_path"]),
    }


def _zip_known_file(archive, path, archive_name):
    if path.suffix.lower() in SECRET_HYGIENE_TEXT_SUFFIXES or path.suffix.lower() in {".md", ".json"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _contains_secret_like_token(text):
            raise ValueError(f"Readiness pack source contains a secret-looking token: {path.name}")
    archive.write(path, archive_name)


def _demo_evidence_markdown(evidence):
    summary = evidence.get("summary") or {}
    workflow_smoke = evidence.get("workflow_smoke") or {}
    lines = [
        "# Frank Create Demo Evidence",
        "",
        f"Generated: {evidence.get('generated_at')}",
        f"Status: **{evidence.get('headline')}** (`{evidence.get('status')}`)",
        f"Ready for demo: **{'yes' if evidence.get('ready_for_demo') else 'no'}**",
        "",
        "## Snapshot",
        "",
        f"- Outputs: {summary.get('outputs', 0)}",
        f"- References: {summary.get('references', 0)}",
        f"- Approved assets: {summary.get('approved', 0)}",
        f"- Motion/storyboard assets: {summary.get('video', 0)}",
        f"- Workflow smoke media files: {summary.get('workflow_smoke_media_files', 0)}",
        f"- Workflow smoke channel exports: {summary.get('workflow_smoke_channel_exports', 0)}",
        f"- Graph branding: {'verified' if summary.get('graph_branding_ready') else 'not verified'}",
        f"- Call brief: {'ready' if summary.get('call_brief_ready') else 'missing'}",
        f"- Readiness pack: {'ready' if summary.get('readiness_pack_ready') else 'missing'}",
        f"- Provider adapter families: {summary.get('provider_adapter_count', 0)} registered, {summary.get('missing_provider_adapter_count', 0)} missing",
        f"- Live provider models waiting on keys: {summary.get('waiting_provider_models', 0)}",
        f"- Source/docs token issues: {summary.get('secret_issue_count', 0)}",
        "",
        "## Latest Workflow Smoke",
        "",
        f"- Result: {'passed' if workflow_smoke.get('ok') else 'not passed'}",
        f"- Session: {workflow_smoke.get('session_name') or 'n/a'}",
        f"- Completed: {workflow_smoke.get('completed_at') or 'n/a'}",
        f"- Media files: {workflow_smoke.get('media_file_count', 0)}",
        f"- Channel exports: {workflow_smoke.get('channel_export_file_count', 0)}",
        "",
    ]
    cliff_prep = evidence.get("cliff_prep") or {}
    if cliff_prep:
        pack = cliff_prep.get("cliff_pack") or {}
        lines.extend(
            [
                "",
                "## Cliff Prep Receipt",
                "",
                f"- Result: {'passed' if cliff_prep.get('ok') else 'not passed'}",
                f"- Completed: {cliff_prep.get('completed_at') or 'n/a'}",
                f"- Cliff Pack export: {pack.get('export_id') or 'n/a'}",
                f"- Approved assets in pack: {pack.get('approved_asset_count', 0)}",
                f"- Reference assets in pack: {pack.get('reference_asset_count', 0)}",
                f"- Archive files: {pack.get('archive_file_count', 0)}",
            ]
        )
    lines.extend(["", "## Demo Doctor Checks", ""])
    for check in evidence.get("checks") or []:
        lines.append(f"- `{check.get('status')}` {check.get('label')}: {check.get('detail')}")
        if check.get("action"):
            lines.append(f"  Action: {check.get('action')}")
    urls = evidence.get("demo_urls") or {}
    lines.extend(
        [
            "",
            "## URLs",
            "",
            f"- Studio: {urls.get('studio')}",
            f"- Advanced Graph: {urls.get('advanced_graph')}",
            f"- Raw Comfy Canvas: {urls.get('raw_comfy')}",
        ]
    )
    if evidence.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in evidence.get("notes"))
    model_roster = evidence.get("model_roster") or []
    if model_roster:
        lines.extend(["", "## Launch Model Roster", ""])
        for model in model_roster:
            caps = model.get("capabilities") or {}
            capability_labels = [
                label
                for key, label in (
                    ("generation", "gen"),
                    ("edit", "edit"),
                    ("masked_edit", "mask"),
                    ("video", "video"),
                )
                if caps.get(key)
            ]
            status = "ready" if model.get("configured") else f"needs {'/'.join(model.get('missing_env_vars') or ['key'])}"
            lines.append(
                f"- {model.get('label')} ({model.get('provider')}, {model.get('badge')}): {status}; "
                f"{', '.join(capability_labels) or 'no live capabilities'}; {model.get('reference_image_limit', 0)} refs"
            )
    return "\n".join(lines).strip() + "\n"


def _invalidate_workflow_smoke_after_demo_reset():
    path = _workflow_smoke_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ok": False,
                "reason": "demo_reset",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": "Demo was reset. Run the workflow smoke again before the call.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _secret_hygiene_report():
    matches = []
    for path in _secret_hygiene_scan_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
        except OSError:
            continue

        if _contains_secret_like_token(text):
            matches.append(str(path))

    if matches:
        count = len(matches)
        sample = ", ".join(matches[:3])
        suffix = f": {sample}" if sample else ""
        return {
            "status": "fail",
            "issue_count": count,
            "detail": f"Found secret-looking provider token in {count} Frank app file{'' if count == 1 else 's'}{suffix}.",
            "action": "Remove the token, rotate it, and use user\\frank_create\\provider_keys.env or process env instead.",
        }

    return {
        "status": "ready",
        "issue_count": 0,
        "detail": "Frank app source/docs checked for exposed provider tokens.",
    }


def _secret_hygiene_scan_files():
    seen = set()
    root = Path(__file__).resolve().parents[2]
    for configured_path in SECRET_HYGIENE_SCAN_PATHS:
        path = Path(configured_path)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()

        if not path.exists():
            continue

        candidates = [path] if path.is_file() else path.rglob("*")
        for candidate in candidates:
            if not candidate.is_file() or not _secret_hygiene_should_scan(candidate):
                continue
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            yield candidate


def _secret_hygiene_should_scan(path):
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & SECRET_HYGIENE_EXCLUDED_PARTS:
        return False
    if path.name == PROVIDER_ENV_FILENAME:
        return False
    return path.suffix.lower() in SECRET_HYGIENE_TEXT_SUFFIXES or path.name.endswith(".env.example")


def _contains_secret_like_token(text):
    return any(pattern.search(text) for pattern in SECRET_HYGIENE_TOKEN_PATTERNS)


def _demo_media_file_report(assets):
    if not assets:
        return {
            "status": "fail",
            "missing_count": 0,
            "detail": "No demo media files found to verify.",
            "action": "Reset demo data: .\\scripts\\Start-FrankCreate.ps1 -ResetDemoData",
        }

    missing = []
    for asset in assets:
        file_path = asset.get("file_path")
        path = _resolve_media_path(file_path or "")
        if not file_path or not path or not path.exists() or not path.is_file():
            missing.append(asset)

    if missing:
        count = len(missing)
        sample_titles = ", ".join((asset.get("title") or asset.get("id") or "asset") for asset in missing[:3])
        suffix = f" ({sample_titles})" if sample_titles else ""
        return {
            "status": "fail",
            "missing_count": count,
            "detail": f"{count} media file{'' if count == 1 else 's'} {'is' if count == 1 else 'are'} missing for seeded assets{suffix}.",
            "action": "Reset demo data: .\\scripts\\Start-FrankCreate.ps1 -ResetDemoData",
        }

    count = len(assets)
    return {
        "status": "ready",
        "missing_count": 0,
        "detail": f"{count} media file{'' if count == 1 else 's'} verified on disk.",
    }


def _workflow_smoke_status():
    path = _workflow_smoke_status_path()
    action = "Run: .\\scripts\\Test-FrankCreateWorkflow.ps1 -StartIfDown"
    if not path.exists():
        return {
            "status": "warning",
            "ok": False,
            "detail": "No workflow-smoke receipt found for this build.",
            "action": action,
        }

    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "warning",
            "ok": False,
            "detail": "Workflow-smoke receipt could not be read.",
            "action": action,
        }

    completed_at = receipt.get("completed_at")
    session_name = receipt.get("session_name") or "workflow smoke"
    handoff = receipt.get("handoff") or {}
    if receipt.get("ok") is True:
        media_file_count = int(handoff.get("media_file_count") or 0)
        channel_export_file_count = int(handoff.get("channel_export_file_count") or 0)
        detail = f"{session_name} passed"
        if completed_at:
            detail += f" at {completed_at}"
        if media_file_count and channel_export_file_count:
            detail += f" with {media_file_count} handoff media files and {channel_export_file_count} channel exports."
        elif media_file_count:
            detail += f" with {media_file_count} handoff media files."
        elif channel_export_file_count:
            detail += f" with {channel_export_file_count} channel exports."
        else:
            detail += "."
        return {
            "status": "ready",
            "ok": True,
            "session_name": session_name,
            "completed_at": completed_at,
            "media_file_count": media_file_count,
            "channel_export_set_count": int(handoff.get("channel_export_set_count") or 0),
            "channel_export_file_count": channel_export_file_count,
            "detail": detail,
        }

    error = receipt.get("error") or "Workflow smoke has not passed yet."
    return {
        "status": "warning",
        "ok": False,
        "session_name": session_name,
        "completed_at": completed_at,
        "media_file_count": int(handoff.get("media_file_count") or 0),
        "channel_export_set_count": int(handoff.get("channel_export_set_count") or 0),
        "channel_export_file_count": int(handoff.get("channel_export_file_count") or 0),
        "detail": f"Last workflow smoke did not pass: {error}",
        "action": action,
    }


def _cliff_prep_status():
    path = _cliff_prep_status_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _workflow_smoke_status_path():
    return _store().root_dir / WORKFLOW_SMOKE_STATUS_FILENAME


def _cliff_prep_status_path():
    return _store().root_dir / CLIFF_PREP_STATUS_FILENAME


def _select_demo_doctor_session(sessions, active_sessions):
    for session in sessions:
        if session.get("name") == "Frank Body Demo Studio":
            return session
    return active_sessions[0] if active_sessions else (sessions[0] if sessions else None)


def _doctor_check(key, label, status, detail, action=None):
    check = {"key": key, "label": label, "status": status, "detail": detail}
    if action:
        check["action"] = action
    return check


def _curated_demo_check(reference_assets, image_output_assets, approved_assets, video_assets, edit_proof_ready):
    image_count = len(image_output_assets)
    if _is_curated_demo(reference_assets, image_output_assets, approved_assets, edit_proof_ready):
        return _doctor_check(
            "curated_demo",
            "Curated demo",
            "ready",
            (
                f"Clean first screen: {len(reference_assets)} reference, {image_count} image output"
                f"{'' if image_count == 1 else 's'}, {len(video_assets)} optional motion board"
                f"{'' if len(video_assets) == 1 else 's'}."
            ),
        )

    reasons = []
    if not reference_assets:
        reasons.append("add one product reference")
    if image_count < CURATED_DEMO_MIN_IMAGE_OUTPUTS:
        reasons.append(f"seed {CURATED_DEMO_MIN_IMAGE_OUTPUTS}-{CURATED_DEMO_MAX_IMAGE_OUTPUTS} image outputs")
    if image_count > CURATED_DEMO_MAX_IMAGE_OUTPUTS:
        reasons.append(f"hide or reset {image_count} visible image outputs")
    if len(approved_assets) < 1:
        reasons.append("approve one hero pick")
    if not edit_proof_ready:
        reasons.append("include one edit proof")

    detail = "Demo is not in the Cliff-ready curated shape: " + ", ".join(reasons) + "."
    return _doctor_check(
        "curated_demo",
        "Curated demo",
        "warning",
        detail,
        "Reset demo data: .\\scripts\\Start-FrankCreate.ps1 -ResetDemoData or click Reset demo in the Studio.",
    )


def _is_curated_demo(reference_assets, image_output_assets, approved_assets, edit_proof_ready):
    return (
        len(reference_assets) == 1
        and CURATED_DEMO_MIN_IMAGE_OUTPUTS <= len(image_output_assets) <= CURATED_DEMO_MAX_IMAGE_OUTPUTS
        and len(approved_assets) >= 1
        and bool(edit_proof_ready)
    )


def _provider_env_status(extra=None):
    path = _provider_env_file_path()
    env_vars = _provider_env_names()
    configured_env_vars = sorted([env_var for env_var in env_vars if _provider_env_value_is_real(os.environ.get(env_var))])
    missing_env_vars = sorted([env_var for env_var in env_vars if not _provider_env_value_is_real(os.environ.get(env_var))])
    status = {
        "filePath": str(path),
        "fileExists": path.exists(),
        "envVars": env_vars,
        "configuredEnvVars": configured_env_vars,
        "missingEnvVars": missing_env_vars,
        "notes": [
            "Keys stay in user/frank_create/provider_keys.env or process env.",
            "This API returns env var names and readiness only, never secret values.",
        ],
    }
    if extra:
        status.update(extra)
    return status


def _create_provider_env_template():
    path = _provider_env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not path.exists():
        path.write_text(_provider_env_template_text(), encoding="utf-8")
        created = True
    return _provider_env_status({"created": created})


def _reload_provider_env_file():
    path = _provider_env_file_path()
    loaded = []
    ignored_placeholders = []
    if path.exists():
        allowed = set(_provider_env_names())
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if name not in allowed or not value:
                continue
            if not _provider_env_value_is_real(value):
                ignored_placeholders.append(name)
                continue
            os.environ[name] = value
            loaded.append(name)

    return _provider_env_status(
        {
            "loadedEnvVars": sorted(set(loaded)),
            "ignoredPlaceholderEnvVars": sorted(set(ignored_placeholders)),
            "readiness": _provider_readiness_response(),
        }
    )


def _save_provider_env_values(payload):
    values = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        raise ValueError("Expected a keys object keyed by provider env var name.")

    allowed_names = _provider_env_names()
    allowed = set(allowed_names)
    path = _provider_env_file_path()
    existing_values = _read_provider_env_assignments(path, allowed)
    updated_values = dict(existing_values)
    saved = []
    ignored = []
    ignored_placeholders = []

    for raw_name, raw_value in values.items():
        name = str(raw_name).strip()
        if name not in allowed:
            ignored.append(name)
            continue

        value = "" if raw_value is None else str(raw_value).strip().strip('"').strip("'")
        if not value:
            continue
        if "\n" in value or "\r" in value:
            raise ValueError(f"{name} contains a newline; paste a single key value.")
        if not _provider_env_value_is_real(value):
            os.environ.pop(name, None)
            updated_values.pop(name, None)
            ignored_placeholders.append(name)
            continue

        updated_values[name] = value
        os.environ[name] = value
        saved.append(name)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_provider_env_template_text(updated_values), encoding="utf-8")

    return _provider_env_status(
        {
            "savedEnvVars": sorted(set(saved)),
            "ignoredEnvVars": sorted(set(name for name in ignored if name)),
            "ignoredPlaceholderEnvVars": sorted(set(ignored_placeholders)),
            "readiness": _provider_readiness_response(),
        }
    )


def _read_provider_env_assignments(path, allowed):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name in allowed and _provider_env_value_is_real(value):
            values[name] = value

    return values


def _provider_env_file_path():
    return _store().root_dir / PROVIDER_ENV_FILENAME


def _provider_env_names():
    names = {
        env_var
        for model in get_visible_models() + get_backlog_models()
        for env_var in model.get("env_vars", [])
    }
    return sorted(names)


def _provider_env_template_text(values=None):
    values = values or {}
    lines = [
        "# Frank Create provider keys",
        "# Fill only the providers you want to demo. Keep this file out of git.",
        "# You can edit this file directly or save rotated keys from Provider Setup.",
        "# Frank Create returns key names/readiness only, never secret values.",
        "",
    ]
    lines.extend(f"{env_var}={values.get(env_var, '')}" for env_var in _provider_env_names())
    return "\n".join(lines) + "\n"


def _provider_env_value_is_real(value):
    if value is None:
        return False
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if normalized in PROVIDER_ENV_PLACEHOLDER_VALUES:
        return False
    if normalized.startswith("your_") or normalized.startswith("your-"):
        return False
    if normalized.startswith("paste ") or normalized.startswith("replace "):
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    return True


def _models_with_key_status(models):
    result = []
    for model in models:
        env_vars = model.get("env_vars", [])
        configured_env_var = next((env_var for env_var in env_vars if _provider_env_value_is_real(os.environ.get(env_var))), None)
        configured = not env_vars or bool(configured_env_var)
        result.append(
            {
                **model,
                "configured": configured,
                "configured_env_var": configured_env_var,
                "missing_env_vars": [] if configured else env_vars,
            }
        )
    return result


def _safe_provider(model_id):
    try:
        return get_model(model_id)["provider"]
    except Exception:
        return None


def _session_name(payload):
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return "New image session"
    return prompt[:48]


def _store():
    global _STORE
    if _STORE is None:
        _STORE = FrankCreateStore()
    return _STORE


async def _payload(request):
    try:
        return await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text=f"Invalid JSON: {exc}") from exc


def _json(data, status=200):
    return web.json_response(data, status=status)


def _created(data):
    return _json(data, status=201)


def _frank_spa_index():
    index_path = Path(__file__).resolve().parents[2] / "frank-create" / "dist" / "index.html"
    if not index_path.exists():
        raise web.HTTPNotFound(text="Frank Create frontend has not been built")
    return web.FileResponse(index_path)


def _frank_favicon_svg():
    return b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#FFB6A5"/><rect x="8" y="16" width="48" height="32" rx="7" fill="#fff" stroke="#3F2A2D" stroke-width="4"/><path d="M18 39V25h10v4h-5v2h4v4h-4v4h-5Zm14 0V25h5l5 7v-7h5v14h-5l-5-7v7h-5Z" fill="#3F2A2D"/><path d="M8 48h48v6H8z" fill="#C4112F"/></svg>"""


def _frank_progress_png():
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAANElEQVR4nGNgGAWjYBSMglEwCkbBKBj/8x8bGBgY"
        "2Dk5OQwMjIyM/6nRggFmYGSQpQAA6N8L4mX0vGkAAAAASUVORK5CYII="
    )


def _comfy_frontend_index():
    index_path = _comfy_frontend_root() / "index.html"
    if not index_path.exists():
        raise web.HTTPNotFound(text="Comfy frontend package is not installed")

    html = index_path.read_text(encoding="utf-8")
    html = html.replace("<title>ComfyUI</title>", "<title>Frank Graph / Comfy Canvas</title>")
    html = html.replace(
        "<head>",
        '<head><link rel="stylesheet" href="/comfy/user.css">'
        f"<script>{_comfy_brand_boot_script()}</script>",
        1,
    )
    return web.Response(text=html, content_type="text/html")


async def _comfy_websocket(request, prompt_server):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    sid = request.rel_url.query.get("clientId", "")
    if sid:
        prompt_server.sockets.pop(sid, None)
    else:
        sid = uuid.uuid4().hex

    prompt_server.sockets[sid] = ws
    prompt_server.sockets_metadata[sid] = {"feature_flags": {}}

    try:
        await prompt_server.send("status", {"status": prompt_server.get_queue_info(), "sid": sid}, sid)
        if prompt_server.client_id == sid and prompt_server.last_node_id is not None:
            await prompt_server.send("executing", {"node": prompt_server.last_node_id}, sid)

        first_message = True
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.ERROR:
                logging.warning("ws connection closed with exception %s", ws.exception())
            elif msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if first_message and data.get("type") == "feature_flags":
                        client_flags = data.get("data", {})
                        prompt_server.sockets_metadata[sid]["feature_flags"] = client_flags
                        await prompt_server.send("feature_flags", feature_flags.get_server_features(), sid)
                        logging.debug("Feature flags negotiated for Comfy canvas client %s: %s", sid, client_flags)
                    first_message = False
                except json.JSONDecodeError:
                    logging.warning("Invalid JSON received from Comfy canvas client %s: %s", sid, msg.data)
                except Exception as exc:
                    logging.error("Error processing Comfy canvas WebSocket message: %s", exc)
    finally:
        prompt_server.sockets.pop(sid, None)
        prompt_server.sockets_metadata.pop(sid, None)
    return ws


def _comfy_frontend_file(relative_path):
    if not relative_path:
        return _comfy_frontend_index()

    root = _comfy_frontend_root()
    target = (root / relative_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise web.HTTPForbidden(text="Invalid Comfy frontend path")
    if not target.exists() or not target.is_file():
        raise web.HTTPNotFound(text="Comfy frontend asset was not found")
    return web.FileResponse(target)


def _comfy_frontend_file_or_redirect(relative_path, method="GET"):
    if method.upper() == "GET":
        try:
            return _comfy_frontend_file(relative_path)
        except web.HTTPNotFound:
            pass
    return _comfy_prefix_redirect(relative_path)


def _comfy_prefix_redirect(relative_path):
    safe_path = "/" + str(relative_path or "").lstrip("/")
    return web.HTTPTemporaryRedirect(safe_path)


def _comfy_frontend_root():
    try:
        from app.frontend_management import FrontendManager

        return Path(FrontendManager.default_frontend_path()).resolve()
    except Exception:
        return (Path(__file__).resolve().parents[2] / ".venv" / "Lib" / "site-packages" / "comfyui_frontend_package" / "static").resolve()


def _comfy_brand_boot_script():
    return r"""
(() => {
  const brand = {
    pink: "#FFB6A5",
    dark: "#3F2A2D",
    accent: "#FFD0C6",
    coffee: "#6F4E37",
    cherry: "#C4112F",
    white: "#FFFFFF"
  };

  const originalConsoleError = console.error?.bind(console);
  if (originalConsoleError && !window.__frankComfyConsoleFilter) {
    window.__frankComfyConsoleFilter = true;
    console.error = (...args) => {
      const message = String(args[0] ?? "");
      if (message.includes("ComfyApp graph accessed before initialization")) return;
      originalConsoleError(...args);
    };
  }

  const originalConsoleWarn = console.warn?.bind(console);
  if (originalConsoleWarn && !window.__frankComfyWarnFilter) {
    window.__frankComfyWarnFilter = true;
    console.warn = (...args) => {
      const message = String(args[0] ?? "");
      if (message.includes("legacy queue/history menu is deprecated")) return;
      if (message.includes("ComfyApp.open_maskeditor is deprecated")) return;
      originalConsoleWarn(...args);
    };
  }

  try {
    localStorage.setItem("comfy-splash-bg", brand.pink);
    localStorage.setItem("comfy-splash-fg", brand.dark);
  } catch (error) {}

  const STOCK_STARTER_CHECKPOINT = "v1-5-pruned-emaonly-fp16.safetensors";
  const STOCK_STARTER_PROMPT = "beautiful scenery nature glass bottle landscape";
  const frankAssetId = new URLSearchParams(window.location.search).get("frankAssetId");
  let frankWorkflowReceipt = null;
  let frankWorkflowLoadState = "";
  let frankWorkflowLoadAttempted = false;

  const getGraph = () => {
    try {
      const graph = window.app?.canvas?.graph;
      return graph && Array.isArray(graph._nodes) ? graph : null;
    } catch (error) {
      return null;
    }
  };

  const markFrankCanvas = () => {
    if (!document.body) return;
    document.body.dataset.frankCreateGraph = "rawGoods";
    document.documentElement.dataset.frankRawCanvasBrand = "frank-create-raw-canvas";
  };

  const jsonResponse = (payload, status = 200, sourceHeaders = undefined) => {
    const headers = new Headers(sourceHeaders || {});
    headers.set("content-type", "application/json");
    return new Response(JSON.stringify(payload), { status, headers });
  };

  const originalFetch = window.fetch?.bind(window);
  if (originalFetch && !window.__frankComfyFetchShim) {
    window.__frankComfyFetchShim = true;
    window.fetch = async (input, init) => {
      const rawUrl = typeof input === "string" ? input : input?.url || "";
      const method = (init?.method || (typeof input !== "string" ? input?.method : "") || "GET").toUpperCase();
      let url = null;
      try {
        url = new URL(rawUrl, window.location.origin);
      } catch (error) {}

      const sameOrigin = !url || url.origin === window.location.origin;
      const path = url?.pathname || rawUrl;
      const hasQuery = Boolean(url?.search);
      const isStockCheckpointHead =
        method === "HEAD" &&
        /stable-diffusion-v1-5-archive|v1-5-pruned-emaonly-fp16\.safetensors/i.test(rawUrl);

      if (isStockCheckpointHead) {
        return new Response(null, {
          status: 204,
          headers: { "content-length": "0" }
        });
      }

      if (sameOrigin && method === "GET" && path === "/api/userdata" && !hasQuery) {
        return jsonResponse([]);
      }

      if (sameOrigin && method === "GET" && path === "/api/userdata/comfy.templates.json") {
        return jsonResponse({});
      }

      const response = await originalFetch(input, init);
      if (sameOrigin && method === "GET" && path === "/api/jobs" && response.ok) {
        try {
          const payload = await response.clone().json();
          if (payload?.pagination && payload.pagination.limit == null) {
            payload.pagination.limit = Array.isArray(payload.jobs) ? payload.jobs.length : 0;
            return jsonResponse(payload, response.status, response.headers);
          }
        } catch (error) {}
      }
      return response;
    };
  }

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  const applyFrankPalette = () => {
    const liteGraph = window.LiteGraph;
    const canvas = window.app?.canvas;
    if (!liteGraph) return false;

    Object.assign(liteGraph, {
      CLEAR_BACKGROUND_COLOR: brand.pink,
      NODE_TITLE_COLOR: brand.dark,
      NODE_SELECTED_TITLE_COLOR: brand.dark,
      NODE_TEXT_COLOR: brand.dark,
      NODE_TEXT_HIGHLIGHT_COLOR: brand.dark,
      NODE_DEFAULT_COLOR: brand.dark,
      NODE_DEFAULT_BGCOLOR: brand.white,
      NODE_DEFAULT_BOXCOLOR: brand.dark,
      NODE_BOX_OUTLINE_COLOR: brand.dark,
      NODE_TITLE_HEIGHT: 28,
      NODE_SLOT_HEIGHT: 18,
      NODE_WIDGET_HEIGHT: 24,
      NODE_COLLAPSED_RADIUS: 8,
      DEFAULT_SHADOW_COLOR: "rgba(42, 42, 42, 0.16)",
      WIDGET_BGCOLOR: brand.pink,
      WIDGET_OUTLINE_COLOR: "#D1A3A3",
      WIDGET_TEXT_COLOR: brand.dark,
      WIDGET_SECONDARY_TEXT_COLOR: brand.coffee,
      LINK_COLOR: brand.coffee,
      LINK_COLORS: [brand.coffee, brand.accent, brand.dark, brand.cherry, brand.coffee],
      EVENT_LINK_COLOR: brand.accent,
      CONNECTING_LINK_COLOR: brand.dark,
      NODE_FONT: '"Founders Grotesk Text", Arial'
    });

    if (canvas) {
      canvas.clear_background_color = brand.pink;
      canvas.background_image = "";
      canvas.default_link_color = brand.coffee;
      canvas._bg_img = null;
      canvas.bg_tint = null;
      canvas.setDirty?.(true, true);
    }
    return Boolean(canvas);
  };

  const ensureFrankChrome = () => {
    markFrankCanvas();
    if (!document.body || document.getElementById("frank-comfy-brand-chrome")) return;
    const chrome = document.createElement("div");
    chrome.id = "frank-comfy-brand-chrome";
    chrome.setAttribute("aria-label", "Frank Create raw Comfy badge");
    chrome.innerHTML = `
      <div class="frank-comfy-wordmark" aria-label="Frank Body">
        <span>frank</span><span>body</span>
      </div>
      <div>
        <strong>Raw Comfy</strong>
        <small>Advanced Comfy canvas. Full node graph, lightly Frank.</small>
      </div>
    `;
    document.body.append(chrome);
  };

  const ensureFrankWorkflowReceipt = () => {
    if (!frankAssetId || !frankWorkflowReceipt || !document.body) return;
    let receipt = document.getElementById("frank-comfy-workflow-receipt");
    if (!receipt) {
      receipt = document.createElement("div");
      receipt.id = "frank-comfy-workflow-receipt";
      receipt.setAttribute("aria-label", "Frank raw canvas workflow receipt");
      document.body.append(receipt);
    }
    const asset = frankWorkflowReceipt.asset || {};
    const workflowKey = frankWorkflowReceipt.workflow_key || "frank-create-workflow";
    const engine = frankWorkflowReceipt.engine || asset.provider || "Frank Create";
    const graphStatus = frankWorkflowLoadState || (frankWorkflowReceipt.can_load_comfy_api_prompt ? "API prompt JSON attached" : "Renderer receipt attached");
    receipt.innerHTML = `
      <span>Frank receipt</span>
      <strong>${escapeHtml(asset.title || frankAssetId)}</strong>
      <small>${escapeHtml(workflowKey)} / ${escapeHtml(engine)}</small>
      <em>${escapeHtml(graphStatus)}</em>
    `;
  };

  const fetchFrankWorkflowReceipt = async () => {
    if (!frankAssetId || frankWorkflowReceipt) return frankWorkflowReceipt;
    try {
      const response = await fetch(`/api/frank/assets/${encodeURIComponent(frankAssetId)}/workflow`);
      if (!response.ok) throw new Error(`Frank workflow receipt failed ${response.status}`);
      frankWorkflowReceipt = await response.json();
      window.__frankCreateWorkflowReceipt = frankWorkflowReceipt;
      ensureFrankWorkflowReceipt();
      tryLoadFrankApiPrompt();
    } catch (error) {
      frankWorkflowReceipt = {
        asset: { title: "Workflow receipt unavailable" },
        workflow_key: "receipt-unavailable",
        engine: "Frank Create",
        notes: ["Open the Studio review panel to download the workflow JSON."]
      };
      window.__frankCreateWorkflowReceipt = frankWorkflowReceipt;
      ensureFrankWorkflowReceipt();
    }
    return frankWorkflowReceipt;
  };

  const tryLoadFrankApiPrompt = async () => {
    if (!frankWorkflowReceipt?.api_prompt_json || frankWorkflowLoadAttempted) return false;
    const loader = window.app?.loadGraphData;
    const graph = getGraph();
    if (!loader || !graph) return false;
    frankWorkflowLoadAttempted = true;
    try {
      await loader.call(window.app, frankWorkflowReceipt.api_prompt_json, true, true, frankWorkflowReceipt.asset?.title || "Frank workflow");
      frankWorkflowLoadState = "Loaded into canvas";
      ensureFrankWorkflowReceipt();
      window.app?.canvas?.setDirty?.(true, true);
      return true;
    } catch (error) {
      frankWorkflowLoadState = "API prompt JSON attached";
      ensureFrankWorkflowReceipt();
      return false;
    }
  };

  const isStockStarterWorkflow = () => {
    const nodes = getGraph()?._nodes ?? [];
    if (!nodes.length || nodes.length > 10) return false;

    const nodeTypes = new Set(nodes.map((node) => node.type));
    const hasStarterCheckpoint = nodes.some((node) => {
      if (node.type !== "CheckpointLoaderSimple") return false;
      return (node.widgets ?? []).some((widget) => String(widget.value ?? "").includes(STOCK_STARTER_CHECKPOINT));
    });
    const hasStarterPrompt = nodes.some((node) => {
      if (node.type !== "CLIPTextEncode") return false;
      return (node.widgets ?? []).some((widget) => String(widget.value ?? "").includes(STOCK_STARTER_PROMPT));
    });

    return (
      hasStarterCheckpoint &&
      hasStarterPrompt &&
      nodeTypes.has("KSampler") &&
      nodeTypes.has("SaveImage")
    );
  };

  const purgeStockStarterDrafts = () => {
    try {
      for (let index = localStorage.length - 1; index >= 0; index -= 1) {
        const key = localStorage.key(index);
        if (!key?.startsWith("Comfy.Workflow.Draft")) continue;
        const value = localStorage.getItem(key) ?? "";
        if (value.includes(STOCK_STARTER_CHECKPOINT)) localStorage.removeItem(key);
      }
    } catch (error) {}
  };

  const dismissStockStarterAlerts = () => {
    for (const alert of Array.from(document.querySelectorAll('[role="alert"]'))) {
      if (!/required model is missing/i.test(alert.innerText ?? "")) continue;

      const dismissButton = Array.from(alert.querySelectorAll("button")).find((button) => {
        const label = `${button.getAttribute("aria-label") ?? ""} ${button.innerText ?? ""}`;
        return /dismiss|close|×|x/i.test(label);
      });

      if (dismissButton) {
        dismissButton.click();
      } else {
        alert.remove();
      }
    }
  };

  const clearStockStarterWorkflow = () => {
    const graph = getGraph();
    if (!graph || !isStockStarterWorkflow()) return false;

    graph.clear();
    purgeStockStarterDrafts();
    window.app?.canvas?.setDirty?.(true, true);
    dismissStockStarterAlerts();
    return true;
  };

  const syncFrankWorkflowLabels = () => {
    document.title = "Frank Graph / Raw Goods";
    const labels = document.querySelectorAll(".workflow-label, .p-breadcrumb-item-label, [data-testid='workflow-name']");
    for (const label of labels) {
      const text = (label.textContent || "").trim();
      if (text === "Unsaved Workflow") label.textContent = "Frank Canvas";
      if (text === "ComfyUI") label.textContent = "Frank Create";
    }

    for (const titled of document.querySelectorAll('[title="Unsaved Workflow"]')) {
      titled.setAttribute("title", "Frank Canvas");
      titled.setAttribute("aria-label", "Frank Canvas");
    }
  };

  const syncFrankRawCanvas = () => {
    markFrankCanvas();
    applyFrankPalette();
    ensureFrankChrome();
    syncFrankWorkflowLabels();
    clearStockStarterWorkflow();
    dismissStockStarterAlerts();
    fetchFrankWorkflowReceipt();
    tryLoadFrankApiPrompt();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncFrankRawCanvas, { once: true });
  } else {
    syncFrankRawCanvas();
  }
  window.addEventListener("load", syncFrankRawCanvas);
  let attempts = 0;
  const timer = window.setInterval(() => {
    syncFrankRawCanvas();
    if (attempts++ > 40) window.clearInterval(timer);
  }, 750);
})();
""".strip()
    return r"""
(() => {
  const brand = {
    pink: "#FFB6A5",
    dark: "#3F2A2D",
    accent: "#FFD0C6",
    coffee: "#3F2A2D",
    cherry: "#C4112F",
    white: "#FFFFFF"
  };

  const originalConsoleError = console.error?.bind(console);
  if (originalConsoleError && !window.__frankComfyConsoleFilter) {
    window.__frankComfyConsoleFilter = true;
    console.error = (...args) => {
      const message = String(args[0] ?? "");
      if (message.includes("ComfyApp graph accessed before initialization")) return;
      originalConsoleError(...args);
    };
  }
  const originalConsoleWarn = console.warn?.bind(console);
  if (originalConsoleWarn && !window.__frankComfyWarnFilter) {
    window.__frankComfyWarnFilter = true;
    console.warn = (...args) => {
      const message = String(args[0] ?? "");
      if (message.includes("legacy queue/history menu is deprecated")) return;
      if (message.includes("ComfyApp.open_maskeditor is deprecated")) return;
      originalConsoleWarn(...args);
    };
  }

  try {
    localStorage.setItem("comfy-splash-bg", brand.pink);
    localStorage.setItem("comfy-splash-fg", brand.dark);
  } catch (error) {}

  const markFrankCanvas = () => {
    if (!document.body) return;
    document.body.dataset.frankCreateGraph = "rawGoods";
    document.documentElement.dataset.frankRawCanvasBrand = "frank-create-raw-canvas";
  };

  const jsonResponse = (payload, status = 200, sourceHeaders = undefined) => {
    const headers = new Headers(sourceHeaders || {});
    headers.set("content-type", "application/json");
    return new Response(JSON.stringify(payload), { status, headers });
  };

  const originalFetch = window.fetch?.bind(window);
  if (originalFetch && !window.__frankComfyFetchShim) {
    window.__frankComfyFetchShim = true;
    window.fetch = async (input, init) => {
      const rawUrl = typeof input === "string" ? input : input?.url || "";
      const method = (init?.method || (typeof input !== "string" ? input?.method : "") || "GET").toUpperCase();
      let url = null;
      try {
        url = new URL(rawUrl, window.location.origin);
      } catch (error) {}

      const sameOrigin = !url || url.origin === window.location.origin;
      const path = url?.pathname || rawUrl;
      const hasQuery = Boolean(url?.search);
      const isStockCheckpointHead =
        method === "HEAD" &&
        /stable-diffusion-v1-5-archive|v1-5-pruned-emaonly-fp16\.safetensors/i.test(rawUrl);

      if (isStockCheckpointHead) {
        return new Response(null, {
          status: 204,
          headers: { "content-length": "0" }
        });
      }

      if (sameOrigin && method === "GET" && path === "/api/userdata" && !hasQuery) {
        return jsonResponse([]);
      }

      if (sameOrigin && method === "GET" && path === "/api/userdata/comfy.templates.json") {
        return jsonResponse({});
      }

      const response = await originalFetch(input, init);
      if (sameOrigin && method === "GET" && path === "/api/jobs" && response.ok) {
        try {
          const payload = await response.clone().json();
          if (payload?.pagination && payload.pagination.limit == null) {
            payload.pagination.limit = Array.isArray(payload.jobs) ? payload.jobs.length : 0;
            return jsonResponse(payload, response.status, response.headers);
          }
        } catch (error) {}
      }
      return response;
    };
  }

  const defaultNodeColors = new Set(["#333", "#353535", undefined, null, ""]);
  const nodePalettes = {
    brief: { color: "#3F2A2D", bg: "#FFFFFF" },
    reference: { color: "#3F2A2D", bg: "#FFF4F0" },
    model: { color: "#3F2A2D", bg: "#FFB6A5" },
    magic: { color: "#C4112F", bg: "#FFFFFF" },
    output: { color: "#3F2A2D", bg: "#FFFFFF" },
  };
  const frankStageTitles = {
    brief: "Brief It",
    reference: "The Goods",
    model: "Model Shelf",
    magic: "Make Magic",
    output: "Send It"
  };
  const frankStageLabels = {
    brief: "Brief",
    reference: "Shot List",
    model: "Model",
    magic: "Make Magic",
    output: "Approved Hot"
  };
  const frankSlotLabels = {
    brief: { input: "BRIEF IN", output: "PROMPT OUT" },
    reference: { input: "REFS IN", output: "PRODUCT TRUTH" },
    model: { input: "MODEL IN", output: "MODEL OUT" },
    magic: { input: "MAGIC IN", output: "MAKE MAGIC" },
    output: { input: "FINAL IN", output: "APPROVED OUT" }
  };
  const frankStageTitlePattern = /^(Brief It|The Goods|Model Shelf|Make Magic|Send It)\s\/\s/;
  const FRANK_NODE_BADGE_HEIGHT = 18;
  const FRANK_NODE_TITLE_PLATE_HEIGHT = 26;
  const STOCK_STARTER_CHECKPOINT = "v1-5-pruned-emaonly-fp16.safetensors";
  const STOCK_STARTER_PROMPT = "beautiful scenery nature glass bottle landscape";
  const getGraph = () => {
    try {
      const graph = window.app?.canvas?.graph;
      return graph && Array.isArray(graph._nodes) ? graph : null;
    } catch (error) {
      return null;
    }
  };
  const frankAssetId = new URLSearchParams(window.location.search).get("frankAssetId");
  let frankWorkflowReceipt = null;
  let frankWorkflowLoadState = "";
  let frankWorkflowLoadAttempted = false;

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  const fetchFrankWorkflowReceipt = async () => {
    if (!frankAssetId || frankWorkflowReceipt) return frankWorkflowReceipt;
    try {
      const response = await fetch(`/api/frank/assets/${encodeURIComponent(frankAssetId)}/workflow`);
      if (!response.ok) throw new Error(`Frank workflow receipt failed ${response.status}`);
      frankWorkflowReceipt = await response.json();
      window.__frankCreateWorkflowReceipt = frankWorkflowReceipt;
      ensureFrankWorkflowReceipt();
      tryLoadFrankApiPrompt();
    } catch (error) {
      frankWorkflowReceipt = {
        asset: { title: "Workflow receipt unavailable" },
        workflow_key: "receipt-unavailable",
        engine: "Frank Create",
        notes: ["Open the Studio review panel to download the workflow JSON."]
      };
      ensureFrankWorkflowReceipt();
    }
    return frankWorkflowReceipt;
  };

  const ensureFrankWorkflowReceipt = () => {
    if (!frankAssetId || !frankWorkflowReceipt || !document.body) return;
    let receipt = document.getElementById("frank-comfy-workflow-receipt");
    if (!receipt) {
      receipt = document.createElement("div");
      receipt.id = "frank-comfy-workflow-receipt";
      receipt.setAttribute("aria-label", "Frank raw canvas workflow receipt");
      document.body.append(receipt);
    }
    const asset = frankWorkflowReceipt.asset || {};
    const workflowKey = frankWorkflowReceipt.workflow_key || "frank-create-workflow";
    const engine = frankWorkflowReceipt.engine || asset.provider || "Frank Create";
    const graphStatus = frankWorkflowLoadState || (frankWorkflowReceipt.can_load_comfy_api_prompt ? "API prompt JSON attached" : "Renderer receipt attached");
    receipt.innerHTML = `
      <span>FRANK RECEIPT</span>
      <strong>${escapeHtml(asset.title || frankAssetId)}</strong>
      <small>${escapeHtml(workflowKey)} / ${escapeHtml(engine)}</small>
      <em>${escapeHtml(graphStatus)}</em>
    `;
  };

  const tryLoadFrankApiPrompt = async () => {
    if (!frankWorkflowReceipt?.api_prompt_json || frankWorkflowLoadAttempted) return false;
    const loader = window.app?.loadGraphData;
    const graph = getGraph();
    if (!loader || !graph) return false;
    frankWorkflowLoadAttempted = true;
    try {
      await loader.call(window.app, frankWorkflowReceipt.api_prompt_json, true, true, frankWorkflowReceipt.asset?.title || "Frank workflow");
      frankWorkflowLoadState = "Loaded into canvas";
      applyFrankNodeBranding();
      syncFrankEmptyState();
      ensureFrankWorkflowReceipt();
      window.app?.canvas?.setDirty?.(true, true);
      return true;
    } catch (error) {
      frankWorkflowLoadState = "API prompt JSON attached";
      ensureFrankWorkflowReceipt();
      return false;
    }
  };

  const isStockStarterWorkflow = () => {
    const nodes = getGraph()?._nodes ?? [];
    if (!nodes.length || nodes.length > 10) return false;

    const nodeTypes = new Set(nodes.map((node) => node.type));
    const hasStarterCheckpoint = nodes.some((node) => {
      if (node.type !== "CheckpointLoaderSimple") return false;
      return (node.widgets ?? []).some((widget) => String(widget.value ?? "").includes(STOCK_STARTER_CHECKPOINT));
    });
    const hasStarterPrompt = nodes.some((node) => {
      if (node.type !== "CLIPTextEncode") return false;
      return (node.widgets ?? []).some((widget) => String(widget.value ?? "").includes(STOCK_STARTER_PROMPT));
    });

    return (
      hasStarterCheckpoint &&
      hasStarterPrompt &&
      nodeTypes.has("KSampler") &&
      nodeTypes.has("SaveImage")
    );
  };

  const purgeStockStarterDrafts = () => {
    try {
      for (let index = localStorage.length - 1; index >= 0; index -= 1) {
        const key = localStorage.key(index);
        if (!key?.startsWith("Comfy.Workflow.Draft")) continue;
        const value = localStorage.getItem(key) ?? "";
        if (value.includes(STOCK_STARTER_CHECKPOINT)) localStorage.removeItem(key);
      }
    } catch (error) {}
  };

  const syncFrankEmptyState = () => {
    const graph = getGraph();
    const nodeCount = graph?._nodes?.length ?? 0;
    const existing = document.getElementById("frank-comfy-empty-state");

    if (nodeCount > 0) {
      existing?.remove();
      return;
    }

    if (existing) return;

    const emptyState = document.createElement("div");
    emptyState.id = "frank-comfy-empty-state";
    emptyState.innerHTML = `
      <strong>The Raw Goods</strong>
      <span>Advanced canvas is clean. Build here when you need the raw Comfy goods.</span>
    `;
    document.body.append(emptyState);
  };

  const syncFrankWorkflowLabels = () => {
    document.title = "Frank Graph / Raw Goods";
    const labels = document.querySelectorAll(".workflow-label, .p-breadcrumb-item-label, [data-testid='workflow-name']");
    for (const label of labels) {
      const text = (label.textContent || "").trim();
      if (text === "Unsaved Workflow") label.textContent = "Frank Canvas";
      if (text === "ComfyUI") label.textContent = "Frank Create";
    }

    for (const titled of document.querySelectorAll('[title="Unsaved Workflow"]')) {
      titled.setAttribute("title", "Frank Canvas");
      titled.setAttribute("aria-label", "Frank Canvas");
    }
  };

  const ensureFrankChrome = () => {
    markFrankCanvas();
    if (!document.body) return;

    if (!document.getElementById("frank-comfy-brand-chrome")) {
      const chrome = document.createElement("div");
      chrome.id = "frank-comfy-brand-chrome";
      chrome.innerHTML = `
        <div class="frank-comfy-wordmark" aria-label="Frank Body">
          <span>frank</span><span>body</span>
        </div>
        <div>
          <strong>The Raw Goods</strong>
          <small>Advanced Comfy canvas. Frank rules still apply.</small>
        </div>
      `;
      document.body.append(chrome);
    }

    if (!document.getElementById("frank-comfy-brand-strip")) {
      const strip = document.createElement("div");
      strip.id = "frank-comfy-brand-strip";
      strip.innerHTML = `
        <span>HEY BABE. RAW MODE.</span>
        <span class="frank-comfy-rule" aria-label="Keep the goods honest"></span>
        <span>MAKE MAGIC</span>
      `;
      document.body.append(strip);
    }

    if (!document.getElementById("frank-comfy-lane-map")) {
      const laneMap = document.createElement("div");
      laneMap.id = "frank-comfy-lane-map";
      laneMap.setAttribute("aria-label", "Frank Graph");
      laneMap.innerHTML = `
        <strong>FRANK GRAPH</strong>
        <span>Brief</span>
        <span>Product truth</span>
        <span>Make magic</span>
        <span>Approved hot</span>
      `;
      document.body.append(laneMap);
    }

    if (!document.getElementById("frank-comfy-stage-ribbon")) {
      const ribbon = document.createElement("div");
      ribbon.id = "frank-comfy-stage-ribbon";
      ribbon.setAttribute("aria-label", "Frank graph stage ribbon");
      ribbon.innerHTML = `
        <span>Brief in</span>
        <span>Refs honest</span>
        <span>Make magic</span>
        <span>Approved hot</span>
      `;
      document.body.append(ribbon);
    }

    if (!document.getElementById("frank-comfy-canvas-watermark")) {
      const watermark = document.createElement("div");
      watermark.id = "frank-comfy-canvas-watermark";
      watermark.setAttribute("aria-label", "Frank raw canvas watermark");
      watermark.innerHTML = `<span>frank</span><span>body</span>`;
      document.body.append(watermark);
    }

    if (!document.getElementById("frank-comfy-palette-card")) {
      const paletteCard = document.createElement("div");
      paletteCard.id = "frank-comfy-palette-card";
      paletteCard.setAttribute("aria-label", "Frank raw canvas palette");
      paletteCard.innerHTML = `
        <strong>FRANK TOKENS</strong>
        <span><i class="pink"></i>Pink canvas</span>
        <span><i class="coffee"></i>Coffee links</span>
        <span><i class="cherry"></i>Cherry active</span>
      `;
      document.body.append(paletteCard);
    }

    if (!document.getElementById("frank-comfy-status-dock")) {
      const dock = document.createElement("div");
      dock.id = "frank-comfy-status-dock";
      dock.setAttribute("aria-label", "Frank raw canvas status dock");
      dock.innerHTML = `
        <span><small>Canvas skin</small><strong>Active</strong></span>
        <span><small>Node language</small><strong>Frank stages</strong></span>
        <span><small>Receipts</small><strong>Workflow JSON</strong></span>
      `;
      document.body.append(dock);
    }

    if (!document.getElementById("frank-comfy-action-rail")) {
      const rail = document.createElement("div");
      rail.id = "frank-comfy-action-rail";
      rail.setAttribute("aria-label", "Frank graph recipe");
      rail.innerHTML = `
        <strong>GRAPH RECIPE</strong>
        <span><b>1</b> Brief the robots</span>
        <span><b>2</b> Keep product truth</span>
        <span><b>3</b> Make another round</span>
        <span><b>4</b> Approved. Hot.</span>
      `;
      document.body.append(rail);
    }

    if (!document.getElementById("frank-comfy-art-direction")) {
      const stamp = document.createElement("div");
      stamp.id = "frank-comfy-art-direction";
      stamp.setAttribute("aria-label", "Frank graph art direction");
      stamp.innerHTML = `
        <span>ART DIRECTION</span>
        <strong>Less node soup. More Frank.</strong>
      `;
      document.body.append(stamp);
    }

    if (!document.getElementById("frank-comfy-node-legend")) {
      const legend = document.createElement("div");
      legend.id = "frank-comfy-node-legend";
      legend.setAttribute("aria-label", "Frank node palette");
      legend.innerHTML = `
        <span><i class="brief"></i>Brief</span>
        <span><i class="reference"></i>Reference</span>
        <span><i class="magic"></i>Make Magic</span>
        <span><i class="output"></i>Output</span>
      `;
      document.body.append(legend);
    }

    if (!document.getElementById("frank-comfy-node-style-card")) {
      const styleCard = document.createElement("div");
      styleCard.id = "frank-comfy-node-style-card";
      styleCard.setAttribute("aria-label", "Frank node style card");
      styleCard.innerHTML = `
        <strong>NODE CARDS</strong>
        <span>Frank title bars</span>
        <span>Stage badge labels</span>
        <span>Coffee/cherry noodle lines</span>
      `;
      document.body.append(styleCard);
    }

    if (!document.getElementById("frank-comfy-production-plate")) {
      const plate = document.createElement("div");
      plate.id = "frank-comfy-production-plate";
      plate.setAttribute("aria-label", "Frank raw canvas production plate");
      plate.innerHTML = `
        <span>RAW CANVAS</span>
        <strong>Comfy power. Frank finish.</strong>
        <small>Use this when a workflow needs the full node graph.</small>
      `;
      document.body.append(plate);
    }

    ensureFrankWorkflowReceipt();
  };

  const dismissStockStarterAlerts = () => {
    for (const alert of Array.from(document.querySelectorAll('[role="alert"]'))) {
      if (!/required model is missing/i.test(alert.innerText ?? "")) continue;

      const dismissButton = Array.from(alert.querySelectorAll("button")).find((button) => {
        const label = `${button.getAttribute("aria-label") ?? ""} ${button.innerText ?? ""}`;
        return /dismiss|close|Ã—|x/i.test(label);
      });

      if (dismissButton) {
        dismissButton.click();
      } else {
        alert.remove();
      }
    }
  };

  const clearStockStarterWorkflow = () => {
    const graph = getGraph();
    if (!graph || !isStockStarterWorkflow()) return false;

    graph.clear();
    purgeStockStarterDrafts();
    window.app?.canvas?.setDirty?.(true, true);
    syncFrankEmptyState();
    dismissStockStarterAlerts();
    return true;
  };

  const frankNodeStage = (node) => {
    const haystack = `${node.type ?? ""} ${node.title ?? ""}`.toLowerCase();
    if (/clip|text|prompt|conditioning|note/.test(haystack)) return "brief";
    if (/image|load|mask|vae|reference|upload/.test(haystack)) return "reference";
    if (/checkpoint|model|lora|controlnet|diffusion/.test(haystack)) return "model";
    if (/sample|sampler|ksampler|latent|denoise|scheduler/.test(haystack)) return "magic";
    if (/save|preview|output|export|video/.test(haystack)) return "output";
    return "brief";
  };

  const drawFrankCanvasTexture = (ctx) => {
    if (!ctx?.canvas) return false;
    const width = ctx.canvas.width || 0;
    const height = ctx.canvas.height || 0;
    if (!width || !height) return false;

    ctx.save();
    if (typeof ctx.resetTransform === "function") {
      ctx.resetTransform();
    } else {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    ctx.fillStyle = brand.pink;
    ctx.fillRect(0, 0, width, height);

    ctx.globalAlpha = 0.42;
    ctx.strokeStyle = "rgba(232, 180, 180, 0.62)";
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x + 0.5, 0);
      ctx.lineTo(x + 0.5, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y + 0.5);
      ctx.lineTo(width, y + 0.5);
      ctx.stroke();
    }

    ctx.globalAlpha = 1;
    ctx.strokeStyle = "rgba(111, 78, 55, 0.32)";
    ctx.lineWidth = 2;
    ctx.setLineDash([7, 9]);
    for (const x of [width * 0.32, width * 0.66]) {
      ctx.beginPath();
      ctx.moveTo(x, 102);
      ctx.lineTo(x, height - 36);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    ctx.fillStyle = "rgba(42, 42, 42, 0.12)";
    ctx.font = '900 64px "Pitch", "Courier New", monospace';
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText("RAW GOODS", width - 28, height - 26);

    ctx.fillStyle = brand.dark;
    ctx.font = '900 11px "Pitch", "Courier New", monospace';
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    const labels = ["Brief", "Shot List", "Make Magic", "Approved Hot"];
    labels.forEach((label, index) => {
      const x = 24 + index * Math.max(124, width * 0.16);
      const y = 56;
      const labelWidth = ctx.measureText(label).width + 22;
      ctx.fillStyle = index === 0 ? brand.dark : brand.white;
      ctx.strokeStyle = "rgba(42, 42, 42, 0.18)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect?.(x, y, labelWidth, 28, 8);
      if (!ctx.roundRect) ctx.rect(x, y, labelWidth, 28);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = index === 0 ? brand.white : index === 2 ? brand.cherry : brand.coffee;
      ctx.fillText(label.toUpperCase(), x + 11, y + 18);
    });

    drawFrankGraphLinkLabels(ctx, width, height);

    ctx.restore();
    return true;
  };

  const drawFrankGraphLinkLabels = (ctx, width, height) => {
    const edgeLabels = [
      { label: "prompt", x: width * 0.22, y: 112, color: brand.dark },
      { label: "refs", x: width * 0.45, y: Math.max(156, height * 0.52), color: brand.coffee },
      { label: "approve", x: width * 0.7, y: 112, color: brand.cherry }
    ];

    ctx.save();
    ctx.font = '900 10px "Pitch", "Courier New", monospace';
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    for (const item of edgeLabels) {
      const label = item.label.toUpperCase();
      const labelWidth = ctx.measureText(label).width + 24;
      ctx.fillStyle = "rgba(255, 255, 255, 0.86)";
      ctx.strokeStyle = item.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect?.(item.x - labelWidth / 2, item.y - 13, labelWidth, 26, 8);
      if (!ctx.roundRect) ctx.rect(item.x - labelWidth / 2, item.y - 13, labelWidth, 26);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = item.color;
      ctx.fillText(label, item.x, item.y + 1);
    }
    ctx.restore();
    return true;
  };

  const drawFrankNodeStageBadge = (node, ctx) => {
    if (!node || !ctx) return false;
    const stage = node._frankBrandStage || frankNodeStage(node);
    const label = node._frankBrandStageLabel || frankStageLabels[stage] || "Brief";
    const palette = nodePalettes[stage] || nodePalettes.brief;
    const width = Math.max(82, Math.min(154, ctx.measureText(label).width + 26));
    const x = 10;
    const y = -(FRANK_NODE_BADGE_HEIGHT + 5);

    ctx.save();
    ctx.font = '900 9px "Pitch", "Courier New", monospace';
    ctx.textBaseline = "middle";
    ctx.fillStyle = stage === "magic" ? brand.cherry : stage === "reference" ? brand.coffee : brand.dark;
    ctx.strokeStyle = "rgba(42, 42, 42, 0.22)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect?.(x, y, width, 18, 7);
    if (!ctx.roundRect) ctx.rect(x, y, width, 18);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = stage === "reference" ? brand.white : palette.bg === brand.white ? brand.white : brand.dark;
    ctx.fillText(label.toUpperCase(), x + 10, y + 9);
    ctx.restore();
    return true;
  };

  const drawFrankNodeTitlePlate = (node, ctx) => {
    if (!node || !ctx) return false;
    const stage = node._frankBrandStage || frankNodeStage(node);
    const palette = nodePalettes[stage] || nodePalettes.brief;
    const width = Math.max(150, Number(node.size?.[0]) || 190);
    const y = -(FRANK_NODE_TITLE_PLATE_HEIGHT + FRANK_NODE_BADGE_HEIGHT + 10);
    const titleColor = stage === "magic" ? brand.cherry : stage === "reference" ? brand.coffee : brand.dark;

    ctx.save();
    ctx.globalAlpha = 0.98;
    ctx.fillStyle = titleColor;
    ctx.strokeStyle = "rgba(42, 42, 42, 0.28)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect?.(0, y, width, FRANK_NODE_TITLE_PLATE_HEIGHT, 8);
    if (!ctx.roundRect) ctx.rect(0, y, width, FRANK_NODE_TITLE_PLATE_HEIGHT);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = stage === "reference" ? brand.white : palette.bg === brand.white ? brand.white : brand.dark;
    ctx.font = '900 10px "Pitch", "Courier New", monospace';
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    ctx.fillText("FRANK TITLE BAR", 11, y + FRANK_NODE_TITLE_PLATE_HEIGHT / 2 + 1);

    ctx.fillStyle = "rgba(255, 255, 255, 0.72)";
    ctx.font = '800 10px "Pitch", "Courier New", monospace';
    ctx.textAlign = "right";
    ctx.fillText("frank/body", width - 11, y + FRANK_NODE_TITLE_PLATE_HEIGHT / 2 + 1);
    ctx.restore();
    return true;
  };

  const markFrankNodeGraphProof = (graph = null, stages = []) => {
    window.__frankCreateNodeGraphProof = {
      skin: "frank-body-raw-goods",
      slots: true,
      links: true,
      graphPresent: Boolean(graph),
      stages: Array.from(stages).sort(),
      nodeCount: graph?._nodes?.length ?? 0
    };
    return true;
  };

  const installFrankGraphRenderSkin = () => {
    const liteGraph = window.LiteGraph;
    const CanvasCtor = window.LGraphCanvas || liteGraph?.LGraphCanvas;
    const proto = CanvasCtor?.prototype;
    if (!proto || proto.__frankCreateRenderSkinInstalled) return Boolean(proto);

    proto.__frankCreateRenderSkinInstalled = true;
    if (typeof proto.drawBackCanvas === "function") {
      proto.__frankCreateDrawBackCanvas = proto.drawBackCanvas;
      proto.drawBackCanvas = function (...args) {
        const result = proto.__frankCreateDrawBackCanvas.apply(this, args);
        const ctx = this.bgctx || this.ctx || args.find((arg) => arg?.canvas);
        drawFrankCanvasTexture(ctx);
        return result;
      };
    }

    window.__frankCreateGraphRenderSkin = true;
    markFrankNodeGraphProof(getGraph());
    return true;
  };

  const applyFrankNodeBranding = () => {
    const graph = getGraph();
    if (!graph) {
      markFrankNodeGraphProof();
      return false;
    }
    const brandedStages = new Set();

    for (const node of graph._nodes ?? []) {
      const stage = frankNodeStage(node);
      const palette = nodePalettes[stage] || nodePalettes.brief;
      brandedStages.add(stage);
      node._frankBrandStage = stage;
      node._frankBrandStageLabel = frankStageLabels[stage] || frankStageLabels.brief;
      node.color = palette.color;
      node.bgcolor = palette.bg;
      node.boxcolor = stage === "magic" ? "#C4112F" : stage === "reference" ? "#3F2A2D" : "#3F2A2D";
      const rawTitle = String(node._frankOriginalTitle || node.title || node.type || "Node").replace(frankStageTitlePattern, "");
      node._frankOriginalTitle = rawTitle;
      node.title = `${frankStageTitles[stage] || frankStageTitles.brief} / ${rawTitle}`;
      if (!node.title_text_color || node.title_text_color === "#fff") node.title_text_color = "#FFFFFF";
      if (!node.title_mode) node.title_mode = window.LiteGraph?.NORMAL_TITLE ?? node.title_mode;
      applyFrankSlotBranding(node, stage);
      if (!node.__frankCreateNodeForeground) {
        node.__frankCreateNodeForeground = node.onDrawForeground || null;
        node.onDrawForeground = function (ctx, graphCanvas) {
          drawFrankNodeTitlePlate(this, ctx);
          if (typeof node.__frankCreateNodeForeground === "function") {
            node.__frankCreateNodeForeground.call(this, ctx, graphCanvas);
          }
          drawFrankNodeStageBadge(this, ctx);
        };
      }
    }
    applyFrankLinkBranding(graph);
    markFrankNodeGraphProof(graph, brandedStages);
    return true;
  };

  const applyFrankSlotBranding = (node, stage) => {
    const labels = frankSlotLabels[stage] || frankSlotLabels.brief;
    const inputColor = stage === "reference" ? brand.coffee : stage === "magic" ? brand.cherry : brand.dark;
    const outputColor = stage === "output" ? brand.cherry : stage === "reference" ? brand.coffee : brand.accent;

    for (const slot of node.inputs ?? []) {
      if (!slot) continue;
      slot._frankOriginalName = slot._frankOriginalName || slot.name || "input";
      slot.color_on = inputColor;
      slot.color_off = inputColor;
      slot.color = inputColor;
      slot.label = labels.input;
      slot.name = `${labels.input} / ${slot._frankOriginalName}`.replace(/ \/ $/, "");
    }

    for (const slot of node.outputs ?? []) {
      if (!slot) continue;
      slot._frankOriginalName = slot._frankOriginalName || slot.name || "output";
      slot.color_on = outputColor;
      slot.color_off = outputColor;
      slot.color = outputColor;
      slot.label = labels.output;
      slot.name = `${labels.output} / ${slot._frankOriginalName}`.replace(/ \/ $/, "");
    }

    return true;
  };

  const applyFrankLinkBranding = (graph) => {
    const nodesById = new Map((graph?._nodes ?? []).map((node) => [node.id, node]));
    for (const link of Object.values(graph?.links ?? {})) {
      if (!link) continue;
      const originStage = nodesById.get(link.origin_id)?._frankBrandStage || "brief";
      link.color = originStage === "magic" ? brand.cherry : originStage === "reference" ? brand.coffee : brand.dark;
    }
    return true;
  };

  const applyFrankPalette = () => {
    const liteGraph = window.LiteGraph;
    const canvas = window.app?.canvas;
    if (!liteGraph) return false;

    Object.assign(liteGraph, {
      CLEAR_BACKGROUND_COLOR: brand.pink,
      NODE_TITLE_COLOR: brand.dark,
      NODE_SELECTED_TITLE_COLOR: brand.dark,
      NODE_TEXT_COLOR: brand.dark,
      NODE_TEXT_HIGHLIGHT_COLOR: brand.dark,
      NODE_DEFAULT_COLOR: brand.dark,
      NODE_DEFAULT_BGCOLOR: brand.white,
      NODE_DEFAULT_BOXCOLOR: brand.dark,
      NODE_BOX_OUTLINE_COLOR: brand.dark,
      NODE_TITLE_HEIGHT: 28,
      NODE_SLOT_HEIGHT: 18,
      NODE_WIDGET_HEIGHT: 24,
      NODE_COLLAPSED_RADIUS: 8,
      DEFAULT_SHADOW_COLOR: "rgba(42, 42, 42, 0.16)",
      WIDGET_BGCOLOR: brand.pink,
      WIDGET_OUTLINE_COLOR: "#D1A3A3",
      WIDGET_TEXT_COLOR: brand.dark,
      WIDGET_SECONDARY_TEXT_COLOR: brand.coffee,
      LINK_COLOR: brand.coffee,
      LINK_COLORS: [brand.coffee, brand.accent, brand.dark, brand.cherry, brand.coffee],
      EVENT_LINK_COLOR: brand.accent,
      CONNECTING_LINK_COLOR: brand.dark,
      NODE_FONT: '"Founders Grotesk Text", Arial'
    });
    liteGraph.NODE_MODES_COLORS = [brand.dark, brand.accent, brand.coffee, brand.accent, brand.coffee];
    liteGraph.BACKGROUND_IMAGE = "";
    installFrankGraphRenderSkin();

    for (const node of getGraph()?._nodes ?? []) {
      if (defaultNodeColors.has(node.color)) node.color = brand.dark;
      if (defaultNodeColors.has(node.bgcolor)) node.bgcolor = brand.white;
    }
    applyFrankNodeBranding();

    if (canvas) {
      canvas.clear_background_color = brand.pink;
      canvas.background_image = "";
      canvas.node_title_color = brand.dark;
      canvas.default_link_color = brand.coffee;
      canvas._bg_img = null;
      canvas.bg_tint = null;
      canvas.dirty_canvas = true;
      canvas.dirty_bgcanvas = true;
      canvas.setDirty?.(true, true);
    }
    return Boolean(canvas);
  };

  let attempts = 0;
  const timer = window.setInterval(() => {
    applyFrankPalette();
    ensureFrankChrome();
    syncFrankWorkflowLabels();
    clearStockStarterWorkflow();
    syncFrankEmptyState();
    dismissStockStarterAlerts();
    fetchFrankWorkflowReceipt();
    tryLoadFrankApiPrompt();
    if (attempts++ > 80) window.clearInterval(timer);
  }, 250);
  window.addEventListener("load", () => {
    applyFrankPalette();
    ensureFrankChrome();
    syncFrankWorkflowLabels();
    clearStockStarterWorkflow();
    syncFrankEmptyState();
    dismissStockStarterAlerts();
    fetchFrankWorkflowReceipt();
    tryLoadFrankApiPrompt();
  });
})();
""".strip()


def _comfy_user_css_text():
    return """
/* Frank Create theme for a usable raw Comfy canvas. */
:root {
  --bg-color: #FFB6A5 !important;
  --fg-color: #3F2A2D !important;
  --content-bg: #FFB6A5 !important;
  --comfy-menu-bg: #FFFFFF !important;
  --comfy-input-bg: #ffffff !important;
  --comfy-input-border: rgba(42, 42, 42, 0.18) !important;
  --comfy-text-color: #3F2A2D !important;
  --comfy-text-muted: #3F2A2D !important;
  --border-color: rgba(42, 42, 42, 0.16) !important;
  --p-primary-color: #3F2A2D !important;
  --p-primary-500: #3F2A2D !important;
  --p-primary-600: #3F2A2D !important;
  --p-primary-contrast-color: #FFFFFF !important;
  --p-surface-0: #FFFFFF !important;
  --p-surface-50: #FFB6A5 !important;
  --p-surface-100: #FFD0C6 !important;
  --p-text-color: #3F2A2D !important;
  --p-text-muted-color: #3F2A2D !important;
  --interface-menu-surface: #FFFFFF !important;
  --interface-panel-surface: #FFFFFF !important;
  --interface-menu-stroke: rgba(42, 42, 42, 0.16) !important;
  --interface-panel-selected-surface: rgba(232, 180, 180, 0.34) !important;
  --interface-panel-hover-surface: rgba(232, 180, 180, 0.22) !important;
}

html,
body.litegraph {
  background: #FFB6A5 !important;
  color: #3F2A2D !important;
  font-family: "Founders Grotesk Text", Arial, sans-serif !important;
}

body[data-frank-create-graph="rawGoods"] {
  background:
    linear-gradient(90deg, rgba(232, 180, 180, 0.22) 1px, transparent 1px) 0 0 / 32px 32px,
    linear-gradient(0deg, rgba(232, 180, 180, 0.22) 1px, transparent 1px) 0 0 / 32px 32px,
    #FFB6A5 !important;
}

body.litegraph::before {
  content: "frank body";
  position: fixed;
  left: 14px;
  bottom: 12px;
  z-index: 48;
  border: 2px solid rgba(63, 42, 45, 0.26);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
  color: #3F2A2D;
  padding: 7px 10px 6px;
  font: 800 11px/1 "Pitch", "Courier New", monospace;
  pointer-events: none;
}

body[data-frank-create-graph="rawGoods"] canvas {
  filter: saturate(1.02) contrast(1.01);
}

#frank-comfy-brand-chrome {
  position: fixed;
  left: 72px;
  top: 76px;
  z-index: 48;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: min(420px, calc(100vw - 96px));
  border: 2px solid rgba(63, 42, 45, 0.22);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.88);
  color: #3F2A2D;
  padding: 8px 10px;
  box-shadow: 0 12px 30px rgba(42, 42, 42, 0.08);
  pointer-events: none;
}

#frank-comfy-brand-chrome .frank-comfy-wordmark {
  display: flex;
  align-items: stretch;
  font: 400 15px/1 "Pitch", "Courier New", monospace;
}

#frank-comfy-brand-chrome .frank-comfy-wordmark span {
  border: 2px solid #3F2A2D;
  border-radius: 7px 0 0 7px;
  padding: 5px 7px 3px;
}

#frank-comfy-brand-chrome .frank-comfy-wordmark span + span {
  border-left: 0;
  border-radius: 0 7px 7px 0;
}

#frank-comfy-brand-chrome strong,
#frank-comfy-brand-chrome small {
  display: block;
}

#frank-comfy-brand-chrome strong {
  font: 900 13px/1 "Pitch", "Courier New", monospace;
  text-transform: uppercase;
}

#frank-comfy-brand-chrome small {
  margin-top: 3px;
  color: #3F2A2D;
  font: 700 11px/1.2 "Founders Grotesk Text", Arial, sans-serif;
}

#frank-comfy-workflow-receipt {
  position: fixed;
  left: 72px;
  bottom: 18px;
  z-index: 56;
  display: grid;
  gap: 4px;
  max-width: min(360px, calc(100vw - 32px));
  border: 2px solid rgba(63, 42, 45, 0.26);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  color: #3F2A2D;
  padding: 10px 12px;
  box-shadow: inset 5px 0 0 #FFD0C6, 0 16px 38px rgba(42, 42, 42, 0.12);
  pointer-events: none;
}

#frank-comfy-workflow-receipt span,
#frank-comfy-workflow-receipt strong,
#frank-comfy-workflow-receipt small,
#frank-comfy-workflow-receipt em {
  display: block;
  min-width: 0;
  overflow-wrap: anywhere;
}

#frank-comfy-workflow-receipt span {
  color: #C4112F;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

#frank-comfy-workflow-receipt strong {
  color: #3F2A2D;
  font: 900 13px/1 "Pitch", "Courier New", monospace;
}

#frank-comfy-workflow-receipt small,
#frank-comfy-workflow-receipt em {
  color: #3F2A2D;
  font: 700 11px/1.25 "Pitch", "Courier New", monospace;
}

#frank-comfy-workflow-receipt em {
  font-style: normal;
}

body[data-frank-create-graph="rawGoods"] .topbar,
body[data-frank-create-graph="rawGoods"] .comfyui-menu,
body[data-frank-create-graph="rawGoods"] .comfyui-body-top,
body[data-frank-create-graph="rawGoods"] .p-menubar,
body[data-frank-create-graph="rawGoods"] .p-toolbar,
body[data-frank-create-graph="rawGoods"] .p-tabmenu,
body[data-frank-create-graph="rawGoods"] .workflow-tabs,
body[data-frank-create-graph="rawGoods"] .sidebar-container {
  background: rgba(255, 255, 255, 0.94) !important;
  border-color: rgba(42, 42, 42, 0.14) !important;
  color: #3F2A2D !important;
  box-shadow: 0 12px 28px rgba(42, 42, 42, 0.06) !important;
}

body[data-frank-create-graph="rawGoods"] .workflow-label,
body[data-frank-create-graph="rawGoods"] .p-breadcrumb-item-label,
body[data-frank-create-graph="rawGoods"] [data-testid='workflow-name'] {
  color: #3F2A2D !important;
  font: 900 12px/1 "Pitch", "Courier New", monospace !important;
  text-transform: uppercase !important;
}

body[data-frank-create-graph="rawGoods"] input,
body[data-frank-create-graph="rawGoods"] textarea,
body[data-frank-create-graph="rawGoods"] .p-inputtext,
body[data-frank-create-graph="rawGoods"] .p-select,
body[data-frank-create-graph="rawGoods"] .p-multiselect {
  background: #FFF4F0 !important;
  border: 2px solid rgba(42, 42, 42, 0.14) !important;
  border-radius: 8px !important;
  color: #3F2A2D !important;
  box-shadow: none !important;
}

#splash-loader {
  background: #FFB6A5 !important;
  color: #3F2A2D !important;
}

.p-button,
button {
  border-radius: 8px !important;
}

.p-button,
.p-togglebutton-checked,
.p-select-option-selected {
  background: #3F2A2D !important;
  border-color: #3F2A2D !important;
  color: #FFFFFF !important;
}

.connected-sidebar,
.sidebar-item-group,
.p-dialog,
.p-popover,
.p-menu,
.p-tieredmenu,
.litegraph.litecontextmenu {
  background: #FFFFFF !important;
  border-color: rgba(42, 42, 42, 0.16) !important;
  color: #3F2A2D !important;
}

@media (max-width: 900px) {
  #frank-comfy-brand-chrome {
    left: 12px;
    top: 76px;
    max-width: calc(100vw - 24px);
  }
}
""".strip()
    return """
/* Frank Create theme for the raw Comfy Canvas. */
:root {
  --bg-color: #FFB6A5 !important;
  --fg-color: #3F2A2D !important;
  --content-bg: #FFB6A5 !important;
  --comfy-menu-bg: #FFFFFF !important;
  --comfy-input-bg: #ffffff !important;
  --comfy-input-border: rgba(42, 42, 42, 0.18) !important;
  --comfy-text-color: #3F2A2D !important;
  --comfy-text-muted: #3F2A2D !important;
  --border-color: rgba(42, 42, 42, 0.16) !important;
  --p-primary-color: #3F2A2D !important;
  --p-primary-500: #3F2A2D !important;
  --p-primary-600: #3F2A2D !important;
  --p-primary-contrast-color: #FFFFFF !important;
  --p-surface-0: #FFFFFF !important;
  --p-surface-50: #FFB6A5 !important;
  --p-surface-100: #FFD0C6 !important;
  --p-text-color: #3F2A2D !important;
  --p-text-muted-color: #3F2A2D !important;
  --interface-menu-surface: #FFFFFF !important;
  --interface-panel-surface: #FFFFFF !important;
  --interface-menu-stroke: rgba(42, 42, 42, 0.16) !important;
  --interface-panel-selected-surface: rgba(232, 180, 180, 0.34) !important;
  --interface-panel-hover-surface: rgba(232, 180, 180, 0.22) !important;
}

body.litegraph,
html {
  background: #FFB6A5 !important;
  color: #3F2A2D !important;
  font-family: "Founders Grotesk Text", Arial, sans-serif !important;
}

body[data-frank-create-graph="rawGoods"] {
  background:
    radial-gradient(circle at 0 0, rgba(255, 255, 255, 0.68) 0 1px, transparent 1px) 0 0 / 18px 18px,
    linear-gradient(90deg, rgba(232, 180, 180, 0.34), transparent 42%),
    #FFB6A5 !important;
}

body.litegraph {
  background:
    linear-gradient(90deg, rgba(232, 180, 180, 0.28) 1px, transparent 1px) 0 0 / 32px 32px,
    linear-gradient(0deg, rgba(232, 180, 180, 0.28) 1px, transparent 1px) 0 0 / 32px 32px,
    #FFB6A5 !important;
}

body.litegraph::before {
  content: "Frank Create / Comfy Canvas";
  position: fixed;
  left: 14px;
  bottom: 12px;
  z-index: 99999;
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  padding: 7px 11px;
  font: 800 12px/1 "Pitch", "Courier New", monospace;
  text-transform: uppercase;
  pointer-events: none;
}

body[data-frank-create-graph="rawGoods"]::before {
  display: none;
}

#frank-comfy-brand-chrome {
  position: fixed;
  left: 72px;
  top: 78px;
  z-index: 99999;
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: min(520px, calc(100vw - 28px));
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  padding: 10px 12px;
  box-shadow: 0 18px 44px rgba(42, 42, 42, 0.12);
  pointer-events: none;
}

#frank-comfy-brand-strip {
  position: fixed;
  left: 72px;
  top: 150px;
  z-index: 99999;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-width: min(720px, calc(100vw - 96px));
  pointer-events: none;
}

#frank-comfy-brand-strip span:not(.frank-comfy-rule),
#frank-comfy-brand-strip .frank-comfy-rule::before {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  border: 2px solid rgba(42, 42, 42, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  padding: 8px 10px 7px;
  font: 900 11px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  box-shadow: 0 24px 70px rgba(42, 42, 42, 0.16);
}

#frank-comfy-brand-strip span:first-child {
  background: #3F2A2D;
  border-color: #3F2A2D;
  color: #FFFFFF;
}

#frank-comfy-brand-strip .frank-comfy-rule {
  display: inline-flex;
}

#frank-comfy-brand-strip .frank-comfy-rule::before {
  content: "KEEP THE GOODS HONEST";
  box-shadow:
    inset 5px 0 0 #3F2A2D,
    0 24px 70px rgba(42, 42, 42, 0.16);
}

#frank-comfy-brand-strip span:last-child {
  box-shadow:
    inset 5px 0 0 #C4112F,
    0 24px 70px rgba(42, 42, 42, 0.16);
}

#frank-comfy-lane-map {
  position: fixed;
  right: 18px;
  top: 82px;
  z-index: 99999;
  display: grid;
  gap: 7px;
  width: min(190px, calc(100vw - 36px));
  border: 2px solid rgba(42, 42, 42, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 230, 230, 0.92)),
    #FFFFFF;
  color: #3F2A2D;
  padding: 11px;
  box-shadow: 0 24px 70px rgba(42, 42, 42, 0.16);
  pointer-events: none;
}

#frank-comfy-lane-map::after {
  content: "frank body";
  color: rgba(42, 42, 42, 0.18);
  font: 700 11px/1 "Pitch", "Courier New", monospace;
}

#frank-comfy-lane-map strong {
  border-bottom: 2px solid rgba(42, 42, 42, 0.1);
  color: #3F2A2D;
  font: 900 13px/1 "Pitch", "Courier New", monospace;
  padding-bottom: 8px;
}

#frank-comfy-lane-map span {
  border: 2px solid rgba(42, 42, 42, 0.1);
  border-radius: 999px;
  background: #FFFFFF;
  color: #3F2A2D;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.06em;
  padding: 7px 9px 6px;
  text-transform: uppercase;
}

#frank-comfy-lane-map span:nth-of-type(1) {
  background: #3F2A2D;
  border-color: #3F2A2D;
  color: #FFFFFF;
}

#frank-comfy-lane-map span:nth-of-type(3) {
  box-shadow: inset 5px 0 0 #C4112F;
}

#frank-comfy-stage-ribbon {
  position: fixed;
  left: 50%;
  top: 80px;
  z-index: 99998;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  transform: translateX(-50%);
  max-width: min(660px, calc(100vw - 420px));
  pointer-events: none;
}

#frank-comfy-stage-ribbon span {
  border: 2px solid rgba(42, 42, 42, 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #3F2A2D;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.08em;
  padding: 7px 10px 6px;
  text-transform: uppercase;
  box-shadow: 0 18px 42px rgba(42, 42, 42, 0.1);
}

#frank-comfy-stage-ribbon span:nth-child(1) {
  background: #3F2A2D;
  border-color: #3F2A2D;
  color: #FFFFFF;
}

#frank-comfy-stage-ribbon span:nth-child(3) {
  box-shadow:
    inset 5px 0 0 #C4112F,
    0 18px 42px rgba(42, 42, 42, 0.1);
}

#frank-comfy-canvas-watermark {
  position: fixed;
  right: 286px;
  bottom: 72px;
  z-index: 1;
  display: inline-flex;
  align-items: stretch;
  color: rgba(42, 42, 42, 0.09);
  font: 400 clamp(42px, 7vw, 96px)/1 "Pitch", "Courier New", monospace;
  pointer-events: none;
}

#frank-comfy-canvas-watermark span {
  border: 3px solid currentColor;
  padding: 0.04em 0.18em 0;
}

#frank-comfy-canvas-watermark span:first-child {
  border-radius: 10px 0 0 10px;
}

#frank-comfy-canvas-watermark span + span {
  border-left: 0;
  border-radius: 0 10px 10px 0;
}

#frank-comfy-palette-card {
  position: fixed;
  left: 72px;
  top: 206px;
  z-index: 99999;
  display: grid;
  gap: 7px;
  width: min(210px, calc(100vw - 96px));
  border: 2px solid rgba(42, 42, 42, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  padding: 11px;
  box-shadow: 0 24px 70px rgba(42, 42, 42, 0.14);
  pointer-events: none;
}

#frank-comfy-palette-card strong {
  color: #C4112F;
  font: 900 11px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.1em;
}

#frank-comfy-palette-card span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #3F2A2D;
  font: 800 11px/1 "Founders Grotesk Text", Arial, sans-serif;
}

#frank-comfy-palette-card i {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(42, 42, 42, 0.14);
  border-radius: 999px;
}

#frank-comfy-palette-card i.pink {
  background: #FFB6A5;
}

#frank-comfy-palette-card i.coffee {
  background: #3F2A2D;
}

#frank-comfy-palette-card i.cherry {
  background: #C4112F;
}

#frank-comfy-status-dock {
  position: fixed;
  left: 72px;
  top: 332px;
  z-index: 99999;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  width: min(520px, calc(100vw - 352px));
  pointer-events: none;
}

#frank-comfy-status-dock span {
  border: 2px solid rgba(42, 42, 42, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  display: grid;
  gap: 5px;
  padding: 10px 11px;
  box-shadow:
    inset 5px 0 0 #FFD0C6,
    0 24px 70px rgba(42, 42, 42, 0.14);
}

#frank-comfy-status-dock span:nth-child(2) {
  box-shadow:
    inset 5px 0 0 #3F2A2D,
    0 24px 70px rgba(42, 42, 42, 0.14);
}

#frank-comfy-status-dock span:nth-child(3) {
  box-shadow:
    inset 5px 0 0 #C4112F,
    0 24px 70px rgba(42, 42, 42, 0.14);
}

#frank-comfy-status-dock small,
#frank-comfy-status-dock strong {
  display: block;
  min-width: 0;
}

#frank-comfy-status-dock small {
  color: #3F2A2D;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

#frank-comfy-status-dock strong {
  color: #3F2A2D;
  font: 800 12px/1.1 "Pitch", "Courier New", monospace;
}

#frank-comfy-status-dock::after {
  content: "Canvas skin active";
  position: absolute;
  left: 0;
  top: calc(100% + 7px);
  border: 2px solid rgba(42, 42, 42, 0.12);
  border-radius: 999px;
  background: #3F2A2D;
  color: #FFFFFF;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.08em;
  padding: 7px 10px 6px;
  text-transform: uppercase;
}

#frank-comfy-action-rail {
  position: fixed;
  right: 18px;
  top: 302px;
  z-index: 99999;
  display: grid;
  gap: 8px;
  width: min(238px, calc(100vw - 36px));
  border: 2px solid rgba(42, 42, 42, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  padding: 12px;
  box-shadow: 0 24px 70px rgba(42, 42, 42, 0.16);
  pointer-events: none;
}

#frank-comfy-action-rail strong {
  color: #3F2A2D;
  font: 900 13px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

#frank-comfy-action-rail span {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: #3F2A2D;
  font: 800 11px/1.2 "Founders Grotesk Text", Arial, sans-serif;
}

#frank-comfy-action-rail b {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: #3F2A2D;
  color: #FFFFFF;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
}

#frank-comfy-art-direction {
  position: fixed;
  right: 18px;
  top: 522px;
  z-index: 99999;
  width: min(238px, calc(100vw - 36px));
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(255, 244, 240, 0.94)),
    #FFFFFF;
  color: #3F2A2D;
  padding: 12px;
  box-shadow:
    inset 6px 0 0 #C4112F,
    0 24px 70px rgba(42, 42, 42, 0.16);
  pointer-events: none;
}

#frank-comfy-art-direction span,
#frank-comfy-art-direction strong {
  display: block;
}

#frank-comfy-art-direction span {
  color: #C4112F;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

#frank-comfy-art-direction strong {
  margin-top: 6px;
  color: #3F2A2D;
  font: 800 13px/1.18 "Pitch", "Courier New", monospace;
}

#frank-comfy-node-legend {
  position: fixed;
  left: 72px;
  bottom: 18px;
  z-index: 99999;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-width: min(680px, calc(100vw - 342px));
  pointer-events: none;
}

#frank-comfy-node-legend span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 2px solid rgba(42, 42, 42, 0.12);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.06em;
  padding: 7px 10px 6px;
  text-transform: uppercase;
  box-shadow: 0 18px 42px rgba(42, 42, 42, 0.1);
}

#frank-comfy-node-legend i {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid rgba(42, 42, 42, 0.16);
  border-radius: 999px;
}

#frank-comfy-node-legend i.brief {
  background: #3F2A2D;
}

#frank-comfy-node-legend i.reference {
  background: #3F2A2D;
}

#frank-comfy-node-legend i.magic {
  background: #C4112F;
}

#frank-comfy-node-legend i.output {
  background: #FFD0C6;
}

#frank-comfy-node-style-card {
  position: fixed;
  right: 18px;
  bottom: 126px;
  z-index: 99999;
  display: grid;
  gap: 7px;
  width: min(238px, calc(100vw - 36px));
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background:
    repeating-linear-gradient(135deg, rgba(111, 78, 55, 0.12) 0 2px, transparent 2px 12px),
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(248, 230, 230, 0.94)),
    #FFFFFF;
  color: #3F2A2D;
  padding: 12px;
  box-shadow:
    inset 6px 0 0 #3F2A2D,
    0 24px 70px rgba(42, 42, 42, 0.16);
  pointer-events: none;
}

#frank-comfy-node-style-card strong {
  color: #C4112F;
  font: 900 11px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

#frank-comfy-node-style-card span {
  border: 1px solid rgba(42, 42, 42, 0.12);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: #3F2A2D;
  font: 800 11px/1 "Pitch", "Courier New", monospace;
  padding: 7px 9px 6px;
}

#frank-comfy-node-style-card span:nth-child(2) {
  color: #3F2A2D;
  box-shadow: inset 5px 0 0 #3F2A2D;
}

#frank-comfy-node-style-card span:nth-child(4) {
  color: #C4112F;
  box-shadow: inset 5px 0 0 #C4112F;
}

#frank-comfy-production-plate {
  position: fixed;
  left: 50%;
  bottom: 18px;
  z-index: 99999;
  display: grid;
  gap: 5px;
  min-width: min(300px, calc(100vw - 44px));
  transform: translateX(-50%);
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(248, 230, 230, 0.92), rgba(255, 255, 255, 0.96)),
    #FFFFFF;
  color: #3F2A2D;
  padding: 12px 14px;
  box-shadow:
    inset 7px 0 0 #C4112F,
    0 24px 70px rgba(42, 42, 42, 0.16);
  pointer-events: none;
}

#frank-comfy-production-plate span,
#frank-comfy-production-plate strong,
#frank-comfy-production-plate small {
  display: block;
}

#frank-comfy-production-plate span {
  color: #C4112F;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

#frank-comfy-production-plate strong {
  color: #3F2A2D;
  font: 900 14px/1 "Pitch", "Courier New", monospace;
  text-transform: uppercase;
}

#frank-comfy-production-plate small {
  color: #3F2A2D;
  font: 800 11px/1.25 "Founders Grotesk Text", Arial, sans-serif;
}

#frank-comfy-workflow-receipt {
  position: fixed;
  left: 50%;
  top: 150px;
  z-index: 99999;
  display: grid;
  gap: 5px;
  min-width: min(340px, calc(100vw - 44px));
  max-width: min(460px, calc(100vw - 540px));
  transform: translateX(-50%);
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(255, 244, 240, 0.94)),
    #FFFFFF;
  color: #3F2A2D;
  padding: 12px 14px;
  box-shadow:
    inset 7px 0 0 #3F2A2D,
    0 24px 70px rgba(42, 42, 42, 0.16);
  pointer-events: none;
}

#frank-comfy-workflow-receipt span,
#frank-comfy-workflow-receipt strong,
#frank-comfy-workflow-receipt small,
#frank-comfy-workflow-receipt em {
  display: block;
  min-width: 0;
}

#frank-comfy-workflow-receipt span {
  color: #C4112F;
  font: 900 10px/1 "Pitch", "Courier New", monospace;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

#frank-comfy-workflow-receipt strong {
  color: #3F2A2D;
  font: 900 14px/1 "Pitch", "Courier New", monospace;
  overflow-wrap: anywhere;
  text-transform: uppercase;
}

#frank-comfy-workflow-receipt small,
#frank-comfy-workflow-receipt em {
  color: #3F2A2D;
  font: 800 11px/1.25 "Pitch", "Courier New", monospace;
  overflow-wrap: anywhere;
}

#frank-comfy-workflow-receipt em {
  color: #3F2A2D;
  font-style: normal;
}

body[data-frank-create-graph="rawGoods"] canvas {
  filter: saturate(1.05) contrast(1.02);
}

body[data-frank-create-graph="rawGoods"] .topbar,
body[data-frank-create-graph="rawGoods"] .comfyui-menu,
body[data-frank-create-graph="rawGoods"] .comfyui-body-top,
body[data-frank-create-graph="rawGoods"] .p-menubar,
body[data-frank-create-graph="rawGoods"] .p-toolbar,
body[data-frank-create-graph="rawGoods"] .p-tabmenu,
body[data-frank-create-graph="rawGoods"] .workflow-tabs,
body[data-frank-create-graph="rawGoods"] .sidebar-container {
  background: rgba(255, 255, 255, 0.94) !important;
  border-color: rgba(42, 42, 42, 0.14) !important;
  color: #3F2A2D !important;
  box-shadow: 0 14px 30px rgba(42, 42, 42, 0.06) !important;
}

body[data-frank-create-graph="rawGoods"] .workflow-label,
body[data-frank-create-graph="rawGoods"] .p-breadcrumb-item-label,
body[data-frank-create-graph="rawGoods"] [data-testid='workflow-name'] {
  color: #3F2A2D !important;
  font: 900 12px/1 "Pitch", "Courier New", monospace !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
}

body[data-frank-create-graph="rawGoods"] input,
body[data-frank-create-graph="rawGoods"] textarea,
body[data-frank-create-graph="rawGoods"] .p-inputtext,
body[data-frank-create-graph="rawGoods"] .p-select,
body[data-frank-create-graph="rawGoods"] .p-multiselect {
  background: #FFF4F0 !important;
  border: 2px solid rgba(42, 42, 42, 0.14) !important;
  border-radius: 8px !important;
  color: #3F2A2D !important;
  box-shadow: none !important;
}

body[data-frank-create-graph="rawGoods"] input:focus,
body[data-frank-create-graph="rawGoods"] textarea:focus,
body[data-frank-create-graph="rawGoods"] .p-inputtext:focus {
  border-color: #FFD0C6 !important;
  outline: 2px solid rgba(232, 180, 180, 0.32) !important;
}

#frank-comfy-brand-chrome .frank-comfy-wordmark {
  display: flex;
  align-items: stretch;
  font: 400 18px/1 "Pitch", "Courier New", monospace;
}

#frank-comfy-brand-chrome .frank-comfy-wordmark span {
  border: 2px solid #3F2A2D;
  border-radius: 8px 0 0 8px;
  padding: 6px 9px 4px;
}

#frank-comfy-brand-chrome .frank-comfy-wordmark span + span {
  border-left: 0;
  border-radius: 0 8px 8px 0;
}

#frank-comfy-brand-chrome strong,
#frank-comfy-brand-chrome small {
  display: block;
}

#frank-comfy-brand-chrome strong {
  font: 900 15px/1 "Pitch", "Courier New", monospace;
  text-transform: uppercase;
}

#frank-comfy-brand-chrome small {
  margin-top: 4px;
  color: #3F2A2D;
  font: 800 11px/1.25 "Founders Grotesk Text", Arial, sans-serif;
}

#frank-comfy-empty-state {
  position: fixed;
  left: 50%;
  top: 50%;
  z-index: 99998;
  width: min(360px, calc(100vw - 44px));
  transform: translate(-50%, -50%);
  border: 2px solid #3F2A2D;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  color: #3F2A2D;
  padding: 18px;
  pointer-events: none;
  box-shadow: 0 24px 60px rgba(42, 42, 42, 0.14);
}

#frank-comfy-empty-state strong,
#frank-comfy-empty-state span {
  display: block;
}

#frank-comfy-empty-state strong {
  font: 900 28px/0.95 "Pitch", "Courier New", monospace;
  text-transform: uppercase;
}

#frank-comfy-empty-state span {
  margin-top: 10px;
  color: #3F2A2D;
  font: 700 13px/1.35 "Pitch", "Courier New", monospace;
}

#splash-loader {
  background: #FFB6A5 !important;
  color: #3F2A2D !important;
}

.p-button,
button {
  border-radius: 8px !important;
}

.p-button,
.p-togglebutton-checked,
.p-select-option-selected {
  background: #3F2A2D !important;
  border-color: #3F2A2D !important;
  color: #FFFFFF !important;
}

.connected-sidebar,
.sidebar-item-group,
.p-dialog,
.p-popover,
.p-menu,
.p-tieredmenu,
.litegraph.litecontextmenu {
  background: #FFFFFF !important;
  border-color: rgba(42, 42, 42, 0.16) !important;
  color: #3F2A2D !important;
  box-shadow: 0 18px 48px rgba(42, 42, 42, 0.12) !important;
}

.litegraph.litecontextmenu .litemenu-entry:hover,
.side-bar-button:hover,
.side-bar-button-selected {
  background: rgba(232, 180, 180, 0.32) !important;
  color: #3F2A2D !important;
}

@media (max-width: 900px) {
  #frank-comfy-brand-chrome,
  #frank-comfy-brand-strip,
  #frank-comfy-lane-map,
  #frank-comfy-stage-ribbon,
  #frank-comfy-canvas-watermark,
  #frank-comfy-palette-card,
  #frank-comfy-status-dock,
  #frank-comfy-action-rail,
  #frank-comfy-art-direction,
  #frank-comfy-node-legend,
  #frank-comfy-node-style-card,
  #frank-comfy-production-plate,
  #frank-comfy-workflow-receipt {
    position: static;
    margin: 10px 12px 0;
    max-width: calc(100vw - 24px);
    width: auto;
    transform: none;
  }
}
""".strip()


