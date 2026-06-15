import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8190"
DEFAULT_OUTPUT_DIR = ROOT / "user" / "frank_create" / "demo_evidence"
SMOKE_STATUS_PATH = ROOT / "user" / "frank_create" / "workflow_smoke_status.json"
CLIFF_PREP_STATUS_PATH = ROOT / "user" / "frank_create" / "cliff_prep_status.json"


class DemoEvidenceError(RuntimeError):
    pass


def fetch_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise DemoEvidenceError(f"Could not read {url}: {exc}") from exc


def read_workflow_smoke_status(path: Path | str = SMOKE_STATUS_PATH) -> dict[str, Any]:
    receipt_path = Path(path)
    if not receipt_path.exists():
        return {"ok": False, "error": "No workflow-smoke receipt found.", "path": str(receipt_path)}
    try:
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"Workflow-smoke receipt could not be read: {exc}", "path": str(receipt_path)}


def read_cliff_prep_status(path: Path | str = CLIFF_PREP_STATUS_PATH) -> dict[str, Any] | None:
    receipt_path = Path(path)
    if not receipt_path.exists():
        return None
    try:
        return json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def build_evidence_payload(
    doctor: dict[str, Any],
    smoke: dict[str, Any],
    base_url: str = DEFAULT_BASE_URL,
    cliff_prep: dict[str, Any] | None = None,
    provider_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = doctor.get("checks") or []
    warnings = [check for check in checks if check.get("status") == "warning"]
    failures = [check for check in checks if check.get("status") == "fail"]
    summary = doctor.get("summary") or {}
    provider_status = provider_status or {}
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "title": "Frank Create Demo Evidence",
        "generated_at": generated_at,
        "base_url": base_url.rstrip("/"),
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
            "waiting_provider_models": int(summary.get("waitingProviderModels") or 0),
            "secret_issue_count": int(summary.get("secretIssueCount") or 0),
            "graph_branding_ready": bool(summary.get("graphBrandingReady")),
            "provider_adapter_count": int(summary.get("providerAdapterCount") or 0),
            "missing_provider_adapter_count": int(summary.get("missingProviderAdapterCount") or 0),
        },
        "checks": checks,
        "warnings": warnings,
        "failures": failures,
        "notes": doctor.get("notes") or [],
        "model_roster": model_roster_for_evidence(provider_status.get("models") or []),
        "workflow_smoke": {
            "ok": bool(smoke.get("ok")),
            "session_name": smoke.get("session_name") or smoke.get("error") or "Workflow smoke",
            "completed_at": smoke.get("completed_at"),
            "handoff": smoke.get("handoff") or {},
            "image_exports": smoke.get("image_exports") or [],
            "video_export": smoke.get("video_export") or {},
            "error": smoke.get("error"),
        },
        "cliff_prep": cliff_prep,
        "demo_urls": {
            "studio": base_url.rstrip("/"),
            "advanced_graph": f"{base_url.rstrip('/')}/graph",
            "raw_comfy": f"{base_url.rstrip('/')}/comfy/",
        },
    }


def model_roster_for_evidence(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    smoke = payload.get("workflow_smoke") or {}
    lines = [
        "# Frank Create Demo Evidence",
        "",
        f"Generated: {payload.get('generated_at')}",
        f"Status: **{payload.get('headline')}** (`{payload.get('status')}`)",
        f"Ready for demo: **{'yes' if payload.get('ready_for_demo') else 'no'}**",
        "",
        "## Snapshot",
        "",
        f"- Outputs: {summary.get('outputs', 0)}",
        f"- References: {summary.get('references', 0)}",
        f"- Approved assets: {summary.get('approved', 0)}",
        f"- Motion/storyboard assets: {summary.get('video', 0)}",
        f"- Workflow smoke media files: {summary.get('workflow_smoke_media_files', 0)}",
        f"- Graph branding: {'verified' if summary.get('graph_branding_ready') else 'not verified'}",
        f"- Provider adapter families: {summary.get('provider_adapter_count', 0)} registered, {summary.get('missing_provider_adapter_count', 0)} missing",
        f"- Live provider models waiting on keys: {summary.get('waiting_provider_models', 0)}",
        f"- Source/docs token issues: {summary.get('secret_issue_count', 0)}",
        "",
        "## Latest Workflow Smoke",
        "",
        f"- Result: {'passed' if smoke.get('ok') else 'not passed'}",
        f"- Session: {smoke.get('session_name') or 'n/a'}",
        f"- Completed: {smoke.get('completed_at') or 'n/a'}",
    ]
    handoff = smoke.get("handoff") or {}
    if handoff:
        lines.extend(
            [
                f"- Handoff assets: {handoff.get('asset_count', 0)} approved, {handoff.get('reference_count', 0)} references",
                f"- Handoff media files: {handoff.get('media_file_count', 0)}",
                f"- Turn count: {handoff.get('turn_count', 0)}",
            ]
        )
    if smoke.get("error"):
        lines.append(f"- Error: {smoke.get('error')}")

    cliff_prep = payload.get("cliff_prep") or {}
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
    for check in payload.get("checks") or []:
        lines.append(f"- `{check.get('status')}` {check.get('label')}: {check.get('detail')}")
        if check.get("action"):
            lines.append(f"  Action: {check.get('action')}")

    urls = payload.get("demo_urls") or {}
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

    notes = payload.get("notes") or []
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)

    model_roster = payload.get("model_roster") or []
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


def write_evidence_files(payload: dict[str, Any], output_dir: Path | str = DEFAULT_OUTPUT_DIR, timestamp: str | None = None) -> dict[str, Path]:
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"frank-create-demo-evidence-{stamp}.md"
    json_path = directory / f"frank-create-demo-evidence-{stamp}.json"
    latest_markdown_path = directory / "frank-create-demo-evidence-latest.md"
    latest_json_path = directory / "frank-create-demo-evidence-latest.json"
    markdown = render_markdown(payload)
    json_payload = json.dumps(payload, indent=2, sort_keys=True)
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


def generate_evidence(base_url: str = DEFAULT_BASE_URL, output_dir: Path | str = DEFAULT_OUTPUT_DIR, timeout: float = 8.0) -> dict[str, Path]:
    root_url = base_url.rstrip("/")
    doctor = fetch_json(f"{root_url}/api/frank/demo-doctor", timeout=timeout)
    provider_status = fetch_json(f"{root_url}/api/frank/provider-status", timeout=timeout)
    smoke = read_workflow_smoke_status()
    cliff_prep = read_cliff_prep_status()
    payload = build_evidence_payload(doctor, smoke, base_url=root_url, cliff_prep=cliff_prep, provider_status=provider_status)
    return write_evidence_files(payload, output_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a Frank Create demo evidence report from Demo Doctor and workflow smoke.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Frank Create server root URL.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for Markdown and JSON evidence files.")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds.")
    args = parser.parse_args(argv)

    try:
        outputs = generate_evidence(base_url=args.base_url, output_dir=args.output_dir, timeout=args.timeout)
    except DemoEvidenceError as exc:
        print(f"[Frank Evidence] FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"[Frank Evidence] Markdown: {outputs['markdown']}")
    print(f"[Frank Evidence] JSON: {outputs['json']}")
    print(f"[Frank Evidence] Latest Markdown: {outputs['latest_markdown']}")
    print(f"[Frank Evidence] Latest JSON: {outputs['latest_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
