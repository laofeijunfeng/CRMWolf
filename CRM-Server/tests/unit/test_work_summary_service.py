from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.contract import Contract, ContractStatus
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceType
from app.models.license_application import LicenseApplication, LicenseApplicationStatus
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.permission import Permission
from app.models.procurement import OpportunityStageSnapshot
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.sales_commitment import FollowUpTask, FollowUpTaskSourceType, FollowUpTaskStatus, SalesCommitment
from app.models.user import User
from app.models.user_role import UserRole
from app.services.work_summary_service import WorkSummaryService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Customer.__table__,
        CustomerMember.__table__,
        CustomerActivity.__table__,
        Opportunity.__table__,
        OpportunityStageSnapshot.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceApplication.__table__,
        LicenseApplication.__table__,
        SalesCommitment.__table__,
        FollowUpTask.__table__,
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
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _seed_customer(db, *, customer_id=101, public_id="cus_test_101", owner_id="9", member_user_id="2"):
    customer = Customer(
        id=customer_id,
        public_id=public_id,
        team_id=1,
        account_name=f"测试客户 {customer_id}",
        city="广州",
        owner_id=owner_id,
        creator_id=owner_id,
    )
    db.add(customer)
    if member_user_id is not None:
        db.add(
            CustomerMember(
                id=customer_id + 1000,
                team_id=1,
                customer_id=customer_id,
                user_id=member_user_id,
                member_role="PRESALES",
                access_level="FOLLOW_UP",
                created_by=owner_id,
                is_active=True,
            )
        )
    return customer


def _seed_completed_task(
    db,
    *,
    customer_id=101,
    owner_id="2",
    public_id="fut_test_001",
    task_id: int | None = None,
    title="确认预算进展",
    due_at=datetime(2026, 8, 5, 9, 0, 0),
    completed_at=datetime(2026, 8, 5, 17, 30, 0),
):
    task = FollowUpTask(
        id=task_id if task_id is not None else (1001 if owner_id == "2" else 1002),
        public_id=public_id,
        team_id=1,
        customer_id=customer_id,
        owner_id=owner_id,
        creator_id=owner_id,
        title=title,
        description="客户上周说要看预算",
        status=FollowUpTaskStatus.COMPLETED,
        due_at=due_at,
        due_at_text="周三",
        due_at_granularity="DATETIME",
        due_at_timezone="Asia/Shanghai",
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        source_key=f"activity:{public_id}",
        confidence=1.0,
        task_hash=f"hash-{public_id}",
        completed_at=completed_at,
    )
    db.add(task)
    return task


def _seed_activity(
    db,
    *,
    customer_id=101,
    owner_id="2",
    activity_id=2001,
    title="微信同步试用",
    occurred_at=datetime(2026, 8, 6, 9, 0, 0),
):
    db.add(
        CustomerActivity(
            id=activity_id,
            team_id=1,
            customer_id=customer_id,
            activity_kind="WECHAT_FOLLOW_UP",
            title=title,
            source_content="客户认可试用方案，已同步下一步演示安排",
            summary="客户认可试用方案",
            next_action="周五演示",
            occurred_at=occurred_at,
            owner_id=owner_id,
            creator_id=owner_id,
        )
    )


def _seed_business_events(db, *, customer_id=101, owner_id="2"):
    opportunity = Opportunity(
        id=3001,
        public_id="opp_00000000000000000000000000003001",
        team_id=1,
        opportunity_number="OPP-2026-3001",
        opportunity_name="测试客户 CRM 项目",
        customer_id=customer_id,
        current_stage_name="方案确认",
        total_amount=Decimal("100000"),
        user_count=100,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        purchase_type="NEW",
        expected_closing_date=date(2026, 9, 30),
        owner_id=owner_id,
        creator_id=owner_id,
    )
    db.add(opportunity)
    db.flush()
    db.add(
        OpportunityStageSnapshot(
            id=3101,
            team_id=1,
            opportunity_id=opportunity.id,
            procurement_stage_template_id=1,
            stage_name="方案确认",
            win_probability=60,
            template_sort_order=2,
            template_code="SOLUTION",
            snapshot_version=1,
            entered_at=datetime(2026, 8, 4, 10, 0, 0),
        )
    )
    contract = Contract(
        id=4001,
        team_id=1,
        contract_number="C-2026-4001",
        contract_name="测试客户 CRM 合同",
        customer_id=customer_id,
        opportunity_id=opportunity.id,
        user_count=100,
        total_amount=Decimal("100000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        standard_unit_price=Decimal("1000"),
        status=ContractStatus.SIGNED,
        signing_date=date(2026, 8, 5),
        owner_id=owner_id,
        creator_id=owner_id,
        created_time=datetime(2026, 8, 5, 11, 0, 0),
    )
    db.add(contract)
    db.flush()
    plan = PaymentPlan(
        id=5001,
        team_id=1,
        contract_id=contract.id,
        plan_number="PP-2026-5001",
        stage_name="首付款",
        planned_amount=Decimal("50000"),
        due_date=date(2026, 8, 15),
        status=PaymentPlanStatus.PENDING,
    )
    db.add(plan)
    db.flush()
    record = PaymentRecord(
        id=6001,
        team_id=1,
        record_number="PR-2026-6001",
        payment_plan_id=plan.id,
        actual_amount=Decimal("50000"),
        actual_payer_name="测试客户",
        payment_date=date(2026, 8, 6),
        creator_id=owner_id,
        creator_name="售前顾问",
        confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        created_time=datetime(2026, 8, 6, 12, 0, 0),
    )
    db.add(record)
    db.flush()
    db.add(
        InvoiceApplication(
            id=7001,
            team_id=1,
            application_number="INV-2026-7001",
            customer_id=customer_id,
            contract_id=contract.id,
            opportunity_id=opportunity.id,
            payment_plan_id=plan.id,
            payment_record_id=record.id,
            invoice_amount=Decimal("50000"),
            invoice_type=InvoiceType.VAT_NORMAL,
            status=InvoiceApplicationStatus.ISSUED,
            applicant_id=owner_id,
            invoice_title_type="COMPANY",
            invoice_title_text="测试客户",
            invoice_taxpayer_id="91440101TESTCRM",
            issued_time=datetime(2026, 8, 6, 13, 0, 0),
            created_time=datetime(2026, 8, 6, 12, 30, 0),
        )
    )
    db.add(
        LicenseApplication(
            id=8001,
            team_id=1,
            application_number="LIC-2026-8001",
            customer_id=customer_id,
            expiry_date=date(2027, 12, 31),
            license_type="TRIAL",
            authorized_users=10,
            applicant_id=owner_id,
            status=LicenseApplicationStatus.APPROVED,
            approved_time=datetime(2026, 8, 6, 14, 0, 0),
            created_time=datetime(2026, 8, 6, 13, 30, 0),
        )
    )


def _seed_other_owner_noise(db):
    _seed_completed_task(
        db,
        owner_id="9",
        public_id="fut_test_other_owner",
    )
    _seed_activity(db, owner_id="9", activity_id=2002)


@pytest.fixture(autouse=True)
def _fixed_business_now(monkeypatch):
    monkeypatch.setattr("app.utils.time.business_now", lambda: datetime(2026, 8, 6, 10, 0, 0))


def test_list_completed_work_returns_structured_task_activity_and_business_facts():
    engine, db = _db_session()
    try:
        _seed_customer(db)
        task = _seed_completed_task(db)
        _seed_activity(db)
        _seed_business_events(db)
        _seed_other_owner_noise(db)
        db.commit()

        result = WorkSummaryService().list_completed_work(db, team_id=1, user_id=2, window="this_week")

        assert result["completed_tasks"][0]["id"] == task.public_id
        assert [activity["title"] for activity in result["activities"]] == ["微信同步试用"]
        assert {
            "opportunity_stage_entered",
            "contract_signed",
            "payment_recorded",
            "invoice_application",
            "license_application",
        }.issubset(result["source_counts"])
        assert result["source_status"] == {
            "completed_tasks": "queried",
            "customer_activities": "queried",
            "business_events": "queried",
        }
        assert result["fact_source_scope"]["payment_record"]["owner_field"] == "creator_id_or_commission_member_id"
        assert result["usage_policy"]["fact_source"] == "mysql"
        assert result["total"] == 7
        assert {item["attribution"]["user_id"] for item in result["items"]} == {"2"}
    finally:
        db.close()
        engine.dispose()


def test_list_completed_work_filters_by_customer_visibility_and_member_access():
    engine, db = _db_session()
    try:
        _seed_customer(db, owner_id="9", member_user_id="2")
        _seed_completed_task(db)
        db.commit()

        result = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="this_week",
            customer_public_id="cus_test_101",
        )

        assert result["total"] == 1
        assert result["filters"]["customer_id"] == "cus_test_101"
    finally:
        db.close()
        engine.dispose()


def test_list_completed_work_rejects_invisible_customer_filter():
    engine, db = _db_session()
    try:
        _seed_customer(db, public_id="cus_test_102", customer_id=102, owner_id="9", member_user_id=None)
        db.commit()

        with pytest.raises(PermissionError, match="无权查看该客户"):
            WorkSummaryService().list_completed_work(
                db,
                team_id=1,
                user_id=2,
                window="this_week",
                customer_public_id="cus_test_102",
            )
    finally:
        db.close()
        engine.dispose()


def test_list_completed_work_include_flags_and_agent_payload_identifiers():
    engine, db = _db_session()
    try:
        _seed_customer(db)
        _seed_completed_task(db)
        _seed_activity(db)
        _seed_business_events(db)
        db.commit()

        result = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="this_week",
            include_tasks=False,
            include_activities=True,
            include_business_events=False,
        )

        assert result["source_status"] == {
            "completed_tasks": "skipped",
            "customer_activities": "queried",
            "business_events": "skipped",
        }
        assert result["completed_tasks"] == []
        assert result["business_events"] == []
        assert result["items"][0]["customer"]["id"] == "cus_test_101"
        assert "id" not in result["items"][0]["payload"]
        assert "source_activity_id" not in result["items"][0]["payload"]
    finally:
        db.close()
        engine.dispose()


def test_list_completed_work_supports_last_week_this_month_and_custom_range():
    engine, db = _db_session()
    try:
        _seed_customer(db)
        _seed_completed_task(
            db,
            task_id=1101,
            public_id="fut_test_last_week",
            title="上周确认试用名单",
            due_at=datetime(2026, 7, 29, 9, 0, 0),
            completed_at=datetime(2026, 7, 29, 17, 0, 0),
        )
        _seed_activity(
            db,
            activity_id=2101,
            title="月初方案同步",
            occurred_at=datetime(2026, 8, 1, 10, 0, 0),
        )
        _seed_completed_task(db)
        db.commit()

        last_week = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="last_week",
            include_activities=False,
            include_business_events=False,
        )
        this_month = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="this_month",
            include_business_events=False,
        )
        custom = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="custom",
            start_at="2026-08-01",
            end_at="2026-08-01",
            include_tasks=False,
            include_business_events=False,
        )

        assert [item["title"] for item in last_week["items"]] == ["上周确认试用名单"]
        assert this_month["filters"]["starts_at"] == "2026-08-01T00:00:00"
        assert this_month["source_total_counts"]["completed_follow_up_task"] == 1
        assert this_month["source_total_counts"]["customer_activity"] == 1
        assert [item["title"] for item in custom["items"]] == ["月初方案同步"]
        assert custom["filters"]["ends_at"] == "2026-08-02T00:00:00"
    finally:
        db.close()
        engine.dispose()


def test_list_completed_work_returns_truncation_and_next_cursor_for_reports():
    engine, db = _db_session()
    try:
        _seed_customer(db)
        _seed_activity(db, activity_id=2201, title="跟进 A", occurred_at=datetime(2026, 8, 6, 10, 0, 0))
        _seed_activity(db, activity_id=2202, title="跟进 B", occurred_at=datetime(2026, 8, 6, 9, 0, 0))
        _seed_activity(db, activity_id=2203, title="跟进 C", occurred_at=datetime(2026, 8, 6, 8, 0, 0))
        db.commit()

        first_page = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="today",
            include_tasks=False,
            include_business_events=False,
            limit=2,
        )
        second_page = WorkSummaryService().list_completed_work(
            db,
            team_id=1,
            user_id=2,
            window="today",
            include_tasks=False,
            include_business_events=False,
            cursor=first_page["next_cursor"],
            limit=2,
        )

        assert [item["title"] for item in first_page["items"]] == ["跟进 A", "跟进 B"]
        assert first_page["truncated"] is True
        assert first_page["pagination"]["next_cursor"] == first_page["next_cursor"]
        assert first_page["available_total"] == 3
        assert first_page["source_total_counts"]["customer_activity"] == 3
        assert [item["title"] for item in second_page["items"]] == ["跟进 C"]
        assert second_page["truncated"] is False
        assert second_page["next_cursor"] is None
    finally:
        db.close()
        engine.dispose()
