from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.list_query.errors import ListQueryError
from app.core.list_query.parse import parse_filters, parse_sorts, resolve_list_query
from app.core.list_query.types import FilterCondition, SortCondition


def parse_request_filters(raw: Any) -> list[FilterCondition]:
    try:
        return parse_filters(raw)
    except ListQueryError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


def parse_request_sorts(raw: Any) -> list[SortCondition]:
    try:
        return parse_sorts(raw)
    except ListQueryError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


def optional_request_filters(raw: Any) -> list[FilterCondition] | None:
    if raw is None or raw == "":
        return None
    return parse_request_filters(raw)


def optional_request_sorts(raw: Any) -> list[SortCondition] | None:
    if raw is None or raw == "":
        return None
    return parse_request_sorts(raw)


def optional_request_list_query(
    *,
    filters_raw: Any = None,
    sorts_raw: Any = None,
) -> tuple[list[FilterCondition] | None, list[SortCondition] | None]:
    """Parse explicitly supplied list-query parameters without losing protocol presence."""
    return optional_request_filters(filters_raw), optional_request_sorts(sorts_raw)


def resolve_request_list_query(
    *, filters_raw: Any = None, sorts_raw: Any = None, legacy_filters=None, legacy_sorts=None
):
    try:
        return resolve_list_query(
            filters_raw=filters_raw,
            sorts_raw=sorts_raw,
            legacy_filters=legacy_filters,
            legacy_sorts=legacy_sorts,
        )
    except ListQueryError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


def run_or_400(func):
    try:
        return func()
    except ListQueryError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


def owner_values_from_filters(filters, field: str = "owner_id") -> list[str]:
    values: list[str] = []
    for condition in parse_filters(filters):
        if condition.field != field or condition.op not in {"eq", "contains", "in"}:
            continue
        raw = condition.value
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            if item is None or item == "":
                continue
            values.append(str(item))
    return values


def enforce_owner_view_scope(
    filters,
    *,
    current_user_id: str,
    has_view_all: bool,
    permission_detail: str,
    field: str = "owner_id",
    default_to_self: bool = True,
) -> str | None:
    requested = []
    for value in owner_values_from_filters(filters, field):
        normalized = str(current_user_id) if value.lower() in {"me", "my"} else value
        requested.append(normalized)
    if requested and any(item != str(current_user_id) for item in requested) and not has_view_all:
        raise HTTPException(status_code=403, detail=permission_detail)
    if has_view_all or requested or not default_to_self:
        return None
    return str(current_user_id)
