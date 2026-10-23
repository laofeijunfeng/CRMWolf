"""Aggregate the complete authorized payment-plan population into a board."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from app.core.list_query.types import FilterCondition, ListQueryContext, SortCondition
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.user import User
from app.schemas.board_primitives import BoardOwner
from app.schemas.payment_plan_board import (
    PaymentPlanAmountMetric,
    PaymentPlanBoardActionState,
    PaymentPlanBoardColumn,
    PaymentPlanBoardItem,
    PaymentPlanBoardMetadata,
    PaymentPlanBoardMetric,
    PaymentPlanBoardResponse,
    PaymentPlanBoardTrendPoint,
    PaymentPlanCountMetric,
)
from app.services.board_trend_window import (
    extract_board_date_bounds,
    month_key,
    resolve_board_trend_window,
)
from app.services.board_value_format import money_string
from app.services.payment_approval_status import payment_approval_status_expression

COLUMN_KEYS = ("PENDING", "OVERDUE", "PARTIAL", "COMPLETED", "UNCLASSIFIED")
COLUMN_LABELS = {
    "PENDING": "待登记",
    "OVERDUE": "已逾期",
    "PARTIAL": "部分回款",
    "COMPLETED": "已登记",
    "UNCLASSIFIED": "未分类",
}
COLUMN_TONES = {
    "PENDING": "neutral",
    "OVERDUE": "danger",
    "PARTIAL": "warning",
    "COMPLETED": "success",
    "UNCLASSIFIED": "muted",
}
SUMMARY_KEYS = (
    "overdue_count",
    "planned_amount",
    "paid_amount",
    "remaining_amount",
    "overdue_remaining_amount",
)
COUNT_LABELS = {"overdue_count": "逾期"}
AMOUNT_LABELS = {
    "planned_amount": "计划金额",
    "paid_amount": "已回款",
    "remaining_amount": "待回款",
    "overdue_remaining_amount": "逾期待回款",
}
_PREVIEW_FIELDS = {
    "plan_number",
    "stage_name",
    "customer_name",
    "contract_name",
    "planned_amount",
    "paid_amount",
    "remaining_amount",
    "due_date",
    "status",
    "created_time",
    "owner_id",
}
_STATUS_ORDER = {"PENDING": 0, "PARTIAL": 1, "COMPLETED": 2, "OVERDUE": 3, "UNCLASSIFIED": 99}


def build_payment_plan_board(
    db: Session,
    *,
    team_id: int,
    current_user_id: str,
    permission_codes: set[str],
    plans: Sequence[PaymentPlan],
    legacy_branch_active: bool,
    due_date_start: date | None,
    due_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    sort: str | None,
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
    today: date | None = None,
) -> PaymentPlanBoardResponse:
    """Group every authorized plan before preview truncation."""
    materialized = list(plans)
    paid_by_plan = sum_canonical_approved_amounts(db, team_id, [int(plan.id) for plan in materialized])
    plans_with_records = _plans_with_records(db, team_id, [int(plan.id) for plan in materialized])
    owners = _owner_map(db, materialized)
    buckets: dict[str, list[PaymentPlan]] = {key: [] for key in COLUMN_KEYS}
    for plan in materialized:
        buckets[_column_key(plan)].append(plan)
    explicit_sort = _has_explicit_sort(sort, order_by, order_dir, sorts)
    columns = [
        _column(
            key,
            buckets[key],
            paid_by_plan,
            plans_with_records,
            owners,
            current_user_id,
            permission_codes,
            explicit_sort,
            sort,
            sorts,
            order_by,
            order_dir,
        )
        for key in COLUMN_KEYS
    ]
    return PaymentPlanBoardResponse(
        summary=_summary(materialized, paid_by_plan),
        columns=columns,
        trends=_trends(
            materialized,
            paid_by_plan,
            legacy_branch_active=legacy_branch_active,
            due_date_start=due_date_start,
            due_date_end=due_date_end,
            filters=filters,
            today=today or date.today(),
        ),
    )


def sum_canonical_approved_amounts(
    db: Session,
    team_id: int,
    plan_ids: Sequence[int],
) -> dict[int, Decimal]:
    """Sum actual amounts whose canonical approval status is approved."""
    paid = {int(plan_id): Decimal("0") for plan_id in plan_ids}
    if not plan_ids:
        return paid
    approval_status = payment_approval_status_expression(ListQueryContext())
    rows = (
        db.query(PaymentRecord.payment_plan_id, func.sum(PaymentRecord.actual_amount))
        .join(PaymentPlan, PaymentPlan.id == PaymentRecord.payment_plan_id)
        .filter(
            PaymentRecord.team_id == team_id,
            PaymentPlan.team_id == team_id,
            PaymentRecord.payment_plan_id.in_(plan_ids),
            approval_status == "approved",
        )
        .group_by(PaymentRecord.payment_plan_id)
        .all()
    )
    for plan_id, amount in rows:
        paid[int(plan_id)] = Decimal(str(amount or 0))
    return paid


def _plans_with_records(db: Session, team_id: int, plan_ids: Sequence[int]) -> set[int]:
    """Return plan IDs that have at least one payment record."""
    if not plan_ids:
        return set()
    record_exists = exists().where(PaymentRecord.payment_plan_id == PaymentPlan.id)
    rows = (
        db.query(PaymentPlan.id)
        .filter(
            PaymentPlan.team_id == team_id,
            PaymentPlan.id.in_(plan_ids),
            record_exists,
        )
        .all()
    )
    return {int(plan_id) for (plan_id,) in rows}


def _column_key(plan: PaymentPlan) -> str:
    status = plan.status if isinstance(plan.status, str) else None
    return status if status in COLUMN_KEYS[:-1] else "UNCLASSIFIED"


def _amounts(plan: PaymentPlan, paid_by_plan: Mapping[int, Decimal]) -> tuple[Decimal, Decimal, Decimal]:
    planned = Decimal(str(plan.planned_amount or 0))
    paid = paid_by_plan.get(int(plan.id), Decimal("0"))
    return planned, paid, planned - paid


def _summary(plans: Sequence[PaymentPlan], paid_by_plan: Mapping[int, Decimal]) -> list[PaymentPlanBoardMetric]:
    planned_total = Decimal("0")
    paid_total = Decimal("0")
    remaining_total = Decimal("0")
    overdue_remaining = Decimal("0")
    overdue_count = 0
    for plan in plans:
        planned, paid, remaining = _amounts(plan, paid_by_plan)
        planned_total += planned
        paid_total += paid
        remaining_total += remaining
        if _column_key(plan) == "OVERDUE":
            overdue_count += 1
            overdue_remaining += remaining
    values = {
        "overdue_count": overdue_count,
        "planned_amount": money_string(planned_total),
        "paid_amount": money_string(paid_total),
        "remaining_amount": money_string(remaining_total),
        "overdue_remaining_amount": money_string(overdue_remaining),
    }
    metrics: list[PaymentPlanBoardMetric] = []
    for key in SUMMARY_KEYS:
        if key in COUNT_LABELS:
            metrics.append(PaymentPlanCountMetric(
                key=key,
                label=COUNT_LABELS[key],
                value_type="count",
                value=values[key],
            ))
        else:
            metrics.append(PaymentPlanAmountMetric(
                key=key,
                label=AMOUNT_LABELS[key],
                value_type="amount",
                value=values[key],
            ))
    return metrics


def _column(
    key: str,
    plans: Sequence[PaymentPlan],
    paid_by_plan: Mapping[int, Decimal],
    plans_with_records: set[int],
    owners: Mapping[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
    explicit_sort: bool,
    sort: str | None,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> PaymentPlanBoardColumn:
    ordered = _preview_order(
        plans,
        paid_by_plan,
        owners,
        explicit_sort,
        sort,
        sorts,
        order_by,
        order_dir,
    )
    planned_total = Decimal("0")
    paid_total = Decimal("0")
    remaining_total = Decimal("0")
    for plan in ordered:
        planned, paid, remaining = _amounts(plan, paid_by_plan)
        planned_total += planned
        paid_total += paid
        remaining_total += remaining
    overdue_remaining = remaining_total if key == "OVERDUE" else Decimal("0")
    return PaymentPlanBoardColumn(
        key=key,
        label=COLUMN_LABELS[key],
        tone=COLUMN_TONES[key],
        count=len(ordered),
        amount=money_string(planned_total),
        planned_amount=money_string(planned_total),
        paid_amount=money_string(paid_total),
        remaining_amount=money_string(remaining_total),
        overdue_remaining_amount=money_string(overdue_remaining),
        items=[
            _item(plan, key, paid_by_plan, plans_with_records, owners, current_user_id, permission_codes)
            for plan in ordered
        ],
        has_more=False,
        remaining_count=0,
    )


def _item(
    plan: PaymentPlan,
    key: str,
    paid_by_plan: Mapping[int, Decimal],
    plans_with_records: set[int],
    owners: Mapping[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
) -> PaymentPlanBoardItem:
    planned, paid, remaining = _amounts(plan, paid_by_plan)
    planned_text = money_string(planned)
    paid_text = money_string(paid)
    remaining_text = money_string(remaining)
    contract = plan.contract
    customer = contract.customer if contract is not None else None
    opportunity = contract.opportunity if contract is not None else None
    owner_id = _owner_id(plan)
    return PaymentPlanBoardItem(
        id=int(plan.id),
        title=plan.plan_number,
        subtitle=plan.stage_name,
        amount=planned_text,
        planned_amount=planned_text,
        paid_amount=paid_text,
        remaining_amount=remaining_text,
        date=_date_text(plan.due_date),
        owner=owners.get(owner_id) if owner_id else None,
        status=key,
        metadata=PaymentPlanBoardMetadata(
            customer_name=customer.account_name if customer is not None else None,
            contract_name=contract.contract_name if contract is not None else None,
            opportunity_name=opportunity.opportunity_name if opportunity is not None else None,
            paid_amount=paid_text,
            remaining_amount=remaining_text,
        ),
        action_state=_action_state(plan, key, plans_with_records, permission_codes),
    )


def _action_state(
    plan: PaymentPlan,
    key: str,
    plans_with_records: set[int],
    permission_codes: set[str],
) -> PaymentPlanBoardActionState:
    has_records = int(plan.id) in plans_with_records
    can_edit = (
        "payment:plan:edit" in permission_codes
        and key != "COMPLETED"
        and not has_records
    )
    can_delete = "payment:plan:delete" in permission_codes and not has_records
    return PaymentPlanBoardActionState(
        can_edit=can_edit,
        can_delete=can_delete,
        can_view_detail=True,
    )


def _owner_id(plan: PaymentPlan) -> str | None:
    contract = plan.contract
    opportunity = contract.opportunity if contract is not None else None
    if opportunity is not None and opportunity.owner_id:
        return str(opportunity.owner_id)
    if contract is not None and contract.owner_id:
        return str(contract.owner_id)
    return None


def _preview_order(
    plans: Sequence[PaymentPlan],
    paid_by_plan: Mapping[int, Decimal],
    owners: Mapping[str, BoardOwner],
    explicit_sort: bool,
    sort: str | None,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[PaymentPlan]:
    indexed = list(enumerate(plans))
    if not explicit_sort:
        return [
            plan
            for _, plan in sorted(
                indexed,
                key=lambda item: (
                    item[1].due_date is None,
                    item[1].due_date.toordinal() if isinstance(item[1].due_date, date) else 0,
                    -int(item[1].id),
                ),
            )
        ]
    requested = _requested_sorts(sort, sorts, order_by, order_dir)
    return [
        plan
        for _, plan in sorted(
            indexed,
            key=lambda item: (
                tuple(
                    _directed(_sort_value(item[1], paid_by_plan, owners, field), ascending)
                    for field, ascending in requested
                ),
                int(item[1].id),
            ),
        )
    ]


def _sort_value(
    plan: PaymentPlan,
    paid_by_plan: Mapping[int, Decimal],
    owners: Mapping[str, BoardOwner],
    field: str,
):
    if field not in _PREVIEW_FIELDS:
        return ""
    planned, paid, remaining = _amounts(plan, paid_by_plan)
    contract = plan.contract
    customer = contract.customer if contract is not None else None
    owner_id = _owner_id(plan)
    values = {
        "plan_number": plan.plan_number or "",
        "stage_name": plan.stage_name or "",
        "customer_name": customer.account_name if customer is not None else "",
        "contract_name": contract.contract_name if contract is not None else "",
        "planned_amount": planned,
        "paid_amount": paid,
        "remaining_amount": remaining,
        "due_date": plan.due_date if isinstance(plan.due_date, date) else None,
        "status": _STATUS_ORDER[_column_key(plan)],
        "created_time": plan.created_time if isinstance(plan.created_time, datetime) else None,
        "owner_id": owners[owner_id].name if owner_id and owner_id in owners else (owner_id or ""),
    }
    return values[field]


def _directed(value, ascending: bool):
    if value is None:
        return (1,)
    if isinstance(value, datetime):
        stamp = value.timestamp()
        return (0, stamp if ascending else -stamp)
    if isinstance(value, date):
        ordinal = value.toordinal()
        return (0, ordinal if ascending else -ordinal)
    if isinstance(value, Decimal):
        return (0, value if ascending else -value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value if ascending else -value)
    text_value = str(value)
    if text_value == "":
        return (1,)
    ordered = text_value if ascending else tuple(-ord(char) for char in text_value)
    return (0, ordered)


def _requested_sorts(
    sort: str | None,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[tuple[str, bool]]:
    if sorts:
        return [(item.field, item.direction != "desc") for item in sorts]
    if sort:
        parsed: list[tuple[str, bool]] = []
        for item in sort.split(","):
            field, separator, direction = item.partition(":")
            if separator and field.strip() and direction.strip().lower() in {"asc", "desc"}:
                parsed.append((field.strip(), direction.strip().lower() != "desc"))
        if parsed:
            return parsed
    if order_by and order_dir:
        return [(order_by, order_dir.lower() != "desc")]
    return []


def _has_explicit_sort(
    sort: str | None,
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
) -> bool:
    return bool(sorts) or bool(sort) or bool(order_by and order_dir)


def _due_window(
    *,
    plans: Sequence[PaymentPlan],
    legacy_branch_active: bool,
    due_date_start: date | None,
    due_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
):
    if not plans:
        return None
    if legacy_branch_active:
        start_bound, end_bound = due_date_start, due_date_end
    else:
        start_bound, end_bound = extract_board_date_bounds(filters, "due_date")
    window = resolve_board_trend_window(today=today, start_bound=start_bound, end_bound=end_bound)
    return None if window.empty else window


def _trends(
    plans: Sequence[PaymentPlan],
    paid_by_plan: Mapping[int, Decimal],
    *,
    legacy_branch_active: bool,
    due_date_start: date | None,
    due_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
) -> list[PaymentPlanBoardTrendPoint]:
    window = _due_window(
        plans=plans,
        legacy_branch_active=legacy_branch_active,
        due_date_start=due_date_start,
        due_date_end=due_date_end,
        filters=filters,
        today=today,
    )
    if window is None:
        return []
    counts = {month: 0 for month in window.months}
    planned_amounts = {month: Decimal("0") for month in window.months}
    paid_amounts = {month: Decimal("0") for month in window.months}
    remaining_amounts = {month: Decimal("0") for month in window.months}
    for plan in plans:
        due_day = plan.due_date if isinstance(plan.due_date, date) else None
        if due_day is None or not window.event_start <= due_day <= window.event_end:
            continue
        key = month_key(due_day)
        planned, paid, remaining = _amounts(plan, paid_by_plan)
        counts[key] += 1
        planned_amounts[key] += planned
        paid_amounts[key] += paid
        remaining_amounts[key] += remaining
    return [
        PaymentPlanBoardTrendPoint(
            date=month,
            count=counts[month],
            planned_amount=money_string(planned_amounts[month]),
            paid_amount=money_string(paid_amounts[month]),
            remaining_amount=money_string(remaining_amounts[month]),
        )
        for month in window.months
    ]


def _owner_map(db: Session, plans: Sequence[PaymentPlan]) -> dict[str, BoardOwner]:
    owner_ids = sorted({
        owner_id
        for plan in plans
        if (owner_id := _owner_id(plan)) and owner_id.isdigit()
    })
    if not owner_ids:
        return {}
    users = db.query(User).filter(User.id.in_([int(owner_id) for owner_id in owner_ids])).all()
    return {
        str(user.id): BoardOwner(id=str(user.id), name=user.name, avatar_url=user.avatar_url)
        for user in users
    }


def _date_text(value: date | datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None
