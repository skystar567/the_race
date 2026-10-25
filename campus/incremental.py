"""Evidence-checked additive updates; unchanged knowledge is retained by code."""

from typing import Any

from pydantic import Field

from .knowledge_models import ConceptDraft, KnowledgeDraft, KnowledgeUpdate, PageDraft, PagesDraft, RelationDraft
from .knowledge_validation import build_snapshot, check_citation, validate_draft, validate_snapshot


class _CombinedDraft(KnowledgeDraft):
    # Per-model-call limits belong to KnowledgeUpdate, not the accumulated course.
    concepts: list[ConceptDraft] = Field(min_length=1)
    relations: list[RelationDraft]


def combined_source(previous: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Union immutable evidence without claiming that unselected content was read."""
    result = {}
    for field in ("chapters", "fragments"):
        result[field] = list({item["id"]: item for item in previous[field] + source[field]}.values())
    result["selection"] = {field: list(dict.fromkeys(previous["selection"][field] + source["selection"][field]))
                           for field in ("material_ids", "chapter_ids")}
    result["character_count"] = sum(len(f["markdown"]) for f in result["fragments"])
    return result


def _compose(update: KnowledgeUpdate, previous: dict[str, Any], source: dict[str, Any]):
    old = {c["id"]: c for c in previous["concepts"]}
    new_snippets = {f["id"] for f in source["fragments"]}
    evidence = {f["id"]: f for f in previous["fragments"] + source["fragments"]}
    keys = [c.key for c in update.concepts]
    existing = [c.existing_id for c in update.concepts if c.existing_id]
    if len(set(keys)) != len(keys) or len(set(existing)) != len(existing):
        raise ValueError("追加知识的临时标识或已有知识点标识重复。")
    if set(keys) & set(old):
        raise ValueError("追加知识临时标识不能占用已有知识点标识。")
    key_map = {c.key: c.existing_id or f"new:{c.key}" for c in update.concepts}
    concepts = {cid: ConceptDraft(key=cid, **{field: c[field] for field in (
        "name", "aliases", "definition", "chapter_ids", "citations")}) for cid, c in old.items()}
    for change in update.concepts:
        if not change.identity_reason.strip():
            raise ValueError("知识点身份判断缺少说明。")
        cited = {c.snippet_id for c in change.citations}
        # Validate raw model evidence before old citations are preserved/combined.
        for citation in change.citations:
            check_citation(citation, evidence)
        if not cited & new_snippets:
            raise ValueError("新增或补充知识必须引用本次追加范围。")
        fields = change.model_dump(include={"name", "aliases", "definition", "chapter_ids", "citations"})
        if change.existing_id:
            if change.existing_id not in old:
                raise ValueError("沿用的知识点标识不属于本次基准版本。")
            before = old[change.existing_id]
            if change.identity_status != "confirmed" or not cited & {c["snippet_id"] for c in before["citations"]}:
                raise ValueError("沿用身份须确认同一概念，并同时提供旧资料与追加资料的依据。")
            fields["aliases"] = list(dict.fromkeys(before["aliases"] + [before["name"]] + change.aliases))
            fields["aliases"] = [a for a in fields["aliases"] if a != change.name]
            fields["chapter_ids"] = list(dict.fromkeys(before["chapter_ids"] + change.chapter_ids))
            fields["citations"] = list({c["snippet_id"]: c for c in fields["citations"] + before["citations"]}.values())
        concepts[key_map[change.key]] = ConceptDraft(key=key_map[change.key], **fields)
    relations = {(r["kind"], r["from_id"], r["to_id"]): RelationDraft(
        from_key=r["from_id"], to_key=r["to_id"], kind=r["kind"], origin=r["origin"],
        citation=r["citation"], reason=r["reason"])
        for r in previous["relations"] if r["kind"] != "contains"}
    for relation in update.relations:
        value = relation.model_copy(update={
            "from_key": key_map.get(relation.from_key, relation.from_key),
            "to_key": key_map.get(relation.to_key, relation.to_key),
        })
        relations[value.kind, value.from_key, value.to_key] = value
    draft = _CombinedDraft(concepts=list(concepts.values()), relations=list(relations.values()))
    validate_draft(draft, combined_source(previous, source))
    return draft, key_map


def validate_update(update: KnowledgeUpdate, previous: dict[str, Any], source: dict[str, Any]) -> None:
    """Check identity decisions and evidence before caching a successful integration."""
    _compose(update, previous, source)


def build_updated_snapshot(
    course_id: str, task_id: str, update: KnowledgeUpdate, pages: PagesDraft,
    previous: dict[str, Any], source: dict[str, Any],
) -> dict[str, Any]:
    draft, key_map = _compose(update, previous, source)
    if len(pages.pages) != len(key_map) or {page.key for page in pages.pages} != set(key_map):
        raise ValueError("追加知识页面与新增、补充知识点不一一对应。")
    old = {c["id"]: c for c in previous["concepts"]}
    all_pages = {cid: PageDraft(key=cid, page_md=c["page_md"], citations=c["citations"]) for cid, c in old.items()}
    all_pages.update({key_map[p.key]: p.model_copy(update={"key": key_map[p.key]}) for p in pages.pages})
    snapshot = build_snapshot(course_id, task_id, draft, PagesDraft(pages=list(all_pages.values())),
                              combined_source(previous, source), existing_ids=set(old))
    by_key = dict(zip((c.key for c in draft.concepts), snapshot["concepts"]))
    for concept in snapshot["concepts"]:
        concept["is_new"] = concept["id"] not in old
        concept["is_updated"] = False
        if concept["id"] in old:
            before = old[concept["id"]]
            concept["status"] = before["status"]
            if "identity_reason" in before:
                concept["identity_reason"] = before["identity_reason"]
    for change in update.concepts:
        concept = by_key[key_map[change.key]]
        concept.update(status=change.identity_status, identity_reason=change.identity_reason,
                       is_updated=bool(change.existing_id))
    old_relations = {(r["kind"], r["from_id"], r["to_id"]): r["id"] for r in previous["relations"]}
    for relation in snapshot["relations"]:
        relation["id"] = old_relations.get((relation["kind"], relation["from_id"], relation["to_id"]), relation["id"])
    snapshot["summary"] = {
        "new_concepts": sum(c["is_new"] for c in snapshot["concepts"]),
        "updated_concepts": sum(c["is_updated"] for c in snapshot["concepts"]),
        "conflicts": 0,
        "needs_review": sum(c["status"] == "needs_review" for c in snapshot["concepts"]),
    }
    validate_snapshot(snapshot)
    return snapshot
