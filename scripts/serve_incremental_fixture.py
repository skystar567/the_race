"""Local browser fixture: scripted model only; no credential or network model use."""

import argparse
import asyncio
import copy
from contextlib import suppress
from pathlib import Path

import uvicorn

from campus.api import create_app
from campus.jobs import Jobs
from campus.materials import Materials
from seed_ticket02_fixture import seed

SUPPLEMENT = "# 补充说明\n\n进程也称运行过程。进程控制块用于记录进程状态。\n"
UNCERTAIN = "# 含糊术语\n\n这里的运行过程含义尚不明确，需要核对。\n"
INVALID = "# 受控失败\n\n这段资料用于验证无效引用不会发布。\n"


class FixtureModel:
    api_key = "fixture-not-a-network-key"

    async def complete(self, instructions, content, schema, **options):
        if "抽取" in instructions:
            fragment = next(f for f in content["fragments"] if f["kind"] != "heading" and not f["markdown"].startswith("#"))
            text = fragment["markdown"]
            uncertain = "尚不明确" in text
            failed = "无效引用" in text
            concepts = [{"key": "process", "name": "运行过程", "aliases": [],
                "definition": "含义尚不明确，需要核对。" if uncertain else "程序的一次执行，也称运行过程。",
                "chapter_ids": [fragment["chapter_id"]],
                "citations": [{"snippet_id": fragment["id"], "quote": "伪造引用" if failed else text.strip()}]}]
            if not uncertain and not failed:
                concepts.append({"key": "pcb", "name": "进程控制块", "aliases": ["PCB"], "definition": "用于记录进程状态。",
                    "chapter_ids": [fragment["chapter_id"]], "citations": [{"snippet_id": fragment["id"], "quote": "进程控制块用于记录进程状态。"}]})
            return {"concepts": concepts, "relations": []}
        if "整合" in instructions:
            draft = copy.deepcopy(content["draft"])
            old = next(c for c in content["existing_concepts"] if c["name"] in {"进程", "运行过程"})
            for c in draft["concepts"]:
                uncertain = "尚不明确" in c["definition"]
                matched = c["key"] == "process" and not uncertain
                c.update(existing_id=old["id"] if matched else None,
                         identity_status="needs_review" if uncertain else "confirmed",
                         identity_reason="当前语境尚不足以确认同一概念。" if uncertain else "根据新旧定义和明确别称判断。")
                if matched:
                    c["citations"] += old["citations"]
            return draft
        if "Markdown 页面" in instructions:
            await asyncio.sleep(4)  # Expose an in-progress update for browser reads.
            return {"pages": [{"key": c["key"], "page_md": c["definition"] + "\n\n" + "\n\n".join(
                f"{ref['quote']}[原文](snippet:{ref['snippet_id']})" for ref in c["citations"]), "citations": c["citations"]}
                for c in content["draft"]["concepts"]]}
        raise AssertionError("Unexpected fixture step")


async def serve(args):
    model = FixtureModel()
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
    parser = argparse.ArgumentParser(description="任务08的受控浏览器服务；不调用真实模型。")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8021)
    args = parser.parse_args()
    if args.data_dir.exists():
        parser.error("请指定不存在的新目录，避免覆盖已有资料。")
    fixture = seed(args.data_dir)
    materials = Materials(args.data_dir)
    for name, content in [("补充.md", SUPPLEMENT), ("含糊.md", UNCERTAIN), ("无效.md", INVALID), ("未选.md", "# 未选\n\n保留未整理。\n")]:
        materials.import_material(fixture["course_id"], name, content.encode())
    asyncio.run(serve(args))
