"""Aggregate the complete authorized customer population into a board."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.list_query.types import FilterCondition, SortCondition
from app.crud.customer_member import customer_member_crud
from app.models.customer import Customer
from app.schemas.board_primitives import BoardOwner
from app.schemas.customer_board import (
    CustomerBoardActionState,
    CustomerBoardColumn,
    CustomerBoardItem,
    CustomerBoardMetadata,
    CustomerBoardMetric,
    CustomerBoardResponse,
    CustomerBoardTrendPoint,
    CustomerCountMetric,
    CustomerPercentageMetric,
)
from app.services.board_trend_window import (
    extract_board_date_bounds,
    fill_month_counts,
    month_key,
    resolve_board_trend_window,
)
from app.services.board_value_format import BOARD_PREVIEW_LIMIT, finite_percentage
from app.services.customer_derived_status import (
    CustomerDerivedStatus,
    DerivedCustomerStatus,
    derive_customer_statuses_for_list,
)


COLUMN_KEYS = ("not_started", "following", "repurchasing", "won", "lost")
_LIFECYCLE_SORT_RANK = {key: rank for rank, key in enumerate(COLUMN_KEYS)}
COLUMN_LABELS = {
    "not_started": "未启动",
    "following": "跟进中",
    "repurchasing": "复购中",
    "won": "已成交",
    "lost": "已流失",
}
COLUMN_TONES = {
    "not_started": "neutral",
    "following": "info",
    "repurchasing": "warning",
    "won": "success",
    "lost": "danger",
}
COUNT_LABELS = {
    "total_count": "客户",
    "following_count": "跟进",
    "repurchasing_count": "复购",
    "won_count": "成交",
    "recent_new_count": "新增",
}
PERCENTAGE_LABELS = {
    "not_started_percentage": "未开始占比",
    "following_percentage": "跟进占比",
    "repurchasing_percentage": "复购占比",
    "won_percentage": "成交占比",
    "lost_percentage": "流失占比",
}
_PUBLIC_POOL = CustomerDerivedStatus.PUBLIC_POOL.value


def build_customer_board(
    db: Session,
    *,
    team_id: int,
    current_user_id: str,
    permission_codes: set[str],
    rows: Sequence[Customer],
    legacy_branch_active: bool,
    created_time_start: date | None,
    created_time_end: date | None,
    filters: Sequence[FilterCondition] | None,
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
    today: date | None = None,
) -> CustomerBoardResponse:
    """Group every authorized row before preview truncation."""
    materialized = list(rows)
    derived = derive_customer_statuses_for_list(db, team_id, materialized)
    buckets: dict[str, list[Customer]] = {key: [] for key in COLUMN_KEYS}
    for row in materialized:
        status = derived[int(row.id)]
        if status.status.value != _PUBLIC_POOL:
            buckets[status.status.value].append(row)

    non_public = [row for key in COLUMN_KEYS for row in buckets[key]]
    owners = _owner_map(db, non_public)
    editable_member_ids = _editable_member_ids(db, team_id, current_user_id, non_public)
    explicit_sort = _has_explicit_sort(order_by, order_dir, sorts)
    denominator = len(non_public)
    summary = _summary(
        buckets,
        denominator,
        non_public,
        today or date.today(),
        legacy_branch_active=legacy_branch_active,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        filters=filters,
    )
    columns = [
        _column(
            key,
            buckets[key],
            derived,
            owners,
            editable_member_ids,
            current_user_id,
            permission_codes,
            explicit_sort,
            sorts,
            order_by,
            order_dir,
        )
        for key in COLUMN_KEYS
    ]
    return CustomerBoardResponse(
        summary=summary,
        columns=columns,
        trends=_trends(
            non_public,
            legacy_branch_active=legacy_branch_active,
            created_time_start=created_time_start,
            created_time_end=created_time_end,
            filters=filters,
            today=today or date.today(),
        ),
    )


def _summary(
    buckets: dict[str, list[Customer]],
    denominator: int,
    non_public: Sequence[Customer],
    today: date,
    *,
    legacy_branch_active: bool,
    created_time_start: date | None,
    created_time_end: date | None,
    filters: Sequence[FilterCondition] | None,
) -> list[CustomerBoardMetric]:
    window = _creation_window(
        rows=non_public,
        legacy_branch_active=legacy_branch_active,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        filters=filters,
        today=today,
    )
    recent_current = 0
    recent_previous = 0
    previous_month = window.months[-2] if window is not None and len(window.months) >= 2 else None
    if window is not None:
        for row in non_public:
            event_day = row.created_time.date() if row.created_time else None
            if event_day is None or not window.event_start <= event_day <= window.event_end:
                continue
            recent_current += 1
            if previous_month is not None and month_key(event_day) == previous_month:
                recent_previous += 1
    counts = {
        "total_count": denominator,
        "following_count": len(buckets["following"]),
        "repurchasing_count": len(buckets["repurchasing"]),
        "won_count": len(buckets["won"]),
        "recent_new_count": recent_current,
    }
    metrics: list[CustomerBoardMetric] = []
    for key, label in COUNT_LABELS.items():
        secondary = (
            {"secondary_label": "上月", "secondary_value": recent_previous}
            if key == "recent_new_count" and previous_month is not None
            else {}
        )
        metrics.append(CustomerCountMetric(
            key=key,
            label=label,
            value_type="count",
            value=counts[key],
            **secondary,
        ))
    for key, label in PERCENTAGE_LABELS.items():
        column_key = key.removesuffix("_percentage")
        metrics.append(CustomerPercentageMetric(
            key=key,
            label=label,
            value_type="percentage",
            value=finite_percentage(len(buckets[column_key]), denominator),
        ))
    return metrics


def _column(
    key: str,
    rows: Sequence[Customer],
    derived: dict[int, DerivedCustomerStatus],
    owners: dict[str, BoardOwner],
    editable_member_ids: set[int],
    current_user_id: str,
    permission_codes: set[str],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> CustomerBoardColumn:
    ordered = _preview_order(rows, derived, explicit_sort, sorts, order_by, order_dir)
    shown = ordered[:BOARD_PREVIEW_LIMIT]
    remaining = len(ordered) - len(shown)
    return CustomerBoardColumn(
        key=key,
        label=COLUMN_LABELS[key],
        tone=COLUMN_TONES[key],
        count=len(ordered),
        amount=None,
        items=[
            _item(row, key, derived[int(row.id)], owners, editable_member_ids, current_user_id, permission_codes)
            for row in shown
        ],
        has_more=remaining > 0,
        remaining_count=remaining,
    )


def _item(
    row: Customer,
    key: str,
    derived: DerivedCustomerStatus,
    owners: dict[str, BoardOwner],
    editable_member_ids: set[int],
    current_user_id: str,
    permission_codes: set[str],
) -> CustomerBoardItem:
    stage_hint = derived.stage_hint or None
    license_type = row.license_type if row.license_type in {"TRIAL", "OFFICIAL"} else None
    license_expiry = row.license_expiry_date.isoformat() if row.license_expiry_date else None
    return CustomerBoardItem(
        id=row.public_id,
        title=row.account_name,
        subtitle=stage_hint,
        amount=None,
        date=row.created_time.date().isoformat() if row.created_time else None,
        owner=owners.get(str(row.owner_id)) if row.owner_id else None,
        status=key,
        metadata=CustomerBoardMetadata(
            stage_hint=stage_hint,
            industry=row.industry,
            city=row.city,
            company_scale=row.company_scale,
            license_type=license_type,
            license_expiry_date=license_expiry,
        ),
        action_state=_action_state(
            row,
            current_user_id,
            permission_codes,
            int(row.id) in editable_member_ids,
        ),
    )


def _action_state(
    row: Customer,
    current_user_id: str,
    permission_codes: set[str],
    member_can_edit: bool,
) -> CustomerBoardActionState:
    owns_row = row.owner_id == str(current_user_id)
    can_edit = (
        "customer:edit:all" in permission_codes
        or member_can_edit
        or ("customer:edit:own" in permission_codes and owns_row)
    )
    can_delete = "customer:delete:all" in permission_codes or (
        "customer:delete:own" in permission_codes and owns_row
    )
    return CustomerBoardActionState(
        can_edit=can_edit,
        can_delete=can_delete,
        can_assign="customer:assign" in permission_codes,
        can_create_opportunity="opportunity:create" in permission_codes and can_edit,
    )


def _preview_order(
    rows: Sequence[Customer],
    derived: dict[int, DerivedCustomerStatus],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[Customer]:
    if not explicit_sort:
        indexed = list(enumerate(rows))
        return [
            row
            for _, row in sorted(
                indexed,
                key=lambda item: (
                    _descending_timestamp(item[1].created_time),
                    _descending_timestamp(item[1].last_modified_time),
                    item[1].public_id,
                ),
            )
        ]
    requested = _requested_sorts(sorts, order_by, order_dir)
    indexed = list(enumerate(rows))
    return [
        row
        for _, row in sorted(
            indexed,
            key=lambda item: (
                tuple(
                    _directed(_sort_value(item[1], derived, field), ascending)
                    for field, ascending in requested
                ),
                item[1].public_id,
            ),
        )
    ]


def _descending_timestamp(value: datetime | None) -> float:
    if not isinstance(value, datetime):
        return float("inf")
    return -value.timestamp()


def _directed(value, ascending: bool):
    if value is None:
        return (1,)
    if isinstance(value, datetime):
        stamp = value.timestamp()
        return (0, stamp if ascending else -stamp)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value if ascending else -value)
    text = str(value)
    if text == "":
        return (1,)
    ordered = text if ascending else tuple(-ord(char) for char in text)
    return (0, ordered)

def _sort_value(row: Customer, derived: dict[int, DerivedCustomerStatus], field: str):
    if field == "account_name":
        return row.account_name or ""
    if field == "status":
        return _LIFECYCLE_SORT_RANK.get(derived[int(row.id)].status.value, len(COLUMN_KEYS))
    if field == "industry":
        return row.industry or ""
    if field == "source":
        return row.source or ""
    if field == "city":
        return row.city or ""
    if field == "company_scale":
        return row.company_scale or ""
    if field == "owner_id":
        return row.owner_id or ""
    if field == "created_time":
        return row.created_time if isinstance(row.created_time, datetime) else None
    if field in {"last_modified_time", "updated_time"}:
        return row.last_modified_time if isinstance(row.last_modified_time, datetime) else None
    return ""


def _requested_sorts(
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[tuple[str, bool]]:
    if sorts:
        return [(sort.field, sort.direction != "desc") for sort in sorts]
    if order_by and order_dir:
        return [(order_by, order_dir.lower() != "desc")]
    return []
def _has_explicit_sort(
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
) -> bool:
    return bool(sorts) or bool(order_by and order_dir)


def _creation_window(
    *,
    rows: Sequence[Customer],
    legacy_branch_active: bool,
    created_time_start: date | None,
    created_time_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
):
    if not rows:
        return None
    if legacy_branch_active:
        start_bound, end_bound = created_time_start, created_time_end
    else:
        start_bound, end_bound = extract_board_date_bounds(filters, "created_time")
    window = resolve_board_trend_window(today=today, start_bound=start_bound, end_bound=end_bound)
    return None if window.empty else window


def _trends(
    rows: Sequence[Customer],
    *,
    legacy_branch_active: bool,
    created_time_start: date | None,
    created_time_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
) -> list[CustomerBoardTrendPoint]:
    window = _creation_window(
        rows=rows,
        legacy_branch_active=legacy_branch_active,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        filters=filters,
        today=today,
    )
    if window is None:
        return []
    counts = fill_month_counts(window)
    for row in rows:
        event_day = row.created_time.date() if row.created_time else None
        if event_day is not None and window.event_start <= event_day <= window.event_end:
            counts[month_key(event_day)] += 1
    return [
        CustomerBoardTrendPoint(date=month, count=counts[month])
        for month in window.months
    ]




def _owner_map(db: Session, rows: Sequence[Customer]) -> dict[str, BoardOwner]:
    owner_ids = sorted({str(row.owner_id) for row in rows if row.owner_id and str(row.owner_id).isdigit()})
    if not owner_ids:
        return {}
    placeholders = ", ".join(f":owner_{index}" for index in range(len(owner_ids)))
    users = db.execute(
        text(f"SELECT id, name, avatar_url FROM users WHERE id IN ({placeholders})"),
        {f"owner_{index}": int(owner_id) for index, owner_id in enumerate(owner_ids)},
    ).fetchall()
    return {
        str(user_id): BoardOwner(id=str(user_id), name=name, avatar_url=avatar_url)
        for user_id, name, avatar_url in users
    }


def _editable_member_ids(
    db: Session,
    team_id: int,
    current_user_id: str,
    rows: Sequence[Customer],
) -> set[int]:
    return {
        int(row.id)
        for row in rows
        if customer_member_crud.has_access(db, team_id, int(row.id), current_user_id, "EDIT")
    }
