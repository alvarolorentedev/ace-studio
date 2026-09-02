from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable


def default_data_root() -> Path:
    if configured := os.environ.get("ACE_STUDIO_DATA_DIR"):
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ACE Studio"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ACE Studio"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ace-studio"


class Storage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_data_root()
        self.runtime_dir = self.root / "runtime"
        self.models_dir = self.root / "models"
        self.audio_dir = self.root / "library" / "audio"
        self.training_dir = self.root / "training"
        self.logs_dir = self.root / "logs"
        for directory in (self.runtime_dir, self.models_dir, self.audio_dir, self.training_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "library" / "ace_studio.db"
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS generations (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    prompt TEXT NOT NULL DEFAULT '',
                    lyrics TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    parent_id TEXT REFERENCES generations(id) ON DELETE SET NULL,
                    favorite INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS generations_created_at
                    ON generations(created_at DESC);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS adapters (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.commit()

    def save_generation(
        self,
        generation_id: str,
        title: str,
        task_type: str,
        audio_path: str,
        prompt: str,
        lyrics: str,
        metadata: dict[str, Any],
        parent_id: str | None = None,
    ) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO generations
                    (id, title, task_type, audio_path, prompt, lyrics, metadata_json, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (generation_id, title, task_type, audio_path, prompt, lyrics, json.dumps(metadata), parent_id),
            )
            connection.commit()

    def generations(self, limit: int = 100, search: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM generations"
        values: list[Any] = []
        if search:
            query += " WHERE title LIKE ? OR prompt LIKE ?"
            values.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY favorite DESC, created_at DESC LIMIT ?"
        values.append(limit)
        with closing(self.connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def toggle_favorite(self, generation_id: str) -> bool:
        with closing(self.connect()) as connection:
            connection.execute(
                "UPDATE generations SET favorite = CASE favorite WHEN 0 THEN 1 ELSE 0 END WHERE id = ?",
                (generation_id,),
            )
            value = connection.execute("SELECT favorite FROM generations WHERE id = ?", (generation_id,)).fetchone()
            connection.commit()
        return bool(value and value[0])

    def update_audio_path(self, generation_id: str, audio_path: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute("UPDATE generations SET audio_path = ? WHERE id = ?", (audio_path, generation_id))
            connection.commit()

    def update_title(self, generation_id: str, title: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute("UPDATE generations SET title = ? WHERE id = ?", (title, generation_id))
            connection.commit()

    def delete_generation(self, generation_id: str) -> bool:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT audio_path FROM generations WHERE id = ?", (generation_id,)).fetchone()
            if not row:
                return False
            connection.execute("DELETE FROM generations WHERE id = ?", (generation_id,))
            connection.commit()
        path = Path(row["audio_path"])
        try:
            path.resolve().relative_to(self.audio_dir.resolve())
        except ValueError:
            return True
        path.unlink(missing_ok=True)
        return True

    def record_job(self, job_id: str, state: str, request: dict[str, Any], error: str | None = None) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO jobs (id, state, request_json, error)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state = excluded.state,
                    error = excluded.error,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (job_id, state, json.dumps(request), error),
            )
            connection.commit()

    def add_adapter(self, adapter_id: str, name: str, path: str, kind: str, metadata: dict[str, Any]) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO adapters (id, name, path, kind, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (adapter_id, name, path, kind, json.dumps(metadata)),
            )
            connection.commit()

    def adapters(self) -> Iterable[sqlite3.Row]:
        with closing(self.connect()) as connection:
            return connection.execute("SELECT * FROM adapters ORDER BY created_at DESC").fetchall()
