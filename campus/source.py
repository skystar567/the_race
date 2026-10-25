"""Identify source locations without rewriting the uploaded text."""

import re
from uuid import UUID, uuid5

from .reading import markdown_parser


def heading_level(title: str, markdown_level: int, numbered_level: int) -> int:
    if re.match(r"^第\s*[一二三四五六七八九十百零〇\d]+\s*[章节篇]", title):
        return 1
    number = re.match(r"^(\d+(?:\.\d+)+)(?:\s|[、.．])", title)
    if number:
        return len(number[1].split("."))
    if re.match(r"^\d+[.．、]\s*\S", title):
        return min(numbered_level + 1, 6)
    return markdown_level


def parse_source(material_id: str, text: str):
    parser = markdown_parser()
    context = {}
    tokens = parser.parse(text.lstrip("\ufeff"), context)
    # Markdown line maps count CR/LF, not Unicode paragraph separators.
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    if lines and not lines[-1]:
        lines.pop()
    namespace = UUID(material_id)
    chapters, fragments, stack = [], [], []
    numbered_level = 1
    for index, token in enumerate(tokens):
        if token.level != 0 or token.map is None:
            continue
        start, stop = token.map
        if token.type == "heading_open":
            title = tokens[index + 1].content
            level = heading_level(title, int(token.tag[1:]), numbered_level)
            if level == 1 or re.match(r"^\d+(?:\.\d+)+\s", title):
                numbered_level = level
            while stack and stack[-1]["level"] >= level:
                stack.pop()["end_line"] = start
            chapter = {
                "id": str(uuid5(namespace, f"chapter:{start}")), "title": title,
                "level": level, "start_line": start + 1, "end_line": len(lines),
                "parent_id": stack[-1]["id"] if stack else None,
            }
            chapters.append(chapter)
            stack.append(chapter)
        markdown = "".join(lines[start:stop])
        image_count = sum(
            child.type == "image"
            for parsed in parser.parse(markdown, context) for child in (parsed.children or [])
        )
        fragments.append({
            "id": str(uuid5(namespace, f"fragment:{start}:{stop}")),
            "chapter_id": stack[-1]["id"] if stack else None,
            "start_line": start + 1, "end_line": stop,
            "kind": token.type.removesuffix("_open"),
            "markdown": markdown, "missing_images": image_count,
        })
    return chapters, fragments
