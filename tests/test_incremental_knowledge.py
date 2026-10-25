"""Incremental knowledge through public jobs, version reads and HTTP commands."""

import asyncio
import copy

import pytest

from campus.jobs import Jobs
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.model import ModelError
from campus.scopes import resolve_scope
from test_knowledge_api import ScriptedModel, client_for, draft_replies, import_source

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def initial_course(data_dir):
    course, material, chapters = await import_source(data_dir)
    materials = Materials(data_dir)
    source = resolve_scope(materials, course["id"], ScopeInput(material_ids=[material["id"]]))
    jobs = Jobs(data_dir, model=ScriptedModel(draft_replies(source, chapters)))
    jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    return course, material, jobs.knowledge.snapshot(course["id"])


def add_supplement(data_dir, course_id, previous):
    materials = Materials(data_dir)
    raw = "# 补充说明\n\n进程也称运行过程。进程控制块用于记录进程状态。\n".encode()
    material = materials.import_material(course_id, "补充.md", raw)
    source = resolve_scope(materials, course_id, ScopeInput(material_ids=[material["id"]]))
    chapter = source["chapters"][0]["id"]
    snippet = next(f["id"] for f in source["fragments"] if "进程也称" in f["markdown"])
    process = next(c for c in previous["concepts"] if c["name"] == "进程")
    citation = {"snippet_id": snippet, "quote": "进程也称运行过程。"}
    extracted = {"concepts": [
        {"key": "process", "name": "运行过程", "aliases": ["进程"], "definition": "程序的一次执行。",
         "chapter_ids": [chapter], "citations": [citation]},
        {"key": "pcb", "name": "进程控制块", "aliases": ["PCB"], "definition": "用于记录进程状态。",
         "chapter_ids": [chapter], "citations": [{"snippet_id": snippet, "quote": "进程控制块用于记录进程状态。"}]},
    ], "relations": []}
    integrated = copy.deepcopy(extracted)
    integrated["concepts"][0].update(existing_id=process["id"], identity_status="confirmed",
        identity_reason="旧定义与新说明都指程序运行的同一过程，新资料明确给出别称。")
    integrated["concepts"][0]["citations"] += copy.deepcopy(process["citations"])
    integrated["concepts"][1].update(existing_id=None, identity_status="confirmed", identity_reason="新增的进程状态记录结构。")
    pages = {"pages": [
        {"key": "process", "page_md": f"进程也称运行过程。[原文](snippet:{snippet})", "citations": [citation]},
        {"key": "pcb", "page_md": f"进程控制块用于记录进程状态。[原文](snippet:{snippet})",
         "citations": extracted["concepts"][1]["citations"]},
    ]}
    return material, raw, {"抽取": extracted, "整合": integrated, "Markdown 页面": pages}


async def test_incremental_update_preserves_identity_old_pages_and_unselected_material(tmp_path):
    course, original, previous = await initial_course(tmp_path)
    material, raw, replies = add_supplement(tmp_path, course["id"], previous)
    outside = Materials(tmp_path).import_material(course["id"], "未选.md", "# 未选\n\n不应进入新版本。\n".encode())
    base = f"/api/courses/{course['id']}"
    async with client_for(tmp_path) as client:
        response = await client.post(base + "/tasks", json={"material_ids": [original["id"], material["id"]]})
        assert response.status_code == 202, response.text
        task = response.json()
        assert task["parent_version_id"] == previous["version_id"]
        assert task["scope"]["characters"] < len(raw.decode()) + 1
        assert (await client.get(base + "/knowledge")).json() == previous
        jobs = Jobs(tmp_path, model=ScriptedModel(replies))
        await jobs.run_once()
        assert jobs.get(course["id"], task["id"])["status"] == "completed"
        current = (await client.get(base + "/knowledge")).json()
        assert current["version_id"] != previous["version_id"]
        assert current["summary"] == {"new_concepts": 1, "updated_concepts": 1, "conflicts": 0, "needs_review": 0}
        process = next(c for c in current["concepts"] if c["name"] == "运行过程")
        old_process = next(c for c in previous["concepts"] if c["name"] == "进程")
        assert process["id"] == old_process["id"] and process["is_updated"] and not process["is_new"]
        assert set(process["aliases"]) >= {"进程", "Process"}
        assert len(process["chapter_ids"]) == 2 and len(process["citations"]) == 2
        old_thread = next(c for c in previous["concepts"] if c["name"] == "线程")
        new_thread = next(c for c in current["concepts"] if c["id"] == old_thread["id"])
        assert new_thread["page_md"] == old_thread["page_md"]
        assert new_thread["citations"] == old_thread["citations"]
        assert (await client.get(base + "/knowledge", params={"version_id": previous["version_id"]})).json() == previous
        versions = (await client.get(base + "/knowledge/versions")).json()
        assert next(v for v in versions if v["is_current"])["parent_version_id"] == previous["version_id"]
        coverage = (await client.get(base + "/knowledge/coverage")).json()
        states = {m["id"]: m["status"] for m in coverage["materials"]}
        assert states == {original["id"]: "organized", material["id"]: "organized", outside["id"]: "unorganized"}
        for citation in process["citations"]:
            assert (await client.get(base + f"/knowledge/versions/{current['version_id']}/sources/{citation['snippet_id']}")).status_code == 200
        assert (await client.get(base + f"/materials/{material['id']}/raw")).content == raw


@pytest.mark.parametrize("damage", ["unknown_identity", "unconfirmed_merge", "no_old_evidence", "bad_old_quote", "bad_page", "bad_relation"])
async def test_invalid_update_never_changes_published_knowledge(tmp_path, damage):
    course, _, previous = await initial_course(tmp_path)
    material, _, replies = add_supplement(tmp_path, course["id"], previous)
    change = replies["整合"]["concepts"][0]
    if damage == "unknown_identity":
        change["existing_id"] = "another-course-concept"
    elif damage == "unconfirmed_merge":
        change["identity_status"] = "needs_review"
    elif damage == "no_old_evidence":
        change["citations"] = change["citations"][:1]
    elif damage == "bad_old_quote":
        change["citations"][-1]["quote"] = "原文没有这样的定义。"
    elif damage == "bad_page":
        replies["Markdown 页面"]["pages"][0]["page_md"] += "[原文](snippet:invented)"
    else:
        replies["整合"]["relations"] = [{"from_key": "missing", "to_key": "process", "kind": "precedes",
                                         "origin": "suggested", "citation": None, "reason": "无效端点。"}]
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "failed"
    assert jobs.knowledge.snapshot(course["id"]) == previous
    assert len(jobs.knowledge.versions(course["id"])) == 1


async def test_uncertain_same_name_stays_separate_and_marked(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    material, _, replies = add_supplement(tmp_path, course["id"], previous)
    replies["整合"]["concepts"][0].update(existing_id=None, name="进程", identity_status="needs_review",
        identity_reason="同名但新定义尚不足以确认与旧概念相同。")
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    current = jobs.knowledge.snapshot(course["id"])
    candidates = [c for c in current["concepts"] if c["name"] == "进程"]
    assert len(candidates) == 2 and len({c["id"] for c in candidates}) == 2
    uncertain = next(c for c in candidates if c["status"] == "needs_review")
    assert uncertain["identity_reason"] == "同名但新定义尚不足以确认与旧概念相同。"
    assert current["summary"]["needs_review"] == 1


async def test_failed_update_retries_saved_steps_without_losing_old_knowledge(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    material, _, replies = add_supplement(tmp_path, course["id"], previous)
    model = ScriptedModel(replies, fail_once={"Markdown 页面": ModelError("truncated", "页面输出截断。")})
    jobs = Jobs(tmp_path, model=model)
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "failed"
    assert jobs.knowledge.snapshot(course["id"]) == previous
    async with client_for(tmp_path) as client:
        retried = await client.post(f"/api/courses/{course['id']}/tasks/{task['id']}/retry")
        assert retried.status_code == 200, retried.text
    await jobs.run_once()
    done = jobs.get(course["id"], task["id"])
    assert done["status"] == "completed"
    assert {s["name"]: s["attempts"] for s in done["steps"]} == {
        "ingest": 0, "extract": 1, "integrate": 1, "render": 2, "validate": 1, "publish": 1}
    assert jobs.knowledge.snapshot(course["id"], previous["version_id"]) == previous


async def test_in_progress_update_reads_old_version_and_rejects_stale_publication(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    material, _, replies = add_supplement(tmp_path, course["id"], previous)
    rendering, release = asyncio.Event(), asyncio.Event()

    class PausedModel(ScriptedModel):
        async def complete(self, instructions, content, schema, **options):
            if "Markdown 页面" in instructions:
                rendering.set()
                await release.wait()
            return await super().complete(instructions, content, schema, **options)

    jobs = Jobs(tmp_path, model=PausedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    running = asyncio.create_task(jobs.run_once())
    try:
        await asyncio.wait_for(rendering.wait(), 5)
        async with client_for(tmp_path) as client:
            base = f"/api/courses/{course['id']}"
            assert (await client.get(base + "/knowledge")).json() == previous
            assert (await client.get(base + f"/tasks/{task['id']}")).json()["status"] == "running"
        # Simulate another publisher using the same public, checked transaction.
        newer_id = jobs.knowledge.publish_task(course["id"], "other-publisher", previous,
                                               parent_version_id=previous["version_id"])
    finally:
        release.set()
        await asyncio.wait_for(running, 5)
    failed = jobs.get(course["id"], task["id"])
    assert failed["status"] == "failed" and "版本已变化" in failed["error_message"]
    assert jobs.knowledge.current_id(course["id"]) == newer_id
    with pytest.raises(ValueError, match="版本已变化"):
        jobs.retry(course["id"], task["id"])
    first_task = next(v["task_id"] for v in jobs.knowledge.versions(course["id"]) if v["id"] == previous["version_id"])
    assert jobs.knowledge.publish_task(course["id"], first_task, previous) == previous["version_id"]
    assert jobs.knowledge.current_id(course["id"]) == newer_id


async def test_updates_reject_foreign_material_and_identity(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    other, foreign_material, foreign = await initial_course(tmp_path)
    material, _, replies = add_supplement(tmp_path, course["id"], previous)
    async with client_for(tmp_path) as client:
        base = f"/api/courses/{course['id']}"
        assert (await client.post(base + "/tasks", json={"material_ids": [foreign_material["id"]]})).status_code == 404
        assert (await client.get(base + "/knowledge", params={"version_id": foreign["version_id"]})).status_code == 404
    replies["整合"]["concepts"][0]["existing_id"] = foreign["concepts"][0]["id"]
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "failed"
    assert jobs.knowledge.snapshot(course["id"]) == previous
    assert jobs.knowledge.snapshot(other["id"]) == foreign


async def test_consecutive_updates_can_reuse_model_keys_for_independent_concepts(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    for _ in range(2):
        material, _, replies = add_supplement(tmp_path, course["id"], previous)
        for concept in replies["整合"]["concepts"]:
            concept.update(existing_id=None, identity_status="needs_review",
                           identity_reason="同名但语境不足，独立保留待核对。")
        replies["整合"]["relations"] = [{"from_key": "process", "to_key": "pcb", "kind": "precedes",
            "origin": "suggested", "citation": None, "reason": "两个独立候选之间的推断关系。"}]
        jobs = Jobs(tmp_path, model=ScriptedModel(replies))
        task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
        await jobs.run_once()
        done = jobs.get(course["id"], task["id"])
        assert done["status"] == "completed", done["error_message"]
        current = jobs.knowledge.snapshot(course["id"])
        assert len(current["concepts"]) == len(previous["concepts"]) + 2
        old_relations = {relation["id"]: relation for relation in previous["relations"]}
        new_relations = {relation["id"]: relation for relation in current["relations"]}
        assert all(new_relations.get(rid) == relation for rid, relation in old_relations.items())
        assert len(new_relations) == len(current["relations"])
        previous = current
