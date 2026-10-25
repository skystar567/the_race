"""HTTP/SSE interfaces for grounded course questions."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .answers import Answers, AskInput


def answers_router(data_dir: Path, model: Any | None = None) -> APIRouter:
    """Version-pinned answers; errors are raised before the SSE stream opens."""
    router = APIRouter()
    answers = Answers(data_dir, model=model)

    @router.post("/api/courses/{course_id}/answers/stream")
    async def ask(course_id: str, body: AskInput):
        try:
            plan = await answers.prepare(course_id, body)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        async def events():
            async for event in answers.stream(plan):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/courses/{course_id}/answers")
    async def history(course_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return answers.history(course_id, limit)

    @router.get("/api/courses/{course_id}/answers/{answer_id}")
    async def detail(course_id: str, answer_id: str) -> dict[str, Any]:
        return answers.detail(course_id, answer_id)

    @router.get("/api/courses/{course_id}/answers/{answer_id}/sources/{snippet_id}")
    async def source(course_id: str, answer_id: str, snippet_id: str) -> dict[str, Any]:
        return answers.source(course_id, answer_id, snippet_id)

    return router
