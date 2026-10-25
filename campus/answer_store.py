"""Small durable log of grounded answers for later re-checking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .knowledge import Knowledge


class AnswerStore:
    def __init__(self, knowledge: Knowledge, data_dir: Path):
        self.knowledge = knowledge
        self.data_dir = Path(data_dir)
        with knowledge.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS answer (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(id),
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS answer_course ON answer(course_id);
            """)

    def save(self, course_id: str, question: str, result: dict[str, Any]) -> str:
        answer_id = str(uuid4())
        with self.knowledge.connect() as db:
            db.execute(
                "INSERT INTO answer(id,course_id,question,answer,status,version_id,citations_json)"
                " VALUES (?,?,?,?,?,?,?)",
                (answer_id, course_id, question, result.get("answer", ""),
                 result.get("status", "unknown"), result.get("version_id", ""),
                 json.dumps(result.get("citations", []), ensure_ascii=False)),
            )
        return answer_id

    def list(self, course_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.knowledge.connect() as db:
            rows = db.execute(
                "SELECT * FROM answer WHERE course_id=? ORDER BY created_at DESC LIMIT ?",
                (course_id, limit),
            ).fetchall()
        return [dict(row) | {"citations": json.loads(row["citations_json"])} for row in rows]

    def get(self, answer_id: str) -> dict[str, Any]:
        with self.knowledge.connect() as db:
            row = db.execute("SELECT * FROM answer WHERE id=?", (answer_id,)).fetchone()
        if row is None:
            raise LookupError("回答不存在。")
        return dict(row) | {"citations": json.loads(row["citations_json"])}
