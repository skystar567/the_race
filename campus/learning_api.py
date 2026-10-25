"""Learning HTTP surface: grounded Q&A, notes, routes, feedback and export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .answer_store import AnswerStore
from .answers import Answers
from .exports import Exporter
from .jobs import Jobs
from .knowledge import Knowledge
from .knowledge_models import ScopeInput
from .materials import Materials
from .model import DeepSeek, ModelError
from .notes_store import NotesStore
from .routes import RouteService


class AskInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    version_id: str | None = None
    material_ids: list[str] = []
    chapter_ids: list[str] = []
    concept_id: str | None = None
    expansion: bool = False


class CitationInput(BaseModel):
    snippet_id: str
    quote: str


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1)
    concept_id: str | None = None
    expansion: bool = False
    citations: list[CitationInput] = []


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    markdown: str | None = None
    expansion: bool | None = None
    citations: list[CitationInput] | None = None


class FeedbackInput(BaseModel):
    target_type: Literal["concept", "relation", "page"]
    target_id: str
    body: str = Field(min_length=1, max_length=4000)


def learning_router(data_dir: Path, model: Any | None = None) -> APIRouter:
    router = APIRouter()
    materials = Materials(data_dir)
    knowledge = Knowledge(data_dir)
    notes = NotesStore(knowledge, data_dir)
    model = model or DeepSeek.from_environment()
    answers = Answers(materials, knowledge, model)
    answer_store = AnswerStore(knowledge, data_dir)
    routes = RouteService(knowledge)
    exporter = Exporter(materials, knowledge, notes)
    jobs = Jobs(data_dir, model=model)
    with knowledge.connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL REFERENCES courses(id),
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                resolution TEXT NOT NULL DEFAULT 'open',
                task_id TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        """)
        try:
            db.execute("ALTER TABLE feedback ADD COLUMN task_id TEXT")
        except Exception:
            pass

    def configured() -> bool:
        return bool(getattr(model, "api_key", ""))

    @router.get("/api/courses/{course_id}/route")
    async def route(course_id: str, target: str, current: str | None = None,
                    version_id: str | None = None) -> dict[str, Any]:
        try:
            return routes.plan(course_id, target, current, version_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/api/courses/{course_id}/ask")
    async def ask(course_id: str, body: AskInput) -> dict[str, Any]:
        if not configured():
            raise HTTPException(503, "后端尚未配置 DEEPSEEK_API_KEY，无法问答。")
        try:
            result = await answers.ask(course_id, body.question, version_id=body.version_id,
                                       material_ids=body.material_ids, chapter_ids=body.chapter_ids,
                                       concept_id=body.concept_id, expansion=body.expansion)
            result["id"] = answer_store.save(course_id, body.question, result)
            return result
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ModelError as exc:
            raise HTTPException(502 if exc.retryable else 503, str(exc)) from exc

    @router.post("/api/courses/{course_id}/ask/stream")
    async def ask_stream(course_id: str, body: AskInput):
        if not configured():
            raise HTTPException(503, "后端尚未配置 DEEPSEEK_API_KEY，无法问答。")
        events = answers.stream(course_id, body.question, version_id=body.version_id,
                                material_ids=body.material_ids, chapter_ids=body.chapter_ids,
                                concept_id=body.concept_id, expansion=body.expansion)

        async def generate():
            async for event in events:
                if event.get("type") == "done":
                    event["id"] = answer_store.save(course_id, body.question, event)
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @router.get("/api/courses/{course_id}/answers")
    async def list_answers(course_id: str) -> list[dict[str, Any]]:
        materials.require_course(course_id)
        return answer_store.list(course_id)

    @router.get("/api/courses/{course_id}/notes")
    async def list_notes(course_id: str) -> list[dict[str, Any]]:
        materials.require_course(course_id)
        return notes.list(course_id)

    @router.post("/api/courses/{course_id}/notes", status_code=201)
    async def create_note(course_id: str, body: NoteInput) -> dict[str, Any]:
        try:
            return notes.create(course_id, body.title, body.markdown, concept_id=body.concept_id,
                                expansion=body.expansion,
                                citations=[item.model_dump() for item in body.citations])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/notes/{note_id}")
    async def get_note(note_id: str) -> dict[str, Any]:
        try:
            return notes.get(note_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.patch("/api/notes/{note_id}")
    async def update_note(note_id: str, body: NoteUpdate) -> dict[str, Any]:
        try:
            citations = None if body.citations is None else [item.model_dump() for item in body.citations]
            return notes.update(note_id, title=body.title, markdown=body.markdown,
                                expansion=body.expansion, citations=citations)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/notes/{note_id}/health")
    async def note_health(note_id: str) -> dict[str, Any]:
        try:
            return notes.health(note_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/api/courses/{course_id}/export")
    async def export_course(course_id: str, version_id: str | None = None):
        try:
            archive, manifest = exporter.export(course_id, version_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        filename = f"{manifest['course']['name']}-{manifest['knowledge_version'][:8]}.zip"
        return Response(archive, media_type="application/zip",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})

    @router.post("/api/courses/{course_id}/feedback", status_code=201)
    async def create_feedback(course_id: str, body: FeedbackInput) -> dict[str, Any]:
        materials.require_course(course_id)
        snapshot = knowledge.snapshot(course_id)
        if snapshot is None:
            raise HTTPException(404, "课程还没有已发布知识版本。")
        if body.target_type == "concept" and not any(item["id"] == body.target_id for item in snapshot["concepts"]):
            raise HTTPException(404, "知识点不属于当前版本。")
        if body.target_type == "relation" and not any(item["id"] == body.target_id for item in snapshot["relations"]):
            raise HTTPException(404, "关系不属于当前版本。")
        from uuid import uuid4
        feedback_id = str(uuid4())
        with knowledge.connect() as db:
            db.execute(
                "INSERT INTO feedback(id,course_id,target_type,target_id,body,status,resolution)"
                " VALUES (?,?,?,?,?,'open','open')",
                (feedback_id, course_id, body.target_type, body.target_id, body.body),
            )
            row = db.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        return dict(row)

    @router.get("/api/feedback/{feedback_id}")
    async def get_feedback(feedback_id: str) -> dict[str, Any]:
        with knowledge.connect() as db:
            row = db.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "反馈不存在。")
        return dict(row)

    @router.post("/api/feedback/{feedback_id}/recheck")
    async def recheck_feedback(feedback_id: str) -> dict[str, Any]:
        with knowledge.connect() as db:
            feedback = db.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        if feedback is None:
            raise HTTPException(404, "反馈不存在。")
        if feedback["task_id"]:
            task = jobs.get(feedback["course_id"], feedback["task_id"])
            if task["status"] in ("queued", "running"):
                return {"feedback": dict(feedback), "task": task}
        snapshot = knowledge.snapshot(feedback["course_id"])
        if snapshot is None:
            raise HTTPException(404, "课程还没有已发布知识版本。")
        target = None
        if feedback["target_type"] == "concept":
            target = next((item for item in snapshot["concepts"] if item["id"] == feedback["target_id"]), None)
        elif feedback["target_type"] == "relation":
            relation = next((item for item in snapshot["relations"] if item["id"] == feedback["target_id"]), None)
            if relation:
                concept_id = relation["from_id"] if relation["from_type"] == "concept" else relation["to_id"]
                target = next((item for item in snapshot["concepts"]
                               if item["id"] == concept_id), None)
        if target is None:
            raise HTTPException(404, "反馈目标不属于当前版本。")
        citations = target.get("citations") or []
        if not citations:
            raise HTTPException(422, "该知识点没有可重新核对的原文引用。")
        fragment = next((item for item in snapshot["fragments"]
                         if item["id"] == citations[0]["snippet_id"]), None)
        if fragment is None:
            raise HTTPException(422, "反馈目标的原文片段已不在当前版本。")
        chapter = next((item for item in snapshot["chapters"]
                        if item["material_id"] == fragment["material_id"]
                        and item["start_line"] <= fragment["start_line"]
                        <= item["end_line"]), None)
        selection = ScopeInput(chapter_ids=[chapter["id"]]) if chapter else ScopeInput(material_ids=[fragment["material_id"]])
        try:
            task = jobs.create(feedback["course_id"], selection)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        with knowledge.connect() as db:
            db.execute("UPDATE feedback SET status='checking',resolution='checking',task_id=? WHERE id=?",
                       (task["id"], feedback_id))
        # Run one local job immediately. If another worker already owns the
        # lease, the feedback stays 'checking' and the caller can poll the task.
        await jobs.run_once()
        task = jobs.get(feedback["course_id"], task["id"])
        if task["status"] in ("queued", "running"):
            with knowledge.connect() as db:
                row = db.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
            return {"feedback": dict(row), "task": task}
        after = knowledge.snapshot(feedback["course_id"])
        same = next((item for item in (after or {}).get("concepts", [])
                     if item["id"] == target["id"] or item["name"] == target["name"]), None)
        changed = bool(same and (same.get("definition") != target.get("definition")
                                 or same.get("page_md") != target.get("page_md")))
        status = "resolved" if task["status"] == "completed" else "open"
        resolution = ("changed" if changed else "unchanged") if status == "resolved" else "failed"
        with knowledge.connect() as db:
            db.execute("UPDATE feedback SET status=?,resolution=? WHERE id=?", (status, resolution, feedback_id))
            row = db.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        return {"feedback": dict(row), "task": task, "changed": changed}

    return router
