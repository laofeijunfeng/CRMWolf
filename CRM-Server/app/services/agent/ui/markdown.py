"""Shared validation rules for the restricted Agent UI Markdown dialect."""

from __future__ import annotations

import re
from typing import Final, Literal

RAW_HTML_PATTERN: Final[str] = r"<(?:[A-Za-z][^>]*|/[A-Za-z][^>]*|![^>]*|\?[^>]*)>"
_RAW_HTML_RE = re.compile(RAW_HTML_PATTERN)

_DISALLOWED_BLOCK_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"(?m)^[ \t]{0,3}#{1,6}(?:[ \t]+|$)"), "headings"),
    (re.compile(r"(?m)^[ \t]{0,3}>"), "blockquotes"),
    (re.compile(r"(?m)^[ \t]{0,3}(?:`{3,}|~{3,})"), "fenced code blocks"),
    (
        re.compile(r"(?m)^[ \t]{0,3}(?:[-+*]|\d+[.)])[ \t]+\[[ xX]\](?:[ \t]+|$)"),
        "task lists",
    ),
    (
        re.compile(r"(?m)^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$"),
        "thematic breaks",
    ),
    (
        re.compile(r"(?m)^[^\n]*\S[^\n]*\n[ \t]{0,3}(?:=+|-+)[ \t]*$"),
        "setext headings",
    ),
    (re.compile(r"(?m)^(?: {4,}|\t)\S"), "indented code blocks"),
    (re.compile(r"(?m)^[ \t]{0,3}\[[^\]\n]+\]:"), "reference-style links"),
    (
        re.compile(
            r"(?m)^[ \t]*\|?[^\n|]+\|[^\n]*\n[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
        ),
        "tables",
    ),
)
_IMAGE_RE = re.compile(r"!\[")
_STRIKETHROUGH_RE = re.compile(r"~~")
_REFERENCE_LINK_RE = re.compile(r"\[[^\]\n]+\]\[[^\]\n]*\]")
_INLINE_LINK_RE = re.compile(r"\[[^\]\n]+\]\(([^)\n]*)\)")
_LINK_OPEN_RE = re.compile(r"\]\(")
_HTTP_LINK_RE = re.compile(r"https?://[^()]+", re.IGNORECASE)
_SETEXT_UNDERLINE_RE = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
_TABLE_SEPARATOR_ROW_RE = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
)


def contains_raw_html(text: str) -> bool:
    """Return whether text contains an HTML tag-like construct."""

    return _RAW_HTML_RE.search(text) is not None


def project_agent_markdown_to_plain_text(value: str) -> str:
    """Project Agent Markdown to deterministic searchable and accessible plain text."""

    projected = value.replace("\r\n", "\n").replace("\r", "\n")
    projected = _project_gfm_tables(projected)
    projected = _project_setext_headings(projected)
    projected = _RAW_HTML_RE.sub("", projected)
    projected = re.sub(r"(?m)^[ \t]{0,3}(?:`{3,}|~{3,})[^\n]*$", "", projected)
    projected = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+", "", projected)
    projected = re.sub(r"(?m)^[ \t]{0,3}>[ \t]?", "", projected)
    projected = re.sub(
        r"(?m)^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$",
        "",
        projected,
    )
    projected = re.sub(r"(?m)^[ \t]{0,3}(?:[-+*]|\d+[.)])[ \t]+\[[ xX]\][ \t]+", "", projected)
    projected = re.sub(r"(?m)^[ \t]{0,3}(?:[-+*]|\d+[.)])[ \t]+", "", projected)
    projected = re.sub(r"!\[([^]\n]*)\]\([^)]*\)", r"\1", projected)
    projected = re.sub(r"\[([^]\n]+)\]\(https?://[^)\n]+\)", r"\1", projected, flags=re.IGNORECASE)
    projected = re.sub(r"\[([^]\n]+)\]\[[^]\n]*\]", r"\1", projected)
    projected = re.sub(r"(?m)^[ \t]*\[[^]\n]+\]:[^\n]*$", "", projected)
    projected = re.sub(r"(`+)([^`\n]+)\1", r"\2", projected)
    projected = re.sub(r"(?<!\\)~~(.+?)(?<!\\)~~", r"\1", projected)
    projected = re.sub(r"(?<!\\)(?:\*\*|__)(.+?)(?<!\\)(?:\*\*|__)", r"\1", projected)
    projected = re.sub(r"(?<!\\)(?:\*|_)(.+?)(?<!\\)(?:\*|_)", r"\1", projected)
    projected = re.sub(r"\\([\\`*_[\]()+.!-])", r"\1", projected)
    lines = [line.rstrip() for line in projected.splitlines()]
    compacted: list[str] = []
    for line in lines:
        if not line and compacted and not compacted[-1]:
            continue
        compacted.append(line)
    return "\n".join(compacted).strip()


def _project_setext_headings(text: str) -> str:
    lines = text.splitlines()
    projected = [
        line
        for index, line in enumerate(lines)
        if not (
            index > 0
            and lines[index - 1].strip()
            and _SETEXT_UNDERLINE_RE.fullmatch(line) is not None
        )
    ]
    return "\n".join(projected)


def _project_gfm_tables(text: str) -> str:
    """Replace GFM table syntax with a tab-delimited, lossless text projection."""

    lines = text.splitlines()
    projected: list[str] = []
    index = 0
    while index < len(lines):
        if (
            index + 1 < len(lines)
            and "|" in lines[index]
            and _TABLE_SEPARATOR_ROW_RE.fullmatch(lines[index + 1]) is not None
        ):
            projected.append("\t".join(_split_gfm_table_row(lines[index])))
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                projected.append("\t".join(_split_gfm_table_row(lines[index])))
                index += 1
            continue
        projected.append(lines[index])
        index += 1
    return "\n".join(projected)


def _split_gfm_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith(r"\|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped:
        if escaped:
            if character == "|":
                current.append(character)
            else:
                current.extend(("\\", character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def normalize_agent_markdown_for_ui(value: str) -> tuple[str, Literal["plain", "markdown"]]:
    """Return model text in the closed Agent UI dialect without failing a turn.

    Assistant prose is model output and may contain Markdown constructs that the
    Agent UI intentionally does not support, such as reference-style links or
    tables.  Those constructs must not invalidate the whole CRM response.  Keep
    valid Markdown as-is; otherwise project it to safe plain text.
    """

    try:
        validate_agent_markdown(value)
    except ValueError:
        return project_agent_markdown_to_plain_text(value), "plain"
    return value, "markdown"


def validate_agent_markdown(text: str) -> None:
    """Raise ``ValueError`` when text uses Markdown outside the frozen allowlist."""

    if contains_raw_html(text):
        raise ValueError("text blocks must not contain raw HTML")

    for pattern, syntax_name in _DISALLOWED_BLOCK_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"markdown syntax is not allowed: {syntax_name}")

    visible_text = _mask_inline_code(text)
    if _has_unescaped_match(_IMAGE_RE, visible_text):
        raise ValueError("markdown syntax is not allowed: images")
    if _has_unescaped_match(_STRIKETHROUGH_RE, visible_text):
        raise ValueError("markdown syntax is not allowed: strikethrough")
    if _has_unescaped_match(_REFERENCE_LINK_RE, visible_text):
        raise ValueError("markdown syntax is not allowed: reference-style links")

    without_valid_links = list(visible_text)
    for match in _INLINE_LINK_RE.finditer(visible_text):
        if _is_escaped(visible_text, match.start()):
            continue
        destination = match.group(1).strip(" \t\r\n\f\v")
        if _HTTP_LINK_RE.fullmatch(destination) is None or any(
            _is_forbidden_link_whitespace(character) for character in destination
        ):
            raise ValueError("markdown links must use an absolute HTTP(S) URL")
        without_valid_links[match.start() : match.end()] = " " * (match.end() - match.start())

    if _has_unescaped_match(_LINK_OPEN_RE, "".join(without_valid_links)):
        raise ValueError("markdown links must use the supported inline HTTP(S) form")


def _is_forbidden_link_whitespace(character: str) -> bool:
    code_point = ord(character)
    return (
        0x0009 <= code_point <= 0x000D
        or 0x001C <= code_point <= 0x0020
        or code_point
        in {
            0x0085,
            0x00A0,
            0x1680,
            0x2028,
            0x2029,
            0x202F,
            0x205F,
            0x3000,
            0xFEFF,
        }
        or 0x2000 <= code_point <= 0x200A
    )


def _has_unescaped_match(pattern: re.Pattern[str], text: str) -> bool:
    return any(not _is_escaped(text, match.start()) for match in pattern.finditer(text))


def _mask_inline_code(text: str) -> str:
    """Mask complete inline-code spans while preserving offsets and newlines."""

    masked = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`" or _is_escaped(text, index):
            index += 1
            continue
        delimiter_end = index
        while delimiter_end < len(text) and text[delimiter_end] == "`":
            delimiter_end += 1
        delimiter = text[index:delimiter_end]
        closing = text.find(delimiter, delimiter_end)
        if closing == -1 or "\n" in text[delimiter_end:closing]:
            index = delimiter_end
            continue
        closing_end = closing + len(delimiter)
        for position in range(index, closing_end):
            if masked[position] != "\n":
                masked[position] = " "
        index = closing_end
    return "".join(masked)


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        slash_count += 1
        index -= 1
    return slash_count % 2 == 1
