"""Portable export of one published knowledge version, notes and raw materials."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledge import Knowledge
from .materials import Materials
from .notes_store import NotesStore


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe(value: str) -> str:
    return (value or "").replace("[", "\\[").replace("]", "\\]")


class Exporter:
    def __init__(self, materials: Materials, knowledge: Knowledge, notes: NotesStore):
        self.materials = materials
        self.knowledge = knowledge
        self.notes = notes

    def export(self, course_id: str, version_id: str | None = None) -> tuple[bytes, dict[str, Any]]:
        snapshot = self.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            raise LookupError("课程还没有已发布知识版本。")
        course = next((item for item in self.materials.courses() if item["id"] == course_id), None)
        if course is None:
            raise LookupError("课程不存在。")
        notes = self.notes.list(course_id)
        materials = self.materials.list_materials(course_id)
        fragments = {fragment["id"]: fragment for fragment in snapshot["fragments"]}
        concepts = {concept["id"]: concept for concept in snapshot["concepts"]}
        chapters = {chapter["id"]: chapter for chapter in snapshot["chapters"]}
        sources: dict[str, list[str]] = {}
        files: dict[str, bytes] = {}
        exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def fragment_link(snippet_id: str, quote: str, root: str) -> str:
            fragment = fragments.get(snippet_id)
            if fragment is None:
                return f"片段 {snippet_id[:8]}（不可定位）"
            sources.setdefault(snippet_id, [])
            if quote not in sources[snippet_id]:
                sources[snippet_id].append(quote)
            return f"[原文 {snippet_id[:8]}]({root}/sources.md#frag-{snippet_id})"

        def concept_link(concept_id: str, prefix: str = "knowledge/concepts") -> str:
            name = concepts.get(concept_id, {}).get("name", concept_id)
            return f"[{_safe(name)}]({prefix}/{concept_id}.md)"

        # Knowledge index.
        contained: dict[str, list[str]] = {}
        for relation in snapshot["relations"]:
            if relation["kind"] == "contains":
                contained.setdefault(relation["from_id"], []).append(relation["to_id"])
        index = [f"# {course['name']} · 知识入口", "",
                 f"- 知识版本：{snapshot['version_id']}",
                 f"- 导出时间：{exported_at}",
                 f"- 知识点：{len(concepts)}；关系：{len(snapshot['relations'])}", ""]
        listed: set[str] = set()
        for chapter_id, concept_ids in contained.items():
            title = chapters.get(chapter_id, {}).get("title", chapter_id)
            index.append(f"## {_safe(title)}")
            for concept_id in sorted(concept_ids, key=lambda item: concepts.get(item, {}).get("name", item)):
                if concept_id in concepts:
                    index.append(f"- {concept_link(concept_id, 'concepts')}")
                    listed.add(concept_id)
            index.append("")
        rest = [concept_id for concept_id in concepts if concept_id not in listed]
        if rest:
            index.append("## 未归属章节")
            index.extend(f"- {concept_link(concept_id, 'concepts')}" for concept_id in rest)
            index.append("")
        index.extend(["## 索引", "- [关系索引](../relations.md)", "- [个人笔记](../notes/index.md)",
                      "- [原文依据](../sources.md)", "- [原始资料](../materials/README.md)", ""])
        files["knowledge/index.md"] = "\n".join(index).encode("utf-8")

        # Concept pages.
        for concept_id, concept in concepts.items():
            lines = [f"# {_safe(concept['name'])}", ""]
            if concept.get("aliases"):
                lines.extend(["别名：" + "、".join(_safe(alias) for alias in concept["aliases"]), ""])
            lines.extend([concept.get("page_md", "").strip(), "", "## 原文依据", ""])
            for citation in concept.get("citations", []):
                lines.append(f"- {fragment_link(citation['snippet_id'], citation['quote'], '../..')}")
                lines.append(f"  > {citation['quote']}")
            lines.extend(["", "## 关系", ""])
            for relation in snapshot["relations"]:
                if relation["kind"] == "precedes" and relation["to_id"] == concept_id:
                    lines.append(f"- 前置：{concept_link(relation['from_id'], '.')}")
                elif relation["kind"] == "precedes" and relation["from_id"] == concept_id:
                    lines.append(f"- 后继：{concept_link(relation['to_id'], '.')}")
                elif relation["kind"] == "contrasts" and concept_id in (relation["from_id"], relation["to_id"]):
                    other = relation["to_id"] if relation["from_id"] == concept_id else relation["from_id"]
                    lines.append(f"- 对比：{concept_link(other, '.')}")
            lines.extend(["", "---", "返回[知识入口](../index.md)。", ""])
            files[f"knowledge/concepts/{concept_id}.md"] = "\n".join(lines).encode("utf-8")

        # Relations index.
        rel = [f"# {course['name']} · 关系索引", "", f"知识版本：{snapshot['version_id']}", ""]
        for label, kind in (("包含", "contains"), ("前置", "precedes"), ("对比", "contrasts")):
            rel.append(f"## {label}")
            found = False
            for relation in snapshot["relations"]:
                if relation["kind"] != kind:
                    continue
                found = True
                if kind == "contains":
                    left = _safe(chapters.get(relation["from_id"], {}).get("title", relation["from_id"]))
                    right = concept_link(relation["to_id"], "knowledge/concepts")
                else:
                    left = concept_link(relation["from_id"], "knowledge/concepts")
                    right = concept_link(relation["to_id"], "knowledge/concepts")
                origin = "资料依据" if relation["origin"] == "source" else "系统建议"
                cite = ""
                if relation.get("citation"):
                    fragment = fragments.get(relation["citation"]["snippet_id"])
                    if fragment:
                        cite = f"，依据：[{fragment['filename']} 第 {fragment['start_line']}–{fragment['end_line']} 行](sources.md#frag-{fragment['id']})"
                rel.append(f"- {left} → {right}（{origin}）{cite}")
            if not found:
                rel.append("- （无）")
            rel.append("")
        rel.extend(["---", "返回[知识入口](knowledge/index.md)。", ""])
        files["relations.md"] = "\n".join(rel).encode("utf-8")

        # Notes.
        note_index = [f"# {course['name']} · 个人笔记", ""]
        for note in notes:
            note_index.append(f"- [{_safe(note['title'])}]({note['id']}.md)"
                              + ("（含模型拓展）" if note["expansion"] else ""))
        if not notes:
            note_index.append("（暂无个人笔记）")
        note_index.append("")
        files["notes/index.md"] = "\n".join(note_index).encode("utf-8")
        for note in notes:
            lines = [f"# {_safe(note['title'])}", "",
                     f"- 更新：{note['updated_at']}",
                     "- 含模型拓展" if note["expansion"] else "- 仅个人内容", "",
                     note["markdown"].strip(), "", "## 原文依据", ""]
            if note["citations"]:
                for citation in note["citations"]:
                    lines.append(f"- {fragment_link(citation['snippet_id'], citation['quote'], '..')}")
                    lines.append(f"  > {citation['quote']}")
            else:
                lines.append("（未记录原文引用）")
            lines.extend(["", "---", "返回[笔记入口](index.md)。", ""])
            files[f"notes/{note['id']}.md"] = "\n".join(lines).encode("utf-8")

        # Sources.
        source_lines = [f"# {course['name']} · 原文依据", "",
                        "引用片段保留资料名、行号和原文；原始文件在 `materials/`，未改写。", ""]
        for snippet_id in sorted(sources):
            fragment = fragments[snippet_id]
            source_lines.append(f'<a id="frag-{snippet_id}"></a>')
            source_lines.append(f"## 片段 {snippet_id[:8]} · {fragment['filename']} 第 {fragment['start_line']}–{fragment['end_line']} 行")
            source_lines.append("")
            for quote in sources[snippet_id]:
                source_lines.extend([f"> {quote}", ""])
            source_lines.append(f"[打开原始资料](materials/{fragment['material_id']}.md)")
            source_lines.append("")
        if not sources:
            source_lines.append("（本包没有引用片段）")
        files["sources.md"] = "\n".join(source_lines).encode("utf-8")

        # Raw materials and index.
        for material in materials:
            files[f"materials/{material['id']}.md"] = self.materials.raw(course_id, material["id"])
        material_index = ["# 原始资料", "", "导入时的原始 Markdown，逐字节保留。", ""]
        material_index.extend(f"- [{_safe(item['filename'])}]({item['id']}.md)（{item['byte_size']} 字节）"
                              for item in materials)
        files["materials/README.md"] = "\n".join(material_index + [""]).encode("utf-8")

        conflicts = snapshot.get("conflicts", [])
        if conflicts:
            conflict_lines = [f"# {course['name']} · 冲突记录", "",
                              "同名但定义或证据不同的条目不会被自动合并；以下记录保留双方。", ""]
            for conflict in conflicts:
                conflict_lines.extend([
                    f"## {_safe(conflict.get('name', '未命名'))} · {conflict.get('kind', '')}",
                    "", f"- 状态：{conflict.get('status', 'open')}",
                    f"- 条目 A：`{conflict.get('other_concept_id', '')}`",
                    f"  > {conflict.get('previous_definition', '')}",
                    f"- 条目 B：`{conflict.get('concept_id', '')}`",
                    f"  > {conflict.get('incoming_definition', '')}", "",
                ])
            files["conflicts.md"] = "\n".join(conflict_lines).encode("utf-8")

        # README and manifest.
        readme = [f"# {course['name']} · 课程资料包", "",
                  f"- 课程：{course['name']}", f"- 知识版本：{snapshot['version_id']}",
                  f"- 导出时间：{exported_at}",
                  f"- 资料：{len(materials)}；知识点：{len(concepts)}；关系：{len(snapshot['relations'])}；笔记：{len(notes)}", "",
                  "## 阅读顺序", "1. [知识入口](knowledge/index.md)", "2. [关系索引](relations.md)",
                  "3. [个人笔记](notes/index.md)", "4. [原文依据](sources.md)", "5. [原始资料](materials/README.md)",
                  *(["6. [冲突记录](conflicts.md)"] if conflicts else []), "",
                  "## 限制", "- 原始 Markdown 逐字节保留，未改写。",
                  "- 个人笔记、模型拓展标记和系统建议关系按导出时快照保存。",
                  "- 缺图保持缺失标记；不承诺恢复。", "- 应用外修改不会同步回应用。", ""]
        files["README.md"] = "\n".join(readme).encode("utf-8")
        manifest = {
            "course": {"id": course_id, "name": course["name"]},
            "knowledge_version": snapshot["version_id"],
            "exported_at": exported_at,
            "counts": {"materials": len(materials), "concepts": len(concepts),
                       "relations": len(snapshot["relations"]), "notes": len(notes),
                       "sources": len(sources), "conflicts": len(conflicts)},
            "files": [{"path": path, "sha256": _sha(data), "bytes": len(data)}
                      for path, data in sorted(files.items())],
        }
        files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, data in sorted(files.items()):
                archive.writestr(path, data)
        return buffer.getvalue(), manifest
