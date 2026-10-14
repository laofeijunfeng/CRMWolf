"""Population queries expose every authorized row while list pagination stays unchanged."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import BigInteger

from app.constants.business_types import BusinessType
from app.core.list_query.types import FilterCondition, SortCondition
from app.crud.contract import contract_crud
from app.crud.customer import customer_crud
from app.crud.opportunity import opportunity_crud
from app.crud.payment import payment_plan_crud, payment_record_crud
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.product import Product, ProductModule
from app.models.user import User


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Product.__table__,
        ProductModule.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        CustomerMember.__table__,
        Opportunity.__table__,
        OpportunityProductModule.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        Approval.__table__,
        PaymentRecord.__table__,
    ]
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _customer(customer_id: int, *, team_id: int = 1, name: str, owner_id: str, status: int, created_time: datetime, **extra) -> Customer:
    return Customer(
        id=customer_id,
        public_id=f"cus_{customer_id}",
        team_id=team_id,
        account_name=name,
        city=extra.pop("city", "上海"),
        status=status,
        owner_id=owner_id,
        creator_id=owner_id,
        created_time=created_time,
        **extra,
    )


def _opportunity(opportunity_id: int, *, customer_id: int, name: str, owner_id: str, created_time: datetime, **extra) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        public_id=f"opp_{opportunity_id}",
        team_id=extra.pop("team_id", 1),
        opportunity_number=f"OPP-{opportunity_id}",
        opportunity_name=name,
        customer_id=customer_id,
        total_amount=Decimal("1000.00"),
        user_count=10,
        unit_price=Decimal("100.00"),
        license_type=extra.pop("license_type", "SUBSCRIPTION"),
        subscription_years=1,
        purchase_type=extra.pop("purchase_type", "NEW"),
        expected_closing_date=extra.pop("expected_closing_date", date(2026, 9, 1)),
        owner_id=owner_id,
        creator_id=owner_id,
        status=extra.pop("status", 0),
        created_time=created_time,
        **extra,
    )


def _contract(contract_id: int, *, customer_id: int, opportunity_id: int, name: str, owner_id: str, created_time: datetime, **extra) -> Contract:
    return Contract(
        id=contract_id,
        team_id=extra.pop("team_id", 1),
        contract_number=f"CT-{contract_id}",
        contract_name=name,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        user_count=10,
        total_amount=Decimal("1000.00"),
        license_type=extra.pop("license_type", "SUBSCRIPTION"),
        subscription_years=extra.pop("subscription_years", 1),
        standard_unit_price=Decimal("100.00"),
        owner_id=owner_id,
        creator_id=extra.pop("creator_id", owner_id),
        status=extra.pop("status", "ACTIVE"),
        created_time=created_time,
        **extra,
    )


def _plan(plan_id: int, *, contract_id: int, name: str, due_date: date, status: str, created_time: datetime) -> PaymentPlan:
    return PaymentPlan(
        id=plan_id,
        team_id=1,
        contract_id=contract_id,
        plan_number=f"PP-{plan_id}",
        stage_name=name,
        planned_amount=Decimal("1000.00"),
        due_date=due_date,
        status=status,
        created_time=created_time,
    )


def _record(record_id: int, *, plan_id: int, amount: Decimal, payment_date: date, creator_id: str = "1", **extra) -> PaymentRecord:
    return PaymentRecord(
        id=record_id,
        team_id=1,
        record_number=extra.pop("record_number", f"PR-{record_id}"),
        payment_plan_id=plan_id,
        actual_amount=amount,
        payment_date=payment_date,
        creator_id=creator_id,
        creator_name="Owner",
        confirmation_status=extra.pop("confirmation_status", PaymentConfirmationStatus.PENDING),
        approval_phase=extra.pop("approval_phase", "draft"),
        created_time=extra.pop("created_time", datetime(2026, 8, record_id)),
        **extra,
    )


def _ids(rows) -> list[int]:
    return [row.id for row in rows]


def _population_ids(query: Query) -> list[int]:
    compiled = str(query.statement.compile(compile_kwargs={"literal_binds": False})).lower()
    assert " limit " not in compiled
    assert " offset " not in compiled
    return _ids(query.all())


def test_customer_population_includes_every_match_while_list_pages(db_session):
    base = datetime(2026, 1, 1)
    rows = [
        _customer(index, name=f"Alpha {index}", owner_id="7", status=0, created_time=base + timedelta(days=index))
        for index in range(1, 8)
    ]
    rows.append(_customer(8, name="Beta", owner_id="7", status=1, created_time=base))
    rows.append(_customer(9, name="Other Team", owner_id="7", status=0, team_id=2, created_time=base))
    db_session.add_all(rows)
    db_session.commit()

    population = customer_crud.build_population_query(
        db_session, team_id=1, keyword="Alpha", order_by="created_time", order_dir="asc",
    )
    assert _population_ids(population) == list(range(1, 8))

    page, total = customer_crud.get_multi(
        db_session, team_id=1, keyword="Alpha", skip=0, limit=2,
        order_by="created_time", order_dir="asc",
    )
    assert total == 7
    assert _ids(page) == [1, 2]

    resorted, resorted_total = customer_crud.get_multi(
        db_session, team_id=1, keyword="Alpha", skip=0, limit=2,
        order_by="created_time", order_dir="desc",
    )
    assert resorted_total == total
    assert _ids(resorted) == [7, 6]
    assert _population_ids(customer_crud.build_population_query(
        db_session, team_id=1, keyword="Alpha", order_by="created_time", order_dir="desc",
    )) == [7, 6, 5, 4, 3, 2, 1]


def test_customer_export_query_keeps_unified_branch_and_omits_legacy_filters(db_session):
    db_session.add_all([
        _customer(1, name="Owned", owner_id="7", status=0, city="北京", created_time=datetime(2026, 2, 1)),
        _customer(2, name="Collaborated", owner_id="8", status=1, city="上海", created_time=datetime(2026, 3, 1)),
        _customer(3, name="Outsider", owner_id="9", status=0, city="北京", created_time=datetime(2026, 1, 1)),
        CustomerMember(id=1, team_id=1, customer_id=2, user_id="7", is_active=True, created_by="7"),
    ])
    db_session.commit()

    exported = customer_crud.build_list_query(
        db_session,
        team_id=1,
        owner_id="8",
        scope="collaborated",
        current_user_id="7",
        include_collaborated=False,
        search=None,
        filters=[FilterCondition(field="city", op="eq", value="上海")],
        sorts=[SortCondition(field="account_name", direction="asc")],
    )
    assert _ids(exported.all()) == [2]

    legacy_page, legacy_total = customer_crud.get_multi(
        db_session, team_id=1, scope="collaborated", current_user_id="7", city="北京",
    )
    assert legacy_total == 0
    assert legacy_page == []


def test_customer_unified_owner_precedes_filters_and_legacy_order_is_default(db_session):
    db_session.add_all([
        _customer(1, name="B Owner", owner_id="7", status=0, city="深圳", created_time=datetime(2026, 1, 2)),
        _customer(2, name="A Other", owner_id="8", status=0, created_time=datetime(2026, 4, 2)),
    ])
    db_session.commit()

    unified = customer_crud.build_population_query(
        db_session,
        team_id=1,
        owner_id="7",
        filters=[FilterCondition(field="city", op="eq", value="深圳")],
        sorts=[SortCondition(field="account_name", direction="asc")],
    )
    assert _population_ids(unified) == [1]

    default_ordered = customer_crud.build_population_query(db_session, team_id=1)
    assert _population_ids(default_ordered) == [2, 1]


def test_opportunity_population_pages_independently_and_preserves_direct_filters(db_session):
    base = datetime(2026, 4, 1)
    db_session.add(_customer(1, name="Acme", owner_id="7", status=0, created_time=base))
    db_session.add_all([
        _opportunity(index, customer_id=1, name=f"Deal {index}", owner_id="7", status=0, created_time=base + timedelta(days=index))
        for index in range(1, 7)
    ])
    db_session.add(_opportunity(7, customer_id=1, name="Lost", owner_id="7", status=2, created_time=base))
    db_session.commit()

    assert _population_ids(opportunity_crud.build_population_query(
        db_session, team_id=1, status="0", order_by="created_time", order_dir="asc",
    )) == list(range(1, 7))

    page, total = opportunity_crud.get_multi(
        db_session, team_id=1, status="0", skip=2, limit=2, order_by="created_time", order_dir="asc",
    )
    assert total == 6
    assert _ids(page) == [3, 4]

    exported = opportunity_crud.build_list_query(
        db_session,
        team_id=1,
        status="0",
        owner_id="7",
        customer_id=1,
        search=None,
        filters=[FilterCondition(field="status", op="eq", value=2)],
        sorts=[SortCondition(field="created_time", direction="desc")],
    )
    assert _ids(exported.all()) == list(range(6, 0, -1))
    empty_status = opportunity_crud.build_list_query(
        db_session, team_id=1, status="", owner_id="9", customer_id=None, search=None, filters=[], sorts=[],
    )
    assert _ids(empty_status.all()) == []


def test_contract_population_excludes_deleted_and_keeps_unified_tie_break(db_session):
    base = datetime(2026, 5, 1)
    db_session.add(_customer(1, name="Acme", owner_id="7", status=0, created_time=base))
    db_session.add(_opportunity(1, customer_id=1, name="Deal", owner_id="7", created_time=base))
    db_session.add_all([
        _contract(index, customer_id=1, opportunity_id=1, name=f"Contract {index}", owner_id="7", created_time=base)
        for index in range(1, 5)
    ])
    db_session.add(_contract(
        5, customer_id=1, opportunity_id=1, name="Deleted", owner_id="7",
        created_time=base, deleted_at=datetime(2026, 6, 1),
    ))
    db_session.commit()

    assert _population_ids(contract_crud.build_population_query(
        db_session, team_id=1, order_by="contract_name", order_dir="asc",
    )) == [1, 2, 3, 4]

    page, total = contract_crud.get_multi(db_session, team_id=1, skip=1, limit=2, order_by="contract_name", order_dir="asc")
    assert total == 4
    assert _ids(page) == [2, 3]

    exported = contract_crud.build_list_query(
        db_session,
        team_id=1,
        customer_id=1,
        status="ACTIVE",
        owner_id="7",
        search=None,
        filters=[FilterCondition(field="status", op="eq", value="DRAFT")],
        sorts=[SortCondition(field="created_time", direction="desc")],
    )
    assert _ids(exported.all()) == [1, 2, 3, 4]

    included = contract_crud.build_population_query(db_session, team_id=1, include_deleted=True)
    assert 5 in _population_ids(included)


def test_payment_plan_scope_uses_contract_owner_and_sort_does_not_change_total(db_session):
    base = datetime(2026, 6, 1)
    db_session.add_all([
        _customer(1, name="Acme", owner_id="7", status=0, created_time=base),
        _customer(2, name="Beta", owner_id="8", status=0, created_time=base),
        _opportunity(1, customer_id=1, name="Owned Deal", owner_id="7", created_time=base),
        _opportunity(2, customer_id=2, name="Other Deal", owner_id="8", created_time=base),
        _contract(1, customer_id=1, opportunity_id=1, name="Owned Contract", owner_id="7", created_time=base),
        _contract(2, customer_id=2, opportunity_id=2, name="Other Contract", owner_id="8", creator_id="7", created_time=base),
    ])
    db_session.add_all([
        _plan(1, contract_id=1, name="Tail", due_date=date(2026, 8, 3), status=PaymentPlanStatus.PENDING, created_time=base),
        _plan(2, contract_id=1, name="Middle", due_date=date(2026, 8, 2), status=PaymentPlanStatus.PENDING, created_time=base),
        _plan(3, contract_id=1, name="Head", due_date=date(2026, 8, 1), status=PaymentPlanStatus.PENDING, created_time=base),
        _plan(4, contract_id=2, name="Foreign", due_date=date(2026, 8, 1), status=PaymentPlanStatus.PENDING, created_time=base),
    ])
    db_session.commit()

    assert _population_ids(payment_plan_crud.build_population_query(db_session, team_id=1, current_user_id="7")) == [3, 2, 1]
    first_page, total = payment_plan_crud.list_plans(db_session, team_id=1, current_user_id="7", skip=0, limit=1)
    assert total == 3
    assert _ids(first_page) == [3]
    resorted, resorted_total = payment_plan_crud.list_plans(
        db_session, team_id=1, current_user_id="7", skip=0, limit=1, order_by="stage_name", order_dir="desc",
    )
    assert resorted_total == total
    assert _ids(resorted) == [1]

    exported = payment_plan_crud.build_list_query(
        db_session,
        team_id=1,
        status=PaymentPlanStatus.PENDING,
        current_user_id="7",
        search=None,
        filters=[FilterCondition(field="status", op="eq", value=PaymentPlanStatus.COMPLETED)],
        sorts=[SortCondition(field="due_date", direction="desc")],
    )
    assert _ids(exported.all()) == [1, 2, 3]


def test_payment_record_scope_uses_contract_creator_and_canonical_approval(db_session):
    base = datetime(2026, 7, 1)
    db_session.add_all([
        User(id=1, email="owner@example.com", name="Owner"),
        User(id=2, email="other@example.com", name="Other"),
        _customer(1, name="Acme", owner_id="1", status=0, created_time=base),
        _opportunity(1, customer_id=1, name="Deal", owner_id="1", created_time=base),
        _contract(1, customer_id=1, opportunity_id=1, name="Mine", owner_id="2", creator_id="1", created_time=base),
        _contract(2, customer_id=1, opportunity_id=1, name="Theirs", owner_id="1", creator_id="2", created_time=base),
        _plan(1, contract_id=1, name="Mine Plan", due_date=date(2026, 8, 1), status=PaymentPlanStatus.PENDING, created_time=base),
        _plan(2, contract_id=2, name="Their Plan", due_date=date(2026, 8, 2), status=PaymentPlanStatus.PENDING, created_time=base),
    ])
    records = [
        _record(1, plan_id=1, amount=Decimal("10.00"), payment_date=date(2026, 8, 1), approval_phase="draft"),
        _record(2, plan_id=1, amount=Decimal("20.00"), payment_date=date(2026, 8, 2), confirmation_status=PaymentConfirmationStatus.CONFIRMED),
        _record(3, plan_id=1, amount=Decimal("30.00"), payment_date=date(2026, 8, 3), approval_phase="withdrawn"),
        _record(4, plan_id=2, amount=Decimal("40.00"), payment_date=date(2026, 8, 4)),
    ]
    db_session.add_all(records)
    db_session.flush()
    approval = Approval(
        id=10, team_id=1, business_type=BusinessType.PAYMENT, business_id=2,
        status=ApprovalStatus.APPROVED, submitter_id="1",
    )
    db_session.add(approval)
    db_session.flush()
    records[1].approval_id = approval.id
    db_session.commit()

    scoped = payment_record_crud.build_population_query(db_session, team_id=1, current_user_id="1")
    assert _population_ids(scoped) == [3, 2, 1]

    approved = payment_record_crud.build_population_query(db_session, team_id=1, approval_status="approved")
    assert _population_ids(approved) == [2]
    confirmed_only, confirmed_total = payment_record_crud.list_records(
        db_session, team_id=1, confirmation_status=PaymentConfirmationStatus.CONFIRMED, skip=0, limit=1,
    )
    assert confirmed_total == 1
    assert _ids(confirmed_only) == [2]

    page, total = payment_record_crud.list_records(db_session, team_id=1, current_user_id="1", skip=0, limit=1)
    assert total == 3
    assert _ids(page) == [3]
    resorted, resorted_total = payment_record_crud.list_records(
        db_session, team_id=1, current_user_id="1", skip=0, limit=1, order_by="actual_amount", order_dir="asc",
    )
    assert resorted_total == total
    assert _ids(resorted) == [1]

    exported = payment_record_crud.build_list_query(
        db_session,
        team_id=1,
        approval_status="approved",
        current_user_id="1",
        search=None,
        filters=[FilterCondition(field="approval_status", op="eq", value="pending_submit")],
        sorts=[SortCondition(field="payment_date", direction="asc")],
    )
    assert _ids(exported.all()) == [2]


def test_population_builders_are_keyword_only_typed_queries(db_session):
    db_session.add(_customer(1, name="Acme", owner_id="7", status=0, created_time=datetime(2026, 1, 1)))
    db_session.commit()

    with pytest.raises(TypeError):
        customer_crud.build_population_query(db_session, 1)

    query = customer_crud.build_population_query(db_session, team_id=1)
    assert isinstance(query, Query)
    assert "limit" not in query.statement._limit_clause.__class__.__name__.lower() or query._limit_clause is None
