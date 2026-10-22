from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
from app.schemas.deal_journey import (
    BusinessJourneyChartCard,
    BusinessJourneyChartPreview,
    BusinessJourneyChartResponse,
    BusinessJourneyChartSegment,
    BusinessJourneyChartSegmentItem,
    BusinessJourneyChartSegmentResponse,
    BusinessJourneyChartSummary,
    ChartCardKey,
)
from app.services.deal_journey_stage import (
    BOARD_COLUMNS,
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


    def list_visible(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
    ) -> list[BusinessJourneyQueryRow]:
        raw_rows = self.query_base(db, request=request).order_by(CustomerDealJourney.id.asc()).all()
        return self._hydrate_rows(db, request.team_id, raw_rows)

    def chart(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
        today: date,
    ) -> BusinessJourneyChartResponse:
        rows = self.list_visible(db, request=request)
        product_names = self._product_names(db, request.team_id, rows)
        return BusinessJourneyChartResponse(
            summary=BusinessJourneyChartSummary(
                total_count=len(rows),
                total_amount=sum(_opportunity_amount(row.opportunity) for row in rows),
            ),
            cards=[
                self._stage_card(rows),
                self._purchase_card(rows),
                self._amount_card(rows),
                self._product_card(rows, product_names),
                self._activity_card(rows, today=today),
                self._closing_card(rows, today=today),
            ],
        )

    def chart_segment(
        self,
        db: Session,
        *,
        request: BusinessJourneyQueryRequest,
        card: ChartCardKey,
        segment: str,
        today: date,
        skip: int,
        limit: int,
    ) -> BusinessJourneyChartSegmentResponse:
        rows = self.list_visible(db, request=request)
        product_names = self._product_names(db, request.team_id, rows)
        selected, label = self._rows_for_segment(
            rows,
            product_names=product_names,
            card=card,
            segment=segment,
            today=today,
        )
        ordered = sorted(selected, key=_dialog_order)
        page = ordered[skip:skip + limit]
        return BusinessJourneyChartSegmentResponse(
            card=card,
            segment=segment,
            label=label,
            total=len(ordered),
            items=[
                BusinessJourneyChartSegmentItem(
                    public_id=row.journey.public_id,
                    customer_id=row.customer.public_id,
                    name=row.journey.name,
                    customer_name=row.customer.account_name,
                    amount=_opportunity_amount(row.opportunity),
                )
                for row in page
            ],
        )

    @staticmethod
    def _product_names(
        db: Session,
        team_id: int,
        rows: list[BusinessJourneyQueryRow],
    ) -> dict[int, str]:
        product_ids = {
            int(row.opportunity.product_id)
            for row in rows
            if row.opportunity is not None and row.opportunity.product_id is not None
        }
        if not product_ids:
            return {}
        products = db.query(Product).filter(Product.team_id == team_id, Product.id.in_(product_ids)).all()
        return {int(product.id): str(product.name) for product in products if product.name}

    def _rows_for_segment(
        self,
        rows: list[BusinessJourneyQueryRow],
        *,
        product_names: dict[int, str],
        card: ChartCardKey,
        segment: str,
        today: date,
    ) -> tuple[list[BusinessJourneyQueryRow], str]:
        grouped = {
            item.key: item
            for item in self._card_for(card, rows, product_names=product_names, today=today).segments
        }
        if segment not in grouped:
            raise ListQueryError("图表分段不存在")
        selected_rows = self._group_rows(rows, product_names=product_names, card=card, today=today)[segment]
        return selected_rows, grouped[segment].label

    def _card_for(
        self,
        card: ChartCardKey,
        rows: list[BusinessJourneyQueryRow],
        *,
        product_names: dict[int, str],
        today: date,
    ) -> BusinessJourneyChartCard:
        if card == "stage":
            return self._stage_card(rows)
        if card == "purchase_type":
            return self._purchase_card(rows)
        if card == "amount_band":
            return self._amount_card(rows)
        if card == "product":
            return self._product_card(rows, product_names)
        if card == "recent_activity":
            return self._activity_card(rows, today=today)
        return self._closing_card(rows, today=today)

    def _group_rows(
        self,
        rows: list[BusinessJourneyQueryRow],
        *,
        product_names: dict[int, str],
        card: ChartCardKey,
        today: date,
    ) -> dict[str, list[BusinessJourneyQueryRow]]:
        grouped: dict[str, list[BusinessJourneyQueryRow]]
        if card == "stage":
            grouped = {key: [] for key, _, _ in BOARD_COLUMNS}
            for row in rows:
                grouped[row.stage].append(row)
            return grouped
        if card == "purchase_type":
            grouped = {key: [] for key, _ in _PURCHASE_TYPES}
            grouped["unset"] = []
            for row in rows:
                raw_type = row.opportunity.purchase_type if row.opportunity is not None else None
                purchase_type = str(raw_type) if raw_type is not None else ""
                grouped[purchase_type if purchase_type in grouped else "unset"].append(row)
            return grouped
        if card == "amount_band":
            grouped = {key: [] for key, _, _, _ in _AMOUNT_BANDS}
            for row in rows:
                amount = _opportunity_amount(row.opportunity)
                for key, _, lower, upper in _AMOUNT_BANDS:
                    if amount >= lower and (upper is None or amount < upper):
                        grouped[key].append(row)
                        break
            return grouped
        if card == "product":
            return self._product_groups(rows, product_names)
        if card == "recent_activity":
            grouped = {key: [] for key, _ in _ACTIVITY_BANDS}
            for row in rows:
                event_at = row.journey.last_event_at if isinstance(row.journey.last_event_at, datetime) else None
                grouped[self._activity_key(event_at, today)].append(row)
            return grouped
        months = [_add_months(date(today.year, today.month, 1), offset) for offset in range(6)]
        grouped = {month.strftime("%Y-%m"): [] for month in months}
        grouped["unscheduled"] = []
        for row in rows:
            closing = row.opportunity.expected_closing_date if row.opportunity is not None else None
            month = date(closing.year, closing.month, 1) if closing is not None else None
            key = month.strftime("%Y-%m") if month in months else "unscheduled"
            grouped[key].append(row)
        return grouped

    @staticmethod
    def _product_groups(
        rows: list[BusinessJourneyQueryRow],
        product_names: dict[int, str],
    ) -> dict[str, list[BusinessJourneyQueryRow]]:
        named: dict[str, list[BusinessJourneyQueryRow]] = {}
        unset: list[BusinessJourneyQueryRow] = []
        for row in rows:
            product_id = row.opportunity.product_id if row.opportunity is not None else None
            name = product_names.get(int(product_id)) if product_id is not None else None
            if name is None or name.strip() == "":
                unset.append(row)
            else:
                named.setdefault(name, []).append(row)
        ranking = sorted(
            named,
            key=lambda name: (
                -len(named[name]),
                -sum(_opportunity_amount(row.opportunity) for row in named[name]),
                name,
            ),
        )
        grouped = {name: named[name] for name in ranking[:8]}
        grouped["other"] = [row for name in ranking[8:] for row in named[name]]
        grouped["unset"] = unset
        return grouped

    @staticmethod
    def _activity_key(value: datetime | None, today: date) -> str:
        if value is None:
            return "none"
        elapsed = (today - value.date()).days
        if elapsed <= 7:
            return "within_7"
        if elapsed <= 30:
            return "8_to_30"
        return "over_30"

    @staticmethod
    def _stage_card(rows: list[BusinessJourneyQueryRow]) -> BusinessJourneyChartCard:
        grouped: dict[str, list[BusinessJourneyQueryRow]] = {key: [] for key, _, _ in BOARD_COLUMNS}
        for row in rows:
            grouped[row.stage].append(row)
        return _card(
            "stage",
            "阶段",
            "八个看板阶段都在。",
            "horizontal_bar",
            [_segment(key, title, grouped[key]) for key, title, _ in BOARD_COLUMNS],
        )

    @staticmethod
    def _purchase_card(rows: list[BusinessJourneyQueryRow]) -> BusinessJourneyChartCard:
        grouped: dict[str, list[BusinessJourneyQueryRow]] = {key: [] for key, _ in _PURCHASE_TYPES}
        grouped["unset"] = []
        for row in rows:
            raw_type = row.opportunity.purchase_type if row.opportunity is not None else None
            purchase_type = str(raw_type) if raw_type is not None else ""
            grouped[purchase_type if purchase_type in grouped else "unset"].append(row)
        return _card(
            "purchase_type",
            "采购类型",
            "按金额占比。没填的单独列出。",
            "pie",
            [_segment(key, label, grouped[key]) for key, label in _PURCHASE_TYPES]
            + [_segment("unset", "未填写", grouped["unset"])],
        )

    @staticmethod
    def _amount_card(rows: list[BusinessJourneyQueryRow]) -> BusinessJourneyChartCard:
        grouped: dict[str, list[BusinessJourneyQueryRow]] = {key: [] for key, _, _, _ in _AMOUNT_BANDS}
        for row in rows:
            amount = _opportunity_amount(row.opportunity)
            for key, _, lower, upper in _AMOUNT_BANDS:
                if amount >= lower and (upper is None or amount < upper):
                    grouped[key].append(row)
                    break
        return _card(
            "amount_band",
            "金额档",
            "看是很多小单，还是几笔大单。",
            "horizontal_bar",
            [_segment(key, label, grouped[key]) for key, label, _, _ in _AMOUNT_BANDS],
        )

    @staticmethod
    def _product_card(
        rows: list[BusinessJourneyQueryRow],
        product_names: dict[int, str],
    ) -> BusinessJourneyChartCard:
        grouped = BusinessJourneyQueryService._product_groups(rows, product_names)
        named = [
            _segment(name, name, grouped[name])
            for name in grouped
            if name not in {"other", "unset"}
        ]
        segments = [
            *named,
            _segment("other", "其他", grouped["other"]),
            _segment("unset", "未填写", grouped["unset"]),
        ]
        return _card(
            "product",
            "产品",
            "数量最多的 8 个，其余并进其他。",
            "horizontal_bar",
            segments,
        )

    @staticmethod
    def _activity_card(
        rows: list[BusinessJourneyQueryRow],
        *,
        today: date,
    ) -> BusinessJourneyChartCard:
        grouped: dict[str, list[BusinessJourneyQueryRow]] = {key: [] for key, _ in _ACTIVITY_BANDS}
        for row in rows:
            event_at = row.journey.last_event_at if isinstance(row.journey.last_event_at, datetime) else None
            grouped[BusinessJourneyQueryService._activity_key(event_at, today)].append(row)
        return _card(
            "recent_activity",
            "最近动态",
            "只看多久没动静，不提示该联系谁。",
            "horizontal_bar",
            [_segment(key, label, grouped[key]) for key, label in _ACTIVITY_BANDS],
        )

    @staticmethod
    def _closing_card(
        rows: list[BusinessJourneyQueryRow],
        *,
        today: date,
    ) -> BusinessJourneyChartCard:
        months = [_add_months(date(today.year, today.month, 1), offset) for offset in range(6)]
        grouped: dict[date, list[BusinessJourneyQueryRow]] = {month: [] for month in months}
        unscheduled: list[BusinessJourneyQueryRow] = []
        for row in rows:
            closing = row.opportunity.expected_closing_date if row.opportunity is not None else None
            month = date(closing.year, closing.month, 1) if isinstance(closing, date) else None
            if month is not None and month in grouped:
                grouped[month].append(row)
            else:
                unscheduled.append(row)
        return _card(
            "expected_closing",
            "预计成交",
            "本月起 6 个月。没填预计成交日的单独是未排期，不并进本月。",
            "vertical_bar",
            [_segment(month.strftime("%Y-%m"), f"{month.month}月", grouped[month]) for month in months]
            + [_segment("unscheduled", "未排期", unscheduled)],
        )

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


_PREVIEW_LIMIT = 8
_TEN_THOUSAND = 100_000.0
_AMOUNT_BANDS = (
    ("under_100k", "10 万以下", 0.0, _TEN_THOUSAND),
    ("100k_500k", "10–50 万", _TEN_THOUSAND, _TEN_THOUSAND * 5),
    ("500k_1m", "50–100 万", _TEN_THOUSAND * 5, _TEN_THOUSAND * 10),
    ("over_1m", "100 万以上", _TEN_THOUSAND * 10, None),
)
_PURCHASE_TYPES = (("NEW", "新购"), ("RENEWAL", "续购"), ("EXPANSION", "增购"))
_ACTIVITY_BANDS = (
    ("within_7", "7 天内"),
    ("8_to_30", "8–30 天"),
    ("over_30", "30 天以上"),
    ("none", "没有动态"),
)



def _dialog_order(row: BusinessJourneyQueryRow) -> tuple[float, str, str]:
    created = row.journey.created_time
    stamp = created.timestamp() if created is not None else 0
    return (-stamp, row.journey.name, row.journey.public_id)


def _opportunity_amount(opportunity: Opportunity | None) -> float:
    if opportunity is None or opportunity.total_amount is None:
        return 0.0
    return float(opportunity.total_amount)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    return date(value.year + month_index // 12, month_index % 12 + 1, 1)


def _segment(
    key: str,
    label: str,
    rows: list[BusinessJourneyQueryRow],
) -> BusinessJourneyChartSegment:
    ordered = sorted(rows, key=lambda row: (-_opportunity_amount(row.opportunity), row.journey.public_id))
    return BusinessJourneyChartSegment(
        key=key,
        label=label,
        count=len(rows),
        amount=sum(_opportunity_amount(row.opportunity) for row in rows),
        preview=[
            BusinessJourneyChartPreview(
                public_id=row.journey.public_id,
                customer_id=row.customer.public_id,
                name=row.journey.name,
                customer_name=row.customer.account_name,
                amount=_opportunity_amount(row.opportunity),
            )
            for row in ordered[:_PREVIEW_LIMIT]
        ],
    )


def _card(
    key: ChartCardKey,
    title: str,
    description: str,
    graphic: Literal["horizontal_bar", "pie", "vertical_bar"],
    segments: list[BusinessJourneyChartSegment],
) -> BusinessJourneyChartCard:
    return BusinessJourneyChartCard(
        key=key,
        title=title,
        description=description,
        graphic=graphic,
        segments=segments,
    )




business_journey_query_service = BusinessJourneyQueryService()


__all__ = [
    "BusinessJourneyQueryRequest",
    "BusinessJourneyQueryRow",
    "BusinessJourneyQueryService",
    "JourneyScopeTab",
    "business_journey_query_service",
]
