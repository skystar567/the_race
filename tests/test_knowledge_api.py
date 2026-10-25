"""Ticket 02: first real knowledge build, versioned reads and failure handling.

Model responses are scripted here on purpose: these tests prove deterministic
constraints only. Real DeepSeek content still needs a manual, credentialed run.
"""

import json
from pathlib import Path

import httpx
import pytest

from campus.api import create_app
from campus.jobs import Jobs
from campus.knowledge import Knowledge
from campus.knowledge_models import KnowledgeDraft, PagesDraft
from campus.knowledge_validation import build_snapshot, validate_snapshot
from campus.model import ModelError

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client_for(data_dir: Path, model=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(data_dir, model=model)),
        base_url="http://localhost",
    )


SOURCE = (
    "# 第二章 进程\n\n"
    "## 2.1 进程的定义\n\n"
    "进程是程序的一次执行，是系统进行资源分配的基本单位。\n\n"
    "## 2.2 线程\n\n"
    "线程是进程中的一个执行单元，是处理机调度的基本单位。\n"
)


class ScriptedModel:
    """Return predefined step outputs, or raise a predefined ModelError."""

    api_key = "test-key"

    def __init__(self, replies, fail_once=None):
        self.replies = replies
        self.fail_once = dict(fail_once or {})
        self.calls = []

    async def complete(self, instructions, content, schema, *, thinking=True):
        step = next((name for name in self.replies if name in instructions), None)
        if step is None:
            raise AssertionError(f"unexpected model step: {instructions[:80]}")
        self.calls.append(step)
        if step in self.fail_once:
            error = self.fail_once.pop(step)
            raise error
        reply = self.replies[step]
        if callable(reply):
            return reply(content)
        return reply


async def import_source(data_dir: Path):
    async with client_for(data_dir) as client:
        course = (await client.post("/api/courses", json={"name": "操作系统"})).json()
        base = f"/api/courses/{course['id']}/materials"
        material = (
            await client.post(base, params={"filename": "教材.md"}, content=SOURCE.encode())
        ).json()
        detail = (await client.get(f"{base}/{material['id']}")).json()
    chapters = {chapter["title"]: chapter["id"] for chapter in detail["chapters"]}
    return course, material, chapters


async def fragments_by_text(data_dir: Path, course_id: str, material_id: str):
    async with client_for(data_dir) as client:
        fragments = (
            await client.get(
                f"/api/courses/{course_id}/materials/{material_id}/fragments"
            )
        ).json()
    return fragments


def draft_replies(source, chapters):
    by_text = {fragment["markdown"].strip(): fragment["id"] for fragment in source["fragments"]}
    process_id = next(fid for text, fid in by_text.items() if "进程是程序" in text)
    thread_id = next(fid for text, fid in by_text.items() if "线程是进程" in text)
    extract = {
        "concepts": [
            {
                "key": "process",
                "name": "进程",
                "aliases": ["Process"],
                "definition": "程序的一次执行，是资源分配的基本单位。",
                "chapter_ids": [chapters["2.1 进程的定义"]],
                "citations": [{"snippet_id": process_id, "quote": "进程是程序的一次执行"}],
            },
            {
                "key": "thread",
                "name": "线程",
                "aliases": [],
                "definition": "进程中的一个执行单元，是处理机调度的基本单位。",
                "chapter_ids": [chapters["2.2 线程"]],
                "citations": [{"snippet_id": thread_id, "quote": "线程是进程中的一个执行单元"}],
            },
        ],
        "relations": [
            {
                "from_key": "process",
                "to_key": "thread",
                "kind": "precedes",
                "origin": "suggested",
                "citation": None,
                "reason": "先理解进程这一资源分配单位，再理解线程这一执行单元。",
            }
        ],
    }
    integrate = json.loads(json.dumps(extract))
    pages = {
        "pages": [
            {
                "key": "process",
                "page_md": f"进程是程序的一次执行。[原文](snippet:{process_id})",
                "citations": [{"snippet_id": process_id, "quote": "进程是程序的一次执行"}],
            },
            {
                "key": "thread",
                "page_md": f"线程是进程中的执行单元。[原文](snippet:{thread_id})",
                "citations": [{"snippet_id": thread_id, "quote": "线程是进程中的一个执行单元"}],
            },
        ]
    }
    return {"抽取": extract, "整合": integrate, "Markdown 页面": pages}


async def create_task(data_dir: Path, course_id: str, material_id: str) -> dict:
    async with client_for(data_dir) as client:
        response = await client.post(
            f"/api/courses/{course_id}/tasks", json={"material_ids": [material_id], "chapter_ids": []}
        )
        assert response.status_code == 202, response.text
        return response.json()


async def test_first_build_publishes_version_pinned_knowledge(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    assert task["status"] == "queued"
    assert task["scope"]["fragments"] > 0

    ingest = _ingest(tmp_path, task["id"])
    model = ScriptedModel(draft_replies(ingest, chapters))
    jobs = Jobs(tmp_path, model=model)
    assert await jobs.run_once() is True
    assert model.calls == ["抽取", "整合", "Markdown 页面"]

    async with client_for(tmp_path) as client:
        knowledge = (await client.get(f"/api/courses/{course['id']}/knowledge")).json()
        assert knowledge["state"] == "published"
        assert knowledge["version_id"]
        assert [concept["name"] for concept in knowledge["concepts"]] == ["进程", "线程"]
        kinds = {(r["kind"], r["from_type"], r["to_type"], r["origin"]) for r in knowledge["relations"]}
        assert ("contains", "chapter", "concept", "source") in kinds
        assert ("precedes", "concept", "concept", "suggested") in kinds
        precedes = next(r for r in knowledge["relations"] if r["kind"] == "precedes")
        assert precedes["from_id"] == knowledge["concepts"][0]["id"]
        assert precedes["to_id"] == knowledge["concepts"][1]["id"]

        versions = (await client.get(f"/api/courses/{course['id']}/knowledge/versions")).json()
        assert [(v["state"], v["is_current"]) for v in versions] == [("published", True)]

        concept = knowledge["concepts"][0]
        detail = (
            await client.get(
                f"/api/courses/{course['id']}/knowledge/versions/"
                f"{knowledge['version_id']}/concepts/{concept['id']}"
            )
        ).json()
        assert "进程是程序的一次执行" in detail["html"]
        assert detail["citations"][0]["start_line"] == 5
        assert detail["citations"][0]["chapter_title"] == "2.1 进程的定义"

        snippet_id = detail["citations"][0]["snippet_id"]
        source_view = (
            await client.get(
                f"/api/courses/{course['id']}/knowledge/versions/"
                f"{knowledge['version_id']}/sources/{snippet_id}"
            )
        ).json()
        assert "进程是程序的一次执行" in source_view["markdown"]
        assert "process" in source_view["html"] or "进程" in source_view["html"]

        finished = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert finished["status"] == "completed"
        assert finished["version_id"] == knowledge["version_id"]
        assert all(step["status"] == "completed" for step in finished["steps"])

    async with client_for(tmp_path) as restarted:
        again = (await restarted.get(f"/api/courses/{course['id']}/knowledge")).json()
        assert again["version_id"] == knowledge["version_id"]
        assert [c["id"] for c in again["concepts"]] == [c["id"] for c in knowledge["concepts"]]


async def test_scope_validation_and_character_limit(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    other, other_material, other_chapters = await import_source(tmp_path)
    async with client_for(tmp_path) as client:
        empty = await client.post(f"/api/courses/{course['id']}/tasks", json={})
        assert empty.status_code == 422
        assert "至少" in empty.json()["detail"]

        foreign = await client.post(
            f"/api/courses/{course['id']}/tasks",
            json={"material_ids": [], "chapter_ids": [other_chapters["2.1 进程的定义"]]},
        )
        assert foreign.status_code == 404

        chapter_only = await client.post(
            f"/api/courses/{course['id']}/tasks",
            json={"material_ids": [], "chapter_ids": [chapters["2.2 线程"]]},
        )
        assert chapter_only.status_code == 202
        assert chapter_only.json()["scope"]["chapters"] == 1
        assert chapter_only.json()["scope"]["fragments"] == 2


async def test_oversized_scope_is_rejected_without_creating_a_task(tmp_path):
    course, material, _ = await import_source(tmp_path)
    big = "# 大节\n\n" + ("进程与线程的说明。" * 12000) + "\n"
    async with client_for(tmp_path) as client:
        imported = (
            await client.post(
                f"/api/courses/{course['id']}/materials",
                params={"filename": "大节.md"},
                content=big.encode(),
            )
        ).json()
        response = await client.post(
            f"/api/courses/{course['id']}/tasks", json={"material_ids": [imported["id"]]}
        )
        assert response.status_code == 422
        assert "超过单次" in response.json()["detail"]
        assert (await client.get(f"/api/courses/{course['id']}/tasks")).json() == []


async def test_invalid_citation_never_publishes_knowledge(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    replies = draft_replies(ingest, chapters)
    replies["抽取"]["concepts"][0]["citations"][0]["quote"] = "教材中并不存在的句子"
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    assert await jobs.run_once() is True

    async with client_for(tmp_path) as client:
        failed = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "validation"
        assert "引用" in failed["error_message"]
        assert (await client.get(f"/api/courses/{course['id']}/knowledge")).json()["state"] == "unpublished"
        assert (await client.get(f"/api/courses/{course['id']}/knowledge/versions")).json() == []


@pytest.mark.parametrize(
    "error,code",
    [
        (ModelError("empty_output", "模型没有返回可用正文。"), "empty_output"),
        (ModelError("truncated", "模型输出被截断，请缩小整理范围后重试。"), "truncated"),
    ],
)
async def test_empty_or_truncated_output_is_visible_and_unpublished(tmp_path, error, code):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    jobs = Jobs(tmp_path, model=ScriptedModel(draft_replies(ingest, chapters), fail_once={"抽取": error}))
    assert await jobs.run_once() is True
    async with client_for(tmp_path) as client:
        failed = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert failed["error_code"] == code
        assert (await client.get(f"/api/courses/{course['id']}/knowledge")).json()["state"] == "unpublished"


async def test_unknown_relation_endpoint_fails_validation(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    replies = draft_replies(ingest, chapters)
    replies["抽取"]["relations"][0]["to_key"] = "missing"
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    assert await jobs.run_once() is True
    async with client_for(tmp_path) as client:
        failed = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert failed["error_code"] == "validation"
        assert "关系端点" in failed["error_message"]
        assert (await client.get(f"/api/courses/{course['id']}/knowledge")).json()["state"] == "unpublished"


async def test_retry_reuses_completed_model_steps(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    model = ScriptedModel(
        draft_replies(ingest, chapters),
        fail_once={"Markdown 页面": ModelError("request", "模型请求被拒绝（400），请检查配置与请求范围。")},
    )
    jobs = Jobs(tmp_path, model=model)
    assert await jobs.run_once() is True
    async with client_for(tmp_path) as client:
        failed = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "request"
        retried = (await client.post(f"/api/courses/{course['id']}/tasks/{task['id']}/retry")).json()
        assert retried["status"] == "queued"
    calls_before = len(model.calls)
    assert await Jobs(tmp_path, model=model).run_once() is True
    assert model.calls[calls_before:] == ["Markdown 页面"]
    async with client_for(tmp_path) as client:
        finished = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert finished["status"] == "completed"
        attempts = {step["name"]: step["attempts"] for step in finished["steps"]}
        assert attempts["extract"] == 1 and attempts["render"] == 2
        assert (await client.get(f"/api/courses/{course['id']}/knowledge")).json()["state"] == "published"


async def test_one_worker_holds_the_lease_and_only_failed_tasks_retry(tmp_path):
    course, material, _ = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    jobs = Jobs(tmp_path, model=ScriptedModel({}))
    claimed = jobs.claim("worker-a")
    assert claimed is not None and claimed["id"] == task["id"]
    assert jobs.claim("worker-b") is None
    with pytest.raises(ValueError, match="失败"):
        jobs.retry(course["id"], task["id"])


async def test_repeated_publish_never_creates_a_second_version(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    model = ScriptedModel(draft_replies(ingest, chapters))
    jobs = Jobs(tmp_path, model=model)
    assert await jobs.run_once() is True
    knowledge = jobs.knowledge.snapshot(course["id"])
    assert knowledge["state"] == "published"

    # Simulate a crash after the pointer switch but before task completion.
    with jobs.knowledge.connect() as db:
        db.execute("UPDATE task SET status='running',owner='retry-owner' WHERE id=?", (task["id"],))
        db.execute("UPDATE task_step SET status='pending' WHERE task_id=? AND name='publish'", (task["id"],))
    assert await jobs.run_once() is True
    versions = jobs.knowledge.versions(course["id"])
    assert len(versions) == 1
    assert jobs.knowledge.current_id(course["id"]) == knowledge["version_id"]
    with jobs.knowledge.connect() as db:
        row = db.execute("SELECT status FROM task WHERE id=?", (task["id"],)).fetchone()
    assert row["status"] == "completed"


async def test_bookkeeping_error_after_publish_keeps_the_task_completed(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    jobs = Jobs(tmp_path, model=ScriptedModel(draft_replies(ingest, chapters)))
    assert await jobs.run_once() is True
    published = jobs.knowledge.current_id(course["id"])
    with jobs.knowledge.connect() as db:
        db.execute("UPDATE task SET status='running',owner='test-owner' WHERE id=?", (task["id"],))
    jobs._fail(task["id"], "test-owner", "publish", "internal", "bookkeeping failed")
    with jobs.knowledge.connect() as db:
        row = db.execute("SELECT status,version_id FROM task WHERE id=?", (task["id"],)).fetchone()
    assert row["status"] == "completed"
    assert row["version_id"] == published


async def test_snapshot_tampering_is_rejected_even_with_validated_flag(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    replies = draft_replies(ingest, chapters)
    draft = KnowledgeDraft.model_validate(replies["抽取"])
    pages = PagesDraft.model_validate(replies["Markdown 页面"])
    snapshot = build_snapshot(course["id"], task["id"], draft, pages, ingest)
    assert snapshot["validated"] is True
    snapshot["relations"][-1]["to_id"] = "not-a-concept"
    with pytest.raises(ValueError, match="关系端点"):
        validate_snapshot(snapshot)
    knowledge = Knowledge(tmp_path)
    with pytest.raises(ValueError, match="关系端点"):
        knowledge.publish_task(course["id"], task["id"], snapshot)
    assert knowledge.current_id(course["id"]) is None


async def test_versions_and_sources_are_isolated_by_course(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    jobs = Jobs(tmp_path, model=ScriptedModel(draft_replies(ingest, chapters)))
    assert await jobs.run_once() is True
    knowledge = jobs.knowledge.snapshot(course["id"])

    async with client_for(tmp_path) as client:
        other = (await client.post("/api/courses", json={"name": "计算机网络"})).json()
        response = await client.get(
            f"/api/courses/{other['id']}/knowledge", params={"version_id": knowledge["version_id"]}
        )
        assert response.status_code == 404
        concept_id = knowledge["concepts"][0]["id"]
        assert (
            await client.get(
                f"/api/courses/{other['id']}/knowledge/versions/"
                f"{knowledge['version_id']}/concepts/{concept_id}"
            )
        ).status_code == 404
        assert (await client.get(f"/api/courses/{other['id']}/knowledge")).json()["state"] == "unpublished"
        # A published course can queue an incremental task; publication merges
        # into the current version instead of replacing it.
        second = await client.post(
            f"/api/courses/{course['id']}/tasks", json={"material_ids": [material["id"]]}
        )
        assert second.status_code == 202
        assert second.json()["status"] == "queued"


async def test_unexpected_step_error_fails_the_task_without_crashing(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    task = await create_task(tmp_path, course["id"], material["id"])
    ingest = _ingest(tmp_path, task["id"])
    model = ScriptedModel(draft_replies(ingest, chapters))
    jobs = Jobs(tmp_path, model=model)

    async def broken(step, current_task, results):
        raise RuntimeError("unexpected failure")

    jobs.execute_step = broken
    assert await jobs.run_once() is True
    async with client_for(tmp_path) as client:
        failed = (await client.get(f"/api/courses/{course['id']}/tasks/{task['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "internal"
        assert (await client.get(f"/api/courses/{course['id']}/knowledge")).json()["state"] == "unpublished"


def _ingest(data_dir: Path, task_id: str) -> dict:
    knowledge = Knowledge(data_dir)
    with knowledge.connect() as db:
        row = db.execute(
            "SELECT result_json FROM task_step WHERE task_id=? AND name='ingest'", (task_id,)
        ).fetchone()
    return json.loads(row["result_json"])
