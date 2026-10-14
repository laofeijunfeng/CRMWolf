"""Aggregate the complete authorized opportunity population into a board."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.core.list_query.types import FilterCondition, SortCondition
from app.models.customer import Customer
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.procurement import OpportunityStageSnapshot, ProcurementMethod, ProcurementStageTemplate
from app.schemas.board_primitives import BoardOwner
from app.schemas.opportunity_board import (
    OpportunityAmountMetric,
    OpportunityBoardActionState,
    OpportunityBoardColumn,
    OpportunityBoardItem,
    OpportunityBoardMetadata,
    OpportunityBoardMetric,
    OpportunityBoardResponse,
    OpportunityBoardTrendPoint,
    OpportunityCountMetric,
)
from app.services.board_trend_window import (
    extract_board_date_bounds,
    month_key,
    resolve_board_trend_window,
)
from app.services.board_value_format import BOARD_PREVIEW_LIMIT, money_string


TERMINAL_KEYS = ("won", "lost", "unset_stage")
TERMINAL_LABELS = {"won": "已赢单", "lost": "已输单", "unset_stage": "未设置阶段"}
TERMINAL_TONES = {"won": "success", "lost": "danger", "unset_stage": "muted"}
ITEM_STATUSES = {"won": "won", "lost": "lost", "unset_stage": "unset_stage"}
COUNT_LABELS = {"total_count": "商机", "won_count": "赢单"}
AMOUNT_LABELS = {
    "pipeline_amount": "预计金额",
    "weighted_amount": "加权金额",
    "won_amount": "赢单金额",
}
SUMMARY_KEYS = ("total_count", "pipeline_amount", "weighted_amount", "won_count", "won_amount")
_PREVIEW_FIELDS = {
    "opportunity_name",
    "customer_name",
    "total_amount",
    "status",
    "license_type",
    "purchase_type",
    "expected_closing_date",
    "stage_name",
    "owner_id",
    "created_time",
    "win_probability",
}


@dataclass(frozen=True)
class _StageFact:
    method_id: int
    template_id: int
    stage_name: str
    sort_order: int
    template_code: str
    method_name: str | None
    method_code: str | None


def build_opportunity_board(
    db: Session,
    *,
    team_id: int,
    current_user_id: str,
    permission_codes: set[str],
    rows: Sequence[Opportunity],
    legacy_branch_active: bool,
    created_time_start: date | None,
    created_time_end: date | None,
    filters: Sequence[FilterCondition] | None,
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
    today: date | None = None,
) -> OpportunityBoardResponse:
    """Group every authorized row before preview truncation."""
    materialized = list(rows)
    facts = _stage_facts(db, team_id, materialized)
    customers = _customer_map(db, team_id, materialized)
    owners = _owner_map(db, materialized)
    active: dict[tuple[int, int], list[Opportunity]] = {}
    terminals: dict[str, list[Opportunity]] = {key: [] for key in TERMINAL_KEYS}
    for row in materialized:
        key = _column_key(row, facts.get(row.current_stage_snapshot_id))
        if key in terminals:
            terminals[key].append(row)
        else:
            active.setdefault((facts[row.current_stage_snapshot_id].method_id, facts[row.current_stage_snapshot_id].template_id), []).append(row)

    explicit_sort = _has_explicit_sort(order_by, order_dir, sorts)
    ordered_identities = sorted(
        active,
        key=lambda identity: (
            facts[active[identity][0].current_stage_snapshot_id].sort_order,
            identity[0],
            identity[1],
        ),
    )
    columns = [
        _active_column(
            identity,
            active[identity],
            facts,
            customers,
            owners,
            current_user_id,
            permission_codes,
            explicit_sort,
            sorts,
            order_by,
            order_dir,
        )
        for identity in ordered_identities
    ]
    columns.extend(
        _terminal_column(
            key,
            terminals[key],
            facts,
            customers,
            owners,
            current_user_id,
            permission_codes,
            explicit_sort,
            sorts,
            order_by,
            order_dir,
        )
        for key in TERMINAL_KEYS
    )
    return OpportunityBoardResponse(
        summary=_summary(materialized),
        columns=columns,
        trends=_trends(
            materialized,
            legacy_branch_active=legacy_branch_active,
            created_time_start=created_time_start,
            created_time_end=created_time_end,
            filters=filters,
            today=today or date.today(),
        ),
    )


def _column_key(row: Opportunity, fact: _StageFact | None) -> str:
    if row.status == OpportunityStatus.WON.value:
        return "won"
    if row.status == OpportunityStatus.LOST.value:
        return "lost"
    if fact is None:
        return "unset_stage"
    return f"stage:{fact.method_id}:{fact.template_id}"


def _stage_facts(
    db: Session,
    team_id: int,
    rows: Sequence[Opportunity],
) -> dict[int, _StageFact]:
    snapshot_ids = {row.current_stage_snapshot_id for row in rows if row.current_stage_snapshot_id}
    if not snapshot_ids:
        return {}
    loaded = (
        db.query(OpportunityStageSnapshot, ProcurementStageTemplate, ProcurementMethod)
        .join(
            ProcurementStageTemplate,
            OpportunityStageSnapshot.procurement_stage_template_id == ProcurementStageTemplate.id,
        )
        .outerjoin(
            ProcurementMethod,
            ProcurementStageTemplate.procurement_method_id == ProcurementMethod.id,
        )
        .filter(
            OpportunityStageSnapshot.team_id == team_id,
            OpportunityStageSnapshot.id.in_(snapshot_ids),
        )
        .all()
    )
    facts: dict[int, _StageFact] = {}
    for snapshot, template, method in loaded:
        name = snapshot.stage_name.strip() if snapshot.stage_name else ""
        if not snapshot.procurement_stage_template_id or not name or template is None:
            continue
        facts[int(snapshot.id)] = _StageFact(
            method_id=int(template.procurement_method_id),
            template_id=int(template.id),
            stage_name=name,
            sort_order=int(snapshot.template_sort_order),
            template_code=snapshot.template_code,
            method_name=method.name if method is not None else None,
            method_code=method.code if method is not None else None,
        )
    return facts


def _summary(rows: Sequence[Opportunity]) -> list[OpportunityBoardMetric]:
    pipeline = Decimal("0")
    weighted = Decimal("0")
    won = Decimal("0")
    won_count = 0
    for row in rows:
        total = Decimal(str(row.total_amount or 0))
        if row.status == OpportunityStatus.FOLLOWING.value:
            probability = Decimal(str(row.win_probability or 0))
            pipeline += total
            weighted += total * probability / Decimal("100")
        elif row.status == OpportunityStatus.WON.value:
            won_count += 1
            won += Decimal(str(row.actual_amount if row.actual_amount is not None else row.total_amount or 0))
    values = {
        "total_count": len(rows),
        "pipeline_amount": money_string(pipeline),
        "weighted_amount": money_string(weighted),
        "won_count": won_count,
        "won_amount": money_string(won),
    }
    metrics: list[OpportunityBoardMetric] = []
    for key in SUMMARY_KEYS:
        if key in COUNT_LABELS:
            metrics.append(OpportunityCountMetric(
                key=key,
                label=COUNT_LABELS[key],
                value_type="count",
                value=values[key],
            ))
        else:
            metrics.append(OpportunityAmountMetric(
                key=key,
                label=AMOUNT_LABELS[key],
                value_type="amount",
                value=values[key],
            ))
    return metrics


def _active_column(
    identity: tuple[int, int],
    rows: Sequence[Opportunity],
    facts: dict[int, _StageFact],
    customers: dict[int, Customer],
    owners: dict[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> OpportunityBoardColumn:
    fact = facts[rows[0].current_stage_snapshot_id]
    ordered = _preview_order(rows, facts, customers, explicit_sort, sorts, order_by, order_dir)
    shown = ordered[:BOARD_PREVIEW_LIMIT]
    remaining = len(ordered) - len(shown)
    amount = sum((Decimal(str(row.total_amount or 0)) for row in ordered), Decimal("0"))
    return OpportunityBoardColumn(
        key=f"stage:{identity[0]}:{identity[1]}",
        label=fact.stage_name,
        tone="info",
        column_kind="active_stage",
        stage_name=fact.stage_name,
        template_code=fact.template_code,
        template_sort_order=fact.sort_order,
        procurement_method_id=fact.method_id,
        procurement_stage_template_id=fact.template_id,
        count=len(ordered),
        amount=money_string(amount),
        items=[
            _item(row, "active", facts.get(row.current_stage_snapshot_id), customers, owners, current_user_id, permission_codes)
            for row in shown
        ],
        has_more=remaining > 0,
        remaining_count=remaining,
    )


def _terminal_column(
    key: str,
    rows: Sequence[Opportunity],
    facts: dict[int, _StageFact],
    customers: dict[int, Customer],
    owners: dict[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> OpportunityBoardColumn:
    ordered = _preview_order(rows, facts, customers, explicit_sort, sorts, order_by, order_dir)
    shown = ordered[:BOARD_PREVIEW_LIMIT]
    remaining = len(ordered) - len(shown)
    amount = sum((Decimal(str(row.total_amount or 0)) for row in ordered), Decimal("0"))
    return OpportunityBoardColumn(
        key=key,
        label=TERMINAL_LABELS[key],
        tone=TERMINAL_TONES[key],
        column_kind=key,
        count=len(ordered),
        amount=money_string(amount),
        items=[
            _item(
                row,
                ITEM_STATUSES[key],
                facts.get(row.current_stage_snapshot_id),
                customers,
                owners,
                current_user_id,
                permission_codes,
            )
            for row in shown
        ],
        has_more=remaining > 0,
        remaining_count=remaining,
    )


def _item(
    row: Opportunity,
    status: str,
    fact: _StageFact | None,
    customers: dict[int, Customer],
    owners: dict[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
) -> OpportunityBoardItem:
    customer = customers.get(int(row.customer_id))
    customer_name = customer.account_name if customer is not None else None
    closing = row.expected_closing_date.isoformat() if row.expected_closing_date else None
    probability = row.win_probability
    return OpportunityBoardItem(
        id=row.public_id,
        title=row.opportunity_name,
        subtitle=customer_name,
        amount=money_string(row.total_amount),
        date=closing,
        owner=owners.get(str(row.owner_id)) if row.owner_id else None,
        status=status,
        metadata=OpportunityBoardMetadata(
            customer_name=customer_name,
            purchase_type=row.purchase_type,
            license_type=row.license_type,
            expected_closing_date=closing,
            win_probability=None if probability is None else float(probability),
            stage_name=fact.stage_name if fact is not None else None,
            stage_sort_order=fact.sort_order if fact is not None else None,
            procurement_method_name=fact.method_name if fact is not None else None,
            procurement_method_code=fact.method_code if fact is not None else None,
            procurement_stage_template_id=fact.template_id if fact is not None else None,
            template_code=fact.template_code if fact is not None else None,
        ),
        action_state=_action_state(row, status, current_user_id, permission_codes),
    )


def _action_state(
    row: Opportunity,
    status: str,
    current_user_id: str,
    permission_codes: set[str],
) -> OpportunityBoardActionState:
    owns_row = row.owner_id == str(current_user_id)
    can_edit = "opportunity:edit:all" in permission_codes or (
        "opportunity:edit:own" in permission_codes and owns_row
    )
    can_delete = "opportunity:delete:all" in permission_codes or (
        "opportunity:delete:own" in permission_codes and owns_row
    )
    approved = row.approval_phase == ApprovalPhase.APPROVED.value
    active = status == "active"
    return OpportunityBoardActionState(
        can_edit=can_edit,
        can_delete=can_delete,
        can_move_stage=can_edit and active and approved,
        can_mark_won=can_edit and active and approved and "opportunity:win" in permission_codes,
        can_mark_lost=can_edit and active and approved and "opportunity:lose" in permission_codes,
    )


def _preview_order(
    rows: Sequence[Opportunity],
    facts: dict[int, _StageFact],
    customers: dict[int, Customer],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[Opportunity]:
    indexed = list(enumerate(rows))
    if not explicit_sort:
        return [
            row
            for _, row in sorted(
                indexed,
                key=lambda item: (
                    item[1].expected_closing_date is None,
                    item[1].expected_closing_date or date.max,
                    -Decimal(str(item[1].total_amount or 0)),
                    item[1].public_id,
                ),
            )
        ]
    requested = _requested_sorts(sorts, order_by, order_dir)
    return [
        row
        for _, row in sorted(
            indexed,
            key=lambda item: (
                tuple(
                    _directed(_sort_value(item[1], facts, customers, field), ascending)
                    for field, ascending in requested
                ),
                item[1].public_id,
            ),
        )
    ]


def _sort_value(
    row: Opportunity,
    facts: dict[int, _StageFact],
    customers: dict[int, Customer],
    field: str,
):
    if field not in _PREVIEW_FIELDS:
        return ""
    if field == "opportunity_name":
        return row.opportunity_name or ""
    if field == "customer_name":
        customer = customers.get(int(row.customer_id))
        return customer.account_name if customer is not None and customer.account_name else ""
    if field == "total_amount":
        return Decimal(str(row.total_amount or 0))
    if field == "status":
        return row.status
    if field == "license_type":
        return row.license_type or ""
    if field == "purchase_type":
        return row.purchase_type or ""
    if field == "expected_closing_date":
        return row.expected_closing_date
    if field == "stage_name":
        fact = facts.get(row.current_stage_snapshot_id)
        return fact.stage_name if fact is not None else ""
    if field == "owner_id":
        return row.owner_id or ""
    if field == "created_time":
        return row.created_time if isinstance(row.created_time, datetime) else None
    if field == "win_probability":
        return row.win_probability
    return ""


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
    text = str(value)
    if text == "":
        return (1,)
    ordered = text if ascending else tuple(-ord(char) for char in text)
    return (0, ordered)


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
    rows: Sequence[Opportunity],
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
    rows: Sequence[Opportunity],
    *,
    legacy_branch_active: bool,
    created_time_start: date | None,
    created_time_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
) -> list[OpportunityBoardTrendPoint]:
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
    counts = {month: 0 for month in window.months}
    amounts = {month: Decimal("0") for month in window.months}
    for row in rows:
        event_day = row.created_time.date() if isinstance(row.created_time, datetime) else None
        if event_day is None or not window.event_start <= event_day <= window.event_end:
            continue
        key = month_key(event_day)
        counts[key] += 1
        amounts[key] += Decimal(str(row.total_amount or 0))
    return [
        OpportunityBoardTrendPoint(date=month, count=counts[month], amount=money_string(amounts[month]))
        for month in window.months
    ]


def _customer_map(db: Session, team_id: int, rows: Sequence[Opportunity]) -> dict[int, Customer]:
    customer_ids = {int(row.customer_id) for row in rows if row.customer_id}
    if not customer_ids:
        return {}
    loaded = db.query(Customer).filter(Customer.team_id == team_id, Customer.id.in_(customer_ids)).all()
    return {int(customer.id): customer for customer in loaded}


def _owner_map(db: Session, rows: Sequence[Opportunity]) -> dict[str, BoardOwner]:
    owner_ids = sorted({str(row.owner_id) for row in rows if row.owner_id and str(row.owner_id).isdigit()})
    if not owner_ids:
        return {}
    from sqlalchemy import text

    placeholders = ", ".join(f":owner_{index}" for index in range(len(owner_ids)))
    users = db.execute(
        text(f"SELECT id, name, avatar_url FROM users WHERE id IN ({placeholders})"),
        {f"owner_{index}": int(owner_id) for index, owner_id in enumerate(owner_ids)},
    ).fetchall()
    return {
        str(user_id): BoardOwner(id=str(user_id), name=name, avatar_url=avatar_url)
        for user_id, name, avatar_url in users
    }
