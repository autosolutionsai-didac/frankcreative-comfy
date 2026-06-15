import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def _user_root():
    try:
        import folder_paths

        return Path(folder_paths.get_user_directory()) / "frank_create"
    except Exception:
        return Path.cwd() / "user" / "frank_create"


class FrankCreateStore:
    def __init__(self, db_path=None, root_dir=None):
        self.root_dir = Path(root_dir) if root_dir else _user_root()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else self.root_dir / "frank_create.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    def initialize(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    client TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS briefs (
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
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    brief_id TEXT NOT NULL,
                    workflow_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_id TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    notes TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(brief_id) REFERENCES briefs(id)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'image',
                    status TEXT NOT NULL DEFAULT 'active',
                    summary TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS turns (
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
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    brief_id TEXT,
                    session_id TEXT,
                    turn_id TEXT,
                    kind TEXT NOT NULL DEFAULT 'candidate',
                    title TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'image',
                    provider TEXT,
                    model TEXT,
                    prompt TEXT,
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    source_asset_id TEXT,
                    reference_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                    file_path TEXT,
                    preview_url TEXT,
                    width INTEGER,
                    height INTEGER,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    approval_status TEXT NOT NULL DEFAULT 'review',
                    notes TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exports (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    preset TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    sync_status TEXT NOT NULL DEFAULT 'local',
                    remote_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(asset_id) REFERENCES assets(id)
                );
                """
            )
            self._ensure_columns(
                conn,
                "projects",
                {
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )
            self._ensure_columns(
                conn,
                "briefs",
                {
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )
            self._ensure_columns(
                conn,
                "runs",
                {
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )
            self._ensure_columns(
                conn,
                "sessions",
                {
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )
            self._ensure_columns(
                conn,
                "turns",
                {
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )
            self._ensure_columns(
                conn,
                "assets",
                {
                    "session_id": "session_id TEXT",
                    "turn_id": "turn_id TEXT",
                    "media_type": "media_type TEXT NOT NULL DEFAULT 'image'",
                    "provider": "provider TEXT",
                    "model": "model TEXT",
                    "prompt": "prompt TEXT",
                    "settings_json": "settings_json TEXT NOT NULL DEFAULT '{}'",
                    "source_asset_id": "source_asset_id TEXT",
                    "reference_asset_ids_json": "reference_asset_ids_json TEXT NOT NULL DEFAULT '[]'",
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )
            self._ensure_columns(
                conn,
                "exports",
                {
                    "sync_status": "sync_status TEXT NOT NULL DEFAULT 'local'",
                    "remote_id": "remote_id TEXT",
                },
            )

    def create_project(self, payload):
        now = _utc_now()
        record = {
            "id": payload.get("id") or _new_id("project"),
            "name": _required(payload, "name"),
            "client": payload.get("client", "Frank Body"),
            "status": payload.get("status", "active"),
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
            "updated_at": now,
        }
        return self._insert("projects", record)

    def list_projects(self, status=None):
        if status:
            return self._select("SELECT * FROM projects WHERE status = ? ORDER BY updated_at DESC", (status,))
        return self._select("SELECT * FROM projects ORDER BY updated_at DESC")

    def update_project(self, project_id, payload):
        return self._update("projects", project_id, payload, {"name", "client", "status", "sync_status", "remote_id"})

    def create_brief(self, payload):
        now = _utc_now()
        record = {
            "id": payload.get("id") or _new_id("brief"),
            "project_id": _required(payload, "project_id"),
            "title": _required(payload, "title"),
            "product_name": payload.get("product_name"),
            "task_type": _required(payload, "task_type"),
            "channel": payload.get("channel"),
            "tone": payload.get("tone"),
            "prompt": payload.get("prompt"),
            "negative_prompt": payload.get("negative_prompt"),
            "reference_image_path": payload.get("reference_image_path"),
            "status": payload.get("status", "draft"),
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
            "updated_at": now,
        }
        return self._insert("briefs", record)

    def list_briefs(self, project_id=None):
        if project_id:
            return self._select("SELECT * FROM briefs WHERE project_id = ? ORDER BY updated_at DESC", (project_id,))
        return self._select("SELECT * FROM briefs ORDER BY updated_at DESC")

    def update_brief(self, brief_id, payload):
        return self._update(
            "briefs",
            brief_id,
            payload,
            {
                "title",
                "product_name",
                "task_type",
                "channel",
                "tone",
                "prompt",
                "negative_prompt",
                "reference_image_path",
                "status",
                "sync_status",
                "remote_id",
            },
        )

    def create_run(self, payload):
        now = _utc_now()
        record = {
            "id": payload.get("id") or _new_id("run"),
            "brief_id": _required(payload, "brief_id"),
            "workflow_key": payload.get("workflow_key", "local-product-shot"),
            "provider": payload.get("provider", "local"),
            "prompt_id": payload.get("prompt_id"),
            "status": payload.get("status", "queued"),
            "notes": payload.get("notes"),
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
            "updated_at": now,
        }
        return self._insert("runs", record)

    def list_runs(self, brief_id=None):
        if brief_id:
            return self._select("SELECT * FROM runs WHERE brief_id = ? ORDER BY created_at DESC", (brief_id,))
        return self._select("SELECT * FROM runs ORDER BY created_at DESC")

    def update_run(self, run_id, payload):
        return self._update(
            "runs",
            run_id,
            payload,
            {"workflow_key", "provider", "prompt_id", "status", "notes", "sync_status", "remote_id"},
        )

    def create_session(self, payload):
        now = _utc_now()
        record = {
            "id": payload.get("id") or _new_id("session"),
            "project_id": payload.get("project_id"),
            "name": payload.get("name") or "Untitled image session",
            "mode": payload.get("mode", "image"),
            "status": payload.get("status", "active"),
            "summary": payload.get("summary"),
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
            "updated_at": now,
        }
        return self._insert("sessions", record)

    def list_sessions(self, status=None, project_id=None):
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        else:
            clauses.append("status != ?")
            params.append("archived")
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._select(f"SELECT * FROM sessions {where} ORDER BY updated_at DESC", tuple(params))

    def update_session(self, session_id, payload):
        return self._update(
            "sessions",
            session_id,
            payload,
            {"project_id", "name", "mode", "status", "summary", "sync_status", "remote_id"},
        )

    def create_turn(self, payload):
        now = _utc_now()
        record = {
            "id": payload.get("id") or _new_id("turn"),
            "session_id": _required(payload, "session_id"),
            "kind": payload.get("kind", "generate"),
            "provider": payload.get("provider"),
            "model": _required(payload, "model"),
            "prompt": payload.get("prompt", ""),
            "settings_json": _json_dumps(payload.get("settings", payload.get("settings_json", {}))),
            "source_asset_id": payload.get("source_asset_id") or payload.get("edit_source_asset_id"),
            "reference_asset_ids_json": _json_dumps(
                payload.get("reference_asset_ids", payload.get("reference_asset_ids_json", []))
            ),
            "output_asset_ids_json": _json_dumps(payload.get("output_asset_ids", payload.get("output_asset_ids_json", []))),
            "frank_body_mode": _to_int(payload.get("frank_body_mode", False)),
            "preset_key": payload.get("preset_key"),
            "status": payload.get("status", "queued"),
            "error_json": _json_dumps(payload.get("error")) if payload.get("error") is not None else None,
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
            "updated_at": now,
        }
        return self._insert("turns", record)

    def list_turns(self, session_id=None, status=None):
        clauses = []
        params = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._select(f"SELECT * FROM turns {where} ORDER BY created_at ASC", tuple(params))

    def update_turn(self, turn_id, payload):
        normalized = dict(payload)
        _normalize_json_update(normalized, "settings", "settings_json")
        _normalize_json_update(normalized, "reference_asset_ids", "reference_asset_ids_json")
        _normalize_json_update(normalized, "output_asset_ids", "output_asset_ids_json")
        _normalize_json_update(normalized, "error", "error_json")
        if "frank_body_mode" in normalized:
            normalized["frank_body_mode"] = _to_int(normalized["frank_body_mode"])

        return self._update(
            "turns",
            turn_id,
            normalized,
            {
                "kind",
                "provider",
                "model",
                "prompt",
                "settings_json",
                "source_asset_id",
                "reference_asset_ids_json",
                "output_asset_ids_json",
                "frank_body_mode",
                "preset_key",
                "status",
                "error_json",
                "sync_status",
                "remote_id",
            },
        )

    def create_asset(self, payload):
        now = _utc_now()
        record = {
            "id": payload.get("id") or _new_id("asset"),
            "run_id": payload.get("run_id"),
            "brief_id": self._ensure_brief_for_asset(payload),
            "session_id": payload.get("session_id"),
            "turn_id": payload.get("turn_id"),
            "kind": payload.get("kind", "candidate"),
            "title": _required(payload, "title"),
            "media_type": payload.get("media_type", "image"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "prompt": payload.get("prompt"),
            "settings_json": _json_dumps(payload.get("settings", payload.get("settings_json", {}))),
            "source_asset_id": payload.get("source_asset_id"),
            "reference_asset_ids_json": _json_dumps(
                payload.get("reference_asset_ids", payload.get("reference_asset_ids_json", []))
            ),
            "file_path": payload.get("file_path"),
            "preview_url": payload.get("preview_url"),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "favorite": _to_int(payload.get("favorite", False)),
            "approval_status": payload.get("approval_status", "review"),
            "notes": payload.get("notes"),
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
            "updated_at": now,
        }
        return self._insert("assets", record)

    def list_assets(self, run_id=None, brief_id=None, session_id=None, turn_id=None, approval_status=None):
        clauses = []
        params = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if brief_id:
            clauses.append("brief_id = ?")
            params.append(brief_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if turn_id:
            clauses.append("turn_id = ?")
            params.append(turn_id)
        if approval_status:
            clauses.append("approval_status = ?")
            params.append(approval_status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._select(f"SELECT * FROM assets {where} ORDER BY updated_at DESC", tuple(params))

    def update_asset(self, asset_id, payload):
        normalized = dict(payload)
        if "favorite" in normalized:
            normalized["favorite"] = _to_int(normalized["favorite"])
        _normalize_json_update(normalized, "settings", "settings_json")
        _normalize_json_update(normalized, "reference_asset_ids", "reference_asset_ids_json")
        return self._update(
            "assets",
            asset_id,
            normalized,
            {
                "kind",
                "title",
                "session_id",
                "turn_id",
                "media_type",
                "provider",
                "model",
                "prompt",
                "settings_json",
                "source_asset_id",
                "reference_asset_ids_json",
                "file_path",
                "preview_url",
                "width",
                "height",
                "favorite",
                "approval_status",
                "notes",
                "sync_status",
                "remote_id",
            },
        )

    def delete_asset(self, asset_id):
        with self._lock, self._connect() as conn:
            asset = self._get(conn, "assets", asset_id)
            conn.execute("DELETE FROM exports WHERE asset_id = ?", (asset_id,))
            conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            return asset

    def create_export(self, payload):
        now = _utc_now()
        metadata = payload.get("metadata", payload.get("metadata_json", {}))
        record = {
            "id": payload.get("id") or _new_id("export"),
            "asset_id": _required(payload, "asset_id"),
            "preset": _required(payload, "preset"),
            "file_path": _required(payload, "file_path"),
            "metadata_json": metadata if isinstance(metadata, str) else json.dumps(metadata, sort_keys=True),
            "sync_status": payload.get("sync_status", "local"),
            "remote_id": payload.get("remote_id"),
            "created_at": now,
        }
        return self._insert("exports", record)

    def list_exports(self, asset_id=None):
        if asset_id:
            return self._select("SELECT * FROM exports WHERE asset_id = ? ORDER BY created_at DESC", (asset_id,))
        return self._select("SELECT * FROM exports ORDER BY created_at DESC")

    def reset_demo_state(self):
        with self._lock, self._connect() as conn:
            for table in ("exports", "assets", "turns", "runs", "briefs", "projects", "sessions"):
                conn.execute(f"DELETE FROM {table}")

        project = self.create_project(
            {
                "name": "Frank Body Demo Campaign",
                "client": "Frank Body",
                "status": "active",
            }
        )
        brief = self.create_brief(
            {
                "project_id": project["id"],
                "title": "Coffee Scrub Product Image Lab",
                "product_name": "Original Coffee Scrub",
                "task_type": "product-shot-lab",
                "channel": "PDP / paid social",
                "tone": "cheeky-director-ready",
                "prompt": "Place this Frank Body coffee scrub as a clean ecommerce product shot on a soft pink counter.",
                "negative_prompt": "Avoid warped labels, extra lids, generic spa styling, and unreadable packaging.",
                "status": "draft",
            }
        )
        session = self.create_session(
            {
                "name": "Frank Body Demo Studio",
                "project_id": project["id"],
                "mode": "image",
                "summary": brief["title"],
                "sync_status": "local",
            }
        )
        turn = self.create_turn(
            {
                "session_id": session["id"],
                "kind": "generate",
                "provider": "local",
                "model": "frank-local-comfy",
                "prompt": brief["prompt"],
                "settings": {"aspect_ratio": "1:1", "image_size": "2K", "count": 4},
                "reference_asset_ids": [],
                "frank_body_mode": False,
                "preset_key": "product-shot-lab",
                "status": "complete",
            }
        )
        return {"project": project, "brief": brief, "session": session, "turn": turn}

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _insert(self, table, record):
        with self._lock, self._connect() as conn:
            columns = tuple(record.keys())
            placeholders = ", ".join("?" for _ in columns)
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            conn.execute(sql, tuple(record[column] for column in columns))
            return self._get(conn, table, record["id"])

    def _select(self, sql, params=()):
        with self._lock, self._connect() as conn:
            return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]

    def _update(self, table, record_id, payload, allowed_fields):
        changes = {key: value for key, value in payload.items() if key in allowed_fields}
        if not changes:
            with self._lock, self._connect() as conn:
                return self._get(conn, table, record_id)

        changes["updated_at"] = _utc_now()
        assignments = ", ".join(f"{key} = ?" for key in changes)
        params = tuple(changes.values()) + (record_id,)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", params)
            if conn.total_changes == 0:
                raise LookupError(f"{table[:-1]} {record_id} was not found")
            return self._get(conn, table, record_id)

    def _get(self, conn, table, record_id):
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise LookupError(f"{table[:-1]} {record_id} was not found")
        return _row_to_dict(row)

    def _ensure_brief_for_asset(self, payload):
        brief_id = payload.get("brief_id")
        if not brief_id:
            brief_id = _new_id("brief")

        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT id FROM briefs WHERE id = ?", (brief_id,)).fetchone()
            if existing:
                return brief_id

            project_id = self._ensure_system_project(conn)
            now = _utc_now()
            conn.execute(
                """
                INSERT OR IGNORE INTO briefs (
                    id, project_id, title, product_name, task_type, channel, tone, prompt,
                    negative_prompt, reference_image_path, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    brief_id,
                    project_id,
                    payload.get("title", "Studio asset"),
                    payload.get("model"),
                    "conversational-studio",
                    None,
                    None,
                    payload.get("prompt"),
                    None,
                    payload.get("file_path"),
                    "asset",
                    now,
                    now,
                ),
            )
            return brief_id

    def _ensure_system_project(self, conn):
        project_id = "project_frank_create_system"
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row:
            return project_id

        now = _utc_now()
        conn.execute(
            """
            INSERT INTO projects (id, name, client, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, "Frank Create Studio", "Frank Body", "active", now, now),
        )
        return project_id

    def _ensure_columns(self, conn, table, columns):
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _required(payload, key):
    value = payload.get(key)
    if value is None or value == "":
        raise ValueError(f"{key} is required")
    return value


def _json_dumps(value):
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _normalize_json_update(payload, source_key, target_key):
    if source_key in payload:
        payload[target_key] = _json_dumps(payload.pop(source_key))
    elif target_key in payload:
        payload[target_key] = _json_dumps(payload[target_key])


def _to_int(value):
    return 1 if value is True or value == 1 or value == "1" or value == "true" else 0


def _row_to_dict(row):
    data = dict(row)
    if "favorite" in data:
        data["favorite"] = bool(data["favorite"])
    if "frank_body_mode" in data:
        data["frank_body_mode"] = bool(data["frank_body_mode"])
    return data
