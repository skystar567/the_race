from pathlib import Path
import mimetypes

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from urllib.parse import quote, urlsplit
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator

from .materials import Materials
from .reading import reference_context, render
from .answers_api import answers_router
from .knowledge_api import knowledge_router


class CourseInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str):
        if not value.strip():
            raise ValueError("课程名称不能为空")
        return value.strip()


def create_app(data_dir: Path, static_dir: Path | None = None, model=None) -> FastAPI:
    app = FastAPI(title="课程学习空间")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
    materials = Materials(data_dir)

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and "origin" in request.headers:
            try:
                origin = urlsplit(request.headers["origin"])
                allowed = origin.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1"}
            except ValueError:
                allowed = False
            if not allowed:
                return JSONResponse({"detail": "仅接受本机学习空间的操作"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        return response

    @app.exception_handler(LookupError)
    async def missing_resource(request: Request, exc: LookupError):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/api/courses")
    async def list_courses():
        return materials.courses()

    @app.post("/api/courses", status_code=201)
    async def create_course(body: CourseInput):
        return materials.create_course(body.name)

    @app.get("/api/courses/{course_id}/materials")
    async def list_materials(course_id: str):
        return materials.list_materials(course_id)

    @app.post("/api/courses/{course_id}/materials", status_code=201)
    async def import_material(course_id: str, request: Request, filename: str = Query(max_length=240)):
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename.lower().endswith(".md"):
            raise HTTPException(422, "请选择 Markdown（.md）文件")
        materials.require_course(course_id)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(413, "单份资料不能超过 20 MB")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(422, "请使用 UTF-8 编码的 Markdown 文件")
        if not text.lstrip("\ufeff").strip() or "\x00" in text:
            raise HTTPException(422, "资料为空或包含无效文本")
        return materials.import_material(course_id, filename, bytes(content))

    @app.get("/api/courses/{course_id}/materials/{material_id}/raw")
    async def raw_material(course_id: str, material_id: str):
        material = materials.material(course_id, material_id)
        return Response(materials.raw(course_id, material_id), media_type="text/plain",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(material['filename'])}",
                                 "X-Content-Type-Options": "nosniff"})

    @app.get("/api/courses/{course_id}/materials/{material_id}")
    async def material_detail(course_id: str, material_id: str):
        return materials.detail(course_id, material_id)

    @app.get("/api/courses/{course_id}/materials/{material_id}/fragments")
    async def source_fragments(course_id: str, material_id: str, chapter_id: str | None = None):
        context = reference_context(materials.raw(course_id, material_id).decode("utf-8"))
        return [fragment | {"html": render(fragment["markdown"], context)}
                for fragment in materials.fragments(course_id, material_id, chapter_id)]

    app.include_router(knowledge_router(data_dir, model=model))
    app.include_router(answers_router(data_dir, model=model))

    if static_dir is not None:
        static_root = static_dir.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "接口不存在")
            target = (static_root / (path or "index.html")).resolve()
            if not target.is_relative_to(static_root) or not target.is_file():
                raise HTTPException(404, "页面不存在")
            return Response(target.read_bytes(), media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    return app
