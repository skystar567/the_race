"""Ticket 04: version-pinned grounded questions, scope and citation handling."""

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from campus.api import create_app
from campus.answers import Answers, AskInput
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
    "线程是进程中的一个执行单元，是处理机调度的基本单位。同一进程内的多个线程共享该进程的资源。\n\n"
    "## 2.3 对比\n\n"
    "进程拥有独立的资源，线程共享所属进程的资源。线程切换的开销通常小于进程切换。\n"
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
    """Controlled pipeline output; not a real model run."""

    api_key = "test-key"

    def __init__(self, replies):
        self.replies = replies

    async def complete(self, instructions, content, schema, *, thinking=True):
        for name, reply in self.replies.items():
            if name in instructions:
                return reply
        raise AssertionError(f"unexpected build step: {instructions[:60]}")


class AnswerModel:
    api_key = "test-key"

    def __init__(self, chunks=None, resolver=None):
        self.chunks = chunks or []
        self.resolver = {"concept_ids": []} if resolver is None else resolver
        self.stream_calls = 0
        self.complete_calls = 0
        self.received = None

    async def complete(self, instructions, content, schema, *, thinking=True):
        self.complete_calls += 1
        if isinstance(self.resolver, Exception):
            raise self.resolver
        return self.resolver

    async def stream(self, instructions, content):
        self.stream_calls += 1
        self.received = content
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


async def publish_fixture(data_dir: Path):
    materials = Materials(data_dir)
    course = materials.create_course("操作系统")
    material = materials.import_material(course["id"], "教材.md", SOURCE.encode())
    detail = materials.detail(course["id"], material["id"])
    chapters = {chapter["title"]: chapter["id"] for chapter in detail["chapters"]}
    fragments = materials.fragments(course["id"], material["id"])
    process = next(f for f in fragments if "进程是程序的一次执行" in f["markdown"])
    thread = next(f for f in fragments if "线程是进程中的一个执行单元" in f["markdown"])
    compare = next(f for f in fragments if "线程切换的开销" in f["markdown"])

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
        "relations": [
            {
                "from_key": "process", "to_key": "thread", "kind": "contrasts",
                "origin": "suggested", "citation": None,
                "reason": "两者常被放在一起辨析。",
            }
        ],
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
    assert jobs.get(course["id"], task["id"])["status"] == "completed"
    snapshot = jobs.knowledge.snapshot(course["id"])
    concepts = {concept["name"]: concept["id"] for concept in snapshot["concepts"]}
    return {
        "course": course, "material": material, "snapshot": snapshot,
        "chapters": chapters, "concepts": concepts,
        "process": process["id"], "thread": thread["id"], "compare": compare["id"],
    }


def parse_sse(body: str) -> list[tuple[str, dict]]:
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


async def ask(client, course_id: str, question: str, **extra):
    return await client.post(
        f"/api/courses/{course_id}/answers/stream",
        json={"question": question, **extra},
    )


async def test_answer_is_version_pinned_and_citations_open_after_restart(tmp_path):
    fixture = await publish_fixture(tmp_path)
    chunks = [
        f"进程是资源分配和调度的独立单位。[原文](snippet:{fixture['process']})",
        f"\n\n线程是处理机调度的基本单位。[原文](snippet:{fixture['thread']})",
    ]
    model = AnswerModel(chunks)
    async with client_for(tmp_path, model=model) as client:
        response = await ask(client, fixture["course"]["id"], "进程和线程有什么区别？")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(response.text)
        start = next(data for name, data in events if name == "start")
        done = next(data for name, data in events if name == "done")["answer"]
        assert start["version_id"] == fixture["snapshot"]["version_id"]
        assert start["scope"]["label"] == "全部已导入资料"
        assert start["evidence_count"] >= 2
        assert [data["text"] for name, data in events if name == "delta"] == chunks
        assert done["status"] == "completed"
        assert {citation["snippet_id"] for citation in done["citations"]} == {
            fixture["process"], fixture["thread"]
        }
        assert "snippet:" in done["html"]
        assert model.received["question"] == "进程和线程有什么区别？"
        assert model.received["focus"] is None

        detail = (await client.get(f"/api/courses/{fixture['course']['id']}/answers/{done['id']}")).json()
        assert detail["citation_count"] == 2
        assert detail["text"].startswith("进程是资源分配")
        assert detail["version_id"] == fixture["snapshot"]["version_id"]
        history = (await client.get(f"/api/courses/{fixture['course']['id']}/answers")).json()
        assert [item["id"] for item in history] == [done["id"]]
        source = await client.get(
            f"/api/courses/{fixture['course']['id']}/knowledge/versions/"
            f"{detail['version_id']}/sources/{fixture['process']}"
        )
        assert source.status_code == 200

    async with client_for(tmp_path, model=AnswerModel(chunks)) as restarted:
        again = (await restarted.get(
            f"/api/courses/{fixture['course']['id']}/answers/{done['id']}"
        )).json()
        assert again["status"] == "completed"
        assert again["version_id"] == fixture["snapshot"]["version_id"]


async def test_two_character_terms_and_aliases_are_retrieved(tmp_path):
    fixture = await publish_fixture(tmp_path)
    by_question = {}

    class Recording(AnswerModel):
        async def stream(self, instructions, content):
            by_question[content["question"]] = content
            async for chunk in super().stream(instructions, content):
                yield chunk

    model = Recording([f"回答。[原文](snippet:{fixture['thread']})"])
    async with client_for(tmp_path, model=model) as client:
        await ask(client, fixture["course"]["id"], "线程是什么？")
        await ask(client, fixture["course"]["id"], "Process 是什么？")
    thread_evidence = {item["id"] for item in by_question["线程是什么？"]["evidence"]}
    process_evidence = {item["id"] for item in by_question["Process 是什么？"]["evidence"]}
    assert fixture["thread"] in thread_evidence
    assert fixture["process"] in process_evidence


async def test_focus_concept_does_not_restrict_evidence(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel([f"线程与进程的差别。[原文](snippet:{fixture['thread']})"])
    async with client_for(tmp_path, model=model) as client:
        response = await ask(
            client, fixture["course"]["id"], "它和进程有什么区别？",
            focus_concept_id=fixture["concepts"]["进程"],
        )
        events = parse_sse(response.text)
        start = next(data for name, data in events if name == "start")
        done = next(data for name, data in events if name == "done")["answer"]
    assert start["focus"] == "进程"
    evidence_ids = {item["id"] for item in model.received["evidence"]}
    assert fixture["thread"] in evidence_ids
    assert done["status"] == "completed"


async def test_scope_limits_evidence_and_rejects_ids_outside_the_version(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel([f"线程说明。[原文](snippet:{fixture['thread']})"])
    async with client_for(tmp_path, model=model) as client:
        response = await ask(
            client, fixture["course"]["id"], "线程是什么？",
            chapter_ids=[fixture["chapters"]["2.2 线程"]],
        )
        assert response.status_code == 200
        assert fixture["process"] not in {item["id"] for item in model.received["evidence"]}
        start = next(data for name, data in parse_sse(response.text) if name == "start")
        assert "2.2 线程" in start["scope"]["label"]

        outside = await ask(
            client, fixture["course"]["id"], "线程是什么？", chapter_ids=["not-in-version"]
        )
        assert outside.status_code == 422
        foreign_course = (await client.post("/api/courses", json={"name": "另一门课"})).json()
        foreign = await ask(client, foreign_course["id"], "线程是什么？")
        assert foreign.status_code == 409


async def test_invalid_citation_is_never_marked_completed(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel([
        f"有效引用。[原文](snippet:{fixture['process']})",
        " 无效引用。[原文](snippet:not-allowed)",
    ])
    async with client_for(tmp_path, model=model) as client:
        response = await ask(client, fixture["course"]["id"], "进程是什么？")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert done["status"] == "citation_failed"
        assert [c["snippet_id"] for c in done["citations"]] == [fixture["process"]]
        assert done["error_code"] == "invalid_citation"


async def test_answer_without_citations_is_insufficient(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel(["这里似乎没有足够资料。"])
    async with client_for(tmp_path, model=model) as client:
        response = await ask(client, fixture["course"]["id"], "进程是什么？")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert done["status"] == "insufficient"
        assert done["citations"] == []


async def test_no_evidence_skips_the_answer_model_and_does_not_claim_absence(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel([f"不应调用。[原文](snippet:{fixture['process']})"], resolver={"concept_ids": []})
    async with client_for(tmp_path, model=model) as client:
        response = await ask(client, fixture["course"]["id"], "死锁是什么？")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert done["status"] == "insufficient"
        assert "不表示教材中没有" in done["text"]
        assert model.stream_calls == 0


async def test_vague_question_uses_validated_model_routing(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel(
        [f"线程是执行单元。[原文](snippet:{fixture['thread']})"],
        resolver={"concept_ids": [fixture["concepts"]["线程"]]},
    )
    async with client_for(tmp_path, model=model) as client:
        response = await ask(client, fixture["course"]["id"], "这个怎么理解？")
        start = next(data for name, data in parse_sse(response.text) if name == "start")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert start["resolution"] == "model"
        assert fixture["thread"] in {item["id"] for item in model.received["evidence"]}
        assert done["status"] == "completed"

    invalid = AnswerModel(
        [f"回答。[原文](snippet:{fixture['thread']})"],
        resolver={"concept_ids": ["not-a-concept"]},
    )
    async with client_for(tmp_path, model=invalid) as client:
        response = await ask(client, fixture["course"]["id"], "这个怎么理解？")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert done["status"] == "insufficient"
        assert invalid.stream_calls == 0


async def test_interrupted_and_empty_streams_are_visible_failures(tmp_path):
    fixture = await publish_fixture(tmp_path)
    interrupted = AnswerModel(["部分回答", ModelError("interrupted", "回答连接中断，已显示的内容尚未完成。")])
    async with client_for(tmp_path, model=interrupted) as client:
        response = await ask(client, fixture["course"]["id"], "进程是什么？")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert done["status"] == "interrupted"
        assert done["text"] == "部分回答"
        assert done["citations"] == []

    empty = AnswerModel([])
    async with client_for(tmp_path, model=empty) as client:
        response = await ask(client, fixture["course"]["id"], "进程是什么？")
        done = next(data for name, data in parse_sse(response.text) if name == "done")["answer"]
        assert done["status"] == "failed"
        assert done["error_code"] == "empty_output"


async def test_answer_history_is_isolated_by_course(tmp_path):
    fixture = await publish_fixture(tmp_path)
    model = AnswerModel([f"回答。[原文](snippet:{fixture['process']})"])
    async with client_for(tmp_path, model=model) as client:
        response = await ask(client, fixture["course"]["id"], "进程是什么？")
        answer_id = next(data for name, data in parse_sse(response.text) if name == "start")["answer_id"]
        other = (await client.post("/api/courses", json={"name": "另一门课"})).json()
        assert (await client.get(f"/api/courses/{other['id']}/answers/{answer_id}")).status_code == 404
        assert (await client.get(f"/api/courses/{other['id']}/answers")).json() == []


@pytest.mark.parametrize("selection", ["all", "material", "chapter"])
async def test_unorganized_sources_are_retrieved_and_frozen(tmp_path, selection):
    fixture = await publish_fixture(tmp_path)
    course_id = fixture["course"]["id"]
    model = AnswerModel()
    async with client_for(tmp_path, model=model) as client:
        imported = (await client.post(
            f"/api/courses/{course_id}/materials?filename=补充.md",
            content="# 虚拟内存\n\n虚拟内存使用地址转换实现内存抽象。".encode(),
        )).json()
        details = (await client.get(f"/api/courses/{course_id}/materials/{imported['id']}")).json()
        fragments = (await client.get(
            f"/api/courses/{course_id}/materials/{imported['id']}/fragments"
        )).json()
        source = next(fragment for fragment in fragments if "地址转换" in fragment["markdown"])
        model.chunks = [f"地址转换实现内存抽象。[原文](snippet:{source['id']})"]
        scope = ({"material_ids": [imported["id"]]} if selection == "material" else
                 {"chapter_ids": [details["chapters"][0]["id"]]} if selection == "chapter" else {})
        response = await ask(client, course_id, "虚拟内存地址转换是什么？", **scope)
        answer = next(data["answer"] for name, data in parse_sse(response.text) if name == "done")
        assert answer["status"] == "completed"
        assert source["id"] not in {fragment["id"] for fragment in fixture["snapshot"]["fragments"]}
        citation = answer["citations"][0]
        opened = (await client.get(citation["source_url"])).json()
        assert opened["markdown"] == source["markdown"]
        assert opened["filename"] == "补充.md"
        assert opened["version_id"] == fixture["snapshot"]["version_id"]
        assert opened["html"] == source["html"]
        other = (await client.post("/api/courses", json={"name": "其他课"})).json()
        assert (await client.get(citation["source_url"].replace(course_id, other["id"]))).status_code == 404
        assert (await ask(client, course_id, "地址转换是什么？", material_ids=["foreign"])).status_code == 422

    # A saved answer owns the evidence it presented, independently of source-file availability.
    (tmp_path / "originals" / f"{imported['id']}.md").unlink()
    async with client_for(tmp_path, model=AnswerModel()) as restarted:
        saved_source = await restarted.get(citation["source_url"])
        assert saved_source.status_code == 200
        assert saved_source.json() == opened


async def test_requested_old_version_pins_catalog_and_rejects_foreign_version(tmp_path):
    fixture = await publish_fixture(tmp_path)
    knowledge = Knowledge(tmp_path)
    old = fixture["snapshot"]
    updated = deepcopy(old)
    concept = next(item for item in updated["concepts"] if item["name"] == "进程")
    concept["definition"] = "新版定义。"
    knowledge.publish_task(fixture["course"]["id"], str(uuid4()), updated,
                           parent_version_id=old["version_id"])
    model = AnswerModel([f"进程说明。[原文](snippet:{fixture['process']})"])
    async with client_for(tmp_path, model=model) as client:
        result = await ask(client, fixture["course"]["id"], "进程是什么？",
                           version_id=old["version_id"])
        answer = next(data["answer"] for name, data in parse_sse(result.text) if name == "done")
        assert answer["version_id"] == old["version_id"]
        assert next(c for c in model.received["concept_catalog"] if c["name"] == "进程")["definition"] != "新版定义。"
        assert fixture["concepts"]["进程"] in answer["concept_ids"]
        other = (await client.post("/api/courses", json={"name": "其他课"})).json()
        rejected = await ask(client, other["id"], "进程是什么？", version_id=old["version_id"])
        assert rejected.status_code == 409
        assert (await client.get(answer["citations"][0]["source_url"])).json()["version_id"] == old["version_id"]


async def test_conflicting_claims_and_review_status_reach_answer_context(tmp_path):
    fixture = await publish_fixture(tmp_path)
    knowledge = Knowledge(tmp_path)
    snapshot = deepcopy(fixture["snapshot"])
    concept = next(item for item in snapshot["concepts"] if item["name"] == "进程")
    second = {"snippet_id": fixture["thread"], "quote": "线程是进程中的一个执行单元"}
    concept["citations"].append(second)
    concept["status"] = "needs_review"
    concept["conflicts"] = [{"id": str(uuid4()), "reason": "术语适用范围待核对", "claims": [
        {"statement": "进程说法", "context": "进程章节", "citation": concept["citations"][0]},
        {"statement": "线程说法", "context": "线程章节", "citation": second},
    ]}]
    snapshot["summary"]["conflicts"] = 1
    version_id = knowledge.publish_task(fixture["course"]["id"], str(uuid4()), snapshot,
                                        parent_version_id=fixture["snapshot"]["version_id"])
    model = AnswerModel([f"资料范围待核对。[原文](snippet:{fixture['process']})"])
    async with client_for(tmp_path, model=model) as client:
        result = await ask(client, fixture["course"]["id"], "进程是什么？", version_id=version_id)
        assert result.status_code == 200
    context = next(c for c in model.received["concept_catalog"] if c["name"] == "进程")
    assert context["status"] == "needs_review"
    assert len(context["conflicts"][0]["claims"]) == 2
    assert {fixture["process"], fixture["thread"]} <= {item["id"] for item in model.received["evidence"]}


async def test_legacy_answer_table_is_migrated_and_sources_use_saved_version(tmp_path):
    fixture = await publish_fixture(tmp_path)
    course_id = fixture["course"]["id"]
    async with client_for(tmp_path, model=AnswerModel([
        f"进程说明。[原文](snippet:{fixture['process']})"
    ])) as client:
        response = await ask(client, course_id, "进程是什么？")
        answer = next(data["answer"] for name, data in parse_sse(response.text) if name == "done")
    # Recreate the previous release's schema, retaining its saved answer row.
    with sqlite3.connect(tmp_path / "courses.sqlite3") as db:
        db.execute("ALTER TABLE answer DROP COLUMN sources_json")
        db.execute("ALTER TABLE answer DROP COLUMN context_json")
    newer = deepcopy(fixture["snapshot"])
    newer["concepts"][0]["definition"] = "更新后的说明。"
    Knowledge(tmp_path).publish_task(course_id, str(uuid4()), newer,
                                     parent_version_id=fixture["snapshot"]["version_id"])
    async with client_for(tmp_path, model=AnswerModel()) as restarted:
        response = await restarted.get(answer["citations"][0]["source_url"])
        assert response.status_code == 200
        assert response.json()["version_id"] == fixture["snapshot"]["version_id"]
        assert "进程是程序的一次执行" in response.json()["markdown"]


@pytest.mark.parametrize("consume_delta", [False, True])
async def test_closing_public_answer_stream_persists_interrupted_status(tmp_path, consume_delta):
    fixture = await publish_fixture(tmp_path)
    course_id = fixture["course"]["id"]
    answers = Answers(tmp_path, model=AnswerModel(["部分回答", "尚未完成"]))
    stream = answers.stream(await answers.prepare(course_id, AskInput(question="进程是什么？")))
    start = await anext(stream)
    if consume_delta:
        await anext(stream)
    await stream.aclose()
    saved = answers.detail(course_id, start["data"]["answer_id"])
    assert saved["status"] == "interrupted"
    assert saved["text"] == ("部分回答" if consume_delta else "")
