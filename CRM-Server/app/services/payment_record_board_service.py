"""Aggregate the complete authorized payment-record population into a board."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.core.list_query.types import FilterCondition, SortCondition
from app.models.approval import Approval, ApprovalStatus
from app.models.payment import PaymentConfirmationStatus, PaymentRecord
from app.models.user import User
from app.schemas.board_primitives import BoardOwner
from app.schemas.payment_record_board import (
    PaymentRecordAmountMetric,
    PaymentRecordBoardActionState,
    PaymentRecordBoardColumn,
    PaymentRecordBoardItem,
    PaymentRecordBoardMetadata,
    PaymentRecordBoardMetric,
    PaymentRecordBoardResponse,
    PaymentRecordBoardTrendPoint,
    PaymentRecordCountMetric,
)
from app.services.board_trend_window import (
    extract_board_date_bounds,
    month_key,
    resolve_board_trend_window,
)
from app.services.board_value_format import BOARD_PREVIEW_LIMIT, money_string
from app.services.payment_approval_status import (
    LinkedPaymentApproval,
    PaymentApprovalReadStatus,
    resolve_payment_approval_status,
)


COLUMN_KEYS = (
    "pending_submit",
    "pending_approval",
    "rejected",
    "approved",
    "unclassified",
)
COLUMN_LABELS = {
    "pending_submit": "待提交",
    "pending_approval": "审批中",
    "rejected": "已驳回",
    "approved": "已通过",
    "unclassified": "未分类",
}
COLUMN_TONES = {
    "pending_submit": "neutral",
    "pending_approval": "info",
    "rejected": "danger",
    "approved": "success",
    "unclassified": "muted",
}
SUMMARY_KEYS = (
    "total_count",
    "rejected_count",
    "actual_total",
    "confirmed_amount",
    "unconfirmed_amount",
)
COUNT_LABELS = {
    "total_count": "回款笔数",
    "rejected_count": "已驳回",
}
AMOUNT_LABELS = {
    "actual_total": "回款金额",
    "confirmed_amount": "已确认",
    "unconfirmed_amount": "未确认",
}
_PREVIEW_FIELDS = {
    "record_number",
    "customer_name",
    "contract_name",
    "actual_payer_name",
    "actual_amount",
    "payment_date",
    "confirmation_status",
    "approval_status",
    "created_time",
    "owner_name",
    "commission_member_name",
}
_STATUS_ORDER = {
    "pending_submit": 0,
    "pending_approval": 1,
    "rejected": 2,
    "approved": 3,
    "unclassified": 99,
}
_CONFIRMATION_ORDER = {
    PaymentConfirmationStatus.PENDING: 0,
    PaymentConfirmationStatus.CONFIRMED: 1,
    PaymentConfirmationStatus.DISPUTED: 2,
}
_EDITABLE_PHASES = {ApprovalPhase.DRAFT.value, ApprovalPhase.REJECTED.value}
_LOCKED_DELETE_PHASES = {ApprovalPhase.PENDING_REVIEW.value, ApprovalPhase.APPROVED.value}
_LOCKED_DELETE_STATUSES = {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}


def build_payment_record_board(
    db: Session,
    *,
    team_id: int,
    current_user_id: str,
    permission_codes: set[str],
    records: Sequence[PaymentRecord],
    legacy_branch_active: bool,
    payment_date_start: date | None,
    payment_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    sort: str | None,
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
    today: date | None = None,
) -> PaymentRecordBoardResponse:
    """Group every authorized record before preview truncation."""
    materialized = list(records)
    owners = _owner_map(db, materialized)
    buckets: dict[str, list[PaymentRecord]] = {key: [] for key in COLUMN_KEYS}
    for record in materialized:
        buckets[_column_key(record, team_id)].append(record)
    explicit_sort = _has_explicit_sort(sort, order_by, order_dir, sorts)
    columns = [
        _column(
            key,
            buckets[key],
            team_id,
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
    return PaymentRecordBoardResponse(
        summary=_summary(materialized, team_id),
        columns=columns,
        trends=_trends(
            materialized,
            legacy_branch_active=legacy_branch_active,
            payment_date_start=payment_date_start,
            payment_date_end=payment_date_end,
            filters=filters,
            today=today or date.today(),
        ),
    )


def _column_key(record: PaymentRecord, team_id: int) -> str:
    return resolve_payment_approval_status(
        record_id=int(record.id),
        team_id=team_id,
        approval_id=record.approval_id,
        approval_phase=_text(record.approval_phase),
        linked_approval=_linked_approval(record, team_id),
    ).value


def _linked_approval(record: PaymentRecord, team_id: int) -> LinkedPaymentApproval | None:
    approval = record.approval
    if not isinstance(approval, Approval) or approval.id is None:
        return None
    return LinkedPaymentApproval(
        id=int(approval.id),
        team_id=int(approval.team_id),
        business_type=str(approval.business_type),
        business_id=int(approval.business_id) if approval.business_id is not None else 0,
        status=_text(approval.status),
    )


def _actual_amount(record: PaymentRecord) -> Decimal:
    return Decimal(str(record.actual_amount or 0))


def _confirmed_amount(record: PaymentRecord) -> Decimal:
    if _text(record.confirmation_status) == PaymentConfirmationStatus.CONFIRMED:
        return _actual_amount(record)
    return Decimal("0")


def _summary(records: Sequence[PaymentRecord], team_id: int) -> list[PaymentRecordBoardMetric]:
    actual_total = Decimal("0")
    confirmed_total = Decimal("0")
    rejected_count = 0
    for record in records:
        actual_total += _actual_amount(record)
        confirmed_total += _confirmed_amount(record)
        if _column_key(record, team_id) == PaymentApprovalReadStatus.REJECTED:
            rejected_count += 1
    values = {
        "total_count": len(records),
        "rejected_count": rejected_count,
        "actual_total": money_string(actual_total),
        "confirmed_amount": money_string(confirmed_total),
        "unconfirmed_amount": money_string(actual_total - confirmed_total),
    }
    metrics: list[PaymentRecordBoardMetric] = []
    for key in SUMMARY_KEYS:
        if key in COUNT_LABELS:
            metrics.append(PaymentRecordCountMetric(
                key=key,
                label=COUNT_LABELS[key],
                value_type="count",
                value=values[key],
            ))
        else:
            metrics.append(PaymentRecordAmountMetric(
                key=key,
                label=AMOUNT_LABELS[key],
                value_type="amount",
                value=values[key],
            ))
    return metrics


def _column(
    key: str,
    records: Sequence[PaymentRecord],
    team_id: int,
    owners: Mapping[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
    explicit_sort: bool,
    sort: str | None,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> PaymentRecordBoardColumn:
    ordered = _preview_order(
        records,
        team_id,
        owners,
        explicit_sort,
        sort,
        sorts,
        order_by,
        order_dir,
    )
    shown = ordered[:BOARD_PREVIEW_LIMIT]
    remaining_count = len(ordered) - len(shown)
    actual_total = Decimal("0")
    confirmed_total = Decimal("0")
    for record in ordered:
        actual_total += _actual_amount(record)
        confirmed_total += _confirmed_amount(record)
    actual_text = money_string(actual_total)
    return PaymentRecordBoardColumn(
        key=key,
        label=COLUMN_LABELS[key],
        tone=COLUMN_TONES[key],
        count=len(ordered),
        amount=actual_text,
        actual_amount=actual_text,
        confirmed_amount=money_string(confirmed_total),
        unconfirmed_amount=money_string(actual_total - confirmed_total),
        items=[
            _item(record, key, team_id, owners, current_user_id, permission_codes)
            for record in shown
        ],
        has_more=remaining_count > 0,
        remaining_count=remaining_count,
    )


def _item(
    record: PaymentRecord,
    key: str,
    team_id: int,
    owners: Mapping[str, BoardOwner],
    current_user_id: str,
    permission_codes: set[str],
) -> PaymentRecordBoardItem:
    amount_text = money_string(_actual_amount(record))
    contract = record.payment_plan.contract if record.payment_plan is not None else None
    customer = contract.customer if contract is not None else None
    owner_id = _owner_id(record)
    owner = owners.get(owner_id) if owner_id else None
    confirmation = _text(record.confirmation_status)
    if confirmation not in {"PENDING", "CONFIRMED", "DISPUTED"}:
        confirmation = None
    approval = _valid_linked_approval(record, team_id)
    return PaymentRecordBoardItem(
        id=int(record.id),
        title=record.record_number,
        subtitle=customer.account_name if customer is not None else None,
        amount=amount_text,
        actual_amount=amount_text,
        date=_date_text(record.payment_date),
        owner=owner,
        status=key,
        metadata=PaymentRecordBoardMetadata(
            customer_name=customer.account_name if customer is not None else None,
            contract_name=contract.contract_name if contract is not None else None,
            actual_payer_name=record.actual_payer_name,
            creator_name=record.creator_name,
            owner_name=owner.name if owner is not None else None,
            commission_member_name=record.commission_member_name,
            approval_phase=_text(record.approval_phase),
            approval_id=int(approval.id) if approval is not None else None,
            confirmation_status=confirmation,
        ),
        action_state=_action_state(record, key, team_id, current_user_id, permission_codes),
    )


def _action_state(
    record: PaymentRecord,
    key: str,
    team_id: int,
    current_user_id: str,
    permission_codes: set[str],
) -> PaymentRecordBoardActionState:
    phase = _text(record.approval_phase)
    approval = _valid_linked_approval(record, team_id)
    approval_status = _text(approval.status) if approval is not None else None
    is_creator = str(record.creator_id) == current_user_id
    pending_approval = approval_status == ApprovalStatus.PENDING or key == PaymentApprovalReadStatus.PENDING_APPROVAL
    can_edit = (
        not pending_approval
        and phase in _EDITABLE_PHASES
        and ("payment:record:edit" in permission_codes or "payment:edit" in permission_codes or is_creator)
    )
    delete_locked = (
        approval_status in _LOCKED_DELETE_STATUSES
        or phase in _LOCKED_DELETE_PHASES
    )
    can_delete = (
        ("payment:record:delete" in permission_codes or "payment:delete" in permission_codes)
        and not delete_locked
    )
    can_resubmit = (
        "payment:submit" in permission_codes
        and is_creator
        and key == PaymentApprovalReadStatus.REJECTED
    )
    return PaymentRecordBoardActionState(
        can_edit=can_edit,
        can_delete=can_delete,
        can_resubmit=can_resubmit,
    )


def _valid_linked_approval(record: PaymentRecord, team_id: int) -> Approval | None:
    approval = record.approval
    if (
        isinstance(approval, Approval)
        and approval.id == record.approval_id
        and int(approval.team_id) == team_id
        and approval.business_type == BusinessType.PAYMENT
        and approval.business_id == record.id
    ):
        return approval
    return None


def _owner_id(record: PaymentRecord) -> str | None:
    plan = record.payment_plan
    contract = plan.contract if plan is not None else None
    opportunity = contract.opportunity if contract is not None else None
    if opportunity is not None and opportunity.owner_id:
        return str(opportunity.owner_id)
    if contract is not None and contract.owner_id:
        return str(contract.owner_id)
    return None


def _preview_order(
    records: Sequence[PaymentRecord],
    team_id: int,
    owners: Mapping[str, BoardOwner],
    explicit_sort: bool,
    sort: str | None,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[PaymentRecord]:
    indexed = list(enumerate(records))
    if not explicit_sort:
        return [
            record
            for _, record in sorted(
                indexed,
                key=lambda item: (
                    not isinstance(item[1].payment_date, date),
                    -item[1].payment_date.toordinal() if isinstance(item[1].payment_date, date) else 0,
                    -int(item[1].id),
                ),
            )
        ]
    requested = _requested_sorts(sort, sorts, order_by, order_dir)
    return [
        record
        for _, record in sorted(
            indexed,
            key=lambda item: (
                tuple(
                    _directed(_sort_value(item[1], team_id, owners, field), ascending)
                    for field, ascending in requested
                ),
                int(item[1].id),
            ),
        )
    ]


def _sort_value(
    record: PaymentRecord,
    team_id: int,
    owners: Mapping[str, BoardOwner],
    field: str,
):
    if field not in _PREVIEW_FIELDS:
        return ""
    contract = record.payment_plan.contract if record.payment_plan is not None else None
    customer = contract.customer if contract is not None else None
    owner_id = _owner_id(record)
    confirmation = _text(record.confirmation_status)
    values = {
        "record_number": record.record_number or "",
        "customer_name": customer.account_name if customer is not None else "",
        "contract_name": contract.contract_name if contract is not None else "",
        "actual_payer_name": record.actual_payer_name or "",
        "actual_amount": _actual_amount(record),
        "payment_date": record.payment_date if isinstance(record.payment_date, date) else None,
        "confirmation_status": _CONFIRMATION_ORDER.get(confirmation, 99),
        "approval_status": _STATUS_ORDER[_column_key(record, team_id)],
        "created_time": record.created_time if isinstance(record.created_time, datetime) else None,
        "owner_name": owners[owner_id].name if owner_id and owner_id in owners else "",
        "commission_member_name": record.commission_member_name or "",
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


def _payment_window(
    *,
    records: Sequence[PaymentRecord],
    legacy_branch_active: bool,
    payment_date_start: date | None,
    payment_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
):
    if not records:
        return None
    if legacy_branch_active:
        start_bound, end_bound = payment_date_start, payment_date_end
    else:
        start_bound, end_bound = extract_board_date_bounds(filters, "payment_date")
    window = resolve_board_trend_window(today=today, start_bound=start_bound, end_bound=end_bound)
    return None if window.empty else window


def _trends(
    records: Sequence[PaymentRecord],
    *,
    legacy_branch_active: bool,
    payment_date_start: date | None,
    payment_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
) -> list[PaymentRecordBoardTrendPoint]:
    window = _payment_window(
        records=records,
        legacy_branch_active=legacy_branch_active,
        payment_date_start=payment_date_start,
        payment_date_end=payment_date_end,
        filters=filters,
        today=today,
    )
    if window is None:
        return []
    counts = {month: 0 for month in window.months}
    actual_amounts = {month: Decimal("0") for month in window.months}
    confirmed_amounts = {month: Decimal("0") for month in window.months}
    for record in records:
        payment_day = record.payment_date if isinstance(record.payment_date, date) else None
        if payment_day is None or not window.event_start <= payment_day <= window.event_end:
            continue
        key = month_key(payment_day)
        actual = _actual_amount(record)
        counts[key] += 1
        actual_amounts[key] += actual
        confirmed_amounts[key] += _confirmed_amount(record)
    return [
        PaymentRecordBoardTrendPoint(
            date=month,
            count=counts[month],
            actual_amount=money_string(actual_amounts[month]),
            confirmed_amount=money_string(confirmed_amounts[month]),
            unconfirmed_amount=money_string(actual_amounts[month] - confirmed_amounts[month]),
        )
        for month in window.months
    ]


def _owner_map(db: Session, records: Sequence[PaymentRecord]) -> dict[str, BoardOwner]:
    owner_ids = sorted({
        owner_id
        for record in records
        if (owner_id := _owner_id(record)) and owner_id.isdigit()
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


def _text(value: object) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else None
