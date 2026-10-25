"""Kill and restart the real worker against a local HTTP model fixture.

Synthetic content only. Never uses the configured external API or its key.
All observations use public Jobs, Knowledge and Materials methods.
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from campus.jobs import Jobs
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.model import DeepSeek


class LocalModel:
    def __init__(self):
        self.calls = Counter()
        self.prepared = threading.Event()
        self.release = threading.Event()
        self.block_next_page = True

    def prepare(self, payload):
        content = json.loads(payload["input"])
        if "pages" in payload["text"]["format"]["schema"]["properties"]:
            stage = "render"
            result = {"pages": [{"key": c["key"], "page_md": c["definition"] + "\n\n" + "\n\n".join(
                f"{ref['quote']}[原文](snippet:{ref['snippet_id']})" for ref in c["citations"]),
                "citations": c["citations"]} for c in content["draft"]["concepts"]]}
        elif "draft" in content:
            stage = "integrate"
            result = copy.deepcopy(content["draft"])
            if "existing_concepts" in content:
                old = content["existing_concepts"][0]
                for c in result["concepts"]:
                    c.update(existing_id=old["id"], identity_status="confirmed",
                             identity_reason="新旧说明均指程序的一次执行，新资料补充别称。")
                    c["citations"] += old["citations"]
                if "conflicts" in payload["text"]["format"]["schema"]["properties"]:
                    result["conflicts"] = []
        else:
            stage = "extract"
            fragment = next(f for f in content["fragments"] if "进程" in f["markdown"] and f["kind"] != "heading")
            result = {"concepts": [{"key": "process", "name": "进程", "aliases": [],
                "definition": fragment["markdown"].strip(), "chapter_ids": [fragment["chapter_id"]],
                "citations": [{"snippet_id": fragment["id"], "quote": fragment["markdown"].strip()}]}], "relations": []}
        self.calls[stage] += 1
        if stage == "render" and self.block_next_page:
            self.block_next_page = False
            self.prepared.set()  # The external service computed output, but it has not reached the worker.
            if not self.release.wait(20):
                raise TimeoutError("The verifier did not release the fixture response")
        return {"status": "completed", "output": [{"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": json.dumps(result, ensure_ascii=False)}]}]}


def check(data_dir: Path):
    if data_dir.exists():
        raise ValueError("请指定不存在的新目录，避免改动已有资料。")
    fixture = LocalModel()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.path == "/responses"
            assert self.headers.get("Authorization") == "Bearer local-recovery-fixture"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            response = json.dumps(fixture.prepare(payload)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            try:
                self.wfile.write(response)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected for the deliberately killed worker.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    env = os.environ | {"DEEPSEEK_API_KEY": "local-recovery-fixture", "DEEPSEEK_BASE_URL": base_url}
    root = Path(__file__).resolve().parents[1]
    materials = Materials(data_dir)
    jobs = Jobs(data_dir, model=DeepSeek(api_key="local-recovery-fixture", base_url=base_url))
    course = materials.create_course("恢复验收（受控样本）")
    children = []
    reports = []
    log = (data_dir / "worker.log").open("wb")

    def start(*extra):
        child = subprocess.Popen([sys.executable, "-m", "campus.worker", "--data-dir", str(data_dir.resolve()),
                                  "--lease-seconds", "2", *extra], cwd=root, env=env, stdout=log, stderr=log)
        children.append(child)
        return child

    try:
        for phase, text in [("first", "# 定义\n\n进程是程序的一次执行。\n"),
                            ("incremental", "# 别称\n\n进程也称运行过程，指程序的一次执行。\n")]:
            before = jobs.knowledge.snapshot(course["id"])
            raw = text.encode()
            material = materials.import_material(course["id"], phase + ".md", raw)
            task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
            fixture.calls.clear()
            fixture.prepared.clear()
            fixture.release.clear()
            fixture.block_next_page = True
            interrupted = start()
            assert fixture.prepared.wait(10), "Worker did not reach prepared page output; inspect worker.log"
            pending = jobs.get(course["id"], task["id"])
            assert pending["status"] == "running"
            assert {s["name"]: s["status"] for s in pending["steps"]}["integrate"] == "completed"
            interrupted.kill()  # Actual process termination; no graceful task cleanup.
            interrupted.wait(timeout=5)
            assert interrupted.returncode != 0
            assert jobs.knowledge.snapshot(course["id"]) == before
            assert materials.raw(course["id"], material["id"]) == raw
            fixture.release.set()
            restarted = start()
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                done = jobs.get(course["id"], task["id"])
                if done["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            assert done["status"] == "completed", done
            restarted.terminate()
            restarted.wait(timeout=5)
            assert done["recovery_count"] == 1
            assert fixture.calls == {"extract": 1, "integrate": 1, "render": 2}, fixture.calls
            assert {s["name"]: s["attempts"] for s in done["steps"]} == {
                "ingest": 0, "extract": 1, "integrate": 1, "render": 2, "validate": 1, "publish": 1}
            snapshot = jobs.knowledge.snapshot(course["id"])
            assert snapshot["version_id"] == done["version_id"]
            if before:
                assert snapshot["concepts"][0]["id"] == before["concepts"][0]["id"]
                assert jobs.knowledge.snapshot(course["id"], before["version_id"]) == before
            version_count = len(jobs.knowledge.versions(course["id"]))
            assert version_count == (1 if phase == "first" else 2)
            assert start("--once").wait(timeout=5) == 0
            assert len(jobs.knowledge.versions(course["id"])) == version_count
            reports.append({"phase": phase, "task_id": task["id"], "version_id": snapshot["version_id"],
                            "recovery_count": done["recovery_count"], "model_calls": dict(fixture.calls),
                            "versions": version_count, "interrupted_exit": interrupted.returncode})
        return {"course_id": course["id"], "runs": reports}
    finally:
        fixture.release.set()
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
        server.shutdown()
        server.server_close()
        log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实际中断并恢复首次和追加任务，不访问外部模型。")
    parser.add_argument("--data-dir", type=Path, required=True)
    report = check(parser.parse_args().data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
