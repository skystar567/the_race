"""Real API/SQLite browser fixture with a scripted model; never loads credentials."""

import argparse
import asyncio
from contextlib import suppress
from pathlib import Path

import uvicorn

from campus.api import create_app
from campus.jobs import Jobs
from campus.materials import Materials
from campus.model import ModelError
from seed_ticket02_fixture import seed
from serve_identity_fixture import IDENTITY_SAMPLE, RETRY_SAMPLE, IdentityModel


class StudyModel(IdentityModel):
    def __init__(self):
        super().__init__()
        self.failed_render = True

    async def complete(self, instructions, content, schema, **options):
        if "个人学习笔记" in instructions:
            if content.get("source") == "model_expansion":
                return {"title": "拓展解释笔记", "body_md": content["text"]}
            citations = content.get("citations", [])
            text = content.get("answer") or content.get("concept", {}).get("page_md") or content.get("text") or "依据来源记录学习理解。"
            text += "\n\n" + "\n\n".join(f"[原文](snippet:{c['snippet_id']})" for c in citations)
            return {"title": "受控学习笔记", "body_md": text}
        if "拓展解释步骤" in instructions:
            return {"expansion_md": "这是资料外的受控类比：把进程理解为拥有资源的工作间。"}
        if "检索路由步骤" in instructions:
            return {"concept_ids": []}
        return await super().complete(instructions, content, schema, **options)

    async def stream(self, instructions, content, **options):
        assert "evidence" in content
        for fragment in content["evidence"]:
            await asyncio.sleep(0.04)
            yield fragment["markdown"] + f"[原文](snippet:{fragment['id']})\n\n"
            if "发布中" in content["question"]:
                await asyncio.sleep(1.5)
            if "中断" in content["question"]:
                raise ModelError("interrupted", "受控连接中断，当前内容不是完整答案。")


async def serve(args):
    model = StudyModel()
    jobs = Jobs(args.data_dir, model=model)
    app = create_app(args.data_dir, static_dir=Path(__file__).resolve().parents[1] / "dist", model=model)

    async def work():
        while True:
            await jobs.run_once()
            await asyncio.sleep(0.05)

    worker = asyncio.create_task(work())
    try:
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")).serve()
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="问答、笔记和拓展验收；使用合成资料和受控模型。")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8036)
    args = parser.parse_args()
    if args.data_dir.exists():
        parser.error("请使用不存在的新目录，以免覆盖已有资料。")
    fixture = seed(args.data_dir)
    materials = Materials(args.data_dir)
    materials.import_material(fixture["course_id"], "未整理页表.md", "# 页表\n\n页表记录虚拟页到物理页框的映射。\n".encode())
    materials.import_material(fixture["course_id"], "身份与冲突.md", IDENTITY_SAMPLE.encode())
    materials.import_material(fixture["course_id"], "增量复习.md", RETRY_SAMPLE.encode())
    asyncio.run(serve(args))
