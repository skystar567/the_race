"""Build a controlled ticket-02 browser fixture.

This sample text and the scripted model output are test data, not the real
textbook and not a real DeepSeek run. The fixture exists so the graph, concept
page, citation dialog and failure state can be checked in a browser.
"""

import argparse
import asyncio
import json
import shutil
from pathlib import Path

from campus.jobs import Jobs
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.model import ModelError

SAMPLE = """# 第二章 进程的描述与控制

## 2.1 进程的定义

进程是程序的一次执行。进程是系统进行资源分配和调度的独立单位。

以下内容仅用于渲染验收：$1 + 1 = 2$。

```python
print("render fixture")
```

![进程示意图](images/process-fixture.png)

## 2.2 线程

线程是进程中的一个执行单元，是处理机调度的基本单位。
"""

FAILING_SAMPLE = """# 附录 受控失败样本

## A.1 说明

这段受控文本用于验证整理失败时不会发布知识。
"""


class ScriptedModel:
    api_key = "fixture"

    def __init__(self, replies=None, failure=None):
        self.replies = replies or {}
        self.failure = failure

    async def complete(self, instructions, content, schema, *, thinking=True):
        if self.failure is not None:
            raise self.failure
        for name, reply in self.replies.items():
            if name in instructions:
                return reply
        raise AssertionError(f"unexpected model step: {instructions[:80]}")


def seed(data_dir: Path):
    shutil.rmtree(data_dir, ignore_errors=True)
    materials = Materials(data_dir)
    course = materials.create_course("操作系统（受控验收样本）")
    material = materials.import_material(course["id"], "教材节选（受控样本）.md", SAMPLE.encode())
    detail = materials.detail(course["id"], material["id"])
    chapters = {chapter["title"]: chapter["id"] for chapter in detail["chapters"]}
    fragments = materials.fragments(course["id"], material["id"])
    process_snippet = next(f for f in fragments if "进程是程序的一次执行" in f["markdown"])
    thread_snippet = next(f for f in fragments if "线程是进程中的一个执行单元" in f["markdown"])

    draft = {
        "concepts": [
            {
                "key": "process",
                "name": "进程",
                "aliases": ["Process"],
                "definition": "程序的一次执行，是系统进行资源分配和调度的独立单位。",
                "chapter_ids": [chapters["2.1 进程的定义"]],
                "citations": [
                    {"snippet_id": process_snippet["id"], "quote": "进程是程序的一次执行。"}
                ],
            },
            {
                "key": "thread",
                "name": "线程",
                "aliases": [],
                "definition": "进程中的一个执行单元，是处理机调度的基本单位。",
                "chapter_ids": [chapters["2.2 线程"]],
                "citations": [
                    {"snippet_id": thread_snippet["id"], "quote": "线程是进程中的一个执行单元"}
                ],
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
            },
            {
                "from_key": "process",
                "to_key": "thread",
                "kind": "contrasts",
                "origin": "suggested",
                "citation": None,
                "reason": "两者常被放在一起辨析：进程拥有资源，线程是其中被调度的执行流。",
            },
        ],
    }
    page_output = {
        "pages": [
            {
                "key": "process",
                "page_md": (
                    "进程是程序的一次执行，也是资源分配和调度的独立单位。"
                    f"[原文](snippet:{process_snippet['id']})\n\n"
                    "在后续学习中，可以把进程理解为承载资源与执行流的单位。"
                    '\n\n以下内容仅用于渲染验收：$1 + 1 = 2$。\n\n'
                    '```python\nprint("render fixture")\n```\n\n'
                    '![进程示意图](images/process-fixture.png)\n'
                ),
                "citations": [
                    {
                        "snippet_id": process_snippet["id"],
                        "quote": "进程是系统进行资源分配和调度的独立单位。",
                    }
                ],
            },
            {
                "key": "thread",
                "page_md": (
                    "线程是进程中的一个执行单元，是处理机调度的基本单位。"
                    f"[原文](snippet:{thread_snippet['id']})"
                ),
                "citations": [
                    {"snippet_id": thread_snippet["id"], "quote": "线程是进程中的一个执行单元"}
                ],
            },
        ]
    }
    model = ScriptedModel({"抽取": draft, "整合": draft, "Markdown 页面": page_output})
    jobs = Jobs(data_dir, model=model)
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    assert asyncio.run(jobs.run_once()) is True
    state = jobs.get(course["id"], task["id"])
    assert state["status"] == "completed", state
    snapshot = jobs.knowledge.snapshot(course["id"])
    assert snapshot is not None and snapshot["version_id"]

    failed_course = materials.create_course("整理失败（受控验收样本）")
    failed_material = materials.import_material(
        failed_course["id"], "失败样本.md", FAILING_SAMPLE.encode()
    )
    failing_jobs = Jobs(
        data_dir,
        model=ScriptedModel(failure=ModelError("truncated", "模型输出被截断，请缩小整理范围后重试。")),
    )
    failed_task = failing_jobs.create(
        failed_course["id"], ScopeInput(material_ids=[failed_material["id"]])
    )
    assert asyncio.run(failing_jobs.run_once()) is True
    failed_state = failing_jobs.get(failed_course["id"], failed_task["id"])
    assert failed_state["status"] == "failed", failed_state

    return {
        "course_id": course["id"],
        "course_name": course["name"],
        "version_id": snapshot["version_id"],
        "concept_count": len(snapshot["concepts"]),
        "relation_count": len(snapshot["relations"]),
        "task_status": state["status"],
        "failed_course_id": failed_course["id"],
        "failed_course_name": failed_course["name"],
        "failed_task_status": failed_state["status"],
        "failed_error_code": failed_state["error_code"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="生成任务 02 的受控浏览器验收数据（非真实教材、非真实模型调用）。"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/browser-02"))
    result = seed(parser.parse_args().data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
