"""Checkpoint-safe normalization for durable business effects produced by tools."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.state import AgentPostWriteEffects

_CANONICAL_KEY = "follow_up_confirmation_case_public_ids"
_LEGACY_KEY = "confirmation_case_public_ids"


def normalize_post_write_effects(value: object) -> AgentPostWriteEffects:
    """Adapt a known tool/result envelope into the canonical checkpoint shape."""

    return {
        _CANONICAL_KEY: _deduplicate(_ids_from_known_envelope(value)),
    }


def merge_post_write_effects(*effects: object) -> AgentPostWriteEffects:
    case_public_ids: list[str] = []
    for effect in effects:
        case_public_ids.extend(_ids_from_known_envelope(effect))
    return {_CANONICAL_KEY: _deduplicate(case_public_ids)}


def _ids_from_known_envelope(value: object) -> list[str]:
    if isinstance(value, Mapping):
        direct = _ids_from_mapping(value)
        if direct:
            return direct
        # Compatibility adapters for the explicit envelopes emitted by tool/runtime boundaries.
        for key in ("post_write_effects", "post_commit", "data", "tool_result", "result"):
            nested = value.get(key)
            nested_ids = _ids_from_known_envelope(nested)
            if nested_ids:
                return nested_ids
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: list[str] = []
        for item in value:
            result.extend(_ids_from_known_envelope(item))
        return result
    data = getattr(value, "data", None)
    return _ids_from_known_envelope(data) if data is not None else []


def _ids_from_mapping(value: Mapping[object, object]) -> list[str]:
    for key in (_CANONICAL_KEY, _LEGACY_KEY):
        raw_ids = value.get(key)
        if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, (str, bytes)):
            return [str(item).strip() for item in raw_ids if isinstance(item, str) and item.strip()]
    return []


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
