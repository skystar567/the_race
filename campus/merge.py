"""Merge a new scope into the current snapshot without losing old knowledge.

Concept identity is matched by name/alias. A same-name concept whose definition
and evidence disagree is kept as a second concept and recorded as an open
conflict instead of being silently merged.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4


def _key(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _name_key(text: str) -> str:
    """Match display names without parenthetical English glosses or punctuation."""
    value = re.sub(r"[（(].*?[）)]", "", text or "")
    value = re.sub(r"[\s·,，。:：;；/]+", "", value)
    return value.lower()


def _citation_keys(concept: dict[str, Any]) -> set[tuple[str, str]]:
    return {(item["snippet_id"], _key(item["quote"])) for item in concept.get("citations", [])}


def _citation_snippets(concept: dict[str, Any]) -> set[str]:
    return {item["snippet_id"] for item in concept.get("citations", [])}


def _similar(left: str, right: str) -> bool:
    def terms(text: str) -> set[str]:
        clean = _key(text)
        words = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", clean))
        for word in list(words):
            if re.fullmatch(r"[\u4e00-\u9fff]+", word):
                words.update(word[index:index + 2] for index in range(len(word) - 1))
        return words

    a, b = terms(left), terms(right)
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.3


def merge_snapshots(previous: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    old_concepts = {concept["id"]: concept for concept in previous["concepts"]}
    old_by_key: dict[str, dict[str, Any]] = {}
    for concept in previous["concepts"]:
        old_by_key.setdefault(_name_key(concept["name"]), concept)
        for alias in concept.get("aliases", []):
            old_by_key.setdefault(_name_key(alias), concept)
    mapping: dict[str, str] = {}
    merged: dict[str, dict[str, Any]] = {concept_id: dict(concept) for concept_id, concept in old_concepts.items()}
    conflicts: list[dict[str, Any]] = list(previous.get("conflicts", []))
    new_count = updated_count = 0
    for concept in incoming["concepts"]:
        match = old_by_key.get(_name_key(concept["name"]))
        if match is None:
            for alias in concept.get("aliases", []):
                match = old_by_key.get(_name_key(alias))
                if match:
                    break
        incoming_id = concept["id"]
        if match is None:
            merged[incoming_id] = dict(concept)
            mapping[incoming_id] = incoming_id
            new_count += 1
            continue
        definition_changed = _key(match.get("definition", "")) != _key(concept.get("definition", ""))
        evidence_changed = bool(_citation_keys(match) and _citation_keys(concept)
                                and _citation_keys(match) != _citation_keys(concept))
        same_evidence = bool(_citation_snippets(match) & _citation_snippets(concept))
        if (definition_changed and evidence_changed
                and not same_evidence
                and not _similar(match.get("definition", ""), concept.get("definition", ""))):
            # Same name, different meaning: keep both identities and flag it.
            merged[incoming_id] = dict(concept) | {"is_new": True, "status": "unverified"}
            conflicts.append({
                "id": str(uuid4()),
                "concept_id": incoming_id,
                "other_concept_id": match["id"],
                "name": concept["name"],
                "kind": "same-name-different-definition",
                "previous_definition": match.get("definition", ""),
                "incoming_definition": concept.get("definition", ""),
                "status": "open",
            })
            mapping[incoming_id] = incoming_id
            new_count += 1
            continue
        merged_id = match["id"]
        mapping[incoming_id] = merged_id
        updated = dict(concept)
        updated["id"] = merged_id
        updated["is_new"] = False
        updated["aliases"] = sorted(set(match.get("aliases", [])) | set(concept.get("aliases", [])))
        updated["chapter_ids"] = sorted(set(match.get("chapter_ids", [])) | set(concept.get("chapter_ids", [])))
        updated["citations"] = _dedupe_citations(match.get("citations", []), concept.get("citations", []))
        if not updated.get("page_md", "").strip():
            updated["page_md"] = match.get("page_md", "")
        merged[merged_id] = updated
        updated_count += 1

    def remap(value: str) -> str:
        return mapping.get(value, value)

    relations = list(previous["relations"])
    relation_ids = {relation["id"] for relation in relations}
    seen = {(relation["kind"], relation["from_id"], relation["to_id"]) for relation in relations}
    for relation in incoming["relations"]:
        item = dict(relation)
        if item["from_type"] == "concept":
            item["from_id"] = remap(item["from_id"])
        if item["to_type"] == "concept":
            item["to_id"] = remap(item["to_id"])
        key = (item["kind"], item["from_id"], item["to_id"])
        if key in seen:
            continue
        if item["id"] in relation_ids:
            # Older snapshots and local model keys can produce the same
            # deterministic id for different relations; never publish duplicates.
            item["id"] = str(uuid4())
        seen.add(key)
        relation_ids.add(item["id"])
        relations.append(item)

    chapters = {chapter["id"]: chapter for chapter in previous["chapters"]}
    chapters.update({chapter["id"]: chapter for chapter in incoming["chapters"]})
    fragments = {fragment["id"]: fragment for fragment in previous["fragments"]}
    fragments.update({fragment["id"]: fragment for fragment in incoming["fragments"]})
    selection = {
        "material_ids": sorted(set(previous.get("selection", {}).get("material_ids", []))
                               | set(incoming.get("selection", {}).get("material_ids", []))),
        "chapter_ids": sorted(set(previous.get("selection", {}).get("chapter_ids", []))
                              | set(incoming.get("selection", {}).get("chapter_ids", []))),
    }
    return incoming | {
        "concepts": list(merged.values()),
        "relations": relations,
        "chapters": list(chapters.values()),
        "fragments": list(fragments.values()),
        "selection": selection,
        "conflicts": conflicts,
        "summary": {"new_concepts": new_count, "updated_concepts": updated_count,
                    "conflicts": len([item for item in conflicts if item.get("status") == "open"])},
        "validated": True,
    }


def _dedupe_citations(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for citation in group:
            key = (citation["snippet_id"], _key(citation["quote"]))
            if key not in seen:
                seen.add(key)
                result.append(citation)
    return result
