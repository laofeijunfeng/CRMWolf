from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.core.list_query.errors import ListQueryError
from app.core.list_query.types import FilterCondition, SortCondition


def parse_filters(raw: Any) -> list[FilterCondition]:
    payload = _load_payload(raw, empty_detail="筛选条件格式不正确", root_key="filters")
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ListQueryError("filters must be a list")

    conditions: list[FilterCondition] = []
    for item in payload:
        if isinstance(item, FilterCondition):
            conditions.append(item)
            continue
        if not isinstance(item, dict):
            raise ListQueryError("筛选条件格式不正确")
        field = item.get("field")
        op = item.get("op")
        if not field or not op:
            raise ListQueryError("筛选条件缺少 field 或 op")
        conditions.append(FilterCondition(field=str(field), op=str(op), value=item.get("value")))
    return conditions


def parse_sorts(raw: Any) -> list[SortCondition]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list) or isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            payload = _load_json(stripped, "排序条件格式不正确")
        else:
            payload = _parse_legacy_sort_string(stripped)
    else:
        raise ListQueryError("排序条件格式不正确")

    if isinstance(payload, dict):
        payload = payload.get("sorts", [])
    if not isinstance(payload, list):
        raise ListQueryError("sorts must be a list")

    sorts: list[SortCondition] = []
    for item in payload:
        if isinstance(item, SortCondition):
            sorts.append(item)
            continue
        if not isinstance(item, dict):
            raise ListQueryError("排序条件格式不正确")
        field = item.get("field")
        if not field:
            raise ListQueryError("排序条件缺少 field")
        direction = item.get("dir", item.get("direction", "asc"))
        if direction not in {"asc", "desc"}:
            raise ListQueryError("排序方向仅支持 asc/desc")
        sorts.append(SortCondition(field=str(field), direction=direction))
    return sorts


def uses_unified_list_query(*, filters: Any = None, sorts: Any = None) -> bool:
    """Return whether either explicit unified-query parameter was supplied."""
    return filters is not None or sorts is not None


def resolve_list_query(
    *,
    filters_raw: Any = None,
    sorts_raw: Any = None,
    legacy_filters: Iterable[Any] | None = None,
    legacy_sorts: Iterable[Any] | None = None,
) -> tuple[list[FilterCondition], list[SortCondition]]:
    filters = parse_filters(filters_raw) if _has_raw(filters_raw) else parse_filters(list(legacy_filters or []))
    sorts = parse_sorts(sorts_raw) if _has_raw(sorts_raw) else parse_sorts(list(legacy_sorts or []))
    return filters, sorts


def _has_raw(raw: Any) -> bool:
    return raw is not None and raw != ""


def _load_payload(raw: Any, *, empty_detail: str, root_key: str) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (list, dict)):
        payload = raw
    elif isinstance(raw, str):
        payload = _load_json(raw, empty_detail)
    else:
        raise ListQueryError(empty_detail)
    if isinstance(payload, dict):
        return payload.get(root_key, [])
    return payload


def _load_json(raw: str, detail: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ListQueryError(detail) from exc


def _parse_legacy_sort_string(raw: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        if ":" not in piece:
            raise ListQueryError("排序条件格式不正确")
        field, direction = piece.split(":", 1)
        items.append({"field": field.strip(), "dir": direction.strip()})
    return items
