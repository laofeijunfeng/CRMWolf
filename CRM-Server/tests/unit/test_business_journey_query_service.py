"""Shared business-journey query service contract tests."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.approval_phase import ApprovalPhase
from app.core.database import Base
from app.core.list_query.errors import ListQueryError
from app.core.list_query.types import FilterCondition, SortCondition
from app.models.contract import Contract, ContractStatus, PaymentStatus
from app.models.customer import Contact, Customer, CustomerMember
from app.models.customer_identity_term import (
    CustomerIdentityTerm,
    CustomerIdentityTermSource,
    CustomerIdentityTermStatus,
    CustomerIdentityTermType,
)
from app.models.deal_journey import CustomerDealJourney, DealJourneyStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceTitle
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.product import Product
from app.models.user import User, UserStatus
from app.schemas.deal_journey import (
    BusinessJourneyBoardCard,
    BusinessJourneyBoardColumn,
    BusinessJourneyBoardResponse,
    BusinessJourneyBoardSummary,
)
from app.services.business_journey_query_service import (
    BusinessJourneyQueryRequest,
    BusinessJourneyQueryService,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Customer.__table__,
        CustomerMember.__table__,
        CustomerIdentityTerm.__table__,
        Contact.__table__,
        Product.__table__,
        Opportunity.__table__,
        CustomerDealJourney.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceTitle.__table__,
        InvoiceApplication.__table__,
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


service = BusinessJourneyQueryService()


def _request(
    *,
    user_id: int = 1,
    permission_codes: frozenset[str] = frozenset(
        {"customer:view:own", "opportunity:view:own"}
    ),
    tab: str = "all",
    search: str | None = None,
    filters: list[FilterCondition] | None = None,
    sorts: list[SortCondition] | None = None,
) -> BusinessJourneyQueryRequest:
    return BusinessJourneyQueryRequest(
        team_id=1,
        user_id=user_id,
        permission_codes=permission_codes,
        tab=tab,
        search=search,
        filters=filters,
        sorts=sorts,
    )


def _seed_query_case(db: Session) -> dict[str, CustomerDealJourney]:
    db.add_all(
        [
            User(id=1, email="one@example.com", name="User One", status=UserStatus.ACTIVE),
            User(id=2, email="two@example.com", name="User Two", status=UserStatus.ACTIVE),
            Product(team_id=1, code="HIFOX", name="Hifox", created_by="1"),
            Product(team_id=1, code="APIFOX", name="Apifox", created_by="1"),
        ]
    )
    db.flush()
    products = {product.name: product for product in db.query(Product).all()}
    base_time = datetime(2026, 9, 1, 9, 0, 0)

    definitions = [
        ("customer_owned", "1", "2", DealJourneyStatus.WON, "Hifox", Decimal("120"), 90),
        ("opportunity_owned", "2", "1", DealJourneyStatus.ACTIVE, "Hifox", Decimal("200"), 70),
        ("member_visible", "2", "2", DealJourneyStatus.ACTIVE, "Apifox", Decimal("300"), 40),
        ("foreign", "2", "2", DealJourneyStatus.ACTIVE, "Apifox", Decimal("400"), 20),
        ("no_opportunity", "1", None, DealJourneyStatus.ACTIVE, None, None, None),
        ("completed", "1", "1", DealJourneyStatus.COMPLETED, "Apifox", Decimal("500"), 100),
        ("lost", "1", "1", DealJourneyStatus.LOST, "Apifox", Decimal("600"), 10),
        ("archived", "1", "1", DealJourneyStatus.ARCHIVED, "Hifox", Decimal("700"), 10),
    ]
    seeded: dict[str, CustomerDealJourney] = {}
    opportunities: dict[str, Opportunity] = {}
    for index, (key, customer_owner, opportunity_owner, status, product_name, amount, win_probability) in enumerate(
        definitions
    ):
        customer = Customer(
            team_id=1,
            account_name=f"Customer {key}",
            city="Shanghai",
            owner_id=customer_owner,
            creator_id="1",
        )
        db.add(customer)
        db.flush()

        opportunity = None
        if opportunity_owner is not None:
            opportunity = Opportunity(
                team_id=1,
                opportunity_number=f"OPP-{index}",
                opportunity_name=f"Opportunity {key}",
                customer_id=customer.id,
                product_id=products[product_name].id if product_name else None,
                total_amount=(amount * 10 if key == "customer_owned" else amount),
                actual_amount=amount if key == "customer_owned" else None,
                user_count=10,
                unit_price=Decimal("10"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                purchase_type="NEW",
                expected_closing_date=date(2026, 12, 31),
                owner_id=opportunity_owner,
                creator_id="1",
                approval_phase=ApprovalPhase.APPROVED.value,
                created_time=base_time + timedelta(days=index),
                win_probability=win_probability or 0,
            )
            db.add(opportunity)
            db.flush()

        last_event_at = base_time + timedelta(days=20 - index)
        if key in {"customer_owned", "opportunity_owned"}:
            last_event_at = base_time + timedelta(days=30)
        journey = CustomerDealJourney(
            team_id=1,
            customer_id=customer.id,
            primary_opportunity_id=opportunity.id if opportunity else None,
            name=f"Journey {key}",
            status=status,
            started_at=base_time + timedelta(days=index),
            last_event_at=last_event_at,
        )
        db.add(journey)
        db.flush()
        if opportunity is not None:
            opportunity.deal_journey_id = journey.id
            opportunities[key] = opportunity
        seeded[key] = journey

    member_customer_id = seeded["member_visible"].customer_id
    db.add(
        CustomerMember(
            team_id=1,
            customer_id=member_customer_id,
            user_id="1",
            member_role="PRESALES",
            access_level="VIEW",
            created_by="2",
            is_active=True,
        )
    )
    customer_owned_customer = db.get(Customer, seeded["customer_owned"].customer_id)
    db.add(
        CustomerIdentityTerm(
            tenant_id=1,
            team_id=1,
            customer_id=customer_owned_customer.id,
            term="Hifox Alias",
            normalized_term="hifox alias",
            term_type=CustomerIdentityTermType.ALIAS,
            source=CustomerIdentityTermSource.HUMAN,
            confidence=1.0,
            status=CustomerIdentityTermStatus.ACTIVE,
        )
    )

    contracts: dict[str, Contract] = {}
    for key in ("customer_owned", "opportunity_owned", "member_visible"):
        opportunity = opportunities[key]
        contract = Contract(
            team_id=1,
            contract_number=f"CTR-{key}",
            contract_name=f"Contract {key}",
            customer_id=seeded[key].customer_id,
            opportunity_id=opportunity.id,
            deal_journey_id=seeded[key].id,
            user_count=10,
            total_amount=Decimal("9999"),
            license_type="SUBSCRIPTION",
            subscription_years=1,
            standard_unit_price=Decimal("10"),
            status=ContractStatus.SIGNED,
            signing_date=date(2026, 9, 1),
            payment_status=PaymentStatus.UNPAID,
            owner_id="1",
            creator_id="1",
        )
        db.add(contract)
        db.flush()
        contracts[key] = contract

    plans: dict[str, PaymentPlan] = {}
    for key in ("opportunity_owned", "member_visible"):
        plan = PaymentPlan(
            team_id=1,
            contract_id=contracts[key].id,
            deal_journey_id=seeded[key].id,
            plan_number=f"PAY-{key}",
            stage_name="Initial",
            planned_amount=Decimal("100"),
            due_date=date(2026, 10, 1),
            status=PaymentPlanStatus.PENDING,
        )
        db.add(plan)
        db.flush()
        plans[key] = plan

    invoice_opportunity = opportunities["member_visible"]
    db.add(
        InvoiceApplication(
            team_id=1,
            application_number="INV-member-visible",
            customer_id=seeded["member_visible"].customer_id,
            contract_id=contracts["member_visible"].id,
            opportunity_id=invoice_opportunity.id,
            payment_plan_id=plans["member_visible"].id,
            deal_journey_id=seeded["member_visible"].id,
            invoice_amount=Decimal("100"),
            invoice_type="VAT_NORMAL",
            status=InvoiceApplicationStatus.APPROVED,
            approval_phase=ApprovalPhase.APPROVED.value,
            applicant_id="1",
            invoice_title_type="COMPANY",
            invoice_title_text="Member Visible",
            invoice_taxpayer_id="TAX-1",
        )
    )
    db.commit()
    return seeded


def test_own_scope_unions_customer_owner_opportunity_owner_and_member(db):
    seeded = _seed_query_case(db)

    rows, total = service.paginate(db, request=_request(), skip=0, limit=50)

    assert {row.journey.id for row in rows} == {
        seeded["customer_owned"].id,
        seeded["opportunity_owned"].id,
        seeded["member_visible"].id,
        seeded["no_opportunity"].id,
        seeded["completed"].id,
        seeded["lost"].id,
    }
    assert total == 6


def test_member_visibility_does_not_require_own_permission(db):
    seeded = _seed_query_case(db)

    rows, total = service.paginate(
        db,
        request=_request(permission_codes=frozenset()),
        skip=0,
        limit=50,
    )

    assert [row.journey.id for row in rows] == [seeded["member_visible"].id]
    assert total == 1


def test_all_permission_returns_all_non_archived_rows(db):
    seeded = _seed_query_case(db)

    rows, total = service.paginate(
        db,
        request=_request(
            user_id=9,
            permission_codes=frozenset({"customer:view:all"}),
        ),
        skip=0,
        limit=50,
    )

    ids = {row.journey.id for row in rows}
    assert seeded["foreign"].id in ids
    assert seeded["archived"].id not in ids
    assert total == 7


def test_list_and_board_queries_return_same_ids_for_same_request(db):
    _seed_query_case(db)
    request = _request(
        filters=[FilterCondition(field="product_name", op="eq", value="Hifox")],
        sorts=[SortCondition(field="last_event_at", direction="desc")],
    )

    table_rows, total = service.paginate(db, request=request, skip=0, limit=500)
    board_rows, board_total, truncated = service.list_for_board(db, request=request, limit=500)

    assert [row.journey.id for row in board_rows] == [row.journey.id for row in table_rows]
    assert board_total == total
    assert truncated is False


def test_tabs_active_completed_lost_are_mutually_correct(db):
    seeded = _seed_query_case(db)

    active_rows, _ = service.paginate(db, request=_request(tab="active"), skip=0, limit=50)
    completed_rows, _ = service.paginate(db, request=_request(tab="completed"), skip=0, limit=50)
    lost_rows, _ = service.paginate(db, request=_request(tab="lost"), skip=0, limit=50)

    assert {row.journey.status for row in active_rows} == {
        DealJourneyStatus.ACTIVE,
        DealJourneyStatus.WON,
    }
    assert {row.journey.id for row in completed_rows} == {seeded["completed"].id}
    assert {row.journey.id for row in lost_rows} == {seeded["lost"].id}


def test_search_and_filters_apply_before_count(db):
    seeded = _seed_query_case(db)

    rows, total = service.paginate(
        db,
        request=_request(
            search="Hifox Alias",
            filters=[FilterCondition(field="amount", op="eq", value=120)],
        ),
        skip=0,
        limit=50,
    )

    assert [row.journey.id for row in rows] == [seeded["customer_owned"].id]
    assert total == 1


@pytest.mark.parametrize(
    ("stage", "expected_key"),
    [
        ("contract_processing", "customer_owned"),
        ("payment_processing", "opportunity_owned"),
        ("invoice_processing", "member_visible"),
    ],
)
def test_stage_filter_uses_infer_board_stage(db, stage, expected_key):
    seeded = _seed_query_case(db)

    rows, total = service.paginate(
        db,
        request=_request(filters=[FilterCondition(field="stage", op="eq", value=stage)]),
        skip=0,
        limit=50,
    )

    assert [row.journey.id for row in rows] == [seeded[expected_key].id]
    assert rows[0].stage == stage
    assert total == 1


def test_stage_filter_rejects_unsupported_operator(db):
    _seed_query_case(db)

    with pytest.raises(ListQueryError, match="stage.*gte"):
        service.paginate(
            db,
            request=_request(filters=[FilterCondition(field="stage", op="gte", value="completed")]),
            skip=0,
            limit=50,
        )


def test_sort_and_pagination_are_stable(db):
    seeded = _seed_query_case(db)
    request = _request(sorts=[SortCondition(field="last_event_at", direction="desc")])

    first_page, total = service.paginate(db, request=request, skip=0, limit=1)
    second_page, second_total = service.paginate(db, request=request, skip=1, limit=1)

    expected = sorted(
        [seeded["customer_owned"].id, seeded["opportunity_owned"].id],
        reverse=True,
    )
    assert [first_page[0].journey.id, second_page[0].journey.id] == expected
    assert {first_page[0].journey.id}.isdisjoint({second_page[0].journey.id})
    assert total == second_total == 6


def test_explicit_sort_resets_default_order_and_uses_id_tie_break(db):
    seeded = _seed_query_case(db)
    request = _request(sorts=[SortCondition(field="amount", direction="asc")])

    rows, _ = service.paginate(db, request=request, skip=0, limit=50)

    assert rows[0].journey.id == seeded["no_opportunity"].id
    assert [row.journey.id for row in rows[-2:]] == sorted(
        [seeded["completed"].id, seeded["lost"].id]
    )


def test_board_limit_reports_untruncated_total(db):
    _seed_query_case(db)

    rows, total, truncated = service.list_for_board(db, request=_request(), limit=2)

    assert len(rows) == 2
    assert total == 6
    assert truncated is True


def test_owner_options_use_visible_rows_only(db):
    db.add_all(
        [
            User(id=1, email="one@example.com", name="User One", status=UserStatus.ACTIVE),
            User(id=2, email="two@example.com", name="User Two", status=UserStatus.ACTIVE),
        ]
    )
    for index, owner_id in enumerate(("1", "2"), start=1):
        customer = Customer(
            team_id=1,
            account_name=f"Owner customer {index}",
            city="Shanghai",
            owner_id=owner_id,
            creator_id=owner_id,
        )
        db.add(customer)
        db.flush()
        journey = CustomerDealJourney(
            team_id=1,
            customer_id=customer.id,
            name=f"Owner journey {index}",
            status=DealJourneyStatus.ACTIVE,
        )
        db.add(journey)
    db.commit()

    options = service.owner_options(
        db,
        request=_request(permission_codes=frozenset({"customer:view:own"})),
    )

    assert [(option.id, option.name, option.is_me) for option in options] == [
        ("1", "User One（我）", True)
    ]


def test_board_schemas_use_public_ids_and_report_truncation():
    card_fields = BusinessJourneyBoardCard.model_fields
    assert "public_id" in card_fields
    assert "customer_id" in card_fields
    assert "journey_id" not in card_fields

    summary = BusinessJourneyBoardSummary(
        total_count=3,
        total_amount=120,
        active_count=2,
        completed_count=1,
        lost_count=0,
    )
    response = BusinessJourneyBoardResponse(
        columns=[
            BusinessJourneyBoardColumn(
                key="early_communication",
                title="Early",
                description="",
                count=0,
                amount=0,
                cards=[],
            )
        ],
        summary=summary,
        truncated=True,
    )
    assert response.summary.total_count == 3
    assert response.truncated is True
