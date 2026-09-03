"""Canonical contracts shared by customer-activity write and job workflows.

This module is intentionally dependency-light.  It is the single vocabulary
for activity provenance and durable activity-related execution states; API,
workflow, worker, and migration code must not invent parallel string values.
"""

from __future__ import annotations

from enum import StrEnum


class CustomerActivitySubmissionSource(StrEnum):
    """The authoritative origin of an activity submission."""

    AGENT = "AGENT"
    FORM = "FORM"
    CUTOVER_MIGRATION = "CUTOVER_MIGRATION"


class CustomerActivityProcessingStatus(StrEnum):
    """Projection of canonical structuring/processing state on an activity."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CustomerActivityEffectivenessStatus(StrEnum):
    """Projection of canonical activity evaluation state on an activity."""

    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CustomerActivityAIJobStatus(StrEnum):
    """Durable structuring/evaluation job lifecycle."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_PENDING = "RETRY_PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"


class CustomerActivitySuggestionJobStatus(StrEnum):
    """Durable opportunity-suggestion job lifecycle."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_PENDING = "RETRY_PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"


CUSTOMER_ACTIVITY_FIELD_SOURCES = frozenset(
    {
        "UI_DEFAULT",
        "USER",
        "AI_EXTRACTED",
        "AGENT",
        "MIGRATED",
    }
)


def enum_values(enum_type: type[StrEnum]) -> tuple[str, ...]:
    """Return stable values for schema and database constraint generation."""

    return tuple(item.value for item in enum_type)
