"""Payment approval filters agree across catalog, unified query, and legacy tabs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import BigInteger

from app.constants.business_types import BusinessType
from app.core.list_query.catalogs.payment_records import PAYMENT_RECORDS_LIST_QUERY_CATALOG
from app.core.list_query.engine import apply_filters
from app.core.list_query.types import ListQueryContext
from app.crud.payment import payment_record_crud
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.user import User
from app.services.payment_approval_status import PaymentApprovalReadStatus


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
        Customer.__table__,
        Opportunity.__table__,
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


def _seed_graph(db_session) -> dict[str, int]:
    db_session.add_all(
        [
            User(id=1, email="owner@example.com", name="Owner"),
            User(id=2, email="other@example.com", name="Other"),
            Customer(
                id=1,
                public_id="cus_payment_approval_parity",
                team_id=1,
                account_name="Parity Customer",
                city="上海",
                owner_id="1",
                creator_id="1",
            ),
            Opportunity(
                id=1,
                public_id="opp_payment_approval_parity",
                team_id=1,
                opportunity_number="OPP-PARITY",
                opportunity_name="Parity Opportunity",
                customer_id=1,
                total_amount=Decimal("1000"),
                user_count=10,
                unit_price=Decimal("100"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                purchase_type="NEW",
                expected_closing_date=date(2026, 9, 1),
                owner_id="1",
                creator_id="1",
            ),
            Contract(
                id=1,
                team_id=1,
                contract_number="CT-PARITY",
                contract_name="Parity Contract",
                customer_id=1,
                opportunity_id=1,
                user_count=10,
                total_amount=Decimal("1000"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                standard_unit_price=Decimal("100"),
                owner_id="1",
                creator_id="1",
            ),
            PaymentPlan(
                id=1,
                team_id=1,
                contract_id=1,
                plan_number="PP-PARITY",
                stage_name="首付款",
                planned_amount=Decimal("1000"),
                due_date=date(2026, 9, 10),
                status=PaymentPlanStatus.PENDING,
            ),
        ]
    )
    db_session.flush()

    specs = [
        ("pending_submit", "draft", None, PaymentConfirmationStatus.PENDING),
        ("pending_approval", "draft", ApprovalStatus.PENDING, PaymentConfirmationStatus.PENDING),
        ("rejected", "draft", ApprovalStatus.REJECTED, PaymentConfirmationStatus.PENDING),
        ("approved", "draft", ApprovalStatus.APPROVED, PaymentConfirmationStatus.PENDING),
        ("unclassified", "withdrawn", None, PaymentConfirmationStatus.PENDING),
        ("confirmed_unapproved", "draft", None, PaymentConfirmationStatus.CONFIRMED),
        ("wrong_team", "draft", ApprovalStatus.APPROVED, PaymentConfirmationStatus.PENDING),
        ("non_payment", "draft", ApprovalStatus.APPROVED, PaymentConfirmationStatus.PENDING),
    ]
    record_ids: dict[str, int] = {}
    for index, (key, phase, approval_status, confirmation) in enumerate(specs, start=1):
        record = PaymentRecord(
            id=index,
            team_id=1,
            record_number=f"PR-{key}",
            payment_plan_id=1,
            actual_amount=Decimal("100.00"),
            payment_date=date(2026, 8, index),
            creator_id="1",
            creator_name="Owner",
            confirmation_status=confirmation,
            approval_phase=phase,
        )
        db_session.add(record)
        db_session.flush()
        if approval_status is not None:
            approval = Approval(
                id=100 + index,
                team_id=2 if key == "wrong_team" else 1,
                business_type=BusinessType.CONTRACT if key == "non_payment" else BusinessType.PAYMENT,
                business_id=record.id,
                status=approval_status,
                submitter_id="1",
            )
            db_session.add(approval)
            db_session.flush()
            record.approval_id = approval.id
        record_ids[key] = record.id
    db_session.commit()
    return record_ids


def _catalog_ids(db_session, op: str, value) -> set[int]:
    query = apply_filters(
        select(PaymentRecord.id),
        PAYMENT_RECORDS_LIST_QUERY_CATALOG,
        [{"field": "approval_status", "op": op, "value": value}],
        context=ListQueryContext(db=db_session, team_id=1),
    )
    return set(db_session.execute(query).scalars().all())


def _legacy_ids(db_session, **kwargs) -> set[int]:
    records, _total = payment_record_crud.list_records(db_session, team_id=1, **kwargs)
    return {record.id for record in records}


def _unified_ids(db_session, filters: list[dict]) -> set[int]:
    records, _total = payment_record_crud.list_records(
        db_session,
        team_id=1,
        filters=filters,
        sorts=[],
    )
    return {record.id for record in records}


def test_catalog_approval_status_matches_canonical_groups(db_session):
    ids = _seed_graph(db_session)

    assert _catalog_ids(db_session, "eq", PaymentApprovalReadStatus.PENDING_SUBMIT) == {
        ids["pending_submit"],
        ids["confirmed_unapproved"],
        ids["wrong_team"],
        ids["non_payment"],
    }
    assert _catalog_ids(db_session, "eq", PaymentApprovalReadStatus.PENDING_APPROVAL) == {
        ids["pending_approval"]
    }
    assert _catalog_ids(db_session, "eq", PaymentApprovalReadStatus.REJECTED) == {ids["rejected"]}
    assert _catalog_ids(db_session, "eq", PaymentApprovalReadStatus.APPROVED) == {ids["approved"]}
    assert ids["confirmed_unapproved"] not in _catalog_ids(
        db_session, "eq", PaymentApprovalReadStatus.APPROVED
    )
    assert _catalog_ids(db_session, "is_empty", None) == {ids["unclassified"]}


def test_legacy_and_unified_filters_agree_with_catalog(db_session):
    ids = _seed_graph(db_session)
    canonical = {
        "pending_submit": {
            ids["pending_submit"],
            ids["confirmed_unapproved"],
            ids["wrong_team"],
            ids["non_payment"],
        },
        "pending_approval": {ids["pending_approval"]},
        "rejected": {ids["rejected"]},
        "approved": {ids["approved"]},
    }

    for status, expected in canonical.items():
        assert _catalog_ids(db_session, "eq", status) == expected
        assert _legacy_ids(db_session, approval_status=status) == expected
        assert _unified_ids(
            db_session,
            [{"field": "approval_status", "op": "eq", "value": status}],
        ) == expected

    assert ids["confirmed_unapproved"] not in _legacy_ids(db_session, approval_status="approved")
    assert _legacy_ids(db_session, confirmation_status="CONFIRMED") == {ids["confirmed_unapproved"]}


def test_legacy_exclusion_retains_unclassified_nulls(db_session):
    ids = _seed_graph(db_session)
    excluded = _legacy_ids(db_session, approval_status_exclude="approved")

    assert ids["approved"] not in excluded
    assert ids["unclassified"] in excluded
    assert _legacy_ids(db_session, approval_status_exclude="unclassified") == {
        ids["pending_submit"],
        ids["pending_approval"],
        ids["rejected"],
        ids["approved"],
        ids["confirmed_unapproved"],
        ids["wrong_team"],
        ids["non_payment"],
    }


def test_explicit_legacy_approval_status_precedes_unified_filter(db_session):
    ids = _seed_graph(db_session)

    selected = _unified_ids_with_scope(
        db_session,
        approval_status="pending_submit",
        filters=[{"field": "approval_status", "op": "eq", "value": "approved"}],
    )
    assert selected == {
        ids["pending_submit"],
        ids["confirmed_unapproved"],
        ids["wrong_team"],
        ids["non_payment"],
    }

    amount_filtered = _unified_ids_with_scope(
        db_session,
        approval_status=None,
        filters=[{"field": "actual_amount", "op": "eq", "value": 100}],
        actual_amount=999,
    )
    assert ids["pending_submit"] in amount_filtered


def _unified_ids_with_scope(db_session, *, approval_status, filters, **legacy) -> set[int]:
    records, _total = payment_record_crud.list_records(
        db_session,
        team_id=1,
        approval_status=approval_status,
        filters=filters,
        sorts=[],
        **legacy,
    )
    return {record.id for record in records}


def test_linked_foreign_evidence_falls_back_to_native_phase(db_session):
    ids = _seed_graph(db_session)
    approved = _catalog_ids(db_session, "eq", PaymentApprovalReadStatus.APPROVED)
    pending_submit = _catalog_ids(db_session, "eq", PaymentApprovalReadStatus.PENDING_SUBMIT)

    assert ids["wrong_team"] not in approved
    assert ids["non_payment"] not in approved
    assert {ids["wrong_team"], ids["non_payment"]} <= pending_submit
    assert _catalog_ids(db_session, "is_empty", None) == {ids["unclassified"]}
    assert pending_submit == {
        ids["pending_submit"],
        ids["confirmed_unapproved"],
        ids["wrong_team"],
        ids["non_payment"],
    }
