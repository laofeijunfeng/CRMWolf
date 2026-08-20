"""回款计划与回款记录统一列表查询协议回归测试。"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import BigInteger

from app.core.list_query import run_or_400
from app.crud.invoice import invoice_application_crud
from app.crud.payment import payment_plan_crud, payment_record_crud
from app.models.approval import Approval
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import (
    InvoiceApplication,
    InvoiceApplicationStatus,
    InvoiceRedOffset,
    InvoiceRedOffsetSourceType,
    InvoiceReissueApplication,
    InvoiceReissueApplicationStatus,
    InvoiceType,
)
from app.models.opportunity import Opportunity
from app.models.payment import (
    PaymentConfirmationStatus,
    PaymentPlan,
    PaymentPlanStatus,
    PaymentRecord,
)
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
        Customer.__table__,
        Opportunity.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        Approval.__table__,
        PaymentRecord.__table__,
        InvoiceApplication.__table__,
        InvoiceReissueApplication.__table__,
        InvoiceRedOffset.__table__,
    ]
    # SQLite 的索引名是库级唯一，而生产模型中不同表存在同名索引。
    # 这里只创建表结构，不创建索引；列表查询行为不依赖索引。
    with engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table))
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _seed_payment_graph(db_session):
    db_session.add_all(
        [
            User(id=1, email="alice@example.com", name="Alice"),
            User(id=2, email="bob@example.com", name="Bob"),
            Customer(
                id=1,
                public_id="cus_11111111111111111111111111111111",
                team_id=1,
                account_name="Alpha 客户",
                city="上海",
                owner_id="1",
                creator_id="1",
            ),
            Customer(
                id=2,
                public_id="cus_22222222222222222222222222222222",
                team_id=1,
                account_name="Beta 客户",
                city="北京",
                owner_id="2",
                creator_id="2",
            ),
        ]
    )
    db_session.add_all(
        [
            Opportunity(
                id=1,
                public_id="opp_11111111111111111111111111111111",
                team_id=1,
                opportunity_number="OPP-001",
                opportunity_name="Alpha 商机",
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
            Opportunity(
                id=2,
                public_id="opp_22222222222222222222222222222222",
                team_id=1,
                opportunity_number="OPP-002",
                opportunity_name="Beta 商机",
                customer_id=2,
                total_amount=Decimal("3000"),
                user_count=30,
                unit_price=Decimal("100"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                purchase_type="NEW",
                expected_closing_date=date(2026, 9, 2),
                owner_id="2",
                creator_id="2",
            ),
        ]
    )
    db_session.add_all(
        [
            Contract(
                id=1,
                team_id=1,
                contract_number="CT-001",
                contract_name="Alpha 合同",
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
            Contract(
                id=2,
                team_id=1,
                contract_number="CT-002",
                contract_name="Beta 合同",
                customer_id=2,
                opportunity_id=2,
                user_count=30,
                total_amount=Decimal("3000"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                standard_unit_price=Decimal("100"),
                owner_id="2",
                creator_id="2",
            ),
        ]
    )
    db_session.add_all(
        [
            PaymentPlan(
                id=1,
                team_id=1,
                contract_id=1,
                plan_number="PP-001",
                stage_name="首付款",
                planned_amount=Decimal("1000"),
                due_date=date(2026, 9, 10),
                status=PaymentPlanStatus.PENDING,
            ),
            PaymentPlan(
                id=2,
                team_id=1,
                contract_id=2,
                plan_number="PP-002",
                stage_name="尾款",
                planned_amount=Decimal("3000"),
                due_date=date(2026, 9, 20),
                status=PaymentPlanStatus.PENDING,
            ),
        ]
    )
    db_session.add_all(
        [
            PaymentRecord(
                id=1,
                team_id=1,
                record_number="PR-001",
                payment_plan_id=1,
                actual_amount=Decimal("800"),
                actual_payer_name="Alpha 付款方",
                payment_date=date(2026, 8, 10),
                creator_id="1",
                creator_name="Alice",
                confirmation_status=PaymentConfirmationStatus.PENDING,
            ),
            PaymentRecord(
                id=2,
                team_id=1,
                record_number="PR-002",
                payment_plan_id=2,
                actual_amount=Decimal("2800"),
                actual_payer_name="Beta 付款方",
                payment_date=date(2026, 8, 11),
                creator_id="2",
                creator_name="Bob",
                confirmation_status=PaymentConfirmationStatus.PENDING,
            ),
        ]
    )
    db_session.add_all(
        [
            InvoiceApplication(
                team_id=1,
                application_number="INV-001",
                customer_id=1,
                contract_id=1,
                opportunity_id=1,
                payment_plan_id=1,
                payment_record_id=1,
                invoice_amount=Decimal("800"),
                invoice_type=InvoiceType.VAT_NORMAL,
                status=InvoiceApplicationStatus.ISSUED,
                applicant_id="1",
                invoice_title_type="COMPANY",
                invoice_title_text="Alpha 发票抬头",
                invoice_taxpayer_id="TAX-001",
            ),
            InvoiceApplication(
                team_id=1,
                application_number="INV-002",
                customer_id=2,
                contract_id=2,
                opportunity_id=2,
                payment_plan_id=2,
                payment_record_id=2,
                invoice_amount=Decimal("2800"),
                invoice_type=InvoiceType.VAT_NORMAL,
                status=InvoiceApplicationStatus.ISSUED,
                applicant_id="2",
                invoice_title_type="COMPANY",
                invoice_title_text="Beta 发票抬头",
                invoice_taxpayer_id="TAX-002",
            ),
        ]
    )
    db_session.commit()


def test_payment_plan_planned_amount_filters_sorts_and_paginates(db_session):
    _seed_payment_graph(db_session)

    plans, total = payment_plan_crud.list_plans(
        db_session,
        team_id=1,
        skip=0,
        limit=1,
        filters=[{"field": "planned_amount", "op": "neq", "value": 1000}],
        sorts=[{"field": "planned_amount", "direction": "desc"}],
    )

    assert total == 1
    assert [plan.plan_number for plan in plans] == ["PP-002"]


def test_payment_plan_unified_query_excludes_cross_team_contracts(db_session):
    _seed_payment_graph(db_session)
    db_session.add_all(
        [
            Customer(
                id=901,
                public_id="cus_99999999999999999999999999999991",
                team_id=2,
                account_name="外部团队客户",
                city="广州",
                owner_id="2",
                creator_id="2",
            ),
            Opportunity(
                id=901,
                public_id="opp_99999999999999999999999999999991",
                team_id=2,
                opportunity_number="OPP-FOREIGN-901",
                opportunity_name="外部团队商机",
                customer_id=901,
                total_amount=Decimal("9000"),
                user_count=90,
                unit_price=Decimal("100"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                purchase_type="NEW",
                expected_closing_date=date(2026, 9, 30),
                owner_id="2",
                creator_id="2",
            ),
            Contract(
                id=901,
                team_id=2,
                contract_number="CT-FOREIGN-901",
                contract_name="外部团队合同",
                customer_id=901,
                opportunity_id=901,
                user_count=90,
                total_amount=Decimal("9000"),
                license_type="SUBSCRIPTION",
                subscription_years=1,
                standard_unit_price=Decimal("100"),
                owner_id="2",
                creator_id="2",
            ),
            PaymentPlan(
                id=901,
                team_id=1,
                contract_id=901,
                plan_number="PP-CROSS-TEAM-901",
                stage_name="异常跨团队计划",
                planned_amount=Decimal("9000"),
                due_date=date(2026, 9, 30),
                status=PaymentPlanStatus.PENDING,
            ),
        ]
    )
    db_session.commit()

    plans, total = payment_plan_crud.list_plans(
        db_session,
        team_id=1,
        skip=0,
        limit=10,
        filters=[],
        sorts=[],
    )

    assert total == 2
    assert {plan.plan_number for plan in plans} == {"PP-001", "PP-002"}


def test_payment_record_filters_by_derived_invoice_title(db_session):
    _seed_payment_graph(db_session)

    records, total = payment_record_crud.list_records(
        db_session,
        team_id=1,
        skip=0,
        limit=10,
        filters=[
            {"field": "invoice_title_text", "op": "contains", "value": "Beta"},
        ],
        sorts=[{"field": "owner_name", "direction": "asc"}],
    )

    assert total == 1
    assert [record.record_number for record in records] == ["PR-002"]


def test_payment_record_invoice_title_does_not_cross_team_boundary(db_session):
    _seed_payment_graph(db_session)
    db_session.add(
        InvoiceApplication(
            team_id=2,
            application_number="INV-FOREIGN",
            customer_id=1,
            contract_id=1,
            opportunity_id=1,
            payment_plan_id=1,
            payment_record_id=1,
            invoice_amount=Decimal("1000"),
            invoice_type=InvoiceType.VAT_NORMAL,
            status=InvoiceApplicationStatus.ISSUED,
            applicant_id="1",
            invoice_title_type="COMPANY",
            invoice_title_text="跨团队机密抬头",
            invoice_taxpayer_id="TAX-FOREIGN",
        )
    )
    db_session.commit()

    records, total = payment_record_crud.list_records(
        db_session,
        team_id=1,
        skip=0,
        limit=10,
        filters=[
            {"field": "invoice_title_text", "op": "contains", "value": "机密"},
        ],
        sorts=[],
    )

    assert total == 0
    assert records == []


def test_invoice_effective_status_does_not_cross_team_boundary(db_session):
    _seed_payment_graph(db_session)
    db_session.add_all(
        [
            InvoiceReissueApplication(
                team_id=2,
                application_number="REISSUE-FOREIGN",
                original_invoice_application_id=1,
                applicant_id="1",
                reason="跨团队重开发票",
                status=InvoiceReissueApplicationStatus.COMPLETED,
                invoice_title_type="COMPANY",
                invoice_title_text="Foreign Reissue",
                invoice_taxpayer_id="TAX-FOREIGN",
                invoice_amount=Decimal("800"),
                invoice_type=InvoiceType.VAT_NORMAL,
                new_invoice_file_path="foreign-reissue.pdf",
            ),
            InvoiceRedOffset(
                team_id=2,
                invoice_application_id=2,
                source_type=InvoiceRedOffsetSourceType.MANUAL,
                red_invoice_file_path="foreign-red-offset.pdf",
                reason="跨团队冲红",
                created_by="1",
            ),
        ]
    )
    db_session.commit()

    for effective_status in ("REISSUED", "RED_OFFSET"):
        applications, total = invoice_application_crud.list_applications(
            db_session,
            team_id=1,
            filters=[
                {
                    "field": "invoice_effective_status",
                    "op": "eq",
                    "value": effective_status,
                }
            ],
            sorts=[],
        )

        assert total == 0
        assert applications == []


def test_derived_enum_empty_operators_execute_instead_of_being_skipped(db_session):
    _seed_payment_graph(db_session)

    invoices, invoice_total = invoice_application_crud.list_applications(
        db_session,
        team_id=1,
        filters=[
            {"field": "invoice_effective_status", "op": "is_empty", "value": None},
        ],
        sorts=[],
    )
    records, record_total = payment_record_crud.list_records(
        db_session,
        team_id=1,
        filters=[
            {"field": "approval_status", "op": "is_empty", "value": None},
        ],
        sorts=[],
    )

    assert invoice_total == 0
    assert invoices == []
    assert record_total == 0
    assert records == []


def test_payment_list_query_unknown_field_is_http_400(db_session):
    _seed_payment_graph(db_session)

    with pytest.raises(HTTPException) as exc_info:
        run_or_400(
            lambda: payment_plan_crud.list_plans(
                db_session,
                team_id=1,
                filters=[{"field": "missing_field", "op": "eq", "value": "x"}],
                sorts=[],
            )
        )

    assert exc_info.value.status_code == 400
    assert "missing_field" in str(exc_info.value.detail)


def test_unified_invoice_query_does_not_mix_legacy_invoice_type_filter(db_session):
    _seed_payment_graph(db_session)

    applications, total = invoice_application_crud.list_applications(
        db_session,
        team_id=1,
        invoice_type="LEGACY_ONLY_VALUE",
        filters=[],
        sorts=[],
    )

    assert total == 2
    assert {application.application_number for application in applications} == {"INV-001", "INV-002"}


def test_unified_payment_plan_query_does_not_mix_legacy_due_date_filter(db_session):
    _seed_payment_graph(db_session)

    plans, total = payment_plan_crud.list_plans(
        db_session,
        team_id=1,
        due_date_start=date(2026, 9, 15),
        filters=[],
        sorts=[],
    )

    assert total == 2
    assert {plan.plan_number for plan in plans} == {"PP-001", "PP-002"}


def test_unified_payment_record_query_does_not_mix_legacy_amount_filter(db_session):
    _seed_payment_graph(db_session)

    records, total = payment_record_crud.list_records(
        db_session,
        team_id=1,
        min_amount=Decimal("1000"),
        filters=[],
        sorts=[],
    )

    assert total == 2
    assert {record.record_number for record in records} == {"PR-001", "PR-002"}
