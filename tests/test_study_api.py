"""Ticket 05/06/11: personal notes, explicit expansion, preservation."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from campus.api import create_app
from campus.jobs import Jobs
from campus.knowledge import Knowledge
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.model import ModelError

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

    async def stream(self, instructions, content):
        for chunk in self.answer_chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    async def complete(self, instructions, content, schema, *, thinking=True):
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


def publish_second_version(data_dir: Path, course_id: str, change_process: bool):
    """Test fixture simulating ticket 08's pointer switch; not production code."""
    knowledge = Knowledge(data_dir)
    first = knowledge.snapshot(course_id)
    snapshot = {
        key: first[key]
        for key in ("concepts", "relations", "chapters", "fragments", "selection",
                    "validated", "summary")
    }
    if change_process:
        for fragment in snapshot["fragments"]:
            if "进程是程序的一次执行" in fragment["markdown"]:
                fragment["markdown"] = "进程是程序启动后的运行实例。"
    version_id = str(uuid4())
    with knowledge.connect() as db:
        db.execute(
            """INSERT INTO knowledge_version
            (id,course_id,task_id,parent_version_id,state,snapshot_json)
            VALUES (?,?,?,?, 'published', ?)""",
            (version_id, course_id, str(uuid4()), first["version_id"],
             json.dumps(snapshot, ensure_ascii=False)),
        )
        db.execute(
            "UPDATE course_knowledge SET current_version_id=? WHERE course_id=?",
            (version_id, course_id),
        )
    return version_id


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

    second = publish_second_version(tmp_path, fixture["course"]["id"], change_process=True)
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
