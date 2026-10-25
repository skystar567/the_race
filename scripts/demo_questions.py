"""Run the twenty demo questions against an existing published demo version."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from demo_acceptance import QUESTIONS


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8017"
    course_id = sys.argv[2] if len(sys.argv) > 2 else "99038ccf-8d9f-4f68-8123-1a4791e86d2a"
    output = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "demo-questions.json"
    with httpx.Client(base_url=base, timeout=180) as client:
        snapshot = client.get(f"/api/courses/{course_id}/knowledge").json()
        if not snapshot.get("version_id"):
            print("course has no published version", file=sys.stderr)
            return 2
        results = []
        for index, question in enumerate(QUESTIONS, 1):
            response = client.post(f"/api/courses/{course_id}/ask", json={"question": question})
            try:
                body = response.json()
            except Exception:
                body = {"answer": response.text, "status": "http_error"}
            results.append({
                "index": index, "question": question, "http_status": response.status_code,
                "status": body.get("status"), "answer": body.get("answer"),
                "citations": body.get("citations", []), "warnings": body.get("warnings", []),
                "version_id": body.get("version_id"),
            })
            print(index, response.status_code, body.get("status"),
                  len(body.get("citations", [])), flush=True)
        output.write_text(json.dumps({
            "course_id": course_id, "version_id": snapshot["version_id"],
            "concepts": len(snapshot.get("concepts", [])),
            "relations": len(snapshot.get("relations", [])),
            "conflicts": len(snapshot.get("conflicts", [])),
            "questions": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        completed = sum(item["status"] in {"completed", "completed_with_expansion"} for item in results)
        cited = sum(bool(item["citations"]) for item in results)
        print(f"done: {completed}/{len(results)} completed, {cited}/{len(results)} cited; {output}")
        return 0 if completed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
