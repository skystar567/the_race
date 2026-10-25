"""Personal study notes, independent from the maintained course knowledge."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from .answers import Answers
from .expansions import EXPANSION_MARKER, Expansions
from .knowledge import Knowledge
from .knowledge_models import StrictModel
from .materials import Materials
from .model import DeepSeek, ModelError
from .reading import reference_context, render

NOTE_RULES = """根据给定来源生成一份可编辑的个人学习笔记。只使用来源中的内容，不添加资料外结论。
正文使用 Markdown；保留 [原文](snippet:片段ID) 引用，且只能使用给定 citation id。
若来源是模型拓展解释，必须保留“模型补充（超出课程资料）”标记，不把它写成教材事实，也不添加原文引用。
输出 JSON：title 与 body_md。"""

NOTE_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "body_md": {"type": "string"}},
    "required": ["title", "body_md"],
    "additionalProperties": False,
}


class NoteConflict(Exception):
    """The note changed elsewhere; the caller must reload instead of overwriting."""


class NoteInput(StrictModel):
    title: str
    body_md: str


class NoteUpdate(StrictModel):
    title: str
    body_md: str
    revision: int


class NoteGenerate(StrictModel):
    source_type: str
    source_id: str
    title: str | None = None
    version_id: str | None = None


def _snippet_ids(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"snippet:([A-Za-z0-9._:-]+)", text)))


def _chapter_title(snapshot: dict[str, Any], fragment: dict[str, Any]) -> str | None:
    containing = [
        chapter for chapter in snapshot["chapters"]
        if chapter["material_id"] == fragment["material_id"]
        and chapter["start_line"] <= fragment["start_line"] <= chapter["end_line"]
    ]
    return containing[-1]["title"] if containing else None


def _enrich(citations: list[dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    fragments = {fragment["id"]: fragment for fragment in snapshot["fragments"]}
    enriched = []
    for citation in citations:
        fragment = fragments.get(citation["snippet_id"])
        if fragment is None:
            continue
        enriched.append({
            "snippet_id": citation["snippet_id"],
            "quote": citation.get("quote", ""),
            "filename": fragment["filename"],
            "chapter_title": _chapter_title(snapshot, fragment),
            "start_line": fragment["start_line"],
            "end_line": fragment["end_line"],
            "excerpt": fragment["markdown"][:180],
        })
    return enriched


class Notes:
    """Own note rows. Knowledge updates never write or overwrite these rows."""

    def __init__(self, data_dir: Path, model: DeepSeek | None = None) -> None:
        self.materials = Materials(data_dir)
        self.knowledge = Knowledge(data_dir)
        self.answers = Answers(data_dir, model=model)
        self.expansions = Expansions(data_dir, model=model)
        self.model = model or DeepSeek.from_environment()
        with self.knowledge.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS note (
                    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
                    title TEXT NOT NULL, body_md TEXT NOT NULL,
                    version_id TEXT REFERENCES knowledge_version(id),
                    source_type TEXT NOT NULL, source_id TEXT,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    expansion INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                )
            """)

    def list_notes(self, course_id: str) -> list[dict[str, Any]]:
        self.materials.require_course(course_id)
        with self.knowledge.connect() as db:
            rows = db.execute(
                "SELECT * FROM note WHERE course_id=? ORDER BY updated_at DESC", (course_id,)
            ).fetchall()
        return [self._summary(row, course_id) for row in rows]

    def detail(self, course_id: str, note_id: str) -> dict[str, Any]:
        with self.knowledge.connect() as db:
            row = db.execute(
                "SELECT * FROM note WHERE id=? AND course_id=?", (note_id, course_id)
            ).fetchone()
        if row is None:
            raise LookupError("笔记不存在或不属于当前课程。")
        return self._detail(row, course_id)

    def source(self, course_id: str, note_id: str, snippet_id: str) -> dict[str, Any]:
        """Read the note's original evidence, including unorganized answer sources."""
        note = self.detail(course_id, note_id)
        if snippet_id not in {citation["snippet_id"] for citation in note["citations"]}:
            raise LookupError("原文片段不属于该笔记。")
        if note["source_type"] == "answer":
            return self.answers.source(course_id, note["source_id"], snippet_id) | {"note_id": note_id}
        snapshot = self.knowledge.snapshot(course_id, note["version_id"])
        fragment = next((item for item in snapshot["fragments"] if item["id"] == snippet_id), None)
        if fragment is None:
            raise LookupError("原文片段不属于该笔记的知识版本。")
        original = self.materials.raw(course_id, fragment["material_id"]).decode("utf-8-sig")
        return fragment | {
            "version_id": note["version_id"], "note_id": note_id,
            "chapter_title": _chapter_title(snapshot, fragment),
            "html": render(fragment["markdown"], reference_context(original)),
        }

    def create_manual(self, course_id: str, body: NoteInput) -> dict[str, Any]:
        self.materials.require_course(course_id)
        title, text = self._clean(body.title, body.body_md)
        if _snippet_ids(text):
            raise ValueError("手动笔记不能包含原文引用标记；请从知识点或回答生成笔记。")
        version_id = self.knowledge.current_id(course_id)
        return self._insert(course_id, title, text, version_id, "manual", None, [], False)

    async def generate(self, course_id: str, body: NoteGenerate) -> dict[str, Any]:
        self.materials.require_course(course_id)
        if body.source_type == "concept":
            snapshot = self.knowledge.snapshot(course_id, body.version_id)
            if snapshot is None:
                raise LookupError("课程尚未发布知识版本；请先完成整理。")
            concept = next((c for c in snapshot["concepts"] if c["id"] == body.source_id), None)
            if concept is None:
                raise ValueError("知识点不属于当前知识版本。")
            citations = _enrich(concept["citations"], snapshot)
            allowed = {citation["snippet_id"] for citation in citations}
            version_id = snapshot["version_id"]
            content = {
                "source": "concept",
                "concept": {"name": concept["name"], "aliases": concept["aliases"],
                            "definition": concept["definition"], "page_md": concept["page_md"]},
                "citations": citations,
            }
            default_title = f"{concept['name']} 学习笔记"
            expansion = False
        elif body.source_type == "answer":
            answer = self.answers.detail(course_id, body.source_id)
            if answer["status"] != "completed":
                raise ValueError("只有已完成的回答可以生成笔记。")
            citations = answer["citations"]
            allowed = {citation["snippet_id"] for citation in citations}
            version_id = answer["version_id"]
            content = {"source": "answer", "question": answer["question"],
                       "answer": answer["text"], "citations": citations}
            default_title = f"{answer['question'][:40]} · 笔记"
            expansion = False
        elif body.source_type == "expansion":
            expansion_row = self.expansions.detail(course_id, body.source_id)
            if expansion_row["status"] != "completed":
                raise ValueError("只有已完成的拓展解释可以生成笔记。")
            citations = []
            allowed = set()
            version_id = expansion_row["version_id"]
            content = {"source": "model_expansion", "text": expansion_row["text"],
                       "reminder": "保留“模型补充（超出课程资料）”标记，不添加原文引用。"}
            default_title = "拓展解释笔记"
            expansion = True
        else:
            raise ValueError("不支持的笔记来源。")
        if body.version_id is not None and body.version_id != version_id:
            raise ValueError("笔记必须沿用来源的知识版本。")

        try:
            result = await self.model.complete(
                NOTE_RULES, content, NOTE_SCHEMA, thinking=False
            )
        except ModelError:
            raise
        except (ValidationError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError("模型返回的笔记结构无效。") from exc
        title = result.get("title") if isinstance(result, dict) else None
        text = result.get("body_md") if isinstance(result, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ModelError("empty_output", "模型没有返回可用的笔记正文。")
        title, text = self._clean(
            body.title or (title if isinstance(title, str) and title.strip() else default_title),
            text,
        )
        if set(_snippet_ids(text)) - allowed:
            raise ValueError("生成的笔记引用了未提供的原文片段。")
        if expansion and not text.startswith(EXPANSION_MARKER):
            text = EXPANSION_MARKER + "\n\n" + text
        return self._insert(
            course_id, title, text, version_id, body.source_type, body.source_id,
            citations, expansion,
        )

    def update(self, course_id: str, note_id: str, body: NoteUpdate) -> dict[str, Any]:
        title, text = self._clean(body.title, body.body_md)
        with self.knowledge.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM note WHERE id=? AND course_id=?", (note_id, course_id)
            ).fetchone()
            if row is None:
                raise LookupError("笔记不存在或不属于当前课程。")
            if row["revision"] != body.revision:
                raise NoteConflict("笔记已在别处更新；请重新读取后再保存。")
            allowed = {citation["snippet_id"] for citation in json.loads(row["citations_json"])}
            if set(_snippet_ids(text)) - allowed:
                raise ValueError("笔记引用了未提供的原文片段。")
            if row["expansion"] and not text.startswith(EXPANSION_MARKER):
                text = EXPANSION_MARKER + "\n\n" + text
            db.execute(
                """UPDATE note SET title=?,body_md=?,revision=revision+1,updated_at=?
                WHERE id=?""",
                (title, text, time.time(), note_id),
            )
        return self.detail(course_id, note_id)

    def _insert(
        self, course_id: str, title: str, text: str, version_id: str | None,
        source_type: str, source_id: str | None, citations: list[dict[str, Any]],
        expansion: bool,
    ) -> dict[str, Any]:
        note_id = str(uuid4())
        now = time.time()
        with self.knowledge.connect() as db:
            db.execute(
                """INSERT INTO note
                (id,course_id,title,body_md,version_id,source_type,source_id,
                 citations_json,expansion,revision,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,1,?,?)""",
                (note_id, course_id, title, text, version_id, source_type, source_id,
                 json.dumps(citations, ensure_ascii=False), int(expansion), now, now),
            )
        return self.detail(course_id, note_id)

    def _clean(self, title: str, text: str) -> tuple[str, str]:
        title = title.strip()
        text = text.strip()
        if not title:
            raise ValueError("笔记标题不能为空。")
        if len(title) > 200:
            raise ValueError("笔记标题不能超过 200 字符。")
        if not text:
            raise ValueError("笔记正文不能为空。")
        return title, text

    def _detail(self, row, course_id: str) -> dict[str, Any]:
        citations = [citation | {
            "source_url": f"/api/courses/{course_id}/notes/{row['id']}/sources/{citation['snippet_id']}",
            "version_id": row["version_id"],
        } for citation in json.loads(row["citations_json"])]
        needs_review, reason = self._review(course_id, row, citations)
        return {
            "id": row["id"], "course_id": row["course_id"], "title": row["title"],
            "body_md": row["body_md"], "html": render(row["body_md"]),
            "version_id": row["version_id"], "source_type": row["source_type"],
            "source_id": row["source_id"], "citations": citations,
            "citation_count": len(citations),
            "expansion": bool(row["expansion"]), "revision": row["revision"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "needs_review": needs_review, "review_reason": reason,
        }

    def _summary(self, row, course_id: str) -> dict[str, Any]:
        citations = json.loads(row["citations_json"])
        needs_review, reason = self._review(course_id, row, citations)
        return {
            "id": row["id"], "title": row["title"], "version_id": row["version_id"],
            "source_type": row["source_type"], "source_id": row["source_id"],
            "expansion": bool(row["expansion"]), "revision": row["revision"],
            "citation_count": len(citations),
            "needs_review": needs_review, "review_reason": reason,
            "updated_at": row["updated_at"],
        }

    def _review(
        self, course_id: str, row, citations: list[dict[str, Any]]
    ) -> tuple[bool, str | None]:
        """Only prompt when a cited basis actually changed, not on every new version."""
        version_id = row["version_id"]
        if version_id is None or row["source_type"] == "manual":
            return False, None
        current = self.knowledge.snapshot(course_id)
        if current is None or current["version_id"] == version_id:
            return False, None
        previous = self.knowledge.snapshot(course_id, version_id)
        related = set()
        evidence_citations = citations if row["source_type"] == "answer" else []
        if row["source_type"] == "concept":
            related.add(row["source_id"])
        elif row["source_type"] == "expansion":
            expansion = self.expansions.detail(course_id, row["source_id"])
            if expansion["concept_id"]:
                related.add(expansion["concept_id"])
            if expansion["answer_id"]:
                evidence_citations = self.answers.detail(course_id, expansion["answer_id"])["citations"]
        snippet_ids = {citation["snippet_id"] for citation in evidence_citations}
        for snapshot in (previous, current):
            related.update(concept["id"] for concept in snapshot["concepts"]
                           if any(c["snippet_id"] in snippet_ids for c in concept["citations"]))

        def basis(snapshot):
            result = {}
            for concept in snapshot["concepts"]:
                if concept["id"] not in related:
                    continue
                fields = {field: concept.get(field) for field in ("name", "definition", "page_md", "status")}
                for field in ("aliases", "citations", "conflicts"):
                    fields[field] = sorted(concept.get(field, []), key=lambda item: json.dumps(item, sort_keys=True))
                result[concept["id"]] = fields
            return result

        before, after = basis(previous), basis(current)
        changed = sum(before.get(concept_id) != after.get(concept_id) for concept_id in related)
        if changed:
            return True, f"{changed} 条引用依据已变化，请检查笔记；正文不会被自动改写。"
        return False, None
