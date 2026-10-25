"""Real textbook demo: one first build plus twenty grounded questions.

Run against a server started with a fresh data directory and a configured
DEEPSEEK_API_KEY. The script never reads or writes the key itself.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

QUESTIONS = [
    "进程是什么？",
    "为什么操作系统中要引入进程？",
    "多道程序技术的作用是什么？",
    "程序顺序执行有什么特点？",
    "程序并发执行有什么特点？",
    "前趋图是什么？",
    "前趋图为什么不允许有循环？",
    "前趋关系怎样表示？",
    "什么是初始结点？",
    "什么是终止结点？",
    "结点重量表示什么？",
    "图 2-1(a) 的九结点前趋图包含哪些前趋关系？",
    "循环前趋关系为什么不可能实现？",
    "进程概念与程序并发执行有什么关系？",
    "多道程序技术与程序并发执行有什么关系？",
    "前趋图与 DAG 是什么关系？",
    "前趋图中的有向边表示什么？",
    "前趋图的结点可以表示什么？",
    "程序顺序执行有什么缺点？",
    "图 2-1 在资料中缺失时，页面应怎样说明？",
]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8017"
    sample = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "real02-sample.md"
    output = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "demo-questions.json"
    with httpx.Client(base_url=base, timeout=180) as client:
        status = client.get("/api/model/status").json()
        print("model", status, flush=True)
        if not status.get("configured"):
            print("DEEPSEEK_API_KEY is not configured; refusing fake demo.", file=sys.stderr)
            return 2
        course = client.post("/api/courses", json={"name": "操作系统（真实教材演示）"}).json()
        material = client.post(
            f"/api/courses/{course['id']}/materials",
            params={"filename": "第2章至2.1.1节.md"},
            content=sample.read_bytes(),
        ).json()
        detail = client.get(f"/api/courses/{course['id']}/materials/{material['id']}").json()
        chapter = next(item for item in detail["chapters"] if item["title"].startswith("第二章"))
        task = client.post(f"/api/courses/{course['id']}/tasks",
                           json={"material_ids": [], "chapter_ids": [chapter["id"]]}).json()
        print("task", task["id"], flush=True)
        for _ in range(240):
            task = client.get(f"/api/courses/{course['id']}/tasks/{task['id']}").json()
            if task["status"] in {"completed", "failed"}:
                break
            time.sleep(2)
        snapshot = client.get(f"/api/courses/{course['id']}/knowledge").json()
        print("build", task["status"], snapshot.get("version_id"),
              len(snapshot.get("concepts", [])), len(snapshot.get("relations", [])), flush=True)
        if task["status"] != "completed":
            output.write_text(json.dumps({"task": task, "snapshot": snapshot}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            return 1
        results = []
        for index, question in enumerate(QUESTIONS, 1):
            response = client.post(f"/api/courses/{course['id']}/ask", json={"question": question})
            body = response.json()
            results.append({
                "index": index, "question": question, "http_status": response.status_code,
                "status": body.get("status"), "answer": body.get("answer"),
                "citations": body.get("citations", []), "warnings": body.get("warnings", []),
            })
            print(index, response.status_code, body.get("status"),
                  len(body.get("citations", [])), flush=True)
        output.write_text(json.dumps({
            "course": course, "version_id": snapshot["version_id"], "task_id": task["id"],
            "concepts": len(snapshot["concepts"]), "relations": len(snapshot["relations"]),
            "questions": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        completed = sum(item["status"] in {"completed", "completed_with_expansion"} for item in results)
        cited = sum(bool(item["citations"]) for item in results)
        print(f"done: {completed}/{len(results)} completed, {cited}/{len(results)} cited; {output}")
        return 0 if completed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
