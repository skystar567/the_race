"""Safe reading HTML; math is rendered by KaTeX in the browser."""

from html import escape

from markdown_it import MarkdownIt


def math_inline(state, silent):
    start = state.pos
    if state.src[start] != "$":
        return False
    delimiter = "$$" if state.src.startswith("$$", start) else "$"
    begin = start + len(delimiter)
    if begin >= state.posMax or (delimiter == "$" and state.src[begin].isspace()):
        return False
    end = state.src.find(delimiter, begin)
    while end >= 0 and state.src[end - 1] == "\\":
        end = state.src.find(delimiter, end + len(delimiter))
    if end < 0 or end >= state.posMax:
        return False
    if not silent:
        token = state.push("math", "", 0)
        token.content = state.src[begin:end]
        token.meta["display"] = delimiter == "$$"
    state.pos = end + len(delimiter)
    return True


def math_block(state, start_line, end_line, silent):
    start = state.bMarks[start_line] + state.tShift[start_line]
    if not state.src.startswith("$$", start):
        return False
    end = state.src.find("$$", start + 2)
    if end < 0 or end > state.eMarks[end_line - 1]:
        return False
    if silent:
        return True
    last_line = start_line
    while last_line + 1 < end_line and state.bMarks[last_line + 1] <= end:
        last_line += 1
    trailing = state.src[end + 2:state.eMarks[last_line]]
    if last_line == start_line and trailing.strip():
        return False
    token = state.push("math", "", 0)
    token.content = state.src[start + 2:end].strip()
    token.meta["display"] = True
    token.map = [start_line, last_line + 1]
    if trailing.strip():
        state.push("paragraph_open", "p", 1)
        tail = state.push("inline", "", 0)
        tail.content = trailing.strip()
        tail.children = []
        state.push("paragraph_close", "p", -1)
    state.line = last_line + 1
    return True


def render_math(tokens, index, options, env):
    token = tokens[index]
    display = "true" if token.meta.get("display") else "false"
    return f'<span class="math-source" data-math="{escape(token.content, quote=True)}" data-display="{display}">{escape(token.content)}</span>'


def render_missing_image(tokens, index, options, env):
    token = tokens[index]
    alt = escape(token.content or "教材插图")
    location = escape(token.attrGet("src") or "")
    return f'<span class="missing-image" role="note"><strong>未导入图片 · {alt}</strong><span>{location}</span><small>当前资料仅包含 Markdown，无法显示或解读这张图片。</small></span>'


def markdown_parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": False, "breaks": False})
    parser.enable("table")
    parser.inline.ruler.before("escape", "math", math_inline)
    parser.block.ruler.before("fence", "math_block", math_block)
    parser.renderer.rules["math"] = render_math
    parser.renderer.rules["image"] = render_missing_image
    return parser


def reference_context(markdown: str) -> dict:
    context = {}
    markdown_parser().parse(markdown.lstrip("\ufeff"), context)
    return context


def render(markdown: str, context: dict | None = None) -> str:
    return markdown_parser().render(markdown.lstrip("\ufeff"), context or {})
