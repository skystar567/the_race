"""Chapter scope and identity checks through HTTP and public business methods."""

import pytest

from campus.jobs import Jobs
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from test_knowledge_api import ScriptedModel, client_for

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_coverage_distinguishes_selected_chapters_and_pins_the_version(tmp_path):
    materials = Materials(tmp_path)
    course = materials.create_course("章节范围验收")
    material = materials.import_material(course["id"], "教材.md", (
        "# 教材\n\n总览内容。\n\n## 1.1 第一节\n\n进程是执行中的程序。\n\n"
        "## 1.2 第二节\n\n进程拥有自己的资源。\n\n## 1.3 第三节\n\n未整理的内容。\n"
    ).encode())
    detail = materials.detail(course["id"], material["id"])
    chapters = {chapter["title"]: chapter["id"] for chapter in detail["chapters"]}
    fragments = materials.fragments(course["id"], material["id"])
    citations = [{"snippet_id": fragment["id"], "quote": fragment["markdown"].strip()}
                 for fragment in fragments if "进程" in fragment["markdown"]]
    draft = {"concepts": [{"key": "process", "name": "进程", "aliases": [],
                          "definition": "执行中的程序，拥有自己的资源。",
                          "chapter_ids": [chapters["1.1 第一节"], chapters["1.2 第二节"]],
                          "citations": citations}], "relations": []}
    pages = {"pages": [{"key": "process", "page_md": "进程的定义。" + "".join(
        f"[原文](snippet:{citation['snippet_id']})" for citation in citations), "citations": citations}]}
    jobs = Jobs(tmp_path, model=ScriptedModel({"抽取": draft, "整合": draft, "Markdown 页面": pages}))
    jobs.create(course["id"], ScopeInput(chapter_ids=[chapters["1.1 第一节"], chapters["1.2 第二节"]]))
    await jobs.run_once()
    knowledge = jobs.knowledge.snapshot(course["id"])
    async with client_for(tmp_path) as client:
        base = f"/api/courses/{course['id']}/knowledge"
        response = await client.get(base + "/coverage", params={"version_id": knowledge["version_id"]})
        assert response.status_code == 200
        coverage = response.json()
        assert coverage["version_id"] == knowledge["version_id"]
        row = coverage["materials"][0]
        assert row["status"] == "partial"
        states = {chapter["title"]: chapter["status"] for chapter in row["chapters"]}
        assert states == {"教材": "partial", "1.1 第一节": "organized", "1.2 第二节": "organized", "1.3 第三节": "unorganized"}
        assert len(knowledge["concepts"]) == 1
        concept = knowledge["concepts"][0]
        assert set(concept["chapter_ids"]) == {chapters["1.1 第一节"], chapters["1.2 第二节"]}
        assert len([edge for edge in knowledge["relations"] if edge["to_id"] == concept["id"]]) == 2
        assert not any("未整理的内容" in fragment["markdown"] for fragment in knowledge["fragments"])
        for citation in concept["citations"]:
            source = await client.get(base + f"/versions/{knowledge['version_id']}/sources/{citation['snippet_id']}")
            assert source.status_code == 200
            assert source.json()["version_id"] == knowledge["version_id"]
        added = materials.import_material(course["id"], "补充.md", b"# New\n\nExtra material.\n")
        coverage = (await client.get(base + "/coverage", params={"version_id": knowledge["version_id"]})).json()
        assert next(row for row in coverage["materials"] if row["id"] == added["id"])["status"] == "unorganized"
        other = materials.create_course("另一门课")
        assert (await client.get(f"/api/courses/{other['id']}/knowledge/coverage", params={"version_id": knowledge["version_id"]})).status_code == 404
        assert (await client.get(base + "/coverage", params={"version_id": "missing"})).status_code == 404


async def test_unpublished_course_coverage_never_claims_organized_content(tmp_path):
    materials = Materials(tmp_path)
    course = materials.create_course("仅导入")
    materials.import_material(course["id"], "说明.md", b"# Chapter\n\nText.\n")
    async with client_for(tmp_path) as client:
        response = await client.get(f"/api/courses/{course['id']}/knowledge/coverage")
        assert response.status_code == 200
        coverage = response.json()
        assert coverage["version_id"] is None
        assert coverage["materials"][0]["status"] == "unorganized"
        assert coverage["materials"][0]["chapters"][0]["status"] == "unorganized"
        assert (await client.get("/api/courses/missing/knowledge/coverage")).status_code == 404
