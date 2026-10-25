"""Task 09/10 browser fixture: synthetic sources, scripted model, no network model."""

import argparse
import asyncio
import copy
from contextlib import suppress
from pathlib import Path

import uvicorn

from campus.api import create_app
from campus.jobs import Jobs
from campus.materials import Materials
from campus.model import ModelError
from seed_ticket02_fixture import seed

IDENTITY_SAMPLE = """# 同义说明

运行过程就是程序的一次执行，与进程同义。

# 同名异义

本文的线程是纺织工艺中的线状成品，与操作系统无关。

# 不同语境

在单核处理机上，进程轮流执行；在多核处理机上，多个进程可以同时执行。

# 未确定术语

运行体在此处的具体含义尚未说明。

# 相互矛盾

在本课程相同模型下，线程不是处理机调度的基本单位。
"""
RETRY_SAMPLE = "# 重试说明\n\n进程也称运行过程，这份补充用于验证失败后复用步骤。\n"


class IdentityModel:
    api_key = "fixture-without-network"

    def __init__(self):
        self.failed_render = False

    async def complete(self, instructions, content, schema, **options):
        if "抽取" in instructions:
            fragments = [f for f in content["fragments"] if not f["markdown"].startswith("#")]

            def concept(key, name, definition, *needles):
                selected = [next(f for f in fragments if needle in f["markdown"]) for needle in needles]
                return {"key": key, "name": name, "aliases": [], "definition": definition,
                        "chapter_ids": list(dict.fromkeys(f["chapter_id"] for f in selected)),
                        "citations": [{"snippet_id": f["id"], "quote": f["markdown"].strip()} for f in selected]}

            if any("与进程同义" in f["markdown"] for f in fragments):
                concepts = [
                    concept("process", "运行过程", "程序的一次执行；单核轮流执行和多核同时执行适用语境不同。", "与进程同义", "在单核处理机上"),
                    concept("textile", "线程", "纺织工艺中的线状成品，与操作系统概念不同。", "纺织工艺"),
                    concept("uncertain", "运行体", "含义尚未确定。", "运行体在此处"),
                    concept("thread", "线程", "资料对相同模型下线程是否为处理机调度基本单位存在冲突。", "线程不是处理机"),
                ]
            elif any("验证失败后复用步骤" in f["markdown"] for f in fragments):
                concepts = [concept("recovery", "运行过程", "程序的一次执行。", "验证失败后复用步骤")]
            else:
                concepts = [concept("first", "受控整理说明", "用于验证失败后的首次整理。", "这段受控文本")]
            return {"concepts": concepts, "relations": []}
        if "整合" in instructions:
            draft = copy.deepcopy(content["draft"])
            if "existing_concepts" not in content:
                return draft
            previous = content["existing_concepts"]
            for item in draft["concepts"]:
                if item["key"] in {"process", "recovery"}:
                    old = next(c for c in previous if c["name"] in {"进程", "运行过程"})
                elif item["key"] == "thread":
                    old = next(c for c in previous if c["name"] == "线程" and "处理机" in c["definition"])
                else:
                    old = None
                item.update(existing_id=old["id"] if old else None,
                            identity_status="needs_review" if item["key"] == "uncertain" else "confirmed",
                            identity_reason="语境不足，无法确认与旧概念相同。" if item["key"] == "uncertain" else
                            "依据定义和语境确认同一概念。" if old else "纺织工艺语境与操作系统不同，独立保留。",
                            conflicts=[])
                if old:
                    item["citations"] += copy.deepcopy(old["citations"])
                if item["key"] == "thread":
                    old_ref = dict(next(ref for ref in old["citations"] if "线程" in ref["quote"]),
                                   quote="线程是进程中的一个执行单元，是处理机调度的基本单位。")
                    item["conflicts"] = [{"reason": "相同模型下对是否为处理机调度基本单位给出互斥结论。", "claims": [
                        {"statement": "线程是处理机调度的基本单位。", "context": "本课程默认线程模型。", "citation": old_ref},
                        {"statement": "线程不是处理机调度的基本单位。", "context": "本课程相同线程模型。", "citation": item["citations"][0]},
                    ]}]
            return draft
        if "Markdown 页面" in instructions:
            concepts = content["draft"]["concepts"]
            if any(c["key"] == "recovery" for c in concepts) and not self.failed_render:
                self.failed_render = True
                raise ModelError("truncated", "受控页面输出截断，重试会复用已成功的抽取与整合。")
            return {"pages": [{"key": c["key"], "page_md": c["definition"] + "\n\n" + "\n\n".join(
                f"{ref['quote']}[原文](snippet:{ref['snippet_id']})" for ref in c["citations"]), "citations": c["citations"]}
                for c in concepts]}
        raise AssertionError("Unexpected fixture model stage")


async def serve(args):
    model = IdentityModel()
    jobs = Jobs(args.data_dir, model=model)

    async def work():
        while True:
            await jobs.run_once()
            await asyncio.sleep(0.1)

    app = create_app(args.data_dir, static_dir=Path(__file__).resolve().parents[1] / "dist", model=model)
    worker = asyncio.create_task(work())
    try:
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")).serve()
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="合成身份冲突与重试验收，不调用外部模型。")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8026)
    args = parser.parse_args()
    if args.data_dir.exists():
        parser.error("请使用不存在的新目录，以免覆盖已有资料。")
    fixture = seed(args.data_dir)
    materials = Materials(args.data_dir)
    materials.import_material(fixture["course_id"], "身份与冲突.md", IDENTITY_SAMPLE.encode())
    materials.import_material(fixture["course_id"], "中断后重试.md", RETRY_SAMPLE.encode())
    asyncio.run(serve(args))
