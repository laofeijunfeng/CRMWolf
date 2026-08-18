"""获客来源领域服务。配置解析、种子、导入匹配都走这里。"""

from __future__ import annotations

import logging
from secrets import token_hex
from collections.abc import Callable
from typing import Iterable, TypeVar

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings

from app.constants.acquisition_sources import (
    AI_SOURCE_ALIASES,
    SYSTEM_DEFAULT_SOURCES,
    is_forbidden_source_name,
    map_legacy_source_code,
    normalize_source_name,
)
from app.models.acquisition_source import AcquisitionSource
from app.models.customer import Customer
from app.models.lead import Lead
from app.schemas.acquisition_source import AcquisitionSourceInfo
from app.utils.public_id import generate_public_id, is_acquisition_source_public_id
from app.utils.time import business_now


class AcquisitionSourceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def map_legacy_source(raw: object) -> str | None:
    return map_legacy_source_code(raw)


def seed_default_sources(db: Session, team_id: int, created_by: str) -> list[AcquisitionSource]:
    existing_rows = (
        db.query(AcquisitionSource)
        .filter(AcquisitionSource.team_id == team_id)
        .all()
    )
    by_code = {row.code: row for row in existing_rows}
    by_name = {row.name: row for row in existing_rows}

    for item in SYSTEM_DEFAULT_SOURCES:
        code = str(item["code"])
        name = str(item["name"])
        sort_order = int(item["sort_order"])
        existing = by_code.get(code)
        if existing is not None:
            existing.is_system = 1
            continue

        same_name = by_name.get(name)
        if same_name is not None:
            same_name.code = code
            same_name.is_system = 1
            by_code[code] = same_name
            continue

        row = AcquisitionSource(
            public_id=generate_public_id("acq"),
            team_id=team_id,
            code=code,
            name=name,
            is_system=1,
            is_active=1,
            sort_order=sort_order,
            created_by=created_by,
        )
        db.add(row)
        by_code[code] = row
        by_name[name] = row

    db.flush()
    return (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.team_id == team_id,
            AcquisitionSource.code.in_([str(item["code"]) for item in SYSTEM_DEFAULT_SOURCES]),
        )
        .order_by(AcquisitionSource.sort_order, AcquisitionSource.id)
        .all()
    )


logger = logging.getLogger(__name__)


def get_by_public_id(db: Session, public_id: str, team_id: int) -> AcquisitionSource | None:
    return (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.public_id == public_id,
            AcquisitionSource.team_id == team_id,
        )
        .first()
    )


def get_by_id(db: Session, source_id: int | None, team_id: int) -> AcquisitionSource | None:
    if source_id is None:
        return None
    return (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.id == source_id,
            AcquisitionSource.team_id == team_id,
        )
        .first()
    )


def map_sources_by_ids(db: Session, team_id: int, ids: Iterable[int | None]) -> dict[int, AcquisitionSource]:
    source_ids = [int(source_id) for source_id in ids if source_id is not None]
    if not source_ids:
        return {}
    rows = (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.team_id == team_id,
            AcquisitionSource.id.in_(source_ids),
        )
        .all()
    )
    return {int(row.id): row for row in rows}


def resolve_public_ids_to_ids(db: Session, team_id: int, public_ids: Iterable[object]) -> list[int]:
    cleaned = []
    for item in public_ids:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            cleaned.append(text)
    if not cleaned:
        return []
    rows = (
        db.query(AcquisitionSource.id)
        .filter(
            AcquisitionSource.team_id == team_id,
            AcquisitionSource.public_id.in_(cleaned),
        )
        .all()
    )
    return [int(row.id) for row in rows]


def get_by_code(db: Session, team_id: int, code: str) -> AcquisitionSource | None:
    if not code:
        return None
    return (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.team_id == team_id,
            AcquisitionSource.code == code,
        )
        .first()
    )


T = TypeVar("T")


def _can_query_sources(db: Session | None, team_id: int | None) -> bool:
    return db is not None and team_id is not None and hasattr(db, "query")


def _query_sources_or_fallback(
    db: Session | None,
    team_id: int | None,
    query_fn: Callable[[], T],
    fallback: T,
) -> T:
    if not _can_query_sources(db, team_id):
        return fallback
    assert db is not None
    try:
        with db.begin_nested():
            return query_fn()
    except SQLAlchemyError:
        logger.debug("acquisition source lookup failed; using system defaults", exc_info=True)
        return fallback


def default_source_name(db: Session | None = None, team_id: int | None = None) -> str:
    fallback = next(str(item["name"]) for item in SYSTEM_DEFAULT_SOURCES if item["code"] == "OTHER")

    def _lookup() -> str:
        row = get_by_code(db, team_id, "OTHER")
        return row.name if row is not None else fallback

    return _query_sources_or_fallback(db, team_id, _lookup, fallback)


def format_active_source_names(db: Session | None = None, team_id: int | None = None) -> list[str]:
    fallback = [str(item["name"]) for item in SYSTEM_DEFAULT_SOURCES]

    def _lookup() -> list[str]:
        return [row.name for row in list_options(db, team_id, include_inactive=False)]

    return _query_sources_or_fallback(db, team_id, _lookup, fallback)


def _normalize_ai_source_text(raw: object) -> str:
    text = normalize_source_name(str(raw)) if raw is not None else ""
    if not text:
        return ""
    while text.endswith(("的", "了")):
        text = text[:-1].strip()
    return text


def _alias_code_for_ai_text(text: str) -> str | None:
    folded = text.casefold()
    if not folded:
        return None
    direct = AI_SOURCE_ALIASES.get(folded)
    if direct:
        return direct
    for alias, code in sorted(AI_SOURCE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and alias in folded:
            return code
    return None


def resolve_write_fields_for_ai(
    payload: dict,
    db: Session | None = None,
    team_id: int | None = None,
) -> dict:
    """Normalize AI/agent write payloads onto source_public_id only."""
    normalized = dict(payload)
    raw = normalized.get("source_public_id") or normalized.get("source")

    def _lookup() -> dict:
        row = resolve_source_for_ai(db, int(team_id), raw)
        resolved = dict(normalized)
        resolved["source_public_id"] = row.public_id
        resolved.pop("source", None)
        return resolved

    try:
        resolved = _query_sources_or_fallback(db, team_id, _lookup, None)
    except AcquisitionSourceError:
        resolved = None
    if resolved is not None:
        return resolved
    if is_acquisition_source_public_id(raw):
        normalized["source_public_id"] = raw
        normalized.pop("source", None)
        return normalized
    normalized.pop("source", None)
    return normalized


def resolve_source_for_ai(db: Session, team_id: int, raw: object) -> AcquisitionSource:
    """Match AI / agent free text onto a team source without creating new options."""
    options = list_options(db, team_id, include_inactive=False)
    other = get_by_code(db, team_id, "OTHER")
    if other is None:
        raise AcquisitionSourceError("获客来源不存在", status_code=404)

    text = normalize_source_name(str(raw)) if raw is not None else ""
    if not text or is_forbidden_source_name(text):
        return other

    public_id_hit = get_by_public_id(db, text, team_id)
    if public_id_hit is not None and public_id_hit.is_active == 1:
        return public_id_hit

    by_name = {row.name: row for row in options}
    exact = by_name.get(text)
    if exact is not None:
        return exact

    normalized = _normalize_ai_source_text(text)
    exact_normalized = by_name.get(normalized)
    if exact_normalized is not None:
        return exact_normalized

    alias_code = _alias_code_for_ai_text(normalized) or _alias_code_for_ai_text(text)
    if alias_code:
        alias_row = next((row for row in options if row.code == alias_code), None)
        if alias_row is not None:
            return alias_row
        coded = get_by_code(db, team_id, alias_code)
        if coded is not None:
            return coded

    return other


def list_options(
    db: Session,
    team_id: int,
    *,
    include_inactive: bool = False,
) -> list[AcquisitionSource]:
    query = db.query(AcquisitionSource).filter(AcquisitionSource.team_id == team_id)
    if not include_inactive:
        query = query.filter(AcquisitionSource.is_active == 1)
    return query.order_by(AcquisitionSource.sort_order, AcquisitionSource.id).all()


def resolve_for_write(
    db: Session,
    team_id: int,
    public_id: str,
    *,
    allow_inactive: bool = False,
) -> AcquisitionSource:
    row = get_by_public_id(db, public_id, team_id)
    if row is None:
        raise AcquisitionSourceError("获客来源不存在", status_code=404)
    if not allow_inactive and row.is_active != 1:
        raise AcquisitionSourceError("该获客来源已停用", status_code=400)
    return row


def resolve_for_import(db: Session, team_id: int, name: str) -> AcquisitionSource:
    normalized = normalize_source_name(name)
    if not normalized:
        raise AcquisitionSourceError("获客来源不能为空", status_code=400)
    if is_forbidden_source_name(normalized):
        raise AcquisitionSourceError("不能使用该名称", status_code=400)

    row = (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.team_id == team_id,
            AcquisitionSource.name == normalized,
            AcquisitionSource.is_active == 1,
        )
        .first()
    )
    if row is None:
        available = "、".join(item.name for item in list_options(db, team_id))
        raise AcquisitionSourceError(
            f"获客来源不存在，可选：{available}" if available else "获客来源不存在",
            status_code=400,
        )
    return row


def resolve_legacy_name_for_write(
    db: Session,
    team_id: int,
    raw: object,
    *,
    allow_inactive: bool = False,
) -> AcquisitionSource:
    code = map_legacy_source(raw)
    if code is None:
        raise AcquisitionSourceError("获客来源不能为空", status_code=400)

    normalized = normalize_source_name(str(raw)) if raw is not None else ""
    row = None
    if normalized:
        row = (
            db.query(AcquisitionSource)
            .filter(
                AcquisitionSource.team_id == team_id,
                AcquisitionSource.name == normalized,
            )
            .first()
        )
    if row is None:
        row = (
            db.query(AcquisitionSource)
            .filter(
                AcquisitionSource.team_id == team_id,
                AcquisitionSource.code == code,
            )
            .first()
        )
    if row is None:
        raise AcquisitionSourceError("获客来源不存在", status_code=404)
    if not allow_inactive and row.is_active != 1:
        raise AcquisitionSourceError("该获客来源已停用", status_code=400)
    return row


def resolve_source_for_entity_write(
    db: Session,
    team_id: int,
    *,
    source_public_id: str | None = None,
    legacy_source: object | None = None,
    current_source_id: int | None = None,
    required: bool = False,
) -> AcquisitionSource | None:
    public_id = str(source_public_id).strip() if source_public_id else ""
    if public_id:
        row = get_by_public_id(db, public_id, team_id)
        if row is None:
            raise AcquisitionSourceError("获客来源不存在", status_code=404)
        if row.is_active != 1 and row.id != current_source_id:
            raise AcquisitionSourceError("该获客来源已停用", status_code=400)
        return row

    has_legacy = legacy_source is not None and str(legacy_source).strip() != ""
    if has_legacy:
        if not get_settings().ACQUISITION_SOURCE_ACCEPT_LEGACY_SOURCE:
            raise AcquisitionSourceError("请使用获客来源 public_id", status_code=400)
        logger.warning("legacy acquisition source field used: %s", legacy_source)
        row = resolve_legacy_name_for_write(db, team_id, legacy_source, allow_inactive=True)
        if row.is_active != 1 and row.id != current_source_id:
            raise AcquisitionSourceError("该获客来源已停用", status_code=400)
        return row

    if current_source_id is not None:
        return get_by_id(db, current_source_id, team_id)

    if required:
        raise AcquisitionSourceError("获客来源不能为空", status_code=400)
    return None


def build_source_info(row: AcquisitionSource | None) -> AcquisitionSourceInfo | None:
    if row is None:
        return None
    return AcquisitionSourceInfo(
        public_id=row.public_id,
        name=row.name,
        is_active=bool(row.is_active),
    )


def count_usage(db: Session, team_id: int, source_ids: Iterable[int] | None = None) -> dict[int, dict[str, int]]:
    lead_query = (
        db.query(Lead.source_id, func.count(Lead.id))
        .filter(Lead.team_id == team_id, Lead.source_id.isnot(None))
        .group_by(Lead.source_id)
    )
    customer_query = (
        db.query(Customer.source_id, func.count(Customer.id))
        .filter(Customer.team_id == team_id, Customer.source_id.isnot(None))
        .group_by(Customer.source_id)
    )
    if source_ids is not None:
        ids = list(source_ids)
        if not ids:
            return {}
        lead_query = lead_query.filter(Lead.source_id.in_(ids))
        customer_query = customer_query.filter(Customer.source_id.in_(ids))

    usage: dict[int, dict[str, int]] = {}
    for source_id, count in lead_query.all():
        if source_id is None:
            continue
        usage.setdefault(int(source_id), {"lead_count": 0, "customer_count": 0})["lead_count"] = int(count)
    for source_id, count in customer_query.all():
        if source_id is None:
            continue
        usage.setdefault(int(source_id), {"lead_count": 0, "customer_count": 0})["customer_count"] = int(count)
    return usage


def generate_custom_code() -> str:
    return f"CUSTOM_{token_hex(4)}"


def validate_source_name(db: Session, team_id: int, name: str, *, exclude_id: int | None = None) -> str:
    normalized = normalize_source_name(name)
    if not normalized:
        raise AcquisitionSourceError("获客来源名称不能为空", status_code=400)
    if is_forbidden_source_name(normalized):
        raise AcquisitionSourceError("不能使用该名称", status_code=400)

    query = db.query(AcquisitionSource).filter(
        AcquisitionSource.team_id == team_id,
        AcquisitionSource.name == normalized,
    )
    if exclude_id is not None:
        query = query.filter(AcquisitionSource.id != exclude_id)
    if query.first() is not None:
        raise AcquisitionSourceError("获客来源名称已存在", status_code=409)
    return normalized


def create_custom_source(
    db: Session,
    *,
    team_id: int,
    name: str,
    created_by: str,
    sort_order: int | None = None,
) -> AcquisitionSource:
    normalized = validate_source_name(db, team_id, name)
    if sort_order is None:
        max_sort = (
            db.query(func.max(AcquisitionSource.sort_order))
            .filter(AcquisitionSource.team_id == team_id)
            .scalar()
        )
        sort_order = int(max_sort or 0) + 10

    row = AcquisitionSource(
        public_id=generate_public_id("acq"),
        team_id=team_id,
        code=generate_custom_code(),
        name=normalized,
        is_system=0,
        is_active=1,
        sort_order=sort_order,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_source(
    db: Session,
    *,
    team_id: int,
    public_id: str,
    updater_id: str,
    name: str | None = None,
    is_active: int | None = None,
    sort_order: int | None = None,
) -> AcquisitionSource:
    row = get_by_public_id(db, public_id, team_id)
    if row is None:
        raise AcquisitionSourceError("获客来源不存在", status_code=404)

    if name is not None:
        row.name = validate_source_name(db, team_id, name, exclude_id=row.id)
    if is_active is not None:
        row.is_active = 1 if is_active else 0
    if sort_order is not None:
        row.sort_order = sort_order
    row.updated_by = updater_id
    row.updated_time = business_now()
    db.commit()
    db.refresh(row)
    return row


def reorder_sources(
    db: Session,
    *,
    team_id: int,
    items: list[dict[str, object]],
    updater_id: str,
) -> list[AcquisitionSource]:
    public_ids = [str(item["public_id"]) for item in items if item.get("public_id")]
    if not public_ids:
        return list_options(db, team_id, include_inactive=True)

    rows = (
        db.query(AcquisitionSource)
        .filter(
            AcquisitionSource.team_id == team_id,
            AcquisitionSource.public_id.in_(public_ids),
        )
        .all()
    )
    by_public_id = {row.public_id: row for row in rows}
    now = business_now()
    for item in items:
        public_id = str(item.get("public_id") or "")
        row = by_public_id.get(public_id)
        if row is None:
            continue
        row.sort_order = int(item["sort_order"])
        row.updated_by = updater_id
        row.updated_time = now
    db.commit()
    return list_options(db, team_id, include_inactive=True)
