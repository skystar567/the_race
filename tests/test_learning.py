"""Learning features over one published snapshot: Q&A, notes, route and export."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from campus.answers import Answers
from campus.api import create_app
from campus.exports import Exporter
from campus.knowledge import Knowledge
from campus.knowledge_models import (
    Citation, ConceptDraft, KnowledgeDraft, PageDraft, PagesDraft, RelationDraft, ScopeInput,
)
from campus.knowledge_validation import build_snapshot
from campus.materials import Materials
from campus.notes_store import NotesStore
from campus.routes import RouteService
from campus.scopes import resolve_scope

pytestmark = pytest.mark.anyio

SOURCE = (
    "# 第二章 进程\n\n"
    "## 2.1 进程的定义\n\n"
    "进程是程序的一次执行，是系统进行资源分配的基本单位。\n\n"
    "## 2.2 线程\n\n"
    "线程是进程中的一个执行单元，是处理机调度的基本单位。\n"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class StreamModel:
    api_key = "test-key"

    def __init__(self, answer):
        self.answer = answer

    async def stream(self, instructions, content):
        for chunk in [self.answer[i:i + 12] for i in range(0, len(self.answer), 12)]:
            yield chunk


async def published(data_dir: Path):
    materials = Materials(data_dir)
    course = materials.create_course("操作系统")
    material = materials.import_material(course["id"], "教材.md", SOURCE.encode())
    detail = materials.detail(course["id"], material["id"])
    chapters = {chapter["title"]: chapter["id"] for chapter in detail["chapters"]}
    source = resolve_scope(materials, course["id"], ScopeInput(material_ids=[material["id"]]))
    fragments = {fragment["markdown"].strip(): fragment["id"] for fragment in source["fragments"]}
    process_text = next(text for text in fragments if "进程是程序" in text)
    thread_text = next(text for text in fragments if "线程是进程" in text)
    process_id, thread_id = fragments[process_text], fragments[thread_text]
    draft = KnowledgeDraft(
        concepts=[
            ConceptDraft(key="process", name="进程", aliases=["Process"],
                         definition="程序的一次执行，是资源分配的基本单位。",
                         chapter_ids=[chapters["2.1 进程的定义"]],
                         citations=[Citation(snippet_id=process_id, quote="进程是程序的一次执行")]),
            ConceptDraft(key="thread", name="线程", aliases=[],
                         definition="进程中的执行单元，是处理机调度的基本单位。",
                         chapter_ids=[chapters["2.2 线程"]],
                         citations=[Citation(snippet_id=thread_id, quote="线程是进程中的一个执行单元")]),
        ],
        relations=[RelationDraft(from_key="process", to_key="thread", kind="precedes",
                                 origin="suggested", citation=None,
                                 reason="先理解资源分配单位，再理解执行单元。")],
    )
    pages = PagesDraft(pages=[
        PageDraft(key="process", page_md="# 进程\n\n进程是资源分配的基本单位。[原文](snippet:%s)" % process_id,
                  citations=[Citation(snippet_id=process_id, quote="进程是程序的一次执行")]),
        PageDraft(key="thread", page_md="# 线程\n\n线程是处理机调度的基本单位。[原文](snippet:%s)" % thread_id,
                  citations=[Citation(snippet_id=thread_id, quote="线程是进程中的一个执行单元")]),
    ])
    task_id = "task-learning-1"
    snapshot = build_snapshot(course["id"], task_id, draft, pages, source)
    knowledge = Knowledge(data_dir)
    knowledge.publish_task(course["id"], task_id, snapshot)
    notes = NotesStore(knowledge, data_dir)
    note = notes.create(course["id"], "我的进程笔记", "进程是资源单位。",
                        citations=[{"snippet_id": process_id, "quote": "进程是程序的一次执行"}])
    snapshot = knowledge.snapshot(course["id"])
    concept_ids = {concept["name"]: concept["id"] for concept in snapshot["concepts"]}
    return {"materials": materials, "course": course, "material": material, "source": source,
            "knowledge": knowledge, "notes": notes, "note": note,
            "process_id": process_id, "thread_id": thread_id,
            "process_concept_id": concept_ids["进程"], "thread_concept_id": concept_ids["线程"],
            "version_id": knowledge.current_id(course["id"])}


async def test_notes_create_update_and_health(tmp_path):
    state = await published(tmp_path)
    notes = state["notes"]
    note = notes.get(state["note"]["id"])
    assert note["title"] == "我的进程笔记"
    assert note["citations"][0]["snippet_id"] == state["process_id"]
    updated = notes.update(note["id"], title="改名", markdown="自己的理解。")
    assert updated["title"] == "改名"
    assert updated["citations"] == note["citations"]
    assert notes.health(note["id"])["healthy"] is True


async def test_answers_cite_only_the_version(tmp_path):
    state = await published(tmp_path)
    question = "进程是什么？"
    answer = f"进程是程序的一次执行 [F:{state['process_id']}]。"
    model = StreamModel(answer)
    answers = Answers(state["materials"], state["knowledge"], model)
    result = await answers.ask(state["course"]["id"], question)
    assert result["status"] == "completed"
    assert result["citations"][0]["snippet_id"] == state["process_id"]
    assert result["version_id"] == state["version_id"]

    bad = Answers(state["materials"], state["knowledge"], StreamModel("进程 [F:not-in-scope]"))
    result = await bad.ask(state["course"]["id"], question)
    assert result["status"] == "invalid_citations"


async def test_answers_expansion_is_explicit_and_citable(tmp_path):
    state = await published(tmp_path)
    answer = f"进程是资源单位 [F:{state['process_id']}]。资料外：可以类比工厂。"
    answers = Answers(state["materials"], state["knowledge"], StreamModel(answer))
    result = await answers.ask(state["course"]["id"], "进程是什么？", expansion=True)
    assert result["status"] == "completed_with_expansion"
    assert result["citations"][0]["quote"]
    assert result["warnings"]


async def test_answers_stream_reports_done(tmp_path):
    state = await published(tmp_path)
    answer = f"进程是资源单位 [F:{state['process_id']}]。"
    answers = Answers(state["materials"], state["knowledge"], StreamModel(answer))
    events = [event async for event in answers.stream(state["course"]["id"], "进程是什么？")]
    assert events[0]["type"] == "delta"
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "completed"


async def test_route_uses_precedes_and_marks_suggested(tmp_path):
    state = await published(tmp_path)
    route = RouteService(state["knowledge"]).plan(state["course"]["id"], state["thread_concept_id"])
    assert route["status"] == "partial"
    assert route["route"] == [state["process_concept_id"], state["thread_concept_id"]]
    assert route["unverified"] == [{"from": state["process_concept_id"],
                                    "to": state["thread_concept_id"], "reason": "suggested"}]


async def test_export_package_and_links(tmp_path):
    state = await published(tmp_path)
    archive, manifest = Exporter(state["materials"], state["knowledge"], state["notes"]).export(
        state["course"]["id"])
    assert manifest["counts"]["notes"] == 1
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = set(bundle.namelist())
        for expected in ["README.md", "manifest.json", "knowledge/index.md",
                         "relations.md", "notes/index.md", "sources.md",
                         f"notes/{state['note']['id']}.md"]:
            assert expected in names
        concept = bundle.read(f"knowledge/concepts/{state['process_concept_id']}.md").decode()
        assert "../../sources.md#frag-" in concept
        note = bundle.read(f"notes/{state['note']['id']}.md").decode()
        assert "../sources.md#frag-" in note


async def test_http_learning_surface(tmp_path):
    state = await published(tmp_path)
    app = create_app(tmp_path, model=StreamModel(f"进程是资源单位 [F:{state['process_id']}]。"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        route = await client.get(f"/api/courses/{state['course']['id']}/route",
                                 params={"target": state["thread_concept_id"]})
        assert route.status_code == 200
        assert route.json()["route"] == [state["process_concept_id"], state["thread_concept_id"]]
        notes = await client.get(f"/api/courses/{state['course']['id']}/notes")
        assert notes.status_code == 200 and len(notes.json()) == 1
        created = await client.post(f"/api/courses/{state['course']['id']}/notes", json={
            "title": "第二篇", "markdown": "自己的话。",
            "citations": [{"snippet_id": state["process_id"],
                           "quote": "进程是程序的一次执行"}],
        })
        assert created.status_code == 201
        answer = await client.post(f"/api/courses/{state['course']['id']}/ask",
                                   json={"question": "进程是什么？"})
        assert answer.status_code == 200
        assert answer.json()["status"] == "completed"
        stored = await client.get(f"/api/courses/{state['course']['id']}/answers")
        assert stored.status_code == 200 and len(stored.json()) == 1
        assert stored.json()[0]["version_id"] == state["version_id"]
        export = await client.get(f"/api/courses/{state['course']['id']}/export")
        assert export.status_code == 200 and export.content[:2] == b"PK"
