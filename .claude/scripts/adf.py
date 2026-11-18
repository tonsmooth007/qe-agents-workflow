"""Minimal Atlassian Document Format (ADF) <-> Markdown conversion for Jira Cloud v3."""
from __future__ import annotations

import re
from typing import Any


# --------------------------------------------------------------------------- ADF -> Markdown
def adf_to_md(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    return _block(node, 0).strip() + "\n"


def _children(node: dict, depth: int, sep: str = "") -> str:
    return sep.join(_block(c, depth) for c in node.get("content", []) or [])


def _inline(node: dict) -> str:
    t = node.get("type")
    if t == "text":
        txt = node.get("text", "")
        for m in node.get("marks", []) or []:
            mt = m.get("type")
            if mt == "strong":
                txt = f"**{txt}**"
            elif mt == "em":
                txt = f"*{txt}*"
            elif mt == "code":
                txt = f"`{txt}`"
            elif mt == "strike":
                txt = f"~~{txt}~~"
            elif mt == "link":
                txt = f"[{txt}]({m.get('attrs', {}).get('href', '')})"
        return txt
    if t == "hardBreak":
        return "  \n"
    if t == "mention":
        return "@" + (node.get("attrs", {}).get("text") or "user").lstrip("@")
    if t == "emoji":
        return node.get("attrs", {}).get("text") or node.get("attrs", {}).get("shortName", "")
    if t in ("inlineCard", "blockCard", "embedCard"):
        return node.get("attrs", {}).get("url", "")
    if t == "status":
        return f"[{node.get('attrs', {}).get('text', '')}]"
    if t == "date":
        return str(node.get("attrs", {}).get("timestamp", ""))
    return "".join(_inline(c) for c in node.get("content", []) or [])


def _block(node: dict, depth: int) -> str:
    t = node.get("type")
    ind = "  " * depth
    if t == "doc":
        return _children(node, depth)
    if t == "paragraph":
        return "".join(_inline(c) for c in node.get("content", []) or []) + "\n\n"
    if t == "heading":
        lvl = node.get("attrs", {}).get("level", 2)
        return "#" * lvl + " " + "".join(_inline(c) for c in node.get("content", []) or []) + "\n\n"
    if t in ("bulletList", "orderedList", "taskList"):
        lines = []
        for i, item in enumerate(node.get("content", []) or [], 1):
            if t == "orderedList":
                bullet = f"{i}."
            elif t == "taskList":
                bullet = "- [x]" if item.get("attrs", {}).get("state") == "DONE" else "- [ ]"
            else:
                bullet = "-"
            body = _list_item(item, depth)
            lines.append(f"{ind}{bullet} {body}")
        return "\n".join(lines) + ("\n\n" if depth == 0 else "\n")
    if t == "codeBlock":
        lang = node.get("attrs", {}).get("language", "") or ""
        code = "".join(c.get("text", "") for c in node.get("content", []) or [])
        return f"```{lang}\n{code}\n```\n\n"
    if t == "blockquote":
        inner = _children(node, depth).strip().splitlines()
        return "\n".join("> " + l for l in inner) + "\n\n"
    if t == "panel":
        kind = node.get("attrs", {}).get("panelType", "info").upper()
        inner = _children(node, depth).strip().splitlines()
        return f"> **{kind}:**\n" + "\n".join("> " + l for l in inner) + "\n\n"
    if t == "rule":
        return "---\n\n"
    if t == "table":
        rows = node.get("content", []) or []
        md_rows = []
        for r_i, row in enumerate(rows):
            cells = [_children(c, depth).strip().replace("\n", " ").replace("|", "\\|") for c in row.get("content", []) or []]
            md_rows.append("| " + " | ".join(cells) + " |")
            if r_i == 0:
                md_rows.append("|" + "---|" * len(cells))
        return "\n".join(md_rows) + "\n\n"
    if t in ("mediaSingle", "mediaGroup"):
        names = [m.get("attrs", {}).get("alt") or m.get("attrs", {}).get("id", "media") for m in node.get("content", []) or []]
        return "".join(f"[attachment: {n}]\n" for n in names) + "\n"
    if t == "expand" or t == "nestedExpand":
        title = node.get("attrs", {}).get("title", "")
        return f"**{title}**\n\n" + _children(node, depth)
    if t in ("listItem", "taskItem"):
        return _list_item(node, depth)
    # inline fallthrough
    return _inline(node)


def _list_item(item: dict, depth: int) -> str:
    parts = []
    for c in item.get("content", []) or []:
        if c.get("type") in ("bulletList", "orderedList", "taskList"):
            parts.append("\n" + _block(c, depth + 1).rstrip("\n"))
        elif c.get("type") == "paragraph":
            parts.append("".join(_inline(x) for x in c.get("content", []) or []))
        elif c.get("type") == "text":
            parts.append(_inline(c))
        else:
            parts.append(_block(c, depth + 1).strip())
    return "".join(parts)


# --------------------------------------------------------------------------- Markdown -> ADF
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def _md_inline(text: str) -> list[dict]:
    nodes: list[dict] = []
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            nodes.append({"type": "text", "text": part[2:-2], "marks": [{"type": "strong"}]})
        elif part.startswith("`") and part.endswith("`"):
            nodes.append({"type": "text", "text": part[1:-1], "marks": [{"type": "code"}]})
        elif part.startswith("["):
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if m:
                nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "link", "attrs": {"href": m.group(2)}}]})
            else:
                nodes.append({"type": "text", "text": part})
        else:
            nodes.append({"type": "text", "text": part})
    return nodes


def md_to_adf(md: str) -> dict:
    """Headings, paragraphs, bullet/ordered lists, fenced code, simple tables -> ADF."""
    lines = md.replace("\r\n", "\n").split("\n")
    content: list[dict] = []
    i = 0
    para: list[str] = []

    def flush_para():
        if para:
            content.append({"type": "paragraph", "content": _md_inline(" ".join(s.strip() for s in para))})
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush_para()
            lang = s[3:].strip() or None
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i]); i += 1
            node = {"type": "codeBlock", "content": [{"type": "text", "text": "\n".join(code) or " "}]}
            if lang:
                node["attrs"] = {"language": lang}
            content.append(node)
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", s)
        if h:
            flush_para()
            content.append({"type": "heading", "attrs": {"level": len(h.group(1))}, "content": _md_inline(h.group(2))})
            i += 1
            continue
        if re.match(r"^([-*]|\d+\.)\s+", s):
            flush_para()
            ordered = bool(re.match(r"^\d+\.", s))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                txt = re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])
                items.append({"type": "listItem", "content": [{"type": "paragraph", "content": _md_inline(txt) or [{"type": "text", "text": " "}]}]})
                i += 1
            content.append({"type": "orderedList" if ordered else "bulletList", "content": items})
            continue
        if s.startswith("|") and s.endswith("|"):
            flush_para()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                r = lines[i].strip()
                if not re.match(r"^\|[\s:|-]+\|$", r):
                    rows.append([c.strip() for c in r.strip("|").split("|")])
                i += 1
            table_rows = []
            for r_i, r in enumerate(rows):
                cell_type = "tableHeader" if r_i == 0 else "tableCell"
                table_rows.append({"type": "tableRow", "content": [
                    {"type": cell_type, "content": [{"type": "paragraph", "content": _md_inline(c) or [{"type": "text", "text": " "}]}]}
                    for c in r]})
            content.append({"type": "table", "content": table_rows})
            continue
        if not s:
            flush_para()
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para()
    return {"type": "doc", "version": 1, "content": content or [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}]}
