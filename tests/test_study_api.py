"""Ticket 05/06/11: personal notes, explicit expansion, preservation."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from campus.api import create_app
from campus.jobs import Jobs
from campus.knowledge import Knowledge
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.model import ModelError
from test_incremental_knowledge import add_supplement, initial_course
from test_identity_conflicts import conflict_supplement

pytestmark = pytest.mark.anyio

SOURCE = (
    "# 第二章 进程与线程\n\n"
    "## 2.1 进程\n\n"
    "进程是程序的一次执行。进程是系统进行资源分配和调度的独立单位。每个进程拥有独立的地址空间。\n\n"
    "## 2.2 线程\n\n"
    "线程是进程中的一个执行单元，是处理机调度的基本单位。同一进程内的多个线程共享该进程的资源。\n"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client_for(data_dir: Path, model=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(data_dir, model=model)),
        base_url="http://localhost",
    )


class BuildModel:
    api_key = "test-key"

    def __init__(self, replies):
        self.replies = replies

    async def complete(self, instructions, content, schema, *, thinking=True):
        for name, reply in self.replies.items():
            if name in instructions:
                return reply
        raise AssertionError(f"unexpected build step: {instructions[:60]}")


class StudyModel:
    api_key = "test-key"

    def __init__(self, answer_chunks=None, note_reply=None, expansion_reply=None,
                 note_error=None, expansion_error=None):
        self.answer_chunks = answer_chunks or []
        self.note_reply = note_reply or {"title": "笔记", "body_md": "正文"}
        self.expansion_reply = expansion_reply or {"expansion_md": "资料外补充说明。"}
        self.note_error = note_error
        self.expansion_error = expansion_error
        self.calls = []

    async def stream(self, instructions, content):
        for chunk in self.answer_chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    async def complete(self, instructions, content, schema, *, thinking=True):
        self.calls.append(content)
        if "个人学习笔记" in instructions:
            if self.note_error:
                raise self.note_error
            return self.note_reply
        if "拓展解释" in instructions:
            if self.expansion_error:
                raise self.expansion_error
            return self.expansion_reply
        if "检索路由" in instructions:
            return {"concept_ids": []}
        raise AssertionError(f"unexpected study step: {instructions[:60]}")


async def publish_fixture(data_dir: Path):
    materials = Materials(data_dir)
    course = materials.create_course("操作系统")
    material = materials.import_material(course["id"], "教材.md", SOURCE.encode())
    detail = materials.detail(course["id"], material["id"])
    chapters = {chapter["title"]: chapter["id"] for chapter in detail["chapters"]}
    fragments = materials.fragments(course["id"], material["id"])
    process = next(f for f in fragments if "进程是程序的一次执行" in f["markdown"])
    thread = next(f for f in fragments if "线程是进程中的一个执行单元" in f["markdown"])
    draft = {
        "concepts": [
            {
                "key": "process", "name": "进程", "aliases": ["Process"],
                "definition": "程序的一次执行，是资源分配和调度的独立单位。",
                "chapter_ids": [chapters["2.1 进程"]],
                "citations": [{"snippet_id": process["id"], "quote": "进程是程序的一次执行"}],
            },
            {
                "key": "thread", "name": "线程", "aliases": [],
                "definition": "进程中的执行单元，是处理机调度的基本单位。",
                "chapter_ids": [chapters["2.2 线程"]],
                "citations": [{"snippet_id": thread["id"], "quote": "线程是进程中的一个执行单元"}],
            },
        ],
        "relations": [],
    }
    pages = {
        "pages": [
            {"key": "process", "page_md": f"进程是资源分配单位。[原文](snippet:{process['id']})",
             "citations": [{"snippet_id": process["id"], "quote": "进程是系统进行资源分配和调度的独立单位。"}]},
            {"key": "thread", "page_md": f"线程是调度单位。[原文](snippet:{thread['id']})",
             "citations": [{"snippet_id": thread["id"], "quote": "线程是进程中的一个执行单元"}]},
        ]
    }
    jobs = Jobs(
        data_dir,
        model=BuildModel({"抽取": draft, "整合": draft, "Markdown 页面": pages}),
    )
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    assert await jobs.run_once() is True
    snapshot = jobs.knowledge.snapshot(course["id"])
    concepts = {concept["name"]: concept["id"] for concept in snapshot["concepts"]}
    return {
        "course": course, "snapshot": snapshot, "concepts": concepts,
        "process": process["id"], "thread": thread["id"],
    }


async def completed_answer(client, fixture):
    response = await client.post(
        f"/api/courses/{fixture['course']['id']}/answers/stream",
        json={"question": "进程和线程有什么区别？"},
    )
    events = parse_sse(response.text)
    return next(data for name, data in events if name == "done")["answer"]


def parse_sse(body: str):
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        name, data = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


async def publish_second_version(data_dir: Path, course_id: str):
    """Publish new evidence through the same controlled workflow as users."""
    previous = Knowledge(data_dir).snapshot(course_id)
    material, _, replies = add_supplement(data_dir, course_id, previous)
    jobs = Jobs(data_dir, model=BuildModel(replies))
    task = jobs.create(course_id, ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    done = jobs.get(course_id, task["id"])
    assert done["status"] == "completed", done["error_message"]
    return jobs.knowledge.current_id(course_id)


async def test_manual_note_edit_conflict_restart_and_isolation(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = StudyModel()
    async with client_for(tmp_path, model=model) as client:
        created = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes",
            json={"title": "我的笔记", "body_md": "第一版"},
        )
        assert created.status_code == 201
        note = created.json()
        assert note["revision"] == 1
        assert note["version_id"] == fixture["snapshot"]["version_id"]
        assert note["citations"] == []
        assert "第一版" in note["html"]

        updated = await client.put(
            f"/api/courses/{fixture['course']['id']}/notes/{note['id']}",
            json={"title": "我的笔记", "body_md": "第二版", "revision": 1},
        )
        assert updated.status_code == 200
        assert updated.json()["revision"] == 2
        assert "第二版" in updated.json()["body_md"]

        stale = await client.put(
            f"/api/courses/{fixture['course']['id']}/notes/{note['id']}",
            json={"title": "我的笔记", "body_md": "覆盖", "revision": 1},
        )
        assert stale.status_code == 409
        assert "第二版" in (
            await client.get(f"/api/courses/{fixture['course']['id']}/notes/{note['id']}")
        ).json()["body_md"]

        manual_link = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes",
            json={"title": "手写", "body_md": "[原文](snippet:anything)"},
        )
        assert manual_link.status_code == 422

        other = (await client.post("/api/courses", json={"name": "另一门课"})).json()
        assert (await client.get(f"/api/courses/{other['id']}/notes")).json() == []
        assert (
            await client.get(f"/api/courses/{other['id']}/notes/{note['id']}")
        ).status_code == 404

    async with client_for(tmp_path, model=model) as restarted:
        again = await restarted.get(
            f"/api/courses/{fixture['course']['id']}/notes/{note['id']}"
        )
        assert again.status_code == 200
        assert again.json()["body_md"] == "第二版"
        assert again.json()["revision"] == 2


async def test_generate_note_from_concept_and_answer(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = StudyModel(
        answer_chunks=[f"进程是资源分配单位。[原文](snippet:{fixture['process']})"],
        note_reply={
            "title": "进程与线程笔记",
            "body_md": f"进程是资源分配单位。[原文](snippet:{fixture['process']})",
        },
    )
    async with client_for(tmp_path, model=model) as client:
        answer = await completed_answer(client, fixture)
        assert answer["status"] == "completed"

        from_concept = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "concept", "source_id": fixture["concepts"]["进程"]},
        )
        assert from_concept.status_code == 201, from_concept.text
        note = from_concept.json()
        assert note["source_type"] == "concept"
        assert note["version_id"] == fixture["snapshot"]["version_id"]
        assert note["citations"][0]["snippet_id"] == fixture["process"]
        assert note["expansion"] is False

        from_answer = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "answer", "source_id": answer["id"]},
        )
        assert from_answer.status_code == 201, from_answer.text
        answer_note = from_answer.json()
        assert answer_note["version_id"] == answer["version_id"]
        assert answer_note["citations"][0]["snippet_id"] == fixture["process"]


async def test_invalid_generated_note_and_incomplete_answer_are_rejected(tmp_path):
    fixture = await publish_fixture(tmp_path)
    invalid = StudyModel(
        answer_chunks=["资料不足。"],
        note_reply={"title": "坏引用", "body_md": "[原文](snippet:not-allowed)"},
    )
    async with client_for(tmp_path, model=invalid) as client:
        response = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "concept", "source_id": fixture["concepts"]["进程"]},
        )
        assert response.status_code == 422
        assert (await client.get(f"/api/courses/{fixture['course']['id']}/notes")).json() == []

        insufficient = await completed_answer(client, fixture)
        assert insufficient["status"] == "insufficient"
        rejected = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "answer", "source_id": insufficient["id"]},
        )
        assert rejected.status_code == 422

    failing = StudyModel(note_error=ModelError("temporary", "模型服务暂时不可用。"))
    async with client_for(tmp_path, model=failing) as client:
        response = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "concept", "source_id": fixture["concepts"]["进程"]},
        )
        assert response.status_code == 502
        assert (await client.get(f"/api/courses/{fixture['course']['id']}/notes")).json() == []


async def test_expansion_is_marked_persisted_and_not_in_knowledge(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = StudyModel(
        answer_chunks=[f"进程是资源分配单位。[原文](snippet:{fixture['process']})"],
        expansion_reply={"expansion_md": "进程与线程的调度开销差异还受内核实现影响。"},
        note_reply={"title": "拓展笔记", "body_md": "模型补充（超出课程资料）\n\n调度开销还受内核实现影响。"},
    )
    async with client_for(tmp_path, model=model) as client:
        answer = await completed_answer(client, fixture)
        expansion = await client.post(
            f"/api/courses/{fixture['course']['id']}/expansions",
            json={"answer_id": answer["id"]},
        )
        assert expansion.status_code == 201, expansion.text
        item = expansion.json()
        assert item["status"] == "completed"
        assert item["origin"] == "model_expansion"
        assert item["text"].startswith("> 模型补充（超出课程资料）")
        assert item["version_id"] == answer["version_id"]

        knowledge = (await client.get(f"/api/courses/{fixture['course']['id']}/knowledge")).json()
        assert len(knowledge["concepts"]) == 2
        assert "内核实现" not in json.dumps(knowledge, ensure_ascii=False)

        note = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "expansion", "source_id": item["id"]},
        )
        assert note.status_code == 201, note.text
        saved = note.json()
        assert saved["expansion"] is True
        assert saved["citations"] == []
        assert "模型补充" in saved["body_md"]

        from_concept = await client.post(
            f"/api/courses/{fixture['course']['id']}/expansions",
            json={"concept_id": fixture["concepts"]["线程"]},
        )
        assert from_concept.status_code == 201
        assert from_concept.json()["concept_id"] == fixture["concepts"]["线程"]


async def test_failed_expansion_is_visible_and_cannot_become_a_note(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = StudyModel(
        answer_chunks=[f"进程是资源分配单位。[原文](snippet:{fixture['process']})"],
        expansion_error=ModelError("temporary", "模型服务暂时不可用。"),
    )
    async with client_for(tmp_path, model=model) as client:
        answer = await completed_answer(client, fixture)
        expansion = await client.post(
            f"/api/courses/{fixture['course']['id']}/expansions",
            json={"answer_id": answer["id"]},
        )
        assert expansion.status_code == 201
        failed = expansion.json()
        assert failed["status"] == "failed"
        assert failed["text"] == ""
        assert failed["error_code"] == "temporary"
        rejected = await client.post(
            f"/api/courses/{fixture['course']['id']}/notes/generate",
            json={"source_type": "expansion", "source_id": failed["id"]},
        )
        assert rejected.status_code == 422

        incomplete = await client.post(
            f"/api/courses/{fixture['course']['id']}/expansions",
            json={},
        )
        assert incomplete.status_code == 422


async def test_expansion_origin_survives_model_omission_and_personal_edits(tmp_path):
    fixture = await publish_fixture(tmp_path)
    base = f"/api/courses/{fixture['course']['id']}"
    model = StudyModel(note_reply={"title": "背景笔记", "body_md": "模型漏写来源标记。"})
    async with client_for(tmp_path, model=model) as client:
        expansion = (await client.post(base + "/expansions", json={"concept_id": fixture["concepts"]["进程"]})).json()
        response = await client.post(base + "/notes/generate", json={"source_type": "expansion", "source_id": expansion["id"]})
        assert response.status_code == 201
        note = response.json()
        assert note["body_md"].startswith("> 模型补充（超出课程资料）")
        saved = (await client.put(base + f"/notes/{note['id']}", json={
            "title": "我的拓展笔记", "body_md": "个人改写", "revision": 1})).json()
        assert saved["expansion"] is True
        assert saved["body_md"].startswith("> 模型补充（超出课程资料）")
        model.expansion_reply = {"expansion_md": f"伪造教材依据[原文](snippet:{fixture['process']})"}
        invalid = (await client.post(base + "/expansions", json={"concept_id": fixture["concepts"]["进程"]})).json()
        assert invalid["status"] == "failed"
        assert invalid["error_code"] == "invalid_output"
        assert invalid["text"] == ""


async def test_generations_pin_displayed_and_historical_versions(tmp_path):
    fixture = await publish_fixture(tmp_path)
    old_version = fixture["snapshot"]["version_id"]
    base = f"/api/courses/{fixture['course']['id']}"
    model = StudyModel(answer_chunks=[f"进程说明。[原文](snippet:{fixture['process']})"])
    async with client_for(tmp_path, model=model) as client:
        response = await client.post(base + "/answers/stream", json={
            "question": "进程是什么？", "focus_concept_id": fixture["concepts"]["进程"]})
        answer = next(data["answer"] for event, data in parse_sse(response.text) if event == "done")
        newer_version = await publish_second_version(tmp_path, fixture["course"]["id"])
        old_concept = {"source_type": "concept", "source_id": fixture["concepts"]["进程"],
                       "version_id": old_version}
        note = await client.post(base + "/notes/generate", json=old_concept)
        assert note.status_code == 201, note.text
        assert note.json()["version_id"] == old_version
        assert model.calls[-1]["concept"]["name"] == "进程"
        expansion = await client.post(base + "/expansions", json={
            "concept_id": fixture["concepts"]["进程"], "version_id": old_version})
        assert expansion.status_code == 201, expansion.text
        assert expansion.json()["version_id"] == old_version
        assert model.calls[-1]["concept"] == "进程"
        historical = await client.post(base + "/expansions", json={"answer_id": answer["id"]})
        assert historical.status_code == 201, historical.text
        assert historical.json()["version_id"] == old_version
        assert model.calls[-1]["concept"] == "进程"
        for source_type, source_id in [("answer", answer["id"]), ("expansion", historical.json()["id"])]:
            made = await client.post(base + "/notes/generate", json={
                "source_type": source_type, "source_id": source_id})
            assert made.status_code == 201
            assert made.json()["version_id"] == old_version
            rejected = await client.post(base + "/notes/generate", json={
                "source_type": source_type, "source_id": source_id, "version_id": newer_version})
            assert rejected.status_code == 422
        rejected = await client.post(base + "/expansions", json={
            "answer_id": answer["id"], "version_id": newer_version})
        assert rejected.status_code == 422
        foreign = await publish_fixture(tmp_path)
        old_concept["version_id"] = foreign["snapshot"]["version_id"]
        assert (await client.post(base + "/notes/generate", json=old_concept)).status_code == 404
        assert (await client.post(base + "/expansions", json={
            "concept_id": fixture["concepts"]["进程"], "version_id": foreign["snapshot"]["version_id"]
        })).status_code == 404


async def test_note_sources_keep_unorganized_answer_evidence_and_course_isolation(tmp_path):
    fixture = await publish_fixture(tmp_path)
    course_id = fixture["course"]["id"]
    materials = Materials(tmp_path)
    material = materials.import_material(course_id, "信号量补充.md", "# 信号量\n\n信号量可以协调进程同步。\n".encode())
    fragment = next(f for f in materials.fragments(course_id, material["id"]) if "可以协调" in f["markdown"])
    assert fragment["id"] not in {f["id"] for f in fixture["snapshot"]["fragments"]}
    model = StudyModel(answer_chunks=[f"信号量协调进程同步。[原文](snippet:{fragment['id']})"],
        note_reply={"title": "信号量", "body_md": f"同步说明。[原文](snippet:{fragment['id']})"})
    base = f"/api/courses/{course_id}"
    async with client_for(tmp_path, model=model) as client:
        response = await client.post(base + "/answers/stream", json={"question": "信号量是什么？"})
        answer = next(data["answer"] for event, data in parse_sse(response.text) if event == "done")
        assert answer["status"] == "completed"
        response = await client.post(base + "/notes/generate", json={"source_type": "answer", "source_id": answer["id"]})
        assert response.status_code == 201, response.text
        note = response.json()
        url = base + f"/notes/{note['id']}/sources/{fragment['id']}"
        source = await client.get(url)
        assert source.status_code == 200, source.text
        assert source.json()["markdown"] == fragment["markdown"]
        assert source.json()["version_id"] == fixture["snapshot"]["version_id"]
        assert note["citations"][0]["source_url"] == url
        assert (await client.get(base + f"/notes/{note['id']}/sources/{fixture['thread']}")).status_code == 404
        other = materials.create_course("另一门课")
        assert (await client.get(url.replace(course_id, other["id"]))).status_code == 404
        await publish_second_version(tmp_path, course_id)
        assert (await client.get(url)).json()["markdown"] == fragment["markdown"]
        assert (await client.get(base + f"/notes/{note['id']}")).json()["needs_review"] is False
        model.note_reply = {"title": "进程", "body_md": f"说明[原文](snippet:{fixture['process']})"}
        concept_note = (await client.post(base + "/notes/generate", json={
            "source_type": "concept", "source_id": fixture["concepts"]["进程"],
            "version_id": fixture["snapshot"]["version_id"]})).json()
        source = await client.get(concept_note["citations"][0]["source_url"])
        assert source.status_code == 200
        assert "进程是程序的一次执行" in source.json()["markdown"]


async def test_real_conflict_publication_preserves_concurrent_edits_and_reviews_only_related_notes(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    process = next(c for c in previous["concepts"] if c["name"] == "进程")
    thread = next(c for c in previous["concepts"] if c["name"] == "线程")
    snippet = process["citations"][0]["snippet_id"]
    model = StudyModel(answer_chunks=[f"进程说明。[原文](snippet:{snippet})"])
    base = f"/api/courses/{course['id']}"
    async with client_for(tmp_path, model=model) as client:
        response = await client.post(base + "/answers/stream", json={"question": "进程是什么？"})
        answer = next(data["answer"] for event, data in parse_sse(response.text) if event == "done")
        notes = {}
        for name, source_type, source_id in [("process", "concept", process["id"]),
                                           ("thread", "concept", thread["id"]),
                                           ("answer", "answer", answer["id"])]:
            result = await client.post(base + "/notes/generate", json={"source_type": source_type, "source_id": source_id})
            assert result.status_code == 201
            notes[name] = result.json()
        notes["manual"] = (await client.post(base + "/notes", json={"title": "自学安排", "body_md": "周末复习"})).json()
        material, replies = conflict_supplement(tmp_path, course["id"], previous)
        rendering, release = asyncio.Event(), asyncio.Event()

        class PausedModel(BuildModel):
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
            for name in ("process", "answer"):
                result = await client.put(base + f"/notes/{notes[name]['id']}", json={
                    "title": "个人修改", "body_md": f"发布期间修改 {name}", "revision": 1})
                assert result.status_code == 200
                assert result.json()["needs_review"] is False
        finally:
            release.set()
            await asyncio.wait_for(running, 5)
        assert jobs.get(course["id"], task["id"])["status"] == "completed"
        current = jobs.knowledge.snapshot(course["id"])
        assert next(c for c in current["concepts"] if c["id"] == process["id"])["conflicts"]
        assert all(f in current["fragments"] for f in previous["fragments"])
        for name, note in notes.items():
            saved = (await client.get(base + f"/notes/{note['id']}")).json()
            assert saved["version_id"] == previous["version_id"]
            assert saved["needs_review"] is (name in ("process", "answer"))
            if name in ("process", "answer"):
                assert saved["body_md"] == f"发布期间修改 {name}"
                assert saved["revision"] == 2
                assert (await client.get(saved["citations"][0]["source_url"])).status_code == 200
                stale = await client.put(base + f"/notes/{note['id']}", json={
                    "title": "旧草稿", "body_md": "不应覆盖", "revision": 1})
                assert stale.status_code == 409


async def test_notes_and_answers_survive_a_second_version(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = StudyModel(
        answer_chunks=[f"进程是资源分配单位。[原文](snippet:{fixture['process']})"],
        note_reply={
            "title": "进程笔记",
            "body_md": f"我的理解 [原文](snippet:{fixture['process']})",
        },
    )
    async with client_for(tmp_path, model=model) as client:
        answer = await completed_answer(client, fixture)
        process_note = (
            await client.post(
                f"/api/courses/{fixture['course']['id']}/notes/generate",
                json={"source_type": "concept", "source_id": fixture["concepts"]["进程"]},
            )
        ).json()
        edited = await client.put(
            f"/api/courses/{fixture['course']['id']}/notes/{process_note['id']}",
            json={"title": "我的进程笔记", "body_md": "我自己的修改", "revision": 1},
        )
        assert edited.status_code == 200

        model.note_reply = {
            "title": "线程笔记",
            "body_md": f"线程说明 [原文](snippet:{fixture['thread']})",
        }
        thread_note = (
            await client.post(
                f"/api/courses/{fixture['course']['id']}/notes/generate",
                json={"source_type": "concept", "source_id": fixture["concepts"]["线程"]},
            )
        ).json()
        assert thread_note["needs_review"] is False

    second = await publish_second_version(tmp_path, fixture["course"]["id"])
    async with client_for(tmp_path, model=model) as client:
        knowledge = (await client.get(f"/api/courses/{fixture['course']['id']}/knowledge")).json()
        assert knowledge["version_id"] == second

        saved = (
            await client.get(
                f"/api/courses/{fixture['course']['id']}/notes/{process_note['id']}"
            )
        ).json()
        assert saved["body_md"] == "我自己的修改"
        assert saved["revision"] == 2
        assert saved["version_id"] == fixture["snapshot"]["version_id"]
        assert saved["needs_review"] is True
        assert "依据已变化" in saved["review_reason"]

        unchanged = (
            await client.get(
                f"/api/courses/{fixture['course']['id']}/notes/{thread_note['id']}"
            )
        ).json()
        assert unchanged["needs_review"] is False

        old_answer = (
            await client.get(
                f"/api/courses/{fixture['course']['id']}/answers/{answer['id']}"
            )
        ).json()
        assert old_answer["version_id"] == fixture["snapshot"]["version_id"]
        source = await client.get(
            f"/api/courses/{fixture['course']['id']}/knowledge/versions/"
            f"{old_answer['version_id']}/sources/{fixture['process']}"
        )
        assert source.status_code == 200
        assert "进程是程序的一次执行" in source.json()["markdown"]

        summary = (await client.get(f"/api/courses/{fixture['course']['id']}/notes")).json()
        by_id = {item["id"]: item for item in summary}
        assert by_id[process_note["id"]]["needs_review"] is True
        assert by_id[thread_note["id"]]["needs_review"] is False
