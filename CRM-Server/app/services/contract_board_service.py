"""Aggregate the complete authorized contract population into a board."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.constants.business_types import BusinessType
from app.core.list_query.catalogs.common import latest_official_issued_license
from app.core.list_query.types import FilterCondition, SortCondition
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity
from app.schemas.board_primitives import BoardOwner
from app.schemas.contract_board import (
    ContractAmountMetric,
    ContractBoardActionState,
    ContractBoardColumn,
    ContractBoardItem,
    ContractBoardMetadata,
    ContractBoardMetric,
    ContractBoardResponse,
    ContractBoardTrendPoint,
    ContractCountMetric,
)
from app.services.board_trend_window import (
    extract_board_date_bounds,
    month_key,
    resolve_board_trend_window,
)
from app.services.board_value_format import money_string

COLUMN_KEYS = (
    "DRAFT",
    "PENDING_REVIEW",
    "SIGNED",
    "EFFECTIVE",
    "EXPIRED",
    "TERMINATED",
    "UNCLASSIFIED",
)
COLUMN_LABELS = {
    "DRAFT": "草稿",
    "PENDING_REVIEW": "待审核",
    "SIGNED": "已签署",
    "EFFECTIVE": "已生效",
    "EXPIRED": "已到期",
    "TERMINATED": "已终止",
    "UNCLASSIFIED": "未分类",
}
COLUMN_TONES = {
    "DRAFT": "neutral",
    "PENDING_REVIEW": "warning",
    "SIGNED": "success",
    "EFFECTIVE": "success",
    "EXPIRED": "muted",
    "TERMINATED": "danger",
    "UNCLASSIFIED": "muted",
}
COUNT_LABELS = {"total_count": "合同", "pending_review_count": "待审"}
AMOUNT_LABELS = {"total_amount": "合同金额", "signed_effective_amount": "生效金额"}
SUMMARY_KEYS = ("total_count", "pending_review_count", "total_amount", "signed_effective_amount")
SIGNED_EFFECTIVE = {"SIGNED", "EFFECTIVE"}
_PREVIEW_FIELDS = {
    "contract_number",
    "contract_name",
    "customer_name",
    "opportunity_name",
    "total_amount",
    "license_type",
    "purchase_type",
    "subscription_years",
    "license_authorized_users",
    "standard_unit_price",
    "license_expiry_date",
    "status",
    "signing_date",
    "effective_date",
    "expiry_date",
    "created_time",
    "owner_id",
}


def build_contract_board(
    db: Session,
    *,
    team_id: int,
    current_user_id: str,
    permission_codes: set[str],
    role_codes: set[str],
    rows: Sequence[Contract],
    legacy_branch_active: bool,
    signing_date_start: date | None,
    signing_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    order_by: str | None,
    order_dir: str | None,
    sorts: Sequence[SortCondition] | None,
    today: date | None = None,
) -> ContractBoardResponse:
    """Group every authorized row before preview truncation."""
    materialized = list(rows)
    customers = _customer_map(db, team_id, materialized)
    opportunities = _opportunity_map(db, team_id, materialized)
    owners = _owner_map(db, materialized)
    licenses = _license_facts(db, materialized)
    approvals = _pending_approval_roles(db, team_id, materialized)
    buckets: dict[str, list[Contract]] = {key: [] for key in COLUMN_KEYS}
    for row in materialized:
        buckets[_column_key(row)].append(row)

    explicit_sort = _has_explicit_sort(order_by, order_dir, sorts)
    columns = [
        _column(
            key,
            buckets[key],
            customers,
            opportunities,
            owners,
            licenses,
            approvals,
            current_user_id,
            permission_codes,
            role_codes,
            explicit_sort,
            sorts,
            order_by,
            order_dir,
        )
        for key in COLUMN_KEYS
    ]
    return ContractBoardResponse(
        summary=_summary(materialized),
        columns=columns,
        trends=_trends(
            materialized,
            legacy_branch_active=legacy_branch_active,
            signing_date_start=signing_date_start,
            signing_date_end=signing_date_end,
            filters=filters,
            today=today or date.today(),
        ),
    )


def _column_key(row: Contract) -> str:
    status = row.status if isinstance(row.status, str) else None
    return status if status in COLUMN_KEYS[:-1] else "UNCLASSIFIED"


def _summary(rows: Sequence[Contract]) -> list[ContractBoardMetric]:
    total = Decimal("0")
    signed_effective = Decimal("0")
    pending_review = 0
    for row in rows:
        amount = Decimal(str(row.total_amount or 0))
        total += amount
        key = _column_key(row)
        if key in SIGNED_EFFECTIVE:
            signed_effective += amount
        if key == "PENDING_REVIEW":
            pending_review += 1
    values = {
        "total_count": len(rows),
        "pending_review_count": pending_review,
        "total_amount": money_string(total),
        "signed_effective_amount": money_string(signed_effective),
    }
    metrics: list[ContractBoardMetric] = []
    for key in SUMMARY_KEYS:
        if key in COUNT_LABELS:
            metrics.append(ContractCountMetric(
                key=key,
                label=COUNT_LABELS[key],
                value_type="count",
                value=values[key],
            ))
        else:
            metrics.append(ContractAmountMetric(
                key=key,
                label=AMOUNT_LABELS[key],
                value_type="amount",
                value=values[key],
            ))
    return metrics


def _column(
    key: str,
    rows: Sequence[Contract],
    customers: dict[int, Customer],
    opportunities: dict[int, Opportunity],
    owners: dict[str, BoardOwner],
    licenses: dict[int, tuple[int | None, date | None]],
    approvals: dict[int, str | None],
    current_user_id: str,
    permission_codes: set[str],
    role_codes: set[str],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> ContractBoardColumn:
    ordered = _preview_order(
        rows,
        customers,
        opportunities,
        licenses,
        explicit_sort,
        sorts,
        order_by,
        order_dir,
    )
    amount = sum((Decimal(str(row.total_amount or 0)) for row in ordered), Decimal("0"))
    return ContractBoardColumn(
        key=key,
        label=COLUMN_LABELS[key],
        tone=COLUMN_TONES[key],
        count=len(ordered),
        amount=money_string(amount),
        items=[
            _item(
                row,
                key,
                customers,
                opportunities,
                owners,
                licenses,
                approvals,
                current_user_id,
                permission_codes,
                role_codes,
            )
            for row in ordered
        ],
        has_more=False,
        remaining_count=0,
    )


def _item(
    row: Contract,
    key: str,
    customers: dict[int, Customer],
    opportunities: dict[int, Opportunity],
    owners: dict[str, BoardOwner],
    licenses: dict[int, tuple[int | None, date | None]],
    approvals: dict[int, str | None],
    current_user_id: str,
    permission_codes: set[str],
    role_codes: set[str],
) -> ContractBoardItem:
    customer = customers.get(int(row.customer_id)) if row.customer_id else None
    opportunity = opportunities.get(int(row.opportunity_id)) if row.opportunity_id else None
    authorized_users, license_expiry = licenses.get(int(row.id), (row.user_count, None))
    signing = _date_text(row.signing_date)
    return ContractBoardItem(
        id=int(row.id),
        title=row.contract_name,
        subtitle=row.contract_number,
        amount=money_string(row.total_amount),
        date=signing,
        owner=owners.get(str(row.owner_id)) if row.owner_id else None,
        status=key,
        metadata=ContractBoardMetadata(
            customer_name=customer.account_name if customer is not None else None,
            opportunity_name=opportunity.opportunity_name if opportunity is not None else None,
            license_type=row.license_type,
            purchase_type=opportunity.purchase_type if opportunity is not None else None,
            signing_date=signing,
            effective_date=_date_text(row.effective_date),
            expiry_date=_date_text(row.expiry_date),
            license_expiry_date=_date_text(license_expiry),
            authorized_users=authorized_users,
        ),
        action_state=_action_state(
            row,
            key,
            current_user_id,
            permission_codes,
            role_codes,
            approvals.get(int(row.id)),
        ),
    )


def _action_state(
    row: Contract,
    key: str,
    current_user_id: str,
    permission_codes: set[str],
    role_codes: set[str],
    pending_role: str | None,
) -> ContractBoardActionState:
    owns_row = row.owner_id == str(current_user_id)
    draft = key == "DRAFT"
    can_edit = draft and (
        "contract:edit:all" in permission_codes
        or ("contract:edit:own" in permission_codes and owns_row)
    )
    deletable_phase = row.approval_phase not in {"pending_review", "approved"}
    can_delete = draft and deletable_phase and (
        "contract:delete:all" in permission_codes
        or ("contract:delete:own" in permission_codes and owns_row)
    )
    can_submit = draft and "contract:submit" in permission_codes
    can_decide = False
    if key == "PENDING_REVIEW" and pending_role and pending_role in role_codes:
        is_self = row.creator_id == str(current_user_id)
        can_decide = not is_self or "contract:approve:own" in permission_codes
    return ContractBoardActionState(
        can_edit=can_edit,
        can_delete=can_delete,
        can_submit_approval=can_submit,
        can_approve=can_decide,
        can_reject=can_decide,
    )


def _preview_order(
    rows: Sequence[Contract],
    customers: dict[int, Customer],
    opportunities: dict[int, Opportunity],
    licenses: dict[int, tuple[int | None, date | None]],
    explicit_sort: bool,
    sorts: Sequence[SortCondition] | None,
    order_by: str | None,
    order_dir: str | None,
) -> list[Contract]:
    indexed = list(enumerate(rows))
    if not explicit_sort:
        return [
            row
            for _, row in sorted(
                indexed,
                key=lambda item: (
                    -(item[1].signing_date.toordinal()) if item[1].signing_date else 0,
                    -(item[1].effective_date.toordinal()) if item[1].effective_date else 0,
                    -int(item[1].id),
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
                    _directed(
                        _sort_value(item[1], customers, opportunities, licenses, field),
                        ascending,
                    )
                    for field, ascending in requested
                ),
                int(item[1].id),
            ),
        )
    ]


def _sort_value(
    row: Contract,
    customers: dict[int, Customer],
    opportunities: dict[int, Opportunity],
    licenses: dict[int, tuple[int | None, date | None]],
    field: str,
):
    if field not in _PREVIEW_FIELDS:
        return ""
    if field == "contract_number":
        return row.contract_number or ""
    if field == "contract_name":
        return row.contract_name or ""
    if field == "customer_name":
        customer = customers.get(int(row.customer_id)) if row.customer_id else None
        return customer.account_name if customer is not None and customer.account_name else ""
    if field == "opportunity_name":
        opportunity = opportunities.get(int(row.opportunity_id)) if row.opportunity_id else None
        return opportunity.opportunity_name if opportunity is not None and opportunity.opportunity_name else ""
    if field == "total_amount":
        return Decimal(str(row.total_amount or 0))
    if field == "license_type":
        return row.license_type or ""
    if field == "purchase_type":
        opportunity = opportunities.get(int(row.opportunity_id)) if row.opportunity_id else None
        return opportunity.purchase_type if opportunity is not None and opportunity.purchase_type else ""
    if field == "subscription_years":
        return row.subscription_years
    if field == "license_authorized_users":
        authorized_users, _ = licenses.get(int(row.id), (row.user_count, None))
        return authorized_users
    if field == "standard_unit_price":
        return None if row.standard_unit_price is None else Decimal(str(row.standard_unit_price))
    if field == "license_expiry_date":
        _, expiry = licenses.get(int(row.id), (None, None))
        return expiry
    if field == "status":
        return row.status or ""
    if field == "signing_date":
        return row.signing_date
    if field == "effective_date":
        return row.effective_date
    if field == "expiry_date":
        return row.expiry_date
    if field == "created_time":
        return row.created_time if isinstance(row.created_time, datetime) else None
    if field == "owner_id":
        return row.owner_id or ""
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
    text_value = str(value)
    if text_value == "":
        return (1,)
    ordered = text_value if ascending else tuple(-ord(char) for char in text_value)
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


def _signing_window(
    *,
    rows: Sequence[Contract],
    legacy_branch_active: bool,
    signing_date_start: date | None,
    signing_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
):
    if not rows:
        return None
    if legacy_branch_active:
        start_bound, end_bound = signing_date_start, signing_date_end
    else:
        start_bound, end_bound = extract_board_date_bounds(filters, "signing_date")
    window = resolve_board_trend_window(today=today, start_bound=start_bound, end_bound=end_bound)
    return None if window.empty else window


def _trends(
    rows: Sequence[Contract],
    *,
    legacy_branch_active: bool,
    signing_date_start: date | None,
    signing_date_end: date | None,
    filters: Sequence[FilterCondition] | None,
    today: date,
) -> list[ContractBoardTrendPoint]:
    window = _signing_window(
        rows=rows,
        legacy_branch_active=legacy_branch_active,
        signing_date_start=signing_date_start,
        signing_date_end=signing_date_end,
        filters=filters,
        today=today,
    )
    if window is None:
        return []
    counts = {month: 0 for month in window.months}
    amounts = {month: Decimal("0") for month in window.months}
    for row in rows:
        event_day = row.signing_date if isinstance(row.signing_date, date) else None
        if event_day is None or not window.event_start <= event_day <= window.event_end:
            continue
        key = month_key(event_day)
        counts[key] += 1
        amounts[key] += Decimal(str(row.total_amount or 0))
    return [
        ContractBoardTrendPoint(date=month, count=counts[month], amount=money_string(amounts[month]))
        for month in window.months
    ]


def _customer_map(db: Session, team_id: int, rows: Sequence[Contract]) -> dict[int, Customer]:
    customer_ids = {int(row.customer_id) for row in rows if row.customer_id}
    if not customer_ids:
        return {}
    loaded = db.query(Customer).filter(Customer.team_id == team_id, Customer.id.in_(customer_ids)).all()
    return {int(customer.id): customer for customer in loaded}


def _opportunity_map(db: Session, team_id: int, rows: Sequence[Contract]) -> dict[int, Opportunity]:
    opportunity_ids = {int(row.opportunity_id) for row in rows if row.opportunity_id}
    if not opportunity_ids:
        return {}
    loaded = db.query(Opportunity).filter(
        Opportunity.team_id == team_id,
        Opportunity.id.in_(opportunity_ids),
    ).all()
    return {int(opportunity.id): opportunity for opportunity in loaded}


def _owner_map(db: Session, rows: Sequence[Contract]) -> dict[str, BoardOwner]:
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


def _license_facts(
    db: Session,
    rows: Sequence[Contract],
) -> dict[int, tuple[int | None, date | None]]:
    if not rows:
        return {}
    contract_ids = [int(row.id) for row in rows]
    authorized_users = latest_official_issued_license(LicenseApplication.authorized_users)
    expiry_date = latest_official_issued_license(LicenseApplication.expiry_date)
    loaded = db.execute(
        select(
            Contract.id,
            func.coalesce(authorized_users, Contract.user_count),
            expiry_date,
        ).where(Contract.id.in_(contract_ids))
    ).all()
    return {
        int(contract_id): (None if users is None else int(users), expiry)
        for contract_id, users, expiry in loaded
    }


def _pending_approval_roles(
    db: Session,
    team_id: int,
    rows: Sequence[Contract],
) -> dict[int, str | None]:
    pending_ids = [int(row.id) for row in rows if _column_key(row) == "PENDING_REVIEW"]
    if not pending_ids:
        return {}
    loaded = (
        db.query(Approval)
        .options(selectinload(Approval.current_node))
        .filter(
            Approval.team_id == team_id,
            Approval.business_type == BusinessType.CONTRACT,
            Approval.business_id.in_(pending_ids),
            Approval.status == ApprovalStatus.PENDING,
        )
        .all()
    )
    roles: dict[int, str | None] = {}
    for approval in loaded:
        if approval.business_id is None or approval.current_node is None:
            continue
        roles[int(approval.business_id)] = approval.current_node.approve_role
    return roles


def _date_text(value: date | datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None
