"""Resolve explicit selections using only the materials module's public API."""

from typing import Any

from .knowledge_models import ScopeInput
from .materials import Materials

# A single first build is bounded and fails visibly instead of silently dropping
# source text. Reviewed for ticket 02: one textbook subsection with a few pages
# fits comfortably; a whole chapter set does not.
MAX_SCOPE_CHARACTERS = 60_000


def resolve_scope(
    materials: Materials, course_id: str, selection: ScopeInput,
    *, organized_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Validate course ownership and collect unique, unchanged source fragments."""
    available = materials.list_materials(course_id)
    details = {item["id"]: materials.detail(course_id, item["id"]) for item in available}
    chapters = {
        chapter["id"]: (item["id"], chapter)
        for item in details.values()
        for chapter in item["chapters"]
    }
    if not selection.material_ids and not selection.chapter_ids:
        raise ValueError("请选择至少一份资料或一个章节。")
    if any(mid not in details for mid in selection.material_ids) or any(
        cid not in chapters for cid in selection.chapter_ids
    ):
        raise LookupError("整理范围包含不存在或不属于当前课程的资料、章节。")

    chosen_materials = set(selection.material_ids)
    chosen_chapters = set(selection.chapter_ids)
    fragments: dict[str, dict[str, Any]] = {}
    selected_chapters: dict[str, dict[str, Any]] = {}
    for material_id, detail in details.items():
        whole_material = material_id in chosen_materials
        ranges = [chapter for chapter in detail["chapters"] if chapter["id"] in chosen_chapters]
        if not whole_material and not ranges:
            continue
        for chapter in detail["chapters"]:
            inside = any(
                selected["start_line"] <= chapter["start_line"] <= selected["end_line"]
                for selected in ranges
            )
            if whole_material or inside:
                selected_chapters[chapter["id"]] = chapter | {
                    "material_id": material_id,
                    "filename": detail["filename"],
                }
        for fragment in materials.fragments(course_id, material_id):
            inside = any(
                selected["start_line"] <= fragment["start_line"]
                and fragment["end_line"] <= selected["end_line"]
                for selected in ranges
            )
            if (whole_material or inside) and fragment["id"] not in (organized_ids or set()):
                fragments[fragment["id"]] = fragment | {
                    "material_id": material_id,
                    "filename": detail["filename"],
                }

    if not fragments:
        if organized_ids:
            raise ValueError("所选范围已有知识，全部片段均已整理；请选择尚未整理的资料或章节。")
        raise ValueError("所选范围没有可整理的原文。")
    character_count = sum(len(fragment["markdown"]) for fragment in fragments.values())
    if character_count > MAX_SCOPE_CHARACTERS:
        raise ValueError(
            f"当前整理范围约 {character_count:,} 字符，超过单次 {MAX_SCOPE_CHARACTERS:,} 字符上限；"
            "请先选择更小的小节。"
        )
    return {
        "selection": selection.model_dump(),
        "chapters": sorted(
            selected_chapters.values(),
            key=lambda chapter: (chapter["material_id"], chapter["start_line"]),
        ),
        "fragments": sorted(
            fragments.values(),
            key=lambda fragment: (fragment["material_id"], fragment["start_line"]),
        ),
        "character_count": character_count,
    }
