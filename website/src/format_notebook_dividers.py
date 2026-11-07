#!/usr/bin/env python3
"""Add portable section ornaments to authored notebook Markdown headings.

Run explicitly; the website build never rewrites its notebook inputs. Only cell
source values are patched in the original JSON, preserving unrelated formatting.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import re
import sys
from typing import Iterator


ROOT = Path(__file__).resolve().parents[2]
MARKER = '<p align="center" class="section-break" aria-hidden="true" data-pagefind-ignore="all">• &nbsp; • &nbsp; •</p>'
ATX = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
RULE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
SETEXT = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|"
    "colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|"
    "form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|"
    "menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|"
    "table|tbody|td|tfoot|th|thead|title|tr|track|ul"
)
BLOCK_HTML = re.compile(rf"^ {{0,3}}</?(?:{BLOCK_TAGS})(?=[ \t/>]|$)", re.I)
RAW_HTML = re.compile(r"^ {0,3}<(script|pre|style|textarea)(?=[ \t>]|$)", re.I)
ATTRIBUTE = r"[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?"
COMPLETE_TAG = re.compile(rf"^ {{0,3}}</?[A-Za-z][A-Za-z0-9-]*(?:\s+{ATTRIBUTE})*\s*/?>\s*$")


def markdown_blocks(source: str) -> tuple[set[int], set[int]]:
    """Locate top-level ATX headings and actual thematic rules, not examples.

    Notebook Markdown cells render independently. HTML block termination follows
    Markdown's raw-element/comment terminators or blank-line rule. A hyphen rule
    following paragraph text is a Setext underline and must not be removed.
    """
    headings: set[int] = set()
    rules: set[int] = set()
    fence_char = ""
    fence_length = 0
    html_end: re.Pattern[str] | None = None
    html_until_blank = False
    paragraph = False

    for index, raw_line in enumerate(source.splitlines()):
        line = raw_line.rstrip("\r\n")
        if fence_char:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*", line):
                fence_char = ""
            continue
        if html_end is not None:
            if html_end.search(line):
                html_end = None
            continue
        if html_until_blank:
            if not line.strip():
                html_until_blank = False
            continue
        if not line.strip():
            paragraph = False
            continue
        if len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip(" ")) >= 4:
            # Four-space indented blocks and tabs are code, never headings.
            continue

        fence = FENCE.match(line)
        if fence and not (fence[1][0] == "`" and "`" in fence[2]):
            fence_char, fence_length = fence[1][0], len(fence[1])
            paragraph = False
            continue

        stripped = line.lstrip(" ")
        raw_tag = RAW_HTML.match(line)
        terminator = None
        if raw_tag:
            terminator = rf"</{raw_tag[1]}\s*>"
        elif stripped.startswith("<!--"):
            terminator = r"-->"
        elif stripped.startswith("<?"):
            terminator = r"\?>"
        elif stripped.startswith("<![CDATA["):
            terminator = r"\]\]>"
        elif re.match(r"<![A-Z]", stripped):
            terminator = r">"
        if terminator is not None:
            end = re.compile(terminator, re.I)
            if not end.search(line):
                html_end = end
            paragraph = False
            continue
        if BLOCK_HTML.match(line) or (not paragraph and COMPLETE_TAG.fullmatch(line)):
            html_until_blank = True
            paragraph = False
            continue
        if ATX.match(line):
            headings.add(index)
            paragraph = False
            continue
        if paragraph and SETEXT.fullmatch(line):
            paragraph = False
            continue
        if RULE.fullmatch(line):
            rules.add(index)
            paragraph = False
            continue
        paragraph = True

    return headings, rules


def format_markdown(source: str) -> str:
    """Insert one ornament in the heading's own cell; preserve heading text."""
    lines = source.splitlines(keepends=True)
    headings, rules = markdown_blocks(source)
    newline = "\r\n" if "\r\n" in source else "\n"
    for index in sorted(headings, reverse=True):
        previous = index - 1
        while previous >= 0 and not lines[previous].strip():
            previous -= 1
        start = index
        if previous in rules or (previous >= 0 and lines[previous].strip() == MARKER):
            start = previous
        prefix = newline if start > 0 and lines[start - 1].strip() else ""
        lines[start:index] = [prefix + MARKER + newline + newline]
    return "".join(lines)


def _source(cell: dict) -> str:
    source = cell.get("source", [])
    return source if isinstance(source, str) else "".join(source)


def _set_source(cell: dict, source: str) -> None:
    cell["source"] = source if isinstance(cell.get("source"), str) else source.splitlines(keepends=True)


def format_notebook(notebook: dict) -> set[int]:
    """Change Markdown sources only; return the indexes of changed cells."""
    cells = notebook.get("cells", [])
    originals = [_source(cell) for cell in cells]
    for index, cell in enumerate(cells):
        if cell.get("cell_type") != "markdown":
            continue
        source = _source(cell)
        lines = source.splitlines(keepends=True)
        headings, _ = markdown_blocks(source)
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        if first in headings and index > 0 and cells[index - 1].get("cell_type") == "markdown":
            previous = cells[index - 1]
            previous_source = _source(previous)
            previous_lines = previous_source.splitlines(keepends=True)
            last = next((i for i in range(len(previous_lines) - 1, -1, -1) if previous_lines[i].strip()), None)
            _, previous_rules = markdown_blocks(previous_source)
            if last in previous_rules:
                del previous_lines[last]
                remaining = "".join(previous_lines)
                _set_source(previous, remaining if remaining.strip() else "")
        formatted = format_markdown(source)
        if formatted != source:
            _set_source(cell, formatted)
    return {index for index, cell in enumerate(cells) if _source(cell) != originals[index]}


DECODER = json.JSONDecoder()


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _members(text: str, start: int) -> Iterator[tuple[str, int, int]]:
    """Yield exact JSON value spans without reserializing neighboring fields."""
    index = _skip_space(text, start + 1)
    while text[index] != "}":
        key, end = DECODER.raw_decode(text, index)
        index = _skip_space(text, end)
        index = _skip_space(text, index + 1)  # colon
        _, end = DECODER.raw_decode(text, index)
        yield key, index, end
        index = _skip_space(text, end)
        if text[index] == ",":
            index = _skip_space(text, index + 1)


def _items(text: str, start: int) -> Iterator[tuple[int, int]]:
    index = _skip_space(text, start + 1)
    while text[index] != "]":
        _, end = DECODER.raw_decode(text, index)
        yield index, end
        index = _skip_space(text, end)
        if text[index] == ",":
            index = _skip_space(text, index + 1)


def _source_json(original: str, value: str | list[str]) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    tokens: dict[str, deque[str]] = defaultdict(deque)
    spans = list(_items(original, 0))
    for start, end in spans:
        tokens[json.loads(original[start:end])].append(original[start:end])
    rendered = [tokens[line].popleft() if tokens[line] else json.dumps(line, ensure_ascii=False) for line in value]
    if not rendered:
        return "[]"
    if "\n" not in original:
        return "[" + ", ".join(rendered) + "]"
    first_start = spans[0][0]
    indent = original[original.rfind("\n", 0, first_start) + 1:first_start]
    closing_indent = original[original.rfind("\n") + 1:-1]
    newline = "\r\n" if "\r\n" in original else "\n"
    return "[" + newline + indent + ("," + newline + indent).join(rendered) + newline + closing_indent + "]"


def format_notebook_text(text: str) -> tuple[str, int]:
    """Return updated JSON and changed-cell count, retaining other bytes."""
    notebook = json.loads(text)
    changed = format_notebook(notebook)
    if not changed:
        return text, 0
    cells_start = next(start for key, start, _ in _members(text, _skip_space(text, 0)) if key == "cells")
    replacements = []
    for index, (start, _) in enumerate(_items(text, cells_start)):
        if index not in changed:
            continue
        source_start, source_end = next((a, b) for key, a, b in _members(text, start) if key == "source")
        replacement = _source_json(text[source_start:source_end], notebook["cells"][index]["source"])
        replacements.append((source_start, source_end, replacement))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text, len(changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Notebook files; defaults to all Notebooks/*.ipynb.")
    parser.add_argument("--check", action="store_true", help="Report pending formatting without writing; exit 1 if changes are needed.")
    args = parser.parse_args(argv)
    paths = args.paths or sorted((ROOT / "Notebooks").glob("*.ipynb"))
    pending = False
    for path in paths:
        try:
            with path.open(encoding="utf-8", newline="") as stream:
                original = stream.read()
            formatted, count = format_notebook_text(original)
            if not count:
                continue
            pending = True
            if not args.check:
                with path.open("w", encoding="utf-8", newline="") as stream:
                    stream.write(formatted)
            print(f"{'Would format' if args.check else 'Formatted'} {path}: {count} Markdown cell(s)")
        except (OSError, ValueError, KeyError, StopIteration, TypeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            return 2
    return 1 if args.check and pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
