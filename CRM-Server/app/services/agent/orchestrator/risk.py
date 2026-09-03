"""Structural safety helpers for the Root Orchestrator.

Semantic routing is deliberately *not* implemented here. Ordinary language
must be classified by the Root LLM. This module only recognizes identifiers
whose grammar is part of a server-owned contract; it must never decide whether
a sentence is a query, a workflow, or a continuation.
"""

from __future__ import annotations

import re

_CASE_PUBLIC_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])fuc_[0-9a-f]{32}(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def extract_case_public_id(text: str) -> str | None:
    """Extract a syntactically valid confirmation Case public ID.

    The returned value is only a candidate identifier. Ownership and existence
    are still checked against the server-side context before it can be used.
    """

    match = _CASE_PUBLIC_ID_PATTERN.search(text)
    return match.group(0).lower() if match is not None else None
