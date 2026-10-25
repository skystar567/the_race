"""Incremental merge: stable identity, new concepts and same-name conflicts."""

from campus.merge import merge_snapshots


def concept(concept_id, name, definition, snippet, quote):
    return {
        "id": concept_id, "name": name, "aliases": [], "definition": definition,
        "page_md": f"# {name}", "chapter_ids": ["ch1"], "status": "confirmed",
        "is_new": True, "citations": [{"snippet_id": snippet, "quote": quote}],
    }


def base():
    return {
        "course_id": "course", "version_id": "v1", "state": "published",
        "selection": {"material_ids": ["m1"], "chapter_ids": ["ch1"]},
        "summary": {"new_concepts": 1, "updated_concepts": 0, "conflicts": 0},
        "validated": True,
        "chapters": [{"id": "ch1", "material_id": "m1", "title": "第一章",
                      "level": 1, "parent_id": None, "start_line": 1, "end_line": 10,
                      "filename": "教材.md"}],
        "fragments": [{"id": "f1", "material_id": "m1", "chapter_id": "ch1",
                       "start_line": 1, "end_line": 1, "kind": "paragraph",
                       "markdown": "进程是资源单位。", "missing_images": 0,
                       "filename": "教材.md"}],
        "concepts": [concept("old-process", "进程", "资源单位", "f1", "进程是资源单位")],
        "relations": [{"id": "r1", "kind": "contains", "from_type": "chapter",
                       "from_id": "ch1", "to_type": "concept", "to_id": "old-process",
                       "origin": "source", "citation": None, "reason": "章节归属"}],
    }


def incoming(name="进程", definition="资源单位", snippet="f1", quote="进程是资源单位"):
    return {
        "course_id": "course", "version_id": "candidate", "state": "candidate",
        "selection": {"material_ids": ["m2"], "chapter_ids": ["ch2"]},
        "summary": None,
        "chapters": [{"id": "ch2", "material_id": "m2", "title": "第二章",
                      "level": 1, "parent_id": None, "start_line": 1, "end_line": 10,
                      "filename": "教材2.md"}],
        "fragments": [{"id": "f2", "material_id": "m2", "chapter_id": "ch2",
                       "start_line": 1, "end_line": 1, "kind": "paragraph",
                       "markdown": "线程是调度单位。", "missing_images": 0,
                       "filename": "教材2.md"}],
        "concepts": [concept("new-concept", name, definition, snippet, quote),
                     concept("new-thread", "线程", "调度单位", "f2", "线程是调度单位")],
        "relations": [{"id": "r2", "kind": "precedes", "from_type": "concept",
                       "from_id": "new-concept", "to_type": "concept", "to_id": "new-thread",
                       "origin": "suggested", "citation": None, "reason": "学习建议"}],
    }


def test_same_concept_keeps_old_identity_and_merges_new_one():
    merged = merge_snapshots(base(), incoming())
    process = [item for item in merged["concepts"] if item["name"] == "进程"]
    assert len(process) == 1
    assert process[0]["id"] == "old-process"
    assert merged["summary"] == {"new_concepts": 1, "updated_concepts": 1, "conflicts": 0}
    assert any(item["name"] == "线程" and item["id"] == "new-thread" for item in merged["concepts"])
    relation = next(item for item in merged["relations"] if item["kind"] == "precedes")
    assert relation["from_id"] == "old-process"


def test_same_name_different_definition_is_a_conflict():
    merged = merge_snapshots(base(), incoming(definition="程序的一次执行", snippet="f2", quote="线程是调度单位"))
    process = [item for item in merged["concepts"] if item["name"] == "进程"]
    assert len(process) == 2
    assert {item["id"] for item in process} == {"old-process", "new-concept"}
    assert merged["summary"]["conflicts"] == 1
    assert merged["conflicts"][0]["kind"] == "same-name-different-definition"
