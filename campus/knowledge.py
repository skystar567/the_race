"""Versioned knowledge store. Publishing is a checked, idempotent pointer switch."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from .knowledge_validation import validate_snapshot


class Knowledge:
    """Own knowledge tables without modifying imported materials or personal notes."""

    def __init__(self, data_dir: Path) -> None:
        self.database = data_dir / "courses.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_version (
                    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
                    task_id TEXT NOT NULL UNIQUE, parent_version_id TEXT,
                    state TEXT NOT NULL CHECK(state IN ('candidate','published','failed')),
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS course_knowledge (
                    course_id TEXT PRIMARY KEY REFERENCES courses(id),
                    current_version_id TEXT NOT NULL REFERENCES knowledge_version(id)
                );
                CREATE TABLE IF NOT EXISTS concept (
                    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id)
                );
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Use short WAL transactions shared with independent local processes."""
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def current_id(self, course_id: str) -> str | None:
        """Return the current published pointer, or None before first publication."""
        with self.connect() as db:
            row = db.execute(
                "SELECT current_version_id FROM course_knowledge WHERE course_id=?", (course_id,)
            ).fetchone()
        return row[0] if row else None

    def snapshot(self, course_id: str, version_id: str | None = None) -> dict[str, Any] | None:
        """Read one immutable published snapshot; candidates are never public."""
        version_id = version_id or self.current_id(course_id)
        if version_id is None:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM knowledge_version WHERE course_id=? AND id=? AND state='published'",
                (course_id, version_id),
            ).fetchone()
        if row is None:
            raise LookupError("已发布知识版本不存在或不属于当前课程。")
        snapshot = json.loads(row["snapshot_json"])
        return snapshot | {"version_id": row["id"], "course_id": course_id, "state": row["state"],
                           "parent_version_id": row["parent_version_id"]}

    def versions(self, course_id: str) -> list[dict[str, Any]]:
        """List version identities and states without exposing snapshots."""
        current = self.current_id(course_id)
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, task_id, state, parent_version_id, created_at
                FROM knowledge_version WHERE course_id=? ORDER BY created_at DESC, id""",
                (course_id,),
            ).fetchall()
        return [dict(row) | {"is_current": row["id"] == current} for row in rows]

    def publish_task(
        self,
        course_id: str,
        task_id: str,
        snapshot: dict[str, Any],
        guard: Callable[[sqlite3.Connection], None] | None = None,
        *, parent_version_id: str | None = None,
    ) -> str:
        """Validate and publish in one transaction; repeating the same task is safe.

        ``guard`` runs inside the write transaction so a worker that lost its lease
        cannot switch the published pointer afterwards.
        """
        validate_snapshot(snapshot)
        payload = json.dumps(snapshot, ensure_ascii=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if guard is not None:
                guard(db)
            row = db.execute(
                "SELECT id, state FROM knowledge_version WHERE task_id=? AND course_id=?",
                (task_id, course_id),
            ).fetchone()
            if row is not None and row["state"] == "published":
                return str(row["id"])
            current = db.execute(
                "SELECT current_version_id FROM course_knowledge WHERE course_id=?", (course_id,)
            ).fetchone()
            if (current[0] if current else None) != parent_version_id:
                raise ValueError("课程知识版本已变化，本次候选不能覆盖新版本；请重新发起整理。")
            if row is None:
                version_id = str(uuid4())
                db.execute(
                    """INSERT INTO knowledge_version
                    (id,course_id,task_id,parent_version_id,state,snapshot_json)
                    VALUES (?,?,?,?,'candidate',?)""",
                    (version_id, course_id, task_id, parent_version_id, payload),
                )
            else:
                version_id = str(row["id"])
                db.execute(
                    "UPDATE knowledge_version SET snapshot_json=? WHERE id=? AND state='candidate'",
                    (payload, version_id),
                )
            for concept in snapshot["concepts"]:
                owner = db.execute("SELECT course_id FROM concept WHERE id=?", (concept["id"],)).fetchone()
                if owner and owner[0] != course_id:
                    raise ValueError("知识点标识不属于当前课程。")
                db.execute(
                    "INSERT OR IGNORE INTO concept(id,course_id) VALUES (?,?)",
                    (concept["id"], course_id),
                )
            db.execute("UPDATE knowledge_version SET state='published' WHERE id=?", (version_id,))
            db.execute(
                """INSERT INTO course_knowledge(course_id,current_version_id) VALUES (?,?)
                ON CONFLICT(course_id) DO UPDATE SET current_version_id=excluded.current_version_id""",
                (course_id, version_id),
            )
        return version_id
