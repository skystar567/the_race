"""HTTP interfaces for personal notes and explicit model expansions."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .expansions import ExpansionInput, Expansions
from .model import ModelError
from .notes import NoteConflict, NoteGenerate, NoteInput, NoteUpdate, Notes


def study_router(data_dir: Path, model: Any | None = None) -> APIRouter:
    router = APIRouter()
    notes = Notes(data_dir, model=model)
    expansions = Expansions(data_dir, model=model)

    def raise_for(exc: Exception) -> None:
        if isinstance(exc, NoteConflict):
            raise HTTPException(409, str(exc)) from exc
        if isinstance(exc, ModelError):
            raise HTTPException(502, str(exc)) from exc
        if isinstance(exc, (ValidationError, ValueError)):
            raise HTTPException(422, "模型输出或请求内容无效，请重试。") from exc
        raise exc

    @router.get("/api/courses/{course_id}/notes")
    async def list_notes(course_id: str) -> list[dict[str, Any]]:
        return notes.list_notes(course_id)

    @router.post("/api/courses/{course_id}/notes", status_code=201)
    async def create_note(course_id: str, body: NoteInput) -> dict[str, Any]:
        try:
            return notes.create_manual(course_id, body)
        except (ValueError, LookupError) as exc:
            if isinstance(exc, LookupError):
                raise
            raise HTTPException(422, str(exc)) from exc

    @router.post("/api/courses/{course_id}/notes/generate", status_code=201)
    async def generate_note(course_id: str, body: NoteGenerate) -> dict[str, Any]:
        try:
            return await notes.generate(course_id, body)
        except (ModelError, ValidationError, ValueError) as exc:
            raise_for(exc)

    @router.get("/api/courses/{course_id}/notes/{note_id}")
    async def note_detail(course_id: str, note_id: str) -> dict[str, Any]:
        return notes.detail(course_id, note_id)

    @router.get("/api/courses/{course_id}/notes/{note_id}/sources/{snippet_id}")
    async def note_source(course_id: str, note_id: str, snippet_id: str) -> dict[str, Any]:
        return notes.source(course_id, note_id, snippet_id)

    @router.put("/api/courses/{course_id}/notes/{note_id}")
    async def update_note(course_id: str, note_id: str, body: NoteUpdate) -> dict[str, Any]:
        try:
            return notes.update(course_id, note_id, body)
        except NoteConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/api/courses/{course_id}/expansions", status_code=201)
    async def create_expansion(course_id: str, body: ExpansionInput) -> dict[str, Any]:
        try:
            return await expansions.create(course_id, body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/courses/{course_id}/expansions/{expansion_id}")
    async def expansion_detail(course_id: str, expansion_id: str) -> dict[str, Any]:
        return expansions.detail(course_id, expansion_id)

    return router
