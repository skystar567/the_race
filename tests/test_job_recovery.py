"""Recovery and retry behavior observed through public jobs and model transport."""

import asyncio
import json

import httpx
import pytest

from campus.jobs import Jobs
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.model import DeepSeek
from campus.scopes import resolve_scope
from scripts.check_recovery_process import check as check_worker_recovery
from test_knowledge_api import ScriptedModel, draft_replies, import_source
from test_model_adapter import response_payload

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_interrupted_job_reports_recovery_and_keeps_saved_steps(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    source = resolve_scope(Materials(tmp_path), course["id"], ScopeInput(material_ids=[material["id"]]))
    entered = asyncio.Event()

    class WaitingModel(ScriptedModel):
        async def complete(self, instructions, content, schema, **options):
            if "Markdown 页面" in instructions:
                entered.set()
                await asyncio.Event().wait()
            return await super().complete(instructions, content, schema, **options)

    replies = draft_replies(source, chapters)
    jobs = Jobs(tmp_path, model=WaitingModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    running = asyncio.create_task(jobs.run_once())
    await asyncio.wait_for(entered.wait(), 3)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    restarted = Jobs(tmp_path, model=ScriptedModel(replies))
    await restarted.run_once()
    done = restarted.get(course["id"], task["id"])
    assert done["status"] == "completed"
    assert done["recovery_count"] == 1
    assert {s["name"]: s["attempts"] for s in done["steps"]} == {
        "ingest": 0, "extract": 1, "integrate": 1, "render": 2, "validate": 1, "publish": 1}


async def test_transient_timeout_can_retry_and_publish(tmp_path):
    course, material, chapters = await import_source(tmp_path)
    source = resolve_scope(Materials(tmp_path), course["id"], ScopeInput(material_ids=[material["id"]]))
    replies = draft_replies(source, chapters)
    statuses = [408, 429]
    calls = []

    async def respond(request):
        payload = json.loads(request.content)
        step = next(name for name in replies if name in payload["instructions"])
        calls.append(step)
        if statuses:
            return httpx.Response(statuses.pop(0))
        return httpx.Response(200, json=response_payload(json.dumps(replies[step])))

    model = DeepSeek(api_key="fixture", transport=httpx.MockTransport(respond))
    jobs = Jobs(tmp_path, model=model)
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "completed"
    assert calls == ["抽取", "抽取", "抽取", "整合", "Markdown 页面"]


@pytest.mark.parametrize("status,expected_calls,code", [(503, 3, "temporary"), (400, 1, "request"), (401, 1, "authentication")])
async def test_model_failure_has_bounded_retries_and_never_publishes(tmp_path, status, expected_calls, code):
    course, material, _ = await import_source(tmp_path)
    calls = []

    async def respond(request):
        calls.append(request.url.path)
        return httpx.Response(status, json={"error": "sensitive upstream detail"})

    jobs = Jobs(tmp_path, model=DeepSeek(api_key="fixture", transport=httpx.MockTransport(respond)))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    failed = jobs.get(course["id"], task["id"])
    assert failed["status"] == "failed" and failed["error_code"] == code
    assert len(calls) == expected_calls
    assert "sensitive" not in failed["error_message"]
    assert jobs.knowledge.snapshot(course["id"]) is None


async def test_heartbeat_keeps_other_courses_queued_until_worker_finishes(tmp_path):
    first, material, chapters = await import_source(tmp_path)
    second, other_material, other_chapters = await import_source(tmp_path)
    materials = Materials(tmp_path)
    first_source = resolve_scope(materials, first["id"], ScopeInput(material_ids=[material["id"]]))
    second_source = resolve_scope(materials, second["id"], ScopeInput(material_ids=[other_material["id"]]))
    entered, release = asyncio.Event(), asyncio.Event()

    class SlowModel(ScriptedModel):
        async def complete(self, instructions, content, schema, **options):
            if "抽取" in instructions:
                entered.set()
                await release.wait()
            return await super().complete(instructions, content, schema, **options)

    jobs = Jobs(tmp_path, model=SlowModel(draft_replies(first_source, chapters)), lease_seconds=2)
    first_task = jobs.create(first["id"], ScopeInput(material_ids=[material["id"]]))
    other = Jobs(tmp_path, model=ScriptedModel(draft_replies(second_source, other_chapters)), lease_seconds=2)
    other_task = other.create(second["id"], ScopeInput(material_ids=[other_material["id"]]))
    running = asyncio.create_task(jobs.run_once())
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await asyncio.sleep(2.2)  # Longer than the initial lease; heartbeat must renew it.
        assert not await other.run_once()
        assert other.get(second["id"], other_task["id"])["status"] == "queued"
        assert jobs.get(first["id"], first_task["id"])["status"] == "running"
    finally:
        release.set()
        await asyncio.wait_for(running, 3)
    assert await other.run_once()
    assert other.get(second["id"], other_task["id"])["status"] == "completed"


@pytest.mark.parametrize("lease_seconds", [0, 1, float("nan"), float("inf")])
async def test_invalid_worker_lease_is_rejected(tmp_path, lease_seconds):
    with pytest.raises(ValueError, match="至少 2 秒"):
        Jobs(tmp_path, model=ScriptedModel({}), lease_seconds=lease_seconds)


async def test_real_worker_process_recovers_first_and_incremental_builds(tmp_path):
    report = await asyncio.to_thread(check_worker_recovery, tmp_path / "processes")
    assert [run["phase"] for run in report["runs"]] == ["first", "incremental"]
    assert [run["versions"] for run in report["runs"]] == [1, 2]
    assert all(run["recovery_count"] == 1 for run in report["runs"])
