"""Deterministic source, relationship and page checks.

These checks prove locatability and structural consistency, not semantic truth.
"""

import re
from typing import Any
from uuid import UUID, uuid5

from .knowledge_models import Citation, KnowledgeDraft, PagesDraft

RELATION_KINDS = {"contains", "precedes", "contrasts"}
RELATION_ORIGINS = {"source", "suggested"}
INLINE_REFERENCE = re.compile(r"snippet:([A-Za-z0-9._:-]+)")
MIN_QUOTE_CHARACTERS = 2


def normalize_text(text: str) -> str:
    """Collapse whitespace so line wrapping does not defeat an otherwise exact quote."""
    return " ".join(text.split())


def citation_fragment_id(citation: Citation, fragments: dict[str, dict[str, Any]]) -> str:
    """Return the cited fragment id or fail with a user-safe message."""
    source = fragments.get(citation.snippet_id)
    if source is None:
        raise ValueError("引用标识不在本次整理范围内。")
    quote = normalize_text(citation.quote)
    if len(quote) < MIN_QUOTE_CHARACTERS:
        raise ValueError("引用文字过短，不能作为原文依据。")
    if quote not in normalize_text(source.get("markdown", "")):
        raise ValueError("引用文字与原文不符。")
    return source["id"]


def check_citation(citation: Citation, fragments: dict[str, dict[str, Any]]) -> None:
    citation_fragment_id(citation, fragments)


def citation_inside_chapter(
    citations: list[Citation], chapter: dict[str, Any], fragments: dict[str, dict[str, Any]]
) -> Citation | None:
    """Find a validated citation located inside the given chapter range."""
    for citation in citations:
        fragment = fragments[citation.snippet_id]
        if (
            fragment["material_id"] == chapter["material_id"]
            and chapter["start_line"] <= fragment["start_line"]
            and fragment["end_line"] <= chapter["end_line"]
        ):
            return citation
    return None


def validate_draft(draft: KnowledgeDraft, source: dict[str, Any]) -> None:
    """Validate model-assigned local keys against program-owned source identifiers."""
    fragments = {fragment["id"]: fragment for fragment in source["fragments"]}
    chapters = {chapter["id"]: chapter for chapter in source["chapters"]}
    keys = [concept.key for concept in draft.concepts]
    if len(set(keys)) != len(keys):
        raise ValueError("知识点临时标识重复。")
    for concept in draft.concepts:
        if not concept.name.strip() or not concept.definition.strip():
            raise ValueError("知识点名称或定义为空。")
        if any(not alias.strip() for alias in concept.aliases):
            raise ValueError("知识点别名不能包含空字符串。")
        if not concept.chapter_ids:
            raise ValueError("知识点必须归属至少一个章节。")
        for citation in concept.citations:
            check_citation(citation, fragments)
        for chapter_id in dict.fromkeys(concept.chapter_ids):
            chapter = chapters.get(chapter_id)
            if chapter is None:
                raise ValueError("知识点章节不属于本次整理范围。")
            if citation_inside_chapter(concept.citations, chapter, fragments) is None:
                raise ValueError("知识点的章节归属缺少该章节内的原文依据。")
    for relation in draft.relations:
        if relation.from_key not in keys or relation.to_key not in keys:
            raise ValueError("关系端点不存在。")
        if relation.from_key == relation.to_key:
            raise ValueError("知识点不能以自身作为前置或对比对象。")
        if not relation.reason.strip():
            raise ValueError("关系缺少说明。")
        if relation.origin == "source" and relation.citation is None:
            raise ValueError("资料依据关系缺少原文引用。")
        if relation.citation is not None:
            check_citation(relation.citation, fragments)


def build_snapshot(
    course_id: str,
    task_id: str,
    draft: KnowledgeDraft,
    pages: PagesDraft,
    source: dict[str, Any],
    *, existing_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Create a canonical snapshot with stable IDs and fixed original evidence."""
    validate_draft(draft, source)
    page_map = {page.key: page for page in pages.pages}
    if len(page_map) != len(pages.pages) or set(page_map) != {concept.key for concept in draft.concepts}:
        raise ValueError("知识页面与知识点不一一对应。")
    fragments = {fragment["id"]: fragment for fragment in source["fragments"]}
    chapters = {chapter["id"]: chapter for chapter in source["chapters"]}
    # Concepts minted inside one task keep the same identity on retry. Integration
    # across updates is decided by evidence-checked integration, which supplies existing_ids.
    namespace = UUID(course_id)
    identities = {
        concept.key: concept.key if concept.key in (existing_ids or set()) else str(uuid5(namespace, f"concept:{task_id}:{concept.key}"))
        for concept in draft.concepts
    }
    concepts = []
    for concept in draft.concepts:
        page = page_map[concept.key]
        if not page.page_md.strip():
            raise ValueError("知识页面正文为空。")
        citations = {citation.snippet_id: citation for citation in concept.citations}
        for citation in page.citations:
            check_citation(citation, fragments)
            citations.setdefault(citation.snippet_id, citation)
        inline_ids = INLINE_REFERENCE.findall(page.page_md)
        if any(snippet_id not in citations for snippet_id in inline_ids):
            raise ValueError("知识页面出现未声明的片段引用。")
        concepts.append({
            "id": identities[concept.key],
            "name": concept.name.strip(),
            "aliases": list(dict.fromkeys(alias.strip() for alias in concept.aliases)),
            "definition": concept.definition.strip(),
            "page_md": page.page_md,
            "chapter_ids": list(dict.fromkeys(concept.chapter_ids)),
            "status": "confirmed",
            "is_new": True,
            "citations": [citation.model_dump() for citation in citations.values()],
        })

    relations = []
    for concept in draft.concepts:
        for chapter_id in dict.fromkeys(concept.chapter_ids):
            evidence = citation_inside_chapter(concept.citations, chapters[chapter_id], fragments)
            relations.append({
                "id": str(uuid5(namespace, f"contains:{chapter_id}:{identities[concept.key]}")),
                "kind": "contains",
                "from_type": "chapter",
                "from_id": chapter_id,
                "to_type": "concept",
                "to_id": identities[concept.key],
                "origin": "source",
                "citation": evidence.model_dump() if evidence else None,
                "reason": "由原文章节归属确定",
            })

    seen = set()
    for relation in draft.relations:
        key = (relation.kind, relation.from_key, relation.to_key)
        if key in seen:
            continue
        seen.add(key)
        relations.append({
            "id": str(uuid5(namespace, f"relation:{relation.kind}:{identities[relation.from_key]}:{identities[relation.to_key]}")),
            "kind": relation.kind,
            "from_type": "concept",
            "from_id": identities[relation.from_key],
            "to_type": "concept",
            "to_id": identities[relation.to_key],
            "origin": relation.origin,
            "citation": relation.citation.model_dump() if relation.citation else None,
            "reason": relation.reason.strip(),
        })

    snapshot = {
        "concepts": concepts,
        "relations": relations,
        "chapters": source["chapters"],
        "fragments": source["fragments"],
        "selection": source["selection"],
        "validated": True,
        "summary": {"new_concepts": len(concepts), "updated_concepts": 0, "conflicts": 0},
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    """Re-check a stored snapshot; publication never trusts a self-declared flag."""
    fragments = {fragment.get("id"): fragment for fragment in snapshot.get("fragments", [])}
    chapters = {chapter.get("id"): chapter for chapter in snapshot.get("chapters", [])}
    concepts = snapshot.get("concepts")
    relations = snapshot.get("relations")
    if not isinstance(concepts, list) or not concepts:
        raise ValueError("知识版本没有知识点。")
    if not isinstance(relations, list):
        raise ValueError("知识版本的关系结构无效。")

    concept_ids: set[str] = set()
    citations_by_concept: dict[str, list[Citation]] = {}
    for concept in concepts:
        if not isinstance(concept, dict):
            raise ValueError("知识点结构无效。")
        concept_id = concept.get("id")
        if not isinstance(concept_id, str) or not concept_id or concept_id in concept_ids:
            raise ValueError("知识点标识缺失或重复。")
        concept_ids.add(concept_id)
        for field in ("name", "definition", "page_md"):
            if not isinstance(concept.get(field), str) or not concept[field].strip():
                raise ValueError("知识点名称、定义或页面正文为空。")
        chapter_ids = concept.get("chapter_ids")
        if not isinstance(chapter_ids, list) or not chapter_ids:
            raise ValueError("知识点没有章节归属。")
        if any(chapter_id not in chapters for chapter_id in chapter_ids):
            raise ValueError("知识点章节不属于该知识版本。")
        raw_citations = concept.get("citations")
        if not isinstance(raw_citations, list) or not raw_citations:
            raise ValueError("知识点缺少原文引用。")
        citations = [Citation.model_validate(item) for item in raw_citations]
        for citation in citations:
            check_citation(citation, fragments)
        for chapter_id in dict.fromkeys(chapter_ids):
            if citation_inside_chapter(citations, chapters[chapter_id], fragments) is None:
                raise ValueError("知识点的章节归属缺少该章节内的原文依据。")
        declared = {citation.snippet_id for citation in citations}
        if any(snippet_id not in declared for snippet_id in INLINE_REFERENCE.findall(concept["page_md"])):
            raise ValueError("知识页面引用了未声明的原文片段。")
        citations_by_concept[concept_id] = citations

    expected_contains = {(chapter_id, concept["id"]) for concept in concepts for chapter_id in concept["chapter_ids"]}
    actual_contains: set[tuple[str, str]] = set()
    relation_ids: set[str] = set()
    for relation in relations:
        if not isinstance(relation, dict):
            raise ValueError("关系结构无效。")
        relation_id = relation.get("id")
        if not isinstance(relation_id, str) or not relation_id or relation_id in relation_ids:
            raise ValueError("关系标识缺失或重复。")
        relation_ids.add(relation_id)
        kind = relation.get("kind")
        if kind not in RELATION_KINDS:
            raise ValueError("关系类型不在允许范围内。")
        origin = relation.get("origin")
        if origin not in RELATION_ORIGINS:
            raise ValueError("关系来源标记无效。")
        if kind == "contains":
            if relation.get("from_type") != "chapter" or relation.get("to_type") != "concept":
                raise ValueError("包含关系必须以章节为起点、知识点为终点。")
            if relation.get("from_id") not in chapters or relation.get("to_id") not in concept_ids:
                raise ValueError("包含关系端点不存在。")
            pair = (relation["from_id"], relation["to_id"])
            if pair not in expected_contains or pair in actual_contains:
                raise ValueError("包含关系与章节归属不一致或重复。")
            if origin != "source" or relation.get("citation") is None:
                raise ValueError("包含关系必须保留资料依据。")
            citation = Citation.model_validate(relation["citation"])
            declared = {item.snippet_id for item in citations_by_concept[relation["to_id"]]}
            if citation.snippet_id not in declared or citation_inside_chapter(
                [citation], chapters[relation["from_id"]], fragments
            ) is None:
                raise ValueError("包含关系的引用不属于对应章节和知识点。")
            actual_contains.add(pair)
        else:
            if relation.get("from_type") != "concept" or relation.get("to_type") != "concept":
                raise ValueError("前置与对比关系只能连接知识点。")
            if relation.get("from_id") not in concept_ids or relation.get("to_id") not in concept_ids:
                raise ValueError("关系端点不存在。")
            if relation["from_id"] == relation["to_id"]:
                raise ValueError("知识点不能以自身作为关系端点。")
            if not isinstance(relation.get("reason"), str) or not relation["reason"].strip():
                raise ValueError("关系缺少说明。")
        raw_citation = relation.get("citation")
        if origin == "source" and raw_citation is None:
            raise ValueError("资料依据关系缺少原文引用。")
        if raw_citation is not None:
            check_citation(Citation.model_validate(raw_citation), fragments)

    if actual_contains != expected_contains:
        raise ValueError("包含关系与知识点章节归属不一致。")

    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("知识版本缺少摘要。")
    for field in ("new_concepts", "updated_concepts", "conflicts"):
        value = summary.get(field)
        if not isinstance(value, int) or value < 0:
            raise ValueError("知识版本摘要无效。")
