"""Published knowledge and job HTTP interfaces for members A, B and C."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from .jobs import Jobs
from .knowledge_models import ScopeInput
from .reading import reference_context, render


def knowledge_router(data_dir: Path, model: Any | None = None) -> APIRouter:
    """Create version-pinned read routes and controlled first-build commands."""
    router = APIRouter()
    jobs = Jobs(data_dir, model=model)

    def chapter_title(snapshot: dict[str, Any], fragment: dict[str, Any]) -> str | None:
        containing = [
            chapter
            for chapter in snapshot["chapters"]
            if chapter["material_id"] == fragment["material_id"]
            and chapter["start_line"] <= fragment["start_line"] <= chapter["end_line"]
        ]
        return containing[-1]["title"] if containing else None

    def source_view(snapshot: dict[str, Any], fragment: dict[str, Any]) -> dict[str, Any]:
        original = jobs.materials.raw(snapshot["course_id"], fragment["material_id"]).decode("utf-8-sig")
        return fragment | {
            "version_id": snapshot["version_id"],
            "chapter_title": chapter_title(snapshot, fragment),
            "html": render(fragment["markdown"], reference_context(original)),
        }

    @router.get("/api/model/status")
    async def model_status() -> dict[str, Any]:
        configured = bool(getattr(jobs.model, "api_key", ""))
        return {
            "model": "deepseek-flash",
            "configured": configured,
            "message": (
                "后端已配置模型凭据。"
                if configured
                else "后端尚未配置 DEEPSEEK_API_KEY；可以浏览与导入资料，但不能开始真实整理。"
            ),
        }

    @router.get("/api/courses/{course_id}/tasks")
    async def list_tasks(course_id: str) -> list[dict[str, Any]]:
        return jobs.list(course_id)

    @router.post("/api/courses/{course_id}/tasks", status_code=202)
    async def create_task(course_id: str, selection: ScopeInput) -> dict[str, Any]:
        try:
            return jobs.create(course_id, selection)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/courses/{course_id}/tasks/{task_id}")
    async def task_detail(course_id: str, task_id: str) -> dict[str, Any]:
        return jobs.get(course_id, task_id)

    @router.post("/api/courses/{course_id}/tasks/{task_id}/retry")
    async def retry_task(course_id: str, task_id: str) -> dict[str, Any]:
        try:
            return jobs.retry(course_id, task_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/api/courses/{course_id}/knowledge/versions")
    async def list_versions(course_id: str) -> list[dict[str, Any]]:
        jobs.materials.require_course(course_id)
        return jobs.knowledge.versions(course_id)

    @router.get("/api/courses/{course_id}/knowledge/coverage")
    async def read_coverage(course_id: str, version_id: str | None = None) -> dict[str, Any]:
        """Compare immutable source fragments with the requested knowledge version."""
        available = jobs.materials.list_materials(course_id)
        snapshot = jobs.knowledge.snapshot(course_id, version_id)
        organized = {fragment["id"] for fragment in snapshot["fragments"]} if snapshot else set()

        def scope_status(fragments: list[dict[str, Any]]) -> dict[str, Any]:
            count = sum(fragment["id"] in organized for fragment in fragments)
            return {
                "status": "unorganized" if not count else "organized" if count == len(fragments) else "partial",
                "organized_fragments": count,
                "total_fragments": len(fragments),
            }

        materials = []
        for material in available:
            detail = jobs.materials.detail(course_id, material["id"])
            fragments = jobs.materials.fragments(course_id, material["id"])
            chapters = []
            for chapter in detail["chapters"]:
                inside = [fragment for fragment in fragments
                          if chapter["start_line"] <= fragment["start_line"]
                          and fragment["end_line"] <= chapter["end_line"]]
                chapters.append(chapter | scope_status(inside))
            materials.append(detail | scope_status(fragments) | {"chapters": chapters})
        return {"course_id": course_id, "version_id": snapshot["version_id"] if snapshot else None,
                "materials": materials}

    @router.get("/api/courses/{course_id}/knowledge")
    async def read_knowledge(course_id: str, version_id: str | None = None) -> dict[str, Any]:
        jobs.materials.require_course(course_id)
        snapshot = jobs.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            return {
                "course_id": course_id,
                "version_id": None,
                "state": "unpublished",
                "concepts": [],
                "relations": [],
                "chapters": [],
                "fragments": [],
                "selection": None,
                "summary": None,
            }
        return snapshot

    @router.get("/api/courses/{course_id}/knowledge/versions/{version_id}/concepts/{concept_id}")
    async def read_concept(course_id: str, version_id: str, concept_id: str) -> dict[str, Any]:
        snapshot = jobs.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            raise HTTPException(404, "该课程尚未发布知识版本。")
        concept = next((item for item in snapshot["concepts"] if item["id"] == concept_id), None)
        if concept is None:
            raise HTTPException(404, "知识点不属于该知识版本。")
        fragments = {fragment["id"]: fragment for fragment in snapshot["fragments"]}
        citations = []
        for citation in concept["citations"]:
            fragment = fragments.get(citation["snippet_id"])
            if fragment is None:
                continue
            citations.append(citation | {
                "filename": fragment["filename"],
                "start_line": fragment["start_line"],
                "end_line": fragment["end_line"],
                "chapter_title": chapter_title(snapshot, fragment),
            })
        return concept | {"version_id": version_id, "html": render(concept["page_md"]),
                          "citations": citations}

    @router.get("/api/courses/{course_id}/knowledge/versions/{version_id}/sources/{snippet_id}")
    async def read_source(course_id: str, version_id: str, snippet_id: str) -> dict[str, Any]:
        snapshot = jobs.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            raise HTTPException(404, "该课程尚未发布知识版本。")
        source = next((item for item in snapshot["fragments"] if item["id"] == snippet_id), None)
        if source is None:
            raise HTTPException(404, "原文片段不属于该知识版本。")
        return source_view(snapshot, source)

    return router
