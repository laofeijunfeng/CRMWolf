"""Authoritative provenance policy for AI-enriched customer-activity fields."""

from __future__ import annotations

from typing import TypeVar

AI_EXTRACTED_SOURCE = "AI_EXTRACTED"
AI_REPLACEABLE_SOURCES = frozenset({"AI_EXTRACTED", "UI_DEFAULT"})

ValueT = TypeVar("ValueT")


def can_apply_ai_extracted_value(*, current_value: ValueT | None, current_source: str | None) -> bool:
    """Allow AI to fill an empty field or revise a value already owned by AI/defaulting.

    USER, AGENT, MIGRATED, and unknown non-empty values are authoritative. This
    keeps model enrichment from overwriting information explicitly supplied by
    a person or an upstream deterministic Agent tool.
    """

    if current_value is None:
        return True
    return current_source in AI_REPLACEABLE_SOURCES
