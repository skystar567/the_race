"""Version-pinned, source-grounded course Q&A."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from .knowledge import Knowledge
from .materials import Materials
from .model import DeepSeek, ModelError

CITATION = re.compile(r"\[F:([^\]]+)\]")


def _terms(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text or ""))
    for word in list(words):
        if len(word) > 2 and re.fullmatch(r"[\u4e00-\u9fff]+", word):
            words.update(word[index:index + 2] for index in range(len(word) - 1))
    return {word.lower() for word in words}


class Answers:
    def __init__(self, materials: Materials, knowledge: Knowledge, model: DeepSeek):
        self.materials = materials
        self.knowledge = knowledge
        self.model = model

    def _snapshot(self, course_id: str, version_id: str | None) -> dict[str, Any]:
        snapshot = self.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            raise LookupError("课程还没有已发布知识版本。")
        return snapshot

    def _fragments(self, snapshot: dict[str, Any], material_ids: list[str],
                   chapter_ids: list[str]) -> list[dict[str, Any]]:
        chapters = {chapter["id"]: chapter for chapter in snapshot["chapters"]}
        selected_chapters = [chapters[item] for item in chapter_ids if item in chapters]
        if chapter_ids and len(selected_chapters) != len(chapter_ids):
            raise LookupError("章节不属于当前知识版本。")
        materials = {fragment["material_id"] for fragment in snapshot["fragments"]}
        if material_ids and any(item not in materials for item in material_ids):
            raise LookupError("资料不属于当前知识版本。")
        result = []
        for fragment in snapshot["fragments"]:
            if material_ids and fragment["material_id"] not in material_ids:
                continue
            if selected_chapters and not any(
                chapter["material_id"] == fragment["material_id"]
                and chapter["start_line"] <= fragment["start_line"]
                and fragment["end_line"] <= chapter["end_line"]
                for chapter in selected_chapters
            ):
                continue
            result.append(fragment)
        return result

    def _retrieve(self, snapshot: dict[str, Any], question: str,
                  fragments: list[dict[str, Any]], concept_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        terms = _terms(question)
        candidates = []
        for concept in snapshot["concepts"]:
            score = 0
            names = [concept["name"], *concept["aliases"]]
            for name in names:
                if name and name.lower() in question.lower():
                    score += 5 if name == concept["name"] else 4
                score += len(_terms(name) & terms)
            text = " ".join([concept.get("definition", ""), concept.get("page_md", "")])
            score += len(_terms(text) & terms)
            if concept_id and concept["id"] == concept_id:
                score += 20
            if score:
                candidates.append((score, concept))
        candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
        concepts = [concept for _, concept in candidates[:6]]
        if concept_id and all(concept["id"] != concept_id for concept in concepts):
            match = next((item for item in snapshot["concepts"] if item["id"] == concept_id), None)
            if match:
                concepts.insert(0, match)
        scored_fragments = []
        for fragment in fragments:
            text = fragment.get("markdown", "")
            score = len(_terms(text) & terms)
            if score:
                scored_fragments.append((score, fragment))
        scored_fragments.sort(key=lambda item: (-item[0], item[1]["start_line"]))
        selected_fragments = [fragment for _, fragment in scored_fragments[:12]]
        if not selected_fragments:
            selected_fragments = fragments[:12]
        return concepts, selected_fragments

    def _context(self, snapshot: dict[str, Any], question: str,
                 fragments: list[dict[str, Any]], concept_id: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        concepts, selected_fragments = self._retrieve(snapshot, question, fragments, concept_id)
        return ({
            "course_version": snapshot["version_id"],
            "concepts": [
                {"id": concept["id"], "name": concept["name"], "aliases": concept["aliases"],
                 "definition": concept.get("definition", ""),
                 "page_md": concept.get("page_md", "")[:1600]}
                for concept in concepts
            ],
            "fragments": [
                {"id": fragment["id"], "filename": fragment.get("filename"),
                 "start_line": fragment.get("start_line"), "end_line": fragment.get("end_line"),
                 "markdown": fragment.get("markdown", "")[:1600]}
                for fragment in selected_fragments
            ],
        }, concepts, selected_fragments)

    @staticmethod
    def _instruction(expansion: bool) -> str:
        text = (
            "你只依据给出的课程知识版本回答，不得使用未出现的片段 id，不得编造页码、行号或原文。"
            "每个关键结论后用 [F:<片段id>] 标注依据；只允许使用 context.fragments 中的 id。"
            "资料不足时明确说“资料不足”，不能把没有依据的内容说成教材结论。"
            "如果回答被中断或引用无效，不要声称已完成。"
        )
        if expansion:
            text += " 学生已主动请求拓展解释；资料外内容必须明确标为“模型补充”，不能混入教材结论。"
        return text

    def _validate(self, snapshot: dict[str, Any], answer: str,
                  allowed_ids: set[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
        fragments = {fragment["id"]: fragment for fragment in snapshot["fragments"]}
        cited = list(dict.fromkeys(CITATION.findall(answer)))
        invalid = [item for item in cited if item not in allowed_ids or item not in fragments]
        citations = [{
            "snippet_id": item,
            "quote": fragments[item].get("markdown", "").strip()[:160],
            "filename": fragments[item].get("filename"),
            "start_line": fragments[item].get("start_line"),
            "end_line": fragments[item].get("end_line"),
            "chapter_title": next((chapter["title"] for chapter in snapshot["chapters"]
                                   if chapter["material_id"] == fragments[item]["material_id"]
                                   and chapter["start_line"] <= fragments[item]["start_line"]
                                   and fragments[item]["end_line"] <= chapter["end_line"]), None),
        } for item in cited if item in fragments and item in allowed_ids]
        if invalid:
            return "invalid_citations", citations, invalid
        if not citations:
            return "unverified", citations, []
        return "completed", citations, []

    async def ask(self, course_id: str, question: str, *, version_id: str | None = None,
                  material_ids: list[str] | None = None, chapter_ids: list[str] | None = None,
                  concept_id: str | None = None, expansion: bool = False) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise ValueError("问题不能为空。")
        snapshot = self._snapshot(course_id, version_id)
        fragments = self._fragments(snapshot, material_ids or [], chapter_ids or [])
        if not fragments:
            return {"status": "insufficient", "answer": "当前范围内没有可依据的原文片段。",
                    "citations": [], "version_id": snapshot["version_id"], "warnings": ["资料不足"]}
        context, concepts, selected = self._context(snapshot, question, fragments, concept_id)
        if not context["concepts"] and not context["fragments"]:
            return {"status": "insufficient", "answer": "当前范围内没有找到可用于回答的知识或原文。",
                    "citations": [], "version_id": snapshot["version_id"], "warnings": ["资料不足"]}
        content = json.dumps({"question": question, "context": context}, ensure_ascii=False)
        chunks = []
        async for delta in self.model.stream(self._instruction(expansion), content):
            chunks.append(delta)
        answer = "".join(chunks).strip()
        if not answer:
            raise ModelError("empty_output", "模型没有返回可用回答。")
        status, citations, invalid = self._validate(snapshot, answer, {item["id"] for item in fragments})
        warnings = []
        if status == "invalid_citations":
            warnings.append("回答引用了范围外或不存在于当前版本的片段，不能视为已完成答案。")
        elif status == "unverified":
            warnings.append("回答没有可核对的原文引用。")
        elif expansion:
            status = "completed_with_expansion"
            warnings.append("包含学生主动请求的模型补充，不属于教材原文。")
        return {
            "status": status, "answer": answer, "citations": citations,
            "invalid_citations": invalid, "version_id": snapshot["version_id"],
            "concepts": [concept["id"] for concept in concepts], "warnings": warnings,
            "scope": {"material_ids": material_ids or [], "chapter_ids": chapter_ids or []},
        }

    async def stream(self, course_id: str, question: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        snapshot = self._snapshot(course_id, kwargs.get("version_id"))
        fragments = self._fragments(snapshot, kwargs.get("material_ids") or [], kwargs.get("chapter_ids") or [])
        if not fragments:
            yield {"type": "done", "status": "insufficient",
                   "answer": "当前范围内没有可依据的原文片段。", "citations": [], "warnings": ["资料不足"]}
            return
        context, concepts, selected = self._context(snapshot, question, fragments, kwargs.get("concept_id"))
        content = json.dumps({"question": question, "context": context}, ensure_ascii=False)
        chunks: list[str] = []
        try:
            async for delta in self.model.stream(self._instruction(bool(kwargs.get("expansion"))), content):
                chunks.append(delta)
                yield {"type": "delta", "text": delta}
            answer = "".join(chunks).strip()
            status, citations, invalid = self._validate(snapshot, answer, {item["id"] for item in fragments})
            if status == "completed" and kwargs.get("expansion"):
                status = "completed_with_expansion"
            yield {"type": "done", "status": status, "answer": answer, "citations": citations,
                   "invalid_citations": invalid, "version_id": snapshot["version_id"],
                   "concepts": [concept["id"] for concept in concepts]}
        except ModelError as exc:
            yield {"type": "error", "code": exc.code, "message": str(exc)}
