from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from sqlalchemy import and_, or_

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.errors import ListQueryError
from app.core.list_query.parse import parse_filters, parse_sorts, uses_unified_list_query
from app.core.list_query.types import (
    EMPTY_OPS,
    JoinSpec,
    ListQueryContext,
)


def apply_filters(
    query,
    catalog: ListQueryCatalog,
    filters: Iterable[Any],
    *,
    context: ListQueryContext | None = None,
    joined: set[str] | None = None,
):
    ctx = context or ListQueryContext()
    joined_keys = joined if joined is not None else set()
    for condition in parse_filters(list(filters)):
        field = _require_field(catalog, condition.field, kind="筛选")
        if condition.op not in field.ops():
            raise ListQueryError(f"字段 {field.key} 不支持操作符 {condition.op}")
        parsed_value = None
        if condition.op not in EMPTY_OPS:
            if _is_blank_raw_value(condition.value):
                continue
            parsed_value = _prepare_value(field, condition.value, ctx)
            if parsed_value is None:
                continue
        query = _apply_joins(query, field.joins, joined_keys)
        if field.predicate_builder is not None:
            clause = field.predicate_builder(condition, field, ctx, parsed_value)
            if clause is not None:
                query = query.filter(clause)
            continue
        expression = field.filter_expression(ctx)
        if expression is None:
            raise ListQueryError(f"字段 {field.key} 未配置查询表达式")
        query = query.filter(_build_clause(field, expression, condition.op, parsed_value, ctx))
    return query


def apply_sorts(
    query,
    catalog: ListQueryCatalog,
    sorts: Iterable[Any],
    *,
    context: ListQueryContext | None = None,
    joined: set[str] | None = None,
):
    ctx = context or ListQueryContext()
    joined_keys = joined if joined is not None else set()
    parsed = parse_sorts(list(sorts))
    effective = parsed or list(catalog.default_sorts)
    for sort in effective:
        field = _require_field(catalog, sort.field, kind="排序")
        expression = field.order_expression(ctx)
        if expression is None:
            raise ListQueryError(f"字段 {field.key} 未配置排序表达式")
        query = _apply_joins(query, field.sort_joins or field.joins, joined_keys)
        query = query.order_by(expression.desc() if sort.direction == "desc" else expression.asc())
    return query


def apply_list_query(
    query,
    catalog: ListQueryCatalog,
    filters: Iterable[Any],
    sorts: Iterable[Any],
    *,
    context: ListQueryContext | None = None,
    joined: set[str] | None = None,
):
    joined_keys = joined if joined is not None else set()
    query = apply_filters(query, catalog, filters, context=context, joined=joined_keys)
    query = apply_sorts(query, catalog, sorts, context=context, joined=joined_keys)
    return query


def execute_list_query(
    query,
    catalog: ListQueryCatalog,
    filters: Iterable[Any],
    sorts: Iterable[Any],
    *,
    context: ListQueryContext | None = None,
    joined: set[str] | None = None,
    skip: int = 0,
    limit: int = 100,
):
    joined_keys = joined if joined is not None else set()
    query = apply_filters(query, catalog, filters, context=context, joined=joined_keys)
    total = query.count()
    query = apply_sorts(query, catalog, sorts, context=context, joined=joined_keys)
    return query.offset(skip).limit(limit).all(), total


def apply_optional_list_query(
    query,
    catalog: ListQueryCatalog,
    *,
    filters=None,
    sorts=None,
    context: ListQueryContext | None = None,
    joined: set[str] | None = None,
    legacy_filters=None,
    legacy_sorts=None,
):
    ctx = context or ListQueryContext()
    joined_keys = joined if joined is not None else set()
    unified_protocol = uses_unified_list_query(filters=filters, sorts=sorts)
    if unified_protocol:
        query = apply_filters(query, catalog, filters or [], context=ctx, joined=joined_keys)
    elif legacy_filters is not None:
        query = legacy_filters(query)
    total = query.count()
    if unified_protocol:
        query = apply_sorts(query, catalog, sorts or [], context=ctx, joined=joined_keys)
    elif legacy_sorts is not None:
        query = legacy_sorts(query)
    return query, total


def paginate_optional_list_query(
    query,
    catalog: ListQueryCatalog,
    *,
    skip: int = 0,
    limit: int = 100,
    filters=None,
    sorts=None,
    context: ListQueryContext | None = None,
    joined: set[str] | None = None,
    legacy_filters=None,
    legacy_sorts=None,
):
    query, total = apply_optional_list_query(
        query,
        catalog,
        filters=filters,
        sorts=sorts,
        context=context,
        joined=joined,
        legacy_filters=legacy_filters,
        legacy_sorts=legacy_sorts,
    )
    return query.offset(skip).limit(limit).all(), total


def _require_field(catalog: ListQueryCatalog, key: str, *, kind: str) -> ListQueryField:
    field = catalog.get(key)
    if field is None:
        raise ListQueryError(f"未知{kind}字段: {key}")
    return field


def _apply_joins(query, joins: Iterable[JoinSpec], joined_keys: set[str]):
    for spec in joins:
        if spec.key in joined_keys or _query_already_joined(query, spec.target):
            joined_keys.add(spec.key)
            continue
        query = query.join(spec.target, spec.onclause, isouter=spec.isouter)
        joined_keys.add(spec.key)
    return query


def _query_already_joined(query, target) -> bool:
    setup_joins = getattr(query, "_setup_joins", None) or ()
    target_table = getattr(target, "__table__", None)
    for item in setup_joins:
        joined = item[0]
        joined_table = getattr(joined, "__table__", joined)
        if joined == target or joined == target_table or joined_table == target_table:
            return True

    mapper = getattr(target, "__mapper__", target)
    for attr in ("_join_entities", "_legacy_join_entities"):
        entities = getattr(query, attr, None)
        if not entities:
            continue
        if mapper in entities or target in entities:
            return True
    try:
        from sqlalchemy.orm import Query

        if isinstance(query, Query):
            for item in query.column_descriptions:
                entity = item.get("entity")
                if entity is target or getattr(entity, "__mapper__", None) is mapper:
                    return True
    except Exception:
        return False
    return False


def _is_blank_raw_value(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _prepare_value(field: ListQueryField, value: Any, context: ListQueryContext) -> Any:
    parsed = _parse_value(field, value)
    if parsed is None:
        return None
    values = parsed if isinstance(parsed, list) else [parsed]
    if field.resolve_person_aliases:
        values = [_resolve_person_alias(item, context) for item in values]
    if field.resolve_values is not None:
        values = field.resolve_values(values, context)
    if isinstance(parsed, list) or len(values) != 1:
        return values
    return values[0] if values else []


def _resolve_person_alias(value: Any, context: ListQueryContext) -> Any:
    text = str(value).strip().lower()
    if text in {"me", "my"} and context.current_user_id is not None:
        return str(context.current_user_id)
    return value


def _parse_value(field: ListQueryField, value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        parsed = [_parse_value(field, item) for item in value]
        return [item for item in parsed if item is not None]
    if field.enum_type is not None:
        return _parse_enum(field.enum_type, value)
    if field.type == "number":
        return _parse_number(value)
    if field.type == "date":
        return _parse_date(value)
    return str(value).strip()


def _parse_enum(enum_type, value: Any):
    text = str(value).strip()
    for member in enum_type:
        member_value = member.value if isinstance(member, Enum) else member
        member_name = member.name if isinstance(member, Enum) else str(member)
        if value == member or value == member_value or text == str(member_value) or text == member_name:
            return member
    return None


def _parse_number(value: Any):
    try:
        text = str(value).strip()
        if text == "":
            return None
        if "." in text:
            return Decimal(text)
        return int(text)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _parse_date(value: Any):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value).strip()
    if text == "":
        return None
    try:
        if len(text) == 10:
            return datetime.fromisoformat(f"{text}T00:00:00")
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _build_clause(field: ListQueryField, expression, op: str, parsed_value: Any, context: ListQueryContext):
    if op == "is_empty":
        if field.treats_blank_as_empty():
            return or_(expression.is_(None), expression == "")
        return expression.is_(None)
    if op == "is_not_empty":
        if field.treats_blank_as_empty():
            return and_(expression.is_not(None), expression != "")
        return expression.is_not(None)

    if field.type == "date":
        return _date_clause(field, expression, op, parsed_value, context)

    values = parsed_value if isinstance(parsed_value, list) else [parsed_value]
    comparable = [_enum_value(item, field) for item in values]

    if op == "in":
        return expression.in_(comparable)
    if op == "not_in":
        clause = expression.notin_(comparable)
        return or_(expression.is_(None), clause) if field.neq_includes_null else clause

    if op in {"eq", "contains"} and (isinstance(parsed_value, list) or (field.type == "enum" and op == "contains")):
        if field.type == "text" and op == "contains" and not isinstance(parsed_value, list):
            return expression.like(f"%{parsed_value}%")
        return expression.in_(comparable)
    if op in {"neq", "not_contains"} and (
        isinstance(parsed_value, list) or (field.type == "enum" and op == "not_contains")
    ):
        if field.type == "text" and op == "not_contains" and not isinstance(parsed_value, list):
            clause = expression.notlike(f"%{parsed_value}%")
            return or_(expression.is_(None), clause) if field.neq_includes_null else clause
        clause = expression.notin_(comparable)
        return or_(expression.is_(None), clause) if field.neq_includes_null else clause
    if op == "eq":
        return expression == comparable[0]
    if op == "neq":
        clause = expression != comparable[0]
        return or_(expression.is_(None), clause) if field.neq_includes_null else clause
    if op == "gt":
        return expression > comparable[0]
    if op == "gte":
        return expression >= comparable[0]
    if op == "lt":
        return expression < comparable[0]
    if op == "lte":
        return expression <= comparable[0]
    if op == "contains" and field.type == "text":
        return expression.like(f"%{parsed_value}%")
    if op == "not_contains" and field.type == "text":
        clause = expression.notlike(f"%{parsed_value}%")
        return or_(expression.is_(None), clause) if field.neq_includes_null else clause
    raise ListQueryError(f"字段 {field.key} 不支持操作符 {op}")


def _enum_value(value: Any, field: ListQueryField) -> Any:
    if isinstance(value, Enum):
        return value.name if field.enum_persist == "name" else value.value
    return value


def _date_clause(field: ListQueryField, expression, op: str, parsed_value: datetime, context: ListQueryContext):
    if field.date_kind == "date":
        day = parsed_value.date()
        if op == "eq":
            return expression == day
        if op == "after":
            return expression >= day if field.date_semantics == "day_bounds" else expression > day
        if op == "before":
            return expression <= day if field.date_semantics == "day_bounds" else expression < day
        raise ListQueryError(f"字段 {field.key} 不支持操作符 {op}")

    start = datetime.combine(parsed_value.date(), time.min)
    end = datetime.combine(parsed_value.date(), time.max)
    if op == "eq":
        return and_(expression >= start, expression <= end)
    if op == "after":
        return expression >= start if field.date_semantics == "day_bounds" else expression > parsed_value
    if op == "before":
        return expression <= end if field.date_semantics == "day_bounds" else expression < parsed_value
    raise ListQueryError(f"字段 {field.key} 不支持操作符 {op}")
