import json
import sqlite3

from custom_nodes.frank_create.store import FrankCreateStore


def test_creative_ops_records_round_trip(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")

    project = store.create_project({"name": "Product Shot Lab", "client": "Frank Body"})
    brief = store.create_brief(
        {
            "project_id": project["id"],
            "title": "Cacao Coffee Scrub PDP",
            "product_name": "Cacao Coffee Scrub",
            "task_type": "background-replace",
            "channel": "PDP",
            "tone": "cheeky-director-ready",
            "prompt": "Warm bathroom set, product centered, soft flash.",
            "reference_image_path": "input/cacao-scrub.png",
        }
    )
    run = store.create_run(
        {
            "brief_id": brief["id"],
            "workflow_key": "local-product-shot",
            "provider": "local",
            "prompt_id": "comfy-prompt-123",
            "status": "review",
        }
    )
    asset = store.create_asset(
        {
            "run_id": run["id"],
            "brief_id": brief["id"],
            "kind": "candidate",
            "title": "Round 1 / Candidate 01",
            "file_path": "output/frank_create/candidate-01.png",
            "preview_url": "/api/view?filename=candidate-01.png&type=output",
            "approval_status": "review",
        }
    )

    approved = store.update_asset(
        asset["id"],
        {"favorite": True, "approval_status": "approved", "notes": "Approved. Hot."},
    )
    export = store.create_export(
        {
            "asset_id": approved["id"],
            "preset": "instagram-story",
            "file_path": "user/frank_create/exports/candidate-01-story.png",
            "metadata": {"prompt": brief["prompt"], "workflow_key": run["workflow_key"]},
        }
    )

    assert store.list_projects()[0]["name"] == "Product Shot Lab"
    assert store.list_briefs(project_id=project["id"])[0]["product_name"] == "Cacao Coffee Scrub"
    assert store.list_runs(brief_id=brief["id"])[0]["prompt_id"] == "comfy-prompt-123"
    assert store.list_assets(run_id=run["id"])[0]["approval_status"] == "approved"
    assert approved["favorite"] is True
    assert json.loads(export["metadata_json"])["workflow_key"] == "local-product-shot"


def test_missing_records_raise_lookup_error(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")

    try:
        store.update_asset("missing", {"approval_status": "approved"})
    except LookupError as exc:
        assert "asset" in str(exc)
    else:
        raise AssertionError("Expected update_asset to fail for a missing asset")


def test_delete_asset_removes_asset_and_exports_but_keeps_media_file(tmp_path):
    media_path = tmp_path / "output" / "frank_create" / "bad-reference.png"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"reference-bytes")
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db", root_dir=tmp_path / "user")
    session = store.create_session({"name": "Asset removal QA"})
    asset = store.create_asset(
        {
            "session_id": session["id"],
            "kind": "reference",
            "title": "Bad reference",
            "file_path": str(media_path),
        }
    )
    store.create_export({"asset_id": asset["id"], "preset": "pdp", "file_path": "bad-reference.zip"})

    deleted = store.delete_asset(asset["id"])

    assert deleted["id"] == asset["id"]
    assert store.list_assets(session_id=session["id"]) == []
    assert store.list_exports(asset_id=asset["id"]) == []
    assert media_path.exists()


def test_sessions_turns_and_sync_ready_asset_fields(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")

    session = store.create_session({"name": "Cacao launch", "mode": "image", "project_id": None})
    turn = store.create_turn(
        {
            "session_id": session["id"],
            "kind": "generate",
            "provider": "google",
            "model": "google-nb-pro",
            "prompt": "Warm bathroom shot.",
            "settings": {"aspect_ratio": "1:1", "image_size": "4K", "count": 4},
            "reference_asset_ids": ["asset_ref"],
            "frank_body_mode": True,
            "status": "queued",
        }
    )
    asset = store.create_asset(
        {
            "brief_id": "session-asset",
            "run_id": None,
            "turn_id": turn["id"],
            "session_id": session["id"],
            "kind": "candidate",
            "title": "Round 1 / Candidate",
            "media_type": "image",
            "provider": "google",
            "model": "google-nb-pro",
            "prompt": "Warm bathroom shot.",
            "settings": {"aspect_ratio": "1:1"},
            "source_asset_id": None,
            "reference_asset_ids": ["asset_ref"],
            "remote_id": "remote-image-1",
        }
    )

    updated_turn = store.update_turn(turn["id"], {"status": "complete", "output_asset_ids": [asset["id"]]})

    assert store.list_sessions()[0]["name"] == "Cacao launch"
    assert store.list_turns(session_id=session["id"])[0]["model"] == "google-nb-pro"
    assert updated_turn["status"] == "complete"
    assert json.loads(updated_turn["output_asset_ids_json"]) == [asset["id"]]
    assert store.list_assets(session_id=session["id"])[0]["remote_id"] == "remote-image-1"


def test_exports_are_sync_ready_for_future_dam_or_frankhub_mirror(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    session = store.create_session({"name": "Export sync QA"})
    asset = store.create_asset(
        {
            "session_id": session["id"],
            "title": "Approved PDP crop",
            "approval_status": "approved",
            "file_path": "output/frank_create/pdp.png",
        }
    )

    default_export = store.create_export(
        {
            "asset_id": asset["id"],
            "preset": "pdp",
            "file_path": "user/frank_create/exports/pdp.zip",
        }
    )
    mirrored_export = store.create_export(
        {
            "asset_id": asset["id"],
            "preset": "email-hero",
            "file_path": "user/frank_create/exports/email-hero.zip",
            "metadata": {"channel": "email"},
            "sync_status": "synced",
            "remote_id": "dam-export-123",
        }
    )

    assert default_export["sync_status"] == "local"
    assert default_export["remote_id"] is None
    assert mirrored_export["sync_status"] == "synced"
    assert mirrored_export["remote_id"] == "dam-export-123"
    exports_by_preset = {record["preset"]: record for record in store.list_exports()}
    assert exports_by_preset["email-hero"]["remote_id"] == "dam-export-123"


def test_projects_briefs_and_runs_are_sync_ready(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")

    project = store.create_project(
        {
            "name": "FrankHub launch mirror",
            "client": "Frank Body",
            "sync_status": "synced",
            "remote_id": "supabase-project-1",
        }
    )
    brief = store.create_brief(
        {
            "project_id": project["id"],
            "title": "Body scrub PDP",
            "task_type": "product-shot-lab",
            "sync_status": "pending",
            "remote_id": "supabase-brief-1",
        }
    )
    run = store.create_run(
        {
            "brief_id": brief["id"],
            "workflow_key": "comfy-checkpoint-img2img",
            "provider": "local",
            "sync_status": "pending",
            "remote_id": "supabase-run-1",
        }
    )

    updated_project = store.update_project(project["id"], {"sync_status": "dirty", "remote_id": "supabase-project-2"})
    updated_brief = store.update_brief(brief["id"], {"sync_status": "synced", "remote_id": "supabase-brief-2"})
    updated_run = store.update_run(run["id"], {"sync_status": "synced", "remote_id": "supabase-run-2"})

    assert updated_project["sync_status"] == "dirty"
    assert updated_project["remote_id"] == "supabase-project-2"
    assert updated_brief["sync_status"] == "synced"
    assert updated_brief["remote_id"] == "supabase-brief-2"
    assert updated_run["sync_status"] == "synced"
    assert updated_run["remote_id"] == "supabase-run-2"
    assert store.create_project({"name": "Local only"})["sync_status"] == "local"


def test_legacy_database_migrates_all_sync_metadata_columns(tmp_path):
    db_path = tmp_path / "legacy_frank_create.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                client TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE briefs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                product_name TEXT,
                task_type TEXT NOT NULL,
                channel TEXT,
                tone TEXT,
                prompt TEXT,
                negative_prompt TEXT,
                reference_image_path TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                brief_id TEXT NOT NULL,
                workflow_key TEXT NOT NULL,
                provider TEXT NOT NULL,
                prompt_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                name TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'image',
                status TEXT NOT NULL DEFAULT 'active',
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'generate',
                provider TEXT,
                model TEXT NOT NULL,
                prompt TEXT NOT NULL,
                settings_json TEXT NOT NULL DEFAULT '{}',
                source_asset_id TEXT,
                reference_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                output_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                frank_body_mode INTEGER NOT NULL DEFAULT 0,
                preset_key TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE assets (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                brief_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                kind TEXT NOT NULL DEFAULT 'candidate',
                title TEXT NOT NULL,
                file_path TEXT,
                preview_url TEXT,
                favorite INTEGER NOT NULL DEFAULT 0,
                approval_status TEXT NOT NULL DEFAULT 'review',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE exports (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                preset TEXT NOT NULL,
                file_path TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )

    FrankCreateStore(db_path=db_path, root_dir=tmp_path / "user" / "frank_create")

    with sqlite3.connect(db_path) as conn:
        columns_by_table = {
            table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for table in ("projects", "briefs", "runs", "sessions", "turns", "assets", "exports")
        }

    for table, columns in columns_by_table.items():
        assert "sync_status" in columns, table
        assert "remote_id" in columns, table


def test_archived_sessions_are_hidden_by_default(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")

    active = store.create_session({"name": "Active"})
    archived = store.create_session({"name": "Archived"})
    store.update_session(archived["id"], {"status": "archived"})

    assert [session["id"] for session in store.list_sessions()] == [active["id"]]
    assert store.list_sessions(status="archived")[0]["id"] == archived["id"]


def test_reset_demo_state_clears_records_and_seeds_clean_session(tmp_path):
    store = FrankCreateStore(db_path=tmp_path / "frank_create.db")
    old_session = store.create_session({"name": "Old smoke session"})
    old_turn = store.create_turn(
        {
            "session_id": old_session["id"],
            "model": "frank-local-comfy",
            "provider": "local",
            "prompt": "Old smoke prompt",
        }
    )
    old_asset = store.create_asset(
        {
            "session_id": old_session["id"],
            "turn_id": old_turn["id"],
            "title": "Old smoke image",
            "file_path": "output/frank_create/old.png",
        }
    )
    store.create_export({"asset_id": old_asset["id"], "preset": "pdp", "file_path": "old.zip"})

    result = store.reset_demo_state()

    sessions = store.list_sessions()
    projects = store.list_projects()
    briefs = store.list_briefs(project_id=projects[0]["id"])
    turns = store.list_turns(session_id=sessions[0]["id"])

    assert result["session"]["name"] == "Frank Body Demo Studio"
    assert result["session"]["project_id"] == projects[0]["id"]
    assert projects[0]["name"] == "Frank Body Demo Campaign"
    assert briefs[0]["title"] == "Coffee Scrub Product Image Lab"
    assert briefs[0]["product_name"] == "Original Coffee Scrub"
    assert [session["name"] for session in sessions] == ["Frank Body Demo Studio"]
    assert store.list_assets() == []
    assert store.list_exports() == []
    assert len(turns) == 1
    assert turns[0]["model"] == "frank-local-comfy"
    assert turns[0]["status"] == "complete"
    assert "coffee scrub" in turns[0]["prompt"].lower()
