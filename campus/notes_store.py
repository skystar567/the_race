"""Personal notes kept outside the course knowledge versions."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .knowledge import Knowledge


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _norm(text: str) -> str:
    return " ".join((text or "").split())


class NotesStore:
    def __init__(self, knowledge: Knowledge, data_dir: Path):
        self.knowledge = knowledge
        self.data_dir = Path(data_dir)
        with knowledge.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS note (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(id),
                    concept_id TEXT,
                    title TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    expansion INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS note_citation (
                    id TEXT PRIMARY KEY,
                    note_id TEXT NOT NULL REFERENCES note(id),
                    snippet_id TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    version_id TEXT,
                    UNIQUE(note_id, snippet_id, quote)
                );
                CREATE INDEX IF NOT EXISTS note_course ON note(course_id);
                CREATE INDEX IF NOT EXISTS note_citation_note ON note_citation(note_id);
            """)

    def _snapshot(self, course_id: str, version_id: str | None = None) -> dict[str, Any]:
        snapshot = self.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            raise LookupError("课程还没有已发布知识版本。")
        return snapshot

    def _validate_citations(self, snapshot: dict[str, Any], citations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        fragments = {fragment["id"]: fragment for fragment in snapshot["fragments"]}
        result = []
        for citation in citations:
            snippet_id = (citation.get("snippet_id") or "").strip()
            quote = (citation.get("quote") or "").strip()
            if not snippet_id or not quote:
                raise ValueError("笔记引用需要片段标识和原文。")
            fragment = fragments.get(snippet_id)
            if fragment is None:
                raise ValueError("笔记引用不属于当前知识版本的原文。")
            if _norm(quote) not in _norm(fragment["markdown"]):
                raise ValueError("笔记引用文字与原文不符。")
            result.append({"snippet_id": snippet_id, "quote": quote,
                           "version_id": snapshot["version_id"]})
        return result

    def _citations(self, db, note_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in db.execute(
            "SELECT id, snippet_id, quote, version_id FROM note_citation WHERE note_id=? ORDER BY rowid",
            (note_id,),
        )]

    def _get(self, db, note_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM note WHERE id=?", (note_id,)).fetchone()
        if row is None:
            return None
        return dict(row) | {"expansion": bool(row["expansion"]), "citations": self._citations(db, note_id)}

    def create(self, course_id: str, title: str, markdown: str, *,
               concept_id: str | None = None, expansion: bool = False,
               citations: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise ValueError("笔记标题不能为空。")
        if not (markdown or "").strip():
            raise ValueError("笔记正文不能为空。")
        snapshot = self._snapshot(course_id)
        valid = self._validate_citations(snapshot, citations)
        note_id = str(uuid4())
        now = _now()
        with self.knowledge.connect() as db:
            db.execute(
                "INSERT INTO note(id,course_id,concept_id,title,markdown,expansion,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (note_id, course_id, concept_id, title, markdown, 1 if expansion else 0, now, now),
            )
            for citation in valid:
                db.execute(
                    "INSERT INTO note_citation(id,note_id,snippet_id,quote,version_id) VALUES (?,?,?,?,?)",
                    (str(uuid4()), note_id, citation["snippet_id"], citation["quote"], citation["version_id"]),
                )
            note = self._get(db, note_id)
        return note

    def list(self, course_id: str) -> list[dict[str, Any]]:
        with self.knowledge.connect() as db:
            rows = db.execute(
                "SELECT id FROM note WHERE course_id=? ORDER BY updated_at DESC, id", (course_id,)
            ).fetchall()
            return [self._get(db, row["id"]) for row in rows]

    def get(self, note_id: str) -> dict[str, Any]:
        with self.knowledge.connect() as db:
            note = self._get(db, note_id)
        if note is None:
            raise LookupError("笔记不存在。")
        return note

    def update(self, note_id: str, *, title: str | None = None, markdown: str | None = None,
               expansion: bool | None = None, citations: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        note = self.get(note_id)
        title = note["title"] if title is None else title.strip()
        markdown = note["markdown"] if markdown is None else markdown
        expansion = note["expansion"] if expansion is None else bool(expansion)
        if not title:
            raise ValueError("笔记标题不能为空。")
        if not markdown.strip():
            raise ValueError("笔记正文不能为空。")
        valid = None
        if citations is not None:
            valid = self._validate_citations(self._snapshot(note["course_id"]), citations)
        with self.knowledge.connect() as db:
            db.execute(
                "UPDATE note SET title=?,markdown=?,expansion=?,updated_at=? WHERE id=?",
                (title, markdown, 1 if expansion else 0, _now(), note_id),
            )
            if valid is not None:
                db.execute("DELETE FROM note_citation WHERE note_id=?", (note_id,))
                for citation in valid:
                    db.execute(
                        "INSERT INTO note_citation(id,note_id,snippet_id,quote,version_id) VALUES (?,?,?,?,?)",
                        (str(uuid4()), note_id, citation["snippet_id"], citation["quote"], citation["version_id"]),
                    )
            return self._get(db, note_id)

    def health(self, note_id: str) -> dict[str, Any]:
        note = self.get(note_id)
        snapshot = self.knowledge.snapshot(note["course_id"])
        if snapshot is None:
            return {"note_id": note_id, "healthy": False, "reasons": ["课程还没有已发布知识版本。"]}
        fragments = {fragment["id"]: fragment for fragment in snapshot["fragments"]}
        reasons: list[str] = []
        for citation in note["citations"]:
            fragment = fragments.get(citation["snippet_id"])
            if fragment is None:
                reasons.append("引用的原文片段已不在当前版本。")
            elif _norm(citation["quote"]) not in _norm(fragment["markdown"]):
                reasons.append("引用的原文内容已变化。")
        return {"note_id": note_id, "healthy": not reasons,
                "reasons": sorted(set(reasons)), "current_version_id": snapshot["version_id"]}
