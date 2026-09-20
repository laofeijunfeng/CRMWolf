from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import and_, case, exists, false, func, or_
from sqlalchemy.orm import Query, Session

from app.core.list_query.catalogs.business_journeys import (
    BUSINESS_JOURNEYS_LIST_QUERY_CATALOG,
)
from app.core.list_query.engine import apply_filters, apply_search, apply_sorts
from app.core.list_query.errors import ListQueryError
from app.core.list_query.types import FilterCondition, ListQueryContext, SortCondition
from app.crud.customer_member import ACCESS_LEVEL_RANK
from app.models.customer import Customer, CustomerMember
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.opportunity import Opportunity
from app.models.product import Product
from app.models.user import User
from app.schemas.customer import OwnerOption
from app.services.deal_journey_stage import (
    BoardStageKey,
    BusinessJourneyContractSummary,
    BusinessJourneyInvoiceSummary,
    BusinessJourneyPaymentSummary,
    infer_board_stage,
    load_contract_summaries,
    load_invoice_summaries,
    load_payment_summaries,
)

JourneyScopeTab = Literal["all", "active", "completed", "lost"]
_STAGE_FILTER_OPS = frozenset({"eq", "neq", "in", "not_in"})
_VIEW_ACCESS_LEVELS = tuple(
    level for level, rank in ACCESS_LEVEL_RANK.items() if rank >= ACCESS_LEVEL_RANK["VIEW"]
)


@dataclass(frozen=True)
class BusinessJourneyQueryRequest:
    team_id: int
    user_id: int
    permission_codes: frozenset[str] = frozenset()
    tab: JourneyScopeTab = "all"
    search: str | None = None
    filters: list[FilterCondition] | None = None
    sorts: list[SortCondition] | None = None


@dataclass(frozen=True)
class BusinessJourneyQueryRow:
    journey: CustomerDealJourney
    customer: Customer
    opportunity: Opportunity | None
    owner_id: str | None
    stage: BoardStageKey
    contract_summary: BusinessJourneyContractSummary
    payment_summary: BusinessJourneyPaymentSummary
    invoice_summary: BusinessJourneyInvoiceSummary


class BusinessJourneyQueryService:
    def query_base(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
    ) -> Query:
        query = (
            db.query(CustomerDealJourney, Customer, Opportunity)
            .join(
                Customer,
                and_(
                    Customer.id == CustomerDealJourney.customer_id,
                    Customer.team_id == CustomerDealJourney.team_id,
                ),
            )
            .outerjoin(
                Opportunity,
                and_(
                    Opportunity.id == CustomerDealJourney.primary_opportunity_id,
                    Opportunity.team_id == CustomerDealJourney.team_id,
                ),
            )
            .outerjoin(
                Product,
                and_(
                    Product.id == Opportunity.product_id,
                    Product.team_id == CustomerDealJourney.team_id,
                ),
            )
            .filter(
                CustomerDealJourney.team_id == request.team_id,
                CustomerDealJourney.status != DealJourneyStatus.ARCHIVED,
            )
        )
        query = self._apply_visibility(query, request=request)
        query = self._apply_tab(query, tab=request.tab)

        context = ListQueryContext(
            db=db,
            team_id=request.team_id,
            current_user_id=str(request.user_id),
        )
        stage_filters, ordinary_filters = self._split_stage_filters(request.filters or [])
        query = apply_search(
            query,
            BUSINESS_JOURNEYS_LIST_QUERY_CATALOG,
            request.search,
            context=context,
        )
        query = apply_filters(
            query,
            BUSINESS_JOURNEYS_LIST_QUERY_CATALOG,
            ordinary_filters,
            context=context,
        )
        if stage_filters:
            query = self._apply_stage_filters(
                db,
                query=query,
                request=request,
                filters=stage_filters,
            )
        return query

    def paginate(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
        skip: int,
        limit: int,
    ) -> tuple[list[BusinessJourneyQueryRow], int]:
        query = self.query_base(db, request=request)
        total = query.order_by(None).count()
        ordered = self._apply_order(query, db=db, request=request)
        raw_rows = ordered.offset(skip).limit(limit).all()
        return self._hydrate_rows(db, request.team_id, raw_rows), total

    def list_for_board(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
        limit: int,
    ) -> tuple[list[BusinessJourneyQueryRow], int, bool]:
        rows, total = self.paginate(
            db,
            request=request,
            skip=0,
            limit=limit,
        )
        return rows, total, total > len(rows)

    def get_by_public_id(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
        journey_public_id: str,
    ) -> BusinessJourneyQueryRow | None:
        raw_row = (
            self.query_base(db, request=request)
            .filter(CustomerDealJourney.public_id == journey_public_id)
            .one_or_none()
        )
        if raw_row is None:
            return None
        return self._hydrate_rows(db, request.team_id, [raw_row])[0]

    def owner_options(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
    ) -> list[OwnerOption]:
        owner_expression = func.coalesce(Opportunity.owner_id, Customer.owner_id)
        owner_rows = (
            self.query_base(db, request=request)
            .order_by(None)
            .with_entities(owner_expression)
            .filter(owner_expression.isnot(None))
            .distinct()
            .all()
        )
        owner_ids = {str(owner_id) for (owner_id,) in owner_rows if owner_id}
        numeric_ids = [int(owner_id) for owner_id in owner_ids if owner_id.isdigit()]
        users = db.query(User).filter(User.id.in_(numeric_ids)).all() if numeric_ids else []
        names = {str(user.id): user.name for user in users}
        current_user_id = str(request.user_id)
        options = [
            OwnerOption(
                id=owner_id,
                name=(
                    f"{names.get(owner_id, owner_id)}（我）"
                    if owner_id == current_user_id
                    else names.get(owner_id, owner_id)
                ),
                is_me=owner_id == current_user_id,
            )
            for owner_id in owner_ids
        ]
        return sorted(options, key=lambda option: (not option.is_me, option.name, option.id))

    @staticmethod
    def _apply_visibility(query: Query, *, request: BusinessJourneyQueryRequest) -> Query:
        permissions = request.permission_codes
        if "customer:view:all" in permissions or "opportunity:view:all" in permissions:
            return query

        user_id = str(request.user_id)
        clauses = []
        if "customer:view:own" in permissions:
            clauses.append(Customer.owner_id == user_id)
        if "opportunity:view:own" in permissions:
            clauses.append(Opportunity.owner_id == user_id)

        member_access = exists().where(
            CustomerMember.team_id == request.team_id,
            CustomerMember.customer_id == Customer.id,
            CustomerMember.user_id == user_id,
            CustomerMember.is_active.is_(True),
            CustomerMember.access_level.in_(_VIEW_ACCESS_LEVELS),
        )
        clauses.append(member_access)
        return query.filter(or_(*clauses))

    @staticmethod
    def _apply_tab(query: Query, *, tab: JourneyScopeTab) -> Query:
        if tab == "active":
            return query.filter(
                CustomerDealJourney.status.in_(
                    [DealJourneyStatus.ACTIVE, DealJourneyStatus.WON]
                )
            )
        if tab == "completed":
            return query.filter(CustomerDealJourney.status == DealJourneyStatus.COMPLETED)
        if tab == "lost":
            return query.filter(CustomerDealJourney.status == DealJourneyStatus.LOST)
        if tab != "all":
            raise ListQueryError(f"未知业务旅程范围: {tab}")
        return query

    @staticmethod
    def _split_stage_filters(
        filters: list[FilterCondition],
    ) -> tuple[list[FilterCondition], list[FilterCondition]]:
        stage_filters: list[FilterCondition] = []
        ordinary_filters: list[FilterCondition] = []
        for condition in filters:
            if condition.field == "stage":
                if condition.op not in _STAGE_FILTER_OPS:
                    raise ListQueryError(
                        f"字段 stage 不支持操作符 {condition.op}"
                    )
                stage_filters.append(condition)
            else:
                ordinary_filters.append(condition)
        return stage_filters, ordinary_filters

    def _apply_stage_filters(
        self,
        db: Session,
        *,
        query: Query,
        request: BusinessJourneyQueryRequest,
        filters: list[FilterCondition],
    ) -> Query:
        candidate_ids = [
            int(journey_id)
            for (journey_id,) in query.order_by(None)
            .with_entities(CustomerDealJourney.id)
            .all()
        ]
        if not candidate_ids:
            return query.filter(false())

        journey_rows = (
            db.query(CustomerDealJourney, Opportunity)
            .outerjoin(
                Opportunity,
                and_(
                    Opportunity.id == CustomerDealJourney.primary_opportunity_id,
                    Opportunity.team_id == request.team_id,
                ),
            )
            .filter(
                CustomerDealJourney.team_id == request.team_id,
                CustomerDealJourney.id.in_(candidate_ids),
            )
            .all()
        )
        contract_map = load_contract_summaries(db, request.team_id, candidate_ids)
        payment_map = load_payment_summaries(db, request.team_id, candidate_ids)
        invoice_map = load_invoice_summaries(db, request.team_id, candidate_ids)
        matching_ids = []
        for journey, opportunity in journey_rows:
            journey_id = int(journey.id)
            stage = infer_board_stage(
                journey,
                opportunity,
                contract_map.get(journey_id, self._empty_contract()),
                payment_map.get(journey_id, self._empty_payment()),
                invoice_map.get(journey_id, self._empty_invoice()),
            )
            if all(self._stage_matches(stage, condition) for condition in filters):
                matching_ids.append(journey_id)

        if not matching_ids:
            return query.filter(false())
        return query.filter(CustomerDealJourney.id.in_(matching_ids))

    @staticmethod
    def _stage_matches(stage: BoardStageKey, condition: FilterCondition) -> bool:
        raw_values = condition.value if isinstance(condition.value, list) else [condition.value]
        values = {str(value).strip() for value in raw_values if value is not None}
        if condition.op in {"eq", "in"}:
            return stage in values
        if condition.op in {"neq", "not_in"}:
            return stage not in values
        raise ListQueryError(f"字段 stage 不支持操作符 {condition.op}")

    @staticmethod
    def _apply_order(
        query: Query,
        *,
        db: Session,
        request: BusinessJourneyQueryRequest,
    ) -> Query:
        if request.sorts:
            context = ListQueryContext(
                db=db,
                team_id=request.team_id,
                current_user_id=str(request.user_id),
            )
            query = apply_sorts(
                query.order_by(None),
                BUSINESS_JOURNEYS_LIST_QUERY_CATALOG,
                request.sorts,
                context=context,
            )
            return query.order_by(CustomerDealJourney.id.desc())
        return query.order_by(
            case(
                (CustomerDealJourney.last_event_at.is_(None), 1),
                else_=0,
            ).asc(),
            CustomerDealJourney.last_event_at.desc(),
            CustomerDealJourney.id.desc(),
        )

    def _hydrate_rows(
        self,
        db: Session,
        team_id: int,
        raw_rows: list[tuple[CustomerDealJourney, Customer, Opportunity | None]],
    ) -> list[BusinessJourneyQueryRow]:
        journey_ids = [int(journey.id) for journey, _, _ in raw_rows]
        contract_map = load_contract_summaries(db, team_id, journey_ids)
        payment_map = load_payment_summaries(db, team_id, journey_ids)
        invoice_map = load_invoice_summaries(db, team_id, journey_ids)
        rows: list[BusinessJourneyQueryRow] = []
        for journey, customer, opportunity in raw_rows:
            journey_id = int(journey.id)
            contract_summary = contract_map.get(journey_id, self._empty_contract())
            payment_summary = payment_map.get(journey_id, self._empty_payment())
            invoice_summary = invoice_map.get(journey_id, self._empty_invoice())
            rows.append(
                BusinessJourneyQueryRow(
                    journey=journey,
                    customer=customer,
                    opportunity=opportunity,
                    owner_id=(
                        opportunity.owner_id
                        if opportunity is not None and opportunity.owner_id
                        else customer.owner_id
                    ),
                    stage=infer_board_stage(
                        journey,
                        opportunity,
                        contract_summary,
                        payment_summary,
                        invoice_summary,
                    ),
                    contract_summary=contract_summary,
                    payment_summary=payment_summary,
                    invoice_summary=invoice_summary,
                )
            )
        return rows

    @staticmethod
    def _empty_contract() -> BusinessJourneyContractSummary:
        return BusinessJourneyContractSummary(count=0, signed_count=0, amount=0)

    @staticmethod
    def _empty_payment() -> BusinessJourneyPaymentSummary:
        return BusinessJourneyPaymentSummary(
            plan_count=0,
            record_count=0,
            planned_amount=0,
            paid_amount=0,
            remaining_amount=0,
        )

    @staticmethod
    def _empty_invoice() -> BusinessJourneyInvoiceSummary:
        return BusinessJourneyInvoiceSummary(
            application_count=0,
            issued_count=0,
            applied_amount=0,
            issued_amount=0,
        )


business_journey_query_service = BusinessJourneyQueryService()


__all__ = [
    "BusinessJourneyQueryRequest",
    "BusinessJourneyQueryRow",
    "BusinessJourneyQueryService",
    "JourneyScopeTab",
    "business_journey_query_service",
]
