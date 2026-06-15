import json

from scripts import frank_demo_evidence


def test_demo_evidence_markdown_summarizes_doctor_and_smoke_without_secrets():
    doctor = {
        "status": "ready_with_warnings",
        "readyForDemo": True,
        "headline": "Ready for Cliff",
        "summary": {
            "outputAssetCount": 6,
            "referenceAssetCount": 1,
            "approvedAssetCount": 2,
            "videoAssetCount": 1,
            "workflowSmokeOk": True,
            "workflowSmokeAt": "2026-06-08T20:59:38.549778+00:00",
            "workflowSmokeMediaFileCount": 3,
            "graphBrandingReady": True,
            "providerAdapterCount": 9,
            "missingProviderAdapterCount": 0,
            "waitingProviderModels": 8,
            "secretIssueCount": 0,
        },
        "checks": [
            {"key": "secret_hygiene", "label": "Secret hygiene", "status": "ready", "detail": "Frank app source/docs checked."},
            {
                "key": "provider_keys",
                "label": "Provider keys",
                "status": "warning",
                "detail": "8 live models are waiting on server keys.",
                "action": (
                    "Local renderer still demos end to end. For live API rounds, paste rotated keys in "
                    "Provider Setup -> Save server keys or use user\\frank_create\\provider_keys.env."
                ),
            },
        ],
        "notes": ["Provider readiness reports env var names only, never secret values."],
    }
    smoke = {
        "ok": True,
        "session_name": "Frank Create Workflow Smoke 20260608-205935",
        "completed_at": "2026-06-08T20:59:38.549778+00:00",
        "handoff": {"media_file_count": 3, "asset_count": 2, "reference_count": 1, "turn_count": 3},
        "image_exports": [{"preset": "transparent-png"}, {"preset": "email-hero"}],
        "video_export": {"preset": "video-storyboard"},
    }
    cliff_prep = {
        "ok": True,
        "completed_at": "2026-06-08T21:25:37+00:00",
        "cliff_pack": {
            "export_id": "export_demo_pack",
            "approved_asset_count": 1,
            "reference_asset_count": 1,
            "archive_file_count": 4,
        },
    }
    provider_status = {
        "models": [
            {
                "id": "frank-local-comfy",
                "label": "Frank Local Comfy Studio",
                "short_label": "Local Comfy",
                "provider": "local",
                "badge": "Ready",
                "configured": True,
                "missing_env_vars": [],
                "capabilities": {"generation": True, "edit": True, "masked_edit": True, "video": True},
                "reference_image_limit": 8,
            },
            {
                "id": "openai-gpt-image-2",
                "label": "OpenAI gpt-image-2",
                "short_label": "gpt-image-2",
                "provider": "openai",
                "badge": "4K",
                "configured": False,
                "missing_env_vars": ["OPENAI_API_KEY"],
                "capabilities": {"generation": True, "edit": True, "masked_edit": True, "video": False},
                "reference_image_limit": 10,
            },
            {
                "id": "runway-gen45-video",
                "label": "Runway Gen-4.5 Video",
                "short_label": "Runway Gen-4.5",
                "provider": "runway",
                "badge": "Video",
                "configured": False,
                "missing_env_vars": ["RUNWAYML_API_SECRET", "RUNWAY_API_KEY"],
                "capabilities": {"generation": False, "edit": False, "masked_edit": False, "video": True},
                "reference_image_limit": 1,
            },
        ]
    }

    payload = frank_demo_evidence.build_evidence_payload(
        doctor,
        smoke,
        base_url="http://127.0.0.1:8190",
        cliff_prep=cliff_prep,
        provider_status=provider_status,
    )
    markdown = frank_demo_evidence.render_markdown(payload)

    assert payload["ready_for_demo"] is True
    assert payload["workflow_smoke"]["session_name"] == "Frank Create Workflow Smoke 20260608-205935"
    assert "# Frank Create Demo Evidence" in markdown
    assert "Ready for Cliff" in markdown
    assert "Frank Create Workflow Smoke 20260608-205935" in markdown
    assert "Graph branding: verified" in markdown
    assert "Provider adapter families: 9 registered, 0 missing" in markdown
    assert "Launch Model Roster" in markdown
    assert "Local Comfy (local, Ready): ready; gen, edit, mask, video; 8 refs" in markdown
    assert "gpt-image-2 (openai, 4K): needs OPENAI_API_KEY; gen, edit, mask; 10 refs" in markdown
    assert "Runway Gen-4.5 (runway, Video): needs RUNWAYML_API_SECRET/RUNWAY_API_KEY; video; 1 refs" in markdown
    assert "Secret hygiene" in markdown
    assert "Provider keys" in markdown
    assert "Provider Setup -> Save server keys" in markdown
    assert "user\\frank_create\\provider_keys.env" in markdown
    assert "Cliff Prep Receipt" in markdown
    assert "export_demo_pack" in markdown
    assert "Approved assets in pack: 1" in markdown
    assert ("r8_" + "abcdefghijklmnopqrstuvwxyz123456") not in json.dumps(payload)
    assert "server-side-openai-secret" not in json.dumps(payload)


def test_demo_evidence_reads_optional_cliff_prep_receipt(tmp_path):
    receipt_path = tmp_path / "cliff_prep_status.json"
    receipt_path.write_text(json.dumps({"ok": True, "cliff_pack": {"export_id": "export_from_file"}}), encoding="utf-8-sig")

    receipt = frank_demo_evidence.read_cliff_prep_status(receipt_path)

    assert receipt["ok"] is True
    assert receipt["cliff_pack"]["export_id"] == "export_from_file"
    assert frank_demo_evidence.read_cliff_prep_status(tmp_path / "missing.json") is None


def test_demo_evidence_writes_markdown_and_json(tmp_path):
    payload = frank_demo_evidence.build_evidence_payload(
        {
            "status": "ready",
            "readyForDemo": True,
            "headline": "Ready for Cliff",
            "summary": {},
            "checks": [],
            "notes": [],
        },
        {"ok": True, "session_name": "Smoke"},
        base_url="http://127.0.0.1:8190",
    )

    outputs = frank_demo_evidence.write_evidence_files(payload, tmp_path, timestamp="20260608-210000")

    assert outputs["markdown"].name == "frank-create-demo-evidence-20260608-210000.md"
    assert outputs["json"].name == "frank-create-demo-evidence-20260608-210000.json"
    assert outputs["latest_markdown"].name == "frank-create-demo-evidence-latest.md"
    assert outputs["latest_json"].name == "frank-create-demo-evidence-latest.json"
    assert outputs["markdown"].exists()
    assert outputs["json"].exists()
    assert outputs["latest_markdown"].exists()
    assert outputs["latest_json"].exists()
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))["headline"] == "Ready for Cliff"
    assert json.loads(outputs["latest_json"].read_text(encoding="utf-8"))["headline"] == "Ready for Cliff"
    assert outputs["latest_markdown"].read_text(encoding="utf-8") == outputs["markdown"].read_text(encoding="utf-8")
