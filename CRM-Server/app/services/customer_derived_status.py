"""客户派生状态:由公海标记 + 名下业务旅程读时推导,不落库。

规则(自上而下,命中即停):

1. 公海(Customer.status == 3)→ PUBLIC_POOL
2. 存在进行中旅程(ACTIVE,或 WON 未闭环)→ 无成交史 FOLLOWING / 有成交史 REPURCHASING,
   stage_hint = 阶段最深进行中旅程的「采购类型 · 看板阶段」
3. 存在闭环旅程(COMPLETED)且无进行中 → WON
4. 旅程全输单,或人工流失(Customer.status == 2 且无成交史)→ LOST
5. 名下无任何旅程 → NOT_STARTED
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import ColumnElement, case, exists, select

from app.models.customer import Customer
from app.models.customer import CustomerStatus as LegacyCustomerStatus
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.opportunity import Opportunity
from app.services.deal_journey_stage import (
    BOARD_STAGE_LABELS,
    BoardStageKey,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    infer_board_stage,
    load_contract_summaries,
    load_invoice_summaries,
    load_payment_summaries,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session


class CustomerLike(Protocol):
    status: int


class CustomerDerivedStatus(StrEnum):
    NOT_STARTED = "not_started"
    FOLLOWING = "following"
    REPURCHASING = "repurchasing"
    WON = "won"
    LOST = "lost"
    PUBLIC_POOL = "public_pool"


CUSTOMER_DERIVED_STATUS_LABELS: dict[CustomerDerivedStatus, str] = {
    CustomerDerivedStatus.NOT_STARTED: "未启动",
    CustomerDerivedStatus.FOLLOWING: "跟进中",
    CustomerDerivedStatus.REPURCHASING: "复购中",
    CustomerDerivedStatus.WON: "已成交",
    CustomerDerivedStatus.LOST: "已流失",
    CustomerDerivedStatus.PUBLIC_POOL: "公海",
}

PURCHASE_TYPE_LABELS: dict[str, str] = {
    "NEW": "新购",
    "RENEWAL": "续购",
    "EXPANSION": "增购",
}

_STAGE_RANK: dict[BoardStageKey, int] = {
    stage: rank
    for rank, stage in enumerate(
        [
            "early_communication",
            "active_progress",
            "closing_soon",
            "contract_processing",
            "payment_processing",
            "invoice_processing",
            "completed",
            "lost",
        ]
    )
}

_EMPTY_CONTRACT = BusinessJourneyContractSummary(count=0, signed_count=0, amount=0)
_EMPTY_PAYMENT = BusinessJourneyPaymentSummary(
    plan_count=0, record_count=0, planned_amount=0, paid_amount=0, remaining_amount=0
)
_EMPTY_INVOICE = BusinessJourneyInvoiceSummary(
    application_count=0, issued_count=0, applied_amount=0, issued_amount=0
)


def stage_rank(stage: BoardStageKey) -> int:
    return _STAGE_RANK[stage]


@dataclass
class SimpleJourneyView:
    status: str
    stage: BoardStageKey
    purchase_type: str


@dataclass
class DerivedCustomerStatus:
    status: CustomerDerivedStatus
    stage_hint: str = ""


def derive_customer_status(
    customer: CustomerLike, journeys: Iterable[SimpleJourneyView]
) -> DerivedCustomerStatus:
    """customer: Customer ORM 行;journeys: 名下旅程视图列表。"""
    legacy_status = int(customer.status)

    # 1. 公海:所有权状态优先于一切旅程状态
    if legacy_status == LegacyCustomerStatus.INACTIVE.value:
        return DerivedCustomerStatus(CustomerDerivedStatus.PUBLIC_POOL)

    active = [j for j in journeys if j.status in (DealJourneyStatus.ACTIVE, DealJourneyStatus.WON)]
    has_closed = any(j.status == DealJourneyStatus.COMPLETED for j in journeys)

    # 2. 进行中旅程:老客户复购 vs 首单跟进(WON 未闭环仍算进行中)
    if active:
        deepest = max(active, key=lambda j: stage_rank(j.stage))
        status = (
            CustomerDerivedStatus.REPURCHASING if has_closed else CustomerDerivedStatus.FOLLOWING
        )
        return DerivedCustomerStatus(status, _format_stage_hint(deepest))

    # 3. 历史成交(且无进行中)→ 已成交;人工流失不遮盖成交事实
    if has_closed:
        return DerivedCustomerStatus(CustomerDerivedStatus.WON)

    # 4. 已流失:旅程全输单,或人工标记流失(无成交史时)
    if any(j.status == DealJourneyStatus.LOST for j in journeys):
        return DerivedCustomerStatus(CustomerDerivedStatus.LOST)
    if legacy_status == LegacyCustomerStatus.LOST.value:
        return DerivedCustomerStatus(CustomerDerivedStatus.LOST)

    # 5. 无任何旅程 → 未启动
    return DerivedCustomerStatus(CustomerDerivedStatus.NOT_STARTED)


def _format_stage_hint(journey: SimpleJourneyView) -> str:
    purchase_label = PURCHASE_TYPE_LABELS.get(journey.purchase_type, "新购")
    stage_label = BOARD_STAGE_LABELS.get(journey.stage, journey.stage)
    return f"{purchase_label} · {stage_label}"


def load_customer_journey_views(
    db: Session, team_id: int, customer_ids: list[int]
) -> dict[int, list[SimpleJourneyView]]:
    """批量加载客户旅程视图:推导看板阶段所需的商机赢率 + 合同/回款/发票摘要。

    返回 {customer_id: [SimpleJourneyView]}。
    """
    if not customer_ids:
        return {}

    journeys = (
        db.query(CustomerDealJourney)
        .filter(
            CustomerDealJourney.team_id == team_id,
            CustomerDealJourney.customer_id.in_(customer_ids),
        )
        .all()
    )
    if not journeys:
        return {}

    journey_ids = [int(j.id) for j in journeys]
    opportunity_ids = [int(j.primary_opportunity_id) for j in journeys if j.primary_opportunity_id]
    opportunities = (
        {int(o.id): o for o in db.query(Opportunity).filter(Opportunity.id.in_(opportunity_ids)).all()}
        if opportunity_ids
        else {}
    )
    contracts = load_contract_summaries(db, team_id, journey_ids)
    payments = load_payment_summaries(db, team_id, journey_ids)
    invoices = load_invoice_summaries(db, team_id, journey_ids)

    views_by_customer: dict[int, list[SimpleJourneyView]] = {}
    for journey in journeys:
        opportunity = (
            opportunities.get(int(journey.primary_opportunity_id))
            if journey.primary_opportunity_id
            else None
        )
        stage = infer_board_stage(
            journey,
            opportunity,
            contracts.get(int(journey.id), _EMPTY_CONTRACT),
            payments.get(int(journey.id), _EMPTY_PAYMENT),
            invoices.get(int(journey.id), _EMPTY_INVOICE),
        )
        purchase_type = opportunity.purchase_type if opportunity is not None else "NEW"
        views_by_customer.setdefault(int(journey.customer_id), []).append(
            SimpleJourneyView(status=journey.status, stage=stage, purchase_type=purchase_type)
        )
    return views_by_customer


def derive_customer_statuses_for_list(
    db: Session,
    team_id: int,
    customers: list[CustomerLike],
) -> dict[int, DerivedCustomerStatus]:
    """列表批量派生:返回 {customer_id: DerivedCustomerStatus}。"""
    customer_ids = [int(c.id) for c in customers]  # type: ignore[attr-defined]
    views = load_customer_journey_views(db, team_id, customer_ids)
    return {
        int(c.id): derive_customer_status(c, views.get(int(c.id), []))  # type: ignore[attr-defined]
        for c in customers
    }


def derived_status_expression() -> ColumnElement[Any]:
    """派生大类 SQL 表达式:与 derive_customer_status 规则一致(大类仅依赖旅程存在性,不依赖阶段深浅)。

    用于列表筛选与排序;journeys 通过 team 隔离,子查询按 customer 关联。
    """
    active_journey = exists(
        select(CustomerDealJourney.id).where(
            CustomerDealJourney.team_id == Customer.team_id,
            CustomerDealJourney.customer_id == Customer.id,
            CustomerDealJourney.status.in_([DealJourneyStatus.ACTIVE, DealJourneyStatus.WON]),
        )
    )
    completed_journey = exists(
        select(CustomerDealJourney.id).where(
            CustomerDealJourney.team_id == Customer.team_id,
            CustomerDealJourney.customer_id == Customer.id,
            CustomerDealJourney.status == DealJourneyStatus.COMPLETED,
        )
    )
    lost_journey = exists(
        select(CustomerDealJourney.id).where(
            CustomerDealJourney.team_id == Customer.team_id,
            CustomerDealJourney.customer_id == Customer.id,
            CustomerDealJourney.status == DealJourneyStatus.LOST,
        )
    )
    any_journey = exists(
        select(CustomerDealJourney.id).where(
            CustomerDealJourney.team_id == Customer.team_id,
            CustomerDealJourney.customer_id == Customer.id,
        )
    )
    return case(
        (Customer.status == LegacyCustomerStatus.INACTIVE.value, CustomerDerivedStatus.PUBLIC_POOL.value),
        (active_journey, case(
            (completed_journey, CustomerDerivedStatus.REPURCHASING.value),
            else_=CustomerDerivedStatus.FOLLOWING.value,
        )),
        (completed_journey, CustomerDerivedStatus.WON.value),
        (lost_journey | (Customer.status == LegacyCustomerStatus.LOST.value), CustomerDerivedStatus.LOST.value),
        (any_journey, CustomerDerivedStatus.NOT_STARTED.value),
        else_=CustomerDerivedStatus.NOT_STARTED.value,
    )


def derived_status_predicate(
    condition: Any,  # noqa: ANN401
    field: Any,  # noqa: ANN401
    context: Any,  # noqa: ANN401, ARG001
    parsed_value: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """list_query 谓词构建器:按派生大类筛选。"""
    from app.core.list_query.errors import ListQueryError  # 延迟导入避免 catalogs 循环
    if parsed_value is None:
        return None
    values = parsed_value if isinstance(parsed_value, list) else [parsed_value]
    target = [v.value if isinstance(v, CustomerDerivedStatus) else str(v) for v in values]
    expression = derived_status_expression()
    op = condition.op
    if op in ("eq", "in", "contains"):
        return expression.in_(target)
    if op in ("neq", "not_in", "not_contains"):
        return expression.notin_(target)
    raise ListQueryError(f"字段 {field.key} 不支持操作符 {op}")


__all__ = [
    "CUSTOMER_DERIVED_STATUS_LABELS",
    "CustomerDerivedStatus",
    "DerivedCustomerStatus",
    "SimpleJourneyView",
    "derive_customer_status",
    "derive_customer_statuses_for_list",
    "derived_status_expression",
    "derived_status_predicate",
    "load_customer_journey_views",
    "stage_rank",
]
