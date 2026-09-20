from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import customer_ai as customer_ai_api
from app.api import customer_enrichment as customer_enrichment_api
from app.api import customers as customers_api
from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.models.industry import Industry
from app.schemas.customer import ConvertLeadToCustomer
from app.services.ai_parser import customer_parser as customer_parser_module
from app.services.ai_parser.customer_parser import CustomerAIParser
from app.services.customer_enrichment_contracts import CustomerEnrichmentJobStatus
from app.services.customer_enrichment_plan import ACTIVE_CUSTOMER_ENRICHMENT_PLAN, CustomerEnrichmentPlan
from app.services.customer_enrichment_reconciliation_service import (
    CustomerEnrichmentReconciliationResult,
)
from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest
from app.services.customer_lifecycle_post_commit_coordinator import CustomerLifecyclePostCommitCoordinator


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class _RequestData(SimpleNamespace):
    def model_copy(self, *, update=None):
        values = vars(self).copy()
        values.update(update or {})
        return type(self)(**values)


@pytest.fixture
def customer_and_user():
    return (
        SimpleNamespace(
            id=101,
            public_id="cus_101",
            account_name="客户A",
            owner_id="9",
            team_id=2,
            version=1,
        ),
        SimpleNamespace(id=9, name="管理员"),
    )


def test_add_customer_member_uses_unified_created_event(monkeypatch, customer_and_user):
    customer, user = customer_and_user
    member = SimpleNamespace(
        id=301,
        team_id=2,
        customer_id=101,
        user_id="12",
        member_role="PRESALES",
        access_level="VIEW",
        remark="协同",
        is_active=True,
    )
    calls = []

    monkeypatch.setattr(customers_api, "check_customer_member_manage_permission", lambda *args: customer)
    monkeypatch.setattr(customers_api.team_crud, "is_member", lambda *args: True)
    monkeypatch.setattr(customers_api.customer_member_crud, "create_or_restore", lambda **kwargs: member)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(scheduled=True),
    )
    monkeypatch.setattr(customers_api, "_build_customer_member_response", lambda *args: member)

    result = customers_api.add_customer_member(
        "cus_101",
        _RequestData(user_id=12, member_role="PRESALES", access_level="VIEW", remark="协同"),
        team_id=2,
        current_user=user,
        db=object(),
    )

    assert result is member
    assert calls[0]["business_object"] is member
    assert calls[0]["source_type"] == "customer_member"
    assert calls[0]["change_type"] == "created"
    assert calls[0]["actor_id"] == "9"


def test_update_customer_member_uses_unified_updated_event(monkeypatch, customer_and_user):
    customer, user = customer_and_user
    member = SimpleNamespace(
        id=301,
        team_id=2,
        customer_id=101,
        user_id="12",
        member_role="PRESALES",
        access_level="VIEW",
        remark="协同",
        is_active=True,
    )
    calls = []

    monkeypatch.setattr(customers_api, "check_customer_member_manage_permission", lambda *args: customer)
    monkeypatch.setattr(customers_api.customer_member_crud, "get_by_id", lambda *args: member)
    monkeypatch.setattr(customers_api.customer_member_crud, "update", lambda *args: member)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(scheduled=True),
    )
    monkeypatch.setattr(customers_api, "_build_customer_member_response", lambda *args: member)

    result = customers_api.update_customer_member(
        "cus_101",
        301,
        _RequestData(member_role="SALES", access_level="FOLLOW_UP", remark="重点协同"),
        team_id=2,
        current_user=user,
        db=object(),
    )

    assert result is member
    assert calls[0]["business_object"] is member
    assert calls[0]["change_type"] == "updated"


def test_remove_customer_member_uses_unified_deleted_event(monkeypatch, customer_and_user):
    customer, user = customer_and_user
    member = SimpleNamespace(
        id=301,
        team_id=2,
        customer_id=101,
        user_id="12",
        member_role="PRESALES",
        access_level="VIEW",
        remark="协同",
        is_active=False,
    )
    calls = []

    monkeypatch.setattr(customers_api, "check_customer_member_manage_permission", lambda *args: customer)
    monkeypatch.setattr(customers_api.customer_member_crud, "get_by_id", lambda *args: member)
    monkeypatch.setattr(customers_api.customer_member_crud, "deactivate", lambda *args: None)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(scheduled=True),
    )

    result = customers_api.remove_customer_member(
        "cus_101",
        301,
        team_id=2,
        current_user=user,
        db=object(),
    )

    assert result.message == "移除成功"
    assert calls[0]["business_object"] is member
    assert calls[0]["change_type"] == "deleted"


def _conversion_rows():
    lead = SimpleNamespace(id=44, public_id="lead_44", lead_name="线索客户")
    customer = SimpleNamespace(
        id=101,
        public_id="cus_101",
        account_name="线索客户",
        owner_id="9",
        team_id=2,
        version=1,
        industry=None,
    )
    contact = SimpleNamespace(id=301, name="李华")
    return lead, customer, contact


class _LifecycleSession:
    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _after_commit_coordinator_calls():
    calls = SimpleNamespace(enrichment_kicks=[], publication_profile_kicks=[], coordinator_profile_kicks=[])

    class JobService:
        def ensure(self, db, **kwargs):
            return SimpleNamespace(public_id="cej_1")

        def kick(self, request):
            calls.enrichment_kicks.append(request.job_public_id)

    class IntelligenceService:
        def enqueue_customer_lifecycle_refresh_after_commit(self, **kwargs):
            request = CustomerIntelligenceCommittedEventRequest(
                request_id="profile-1",
                event=SimpleNamespace(),
                scope="full",
            )
            calls.publication_profile_kicks.append(request.request_id)
            return request

    class ProfileService:
        def kick_committed_event_refresh(self, request):
            calls.coordinator_profile_kicks.append(request.request_id)

    coordinator = CustomerLifecyclePostCommitCoordinator(
        job_service=JobService(),
        intelligence_service=IntelligenceService(),
        profile_refresh_service=ProfileService(),
        session_factory=_LifecycleSession,
        settle_seconds=0,
        profile_gate_max_seconds=0,
        max_attempts=1,
    )
    return coordinator, calls


@pytest.mark.asyncio
async def test_legacy_conversion_uses_lifecycle_coordinator_after_commit(monkeypatch):
    lead, customer, contact = _conversion_rows()
    db = MagicMock()
    lifecycle_calls = []
    kick_calls = []
    work = SimpleNamespace(enrichment_request=None, profile_request=None, warnings=())

    monkeypatch.setattr(customers_api.lead_crud, "get_by_public_id", lambda *args: lead)
    monkeypatch.setattr(customers_api, "_ensure_customer_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "convert_from_lead",
        lambda **kwargs: (customer, contact),
    )
    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "enqueue_after_commit",
        lambda **kwargs: lifecycle_calls.append(kwargs) or work,
    )

    def fail_kick(value):
        kick_calls.append(value)
        raise RuntimeError("kick down")

    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "kick",
        fail_kick,
    )
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: SimpleNamespace(id=1),
    )

    response = await customers_api.convert_from_lead(
        ConvertLeadToCustomer(lead_id="lead_44", product_public_id="prd_1"),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="管理员"),
        db=db,
        operation_id=None,
        idempotency_key=None,
        correlation_id=None,
    )

    assert response.customer_id == "cus_101"
    assert lifecycle_calls == [
        {
            "customer": customer,
            "actor_id": "9",
            "trigger_type": "customer_converted_from_lead",
            "source_lead_id": 44,
        }
    ]
    assert kick_calls == [work]



@pytest.mark.asyncio
async def test_legacy_conversion_after_commit_profile_is_kicked_exactly_once(monkeypatch):
    lead, customer, contact = _conversion_rows()
    coordinator, calls = _after_commit_coordinator_calls()

    monkeypatch.setattr(customers_api.lead_crud, "get_by_public_id", lambda *args: lead)
    monkeypatch.setattr(customers_api, "_ensure_customer_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "convert_from_lead",
        lambda **kwargs: (customer, contact),
    )
    monkeypatch.setattr(customers_api, "customer_lifecycle_post_commit_coordinator", coordinator)
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: SimpleNamespace(id=1),
    )

    response = await customers_api.convert_from_lead(
        ConvertLeadToCustomer(lead_id="lead_44", product_public_id="prd_1"),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="管理员"),
        db=MagicMock(),
        operation_id=None,
        idempotency_key=None,
        correlation_id=None,
    )

    assert response.customer_id == "cus_101"
    assert calls.publication_profile_kicks == ["profile-1"]
    assert calls.coordinator_profile_kicks == []
    assert calls.enrichment_kicks == ["cej_1"]

@pytest.mark.asyncio
async def test_modern_conversion_prepares_before_commit_and_kicks_after(monkeypatch):
    lead, customer, contact = _conversion_rows()
    order: list[str] = []
    db = MagicMock()
    db.commit.side_effect = lambda: order.append("commit")
    execution = SimpleNamespace(operation_id="op_1", result_json=None)
    work = SimpleNamespace(enrichment_request=None, profile_request=None, warnings=())
    lifecycle_calls = []

    monkeypatch.setattr(
        customers_api.command_execution_service,
        "begin",
        lambda *args, **kwargs: (execution, False),
    )
    monkeypatch.setattr(customers_api.lead_crud, "get_by_public_id", lambda *args: lead)
    monkeypatch.setattr(customers_api, "_ensure_customer_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "convert_from_lead",
        lambda **kwargs: (customer, contact),
    )

    def succeed(db_session, execution_row, *, data, **kwargs):
        execution_row.result_json = {"data": data}

    monkeypatch.setattr(customers_api.command_execution_service, "succeed", succeed)
    monkeypatch.setattr(
        customers_api.command_execution_service,
        "to_response_payload",
        lambda value: {"operation_id": value.operation_id, "status": "SUCCEEDED", **value.result_json},
    )

    def prepare(db_session, **kwargs):
        order.append("prepare")
        lifecycle_calls.append(kwargs)
        return work

    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "prepare_in_transaction",
        prepare,
    )
    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "kick",
        lambda value: order.append("kick") or (),
    )
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: SimpleNamespace(id=1),
    )

    response = await customers_api.convert_from_lead(
        ConvertLeadToCustomer(lead_id="lead_44", product_public_id="prd_1"),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="管理员"),
        db=db,
        operation_id="op_1",
        idempotency_key="idem_1",
        correlation_id=None,
    )

    assert response.customer_id == "cus_101"
    assert order == ["prepare", "commit", "kick"]
    assert lifecycle_calls == [
        {
            "customer": customer,
            "actor_id": "9",
            "trigger_type": "customer_converted_from_lead",
            "source_lead_id": 44,
        }
    ]


@pytest.mark.asyncio
async def test_customer_ai_submit_uses_lifecycle_coordinator(monkeypatch):
    customer = SimpleNamespace(
        id=101,
        public_id="cus_101",
        account_name="AI客户",
        city="上海",
        status=1,
        team_id=2,
        industry=None,
    )
    parser = SimpleNamespace()
    parser.create_entity = lambda **kwargs: None
    parser.post_create_actions = lambda **kwargs: None

    async def create_entity(**kwargs):
        return customer

    async def post_create_actions(**kwargs):
        return None

    parser.create_entity = create_entity
    parser.post_create_actions = post_create_actions
    work = SimpleNamespace(enrichment_request=None, profile_request=None, warnings=())
    lifecycle_calls = []
    kick_calls = []
    monkeypatch.setattr(customer_ai_api.EntityAIParserFactory, "get_parser", lambda kind: parser)
    monkeypatch.setattr(customer_ai_api, "_ensure_customer_name_available", lambda *args: None)
    monkeypatch.setattr(
        customer_ai_api.customer_lifecycle_post_commit_coordinator,
        "enqueue_after_commit",
        lambda **kwargs: lifecycle_calls.append(kwargs) or work,
    )

    def fail_ai_kick(value):
        kick_calls.append(value)
        raise RuntimeError("kick down")

    monkeypatch.setattr(
        customer_ai_api.customer_lifecycle_post_commit_coordinator,
        "kick",
        fail_ai_kick,
    )
    payload = SimpleNamespace(
        customer_info=SimpleNamespace(account_name="AI客户", model_dump=lambda: {"account_name": "AI客户"}),
        contact_info=SimpleNamespace(model_dump=lambda: {"contact_name": "李华"}),
        follow_up_info=None,
    )

    result = await customer_ai_api.create_customer_from_ai(
        payload,
        current_user=SimpleNamespace(id=9),
        team_id=2,
        db=object(),
    )

    assert result["public_id"] == "cus_101"
    assert lifecycle_calls == [
        {
            "customer": customer,
            "actor_id": "9",
            "trigger_type": "customer_created",
        }
    ]
    assert kick_calls == [work]


@pytest.mark.asyncio
async def test_customer_ai_after_commit_profile_is_kicked_exactly_once(monkeypatch):
    customer = SimpleNamespace(
        id=101,
        public_id="cus_101",
        account_name="AI客户",
        city="上海",
        status=1,
        team_id=2,
        industry=None,
    )
    coordinator, calls = _after_commit_coordinator_calls()

    async def create_entity(**kwargs):
        return customer

    async def post_create_actions(**kwargs):
        return None

    parser = SimpleNamespace(
        create_entity=create_entity,
        post_create_actions=post_create_actions,
    )
    monkeypatch.setattr(customer_ai_api.EntityAIParserFactory, "get_parser", lambda kind: parser)
    monkeypatch.setattr(customer_ai_api, "_ensure_customer_name_available", lambda *args: None)
    monkeypatch.setattr(customer_ai_api, "customer_lifecycle_post_commit_coordinator", coordinator)
    payload = SimpleNamespace(
        customer_info=SimpleNamespace(account_name="AI客户", model_dump=lambda: {"account_name": "AI客户"}),
        contact_info=SimpleNamespace(model_dump=lambda: {"contact_name": "李华"}),
        follow_up_info=None,
    )

    result = await customer_ai_api.create_customer_from_ai(
        payload,
        current_user=SimpleNamespace(id=9),
        team_id=2,
        db=object(),
    )

    assert result["public_id"] == "cus_101"
    assert calls.publication_profile_kicks == ["profile-1"]
    assert calls.coordinator_profile_kicks == []
    assert calls.enrichment_kicks == ["cej_1"]

@pytest.mark.asyncio
async def test_customer_parser_keeps_industry_hint_non_authoritative(monkeypatch):
    captured = {}
    customer = SimpleNamespace(id=101, public_id="cus_101", industry=None)

    monkeypatch.setattr(
        customer_parser_module,
        "industry_crud",
        SimpleNamespace(
            get_industry_hierarchy=lambda db: (_ for _ in ()).throw(
                AssertionError("legacy industry matcher must not run")
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        customer_parser_module,
        "resolve_source_for_ai",
        lambda db, team_id, source: SimpleNamespace(public_id="src_online"),
    )
    monkeypatch.setattr(
        customer_parser_module,
        "first_active_product",
        lambda db, team_id: SimpleNamespace(public_id="prd_crm"),
    )

    def create_customer(**kwargs):
        captured["customer_create"] = kwargs["obj_in"]
        return customer

    monkeypatch.setattr(customer_parser_module.customer_crud, "create", create_customer)
    monkeypatch.setattr(
        customer_parser_module.contact_crud,
        "create",
        lambda **kwargs: SimpleNamespace(id=301),
    )

    created = await CustomerAIParser().create_entity(
        db=object(),
        parsed_data={
            "customer_info": {
                "account_name": "AI客户",
                "city": "上海",
                "company_scale": None,
                "source": "线上注册",
                "industry_hint": "SaaS公司",
            },
            "contact_info": {
                "contact_name": "李华",
                "contact_phone": "13800138000",
                "contact_position": "负责人",
                "contact_gender": "0",
            },
        },
        user_id="9",
        team_id=2,
    )

    assert created is customer
    assert captured["customer_create"].industry is None



@pytest.mark.asyncio
async def test_customer_parser_post_create_actions_does_not_trigger_profile_refresh(monkeypatch):
    parser = CustomerAIParser()
    refresh_calls = []
    monkeypatch.setattr(
        customer_parser_module,
        "customer_intelligence_refresh_service",
        SimpleNamespace(trigger_customer_created_refresh=lambda *args, **kwargs: refresh_calls.append(kwargs)),
        raising=False,
    )

    await parser.post_create_actions(
        db=object(),
        entity=SimpleNamespace(id=101, public_id="cus_101"),
        parsed_data={"follow_up_info": None},
        user_id="9",
        team_id=2,
    )

    assert refresh_calls == []


class _QueryRows:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        del args
        return self

    def order_by(self, *args):
        del args
        return self

    def offset(self, value):
        self.rows = self.rows[value:]
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    def all(self):
        return self.rows

    def count(self):
        return len(self.rows)


class _ListJobsDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *entities):
        del entities
        return _QueryRows(self.rows)


def test_enrichment_job_list_passes_team_scope_and_omits_sensitive_payloads(monkeypatch):
    job = SimpleNamespace(
        public_id="cej_safe",
        team_id=2,
        customer_id=8,
        purpose="HISTORICAL_BACKFILL",
        plan_version="customer-initial-v1",
        requested_fields_json=["industry"],
        status="EXHAUSTED",
        attempt_count=3,
        max_attempts=3,
        requeue_count=0,
        profile_refresh_request_id=None,
        available_at=None,
        next_attempt_at=None,
        first_attempt_finished_at=None,
        profile_gate_timed_out_at=datetime(2026, 9, 20, 10, 0, 30),
        created_time=None,
        updated_time=None,
        result_json={"prompt": "secret", "customer_mobile": "13800000000"},
        error_message="prompt included customer mobile",
    )
    customer = SimpleNamespace(id=8, public_id="cus_8", team_id=2, account_name="PII name")
    captured = {}

    def fake_list(db, **kwargs):
        del db
        captured.update(kwargs)
        return [(job, customer)], 1

    monkeypatch.setattr(customer_enrichment_api, "list_enrichment_jobs_for_team", fake_list)

    response = customer_enrichment_api.list_enrichment_jobs(
        status_filter="EXHAUSTED",
        purpose="HISTORICAL_BACKFILL",
        skip=0,
        limit=20,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert captured == {
        "team_id": 2,
        "status_filter": "EXHAUSTED",
        "purpose": "HISTORICAL_BACKFILL",
        "skip": 0,
        "limit": 20,
    }
    dumped = response.model_dump()
    assert dumped["items"][0]["customer_id"] == "cus_8"
    assert dumped["items"][0]["profile_gate_timed_out_at"] == datetime(2026, 9, 20, 10, 0, 30)
    assert "result_json" not in dumped["items"][0]
    assert "error_message" not in dumped["items"][0]
    assert "account_name" not in dumped["items"][0]


def test_enrichment_job_list_total_matches_joined_rows_when_orphan_exists():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Customer.__table__, CustomerEnrichmentJob.__table__],
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        customer = Customer(
            team_id=2,
            account_name="visible-customer",
            city="X",
            creator_id="9",
        )
        db.add(customer)
        db.flush()
        now = customer_enrichment_api.business_now()
        db.add_all(
            [
                CustomerEnrichmentJob(
                    team_id=2,
                    customer_id=customer.id,
                    purpose="HISTORICAL_BACKFILL",
                    plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
                    requested_fields_json=["industry"],
                    status="QUEUED",
                    available_at=now,
                    attempt_count=0,
                    max_attempts=3,
                    run_id="visible-run",
                    graph_thread_id="visible-thread",
                    requeue_count=0,
                ),
                CustomerEnrichmentJob(
                    team_id=2,
                    customer_id=999,
                    purpose="HISTORICAL_BACKFILL",
                    plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
                    requested_fields_json=["industry"],
                    status="QUEUED",
                    available_at=now,
                    attempt_count=0,
                    max_attempts=3,
                    run_id="orphan-run",
                    graph_thread_id="orphan-thread",
                    requeue_count=0,
                ),
            ]
        )
        db.flush()

        rows, total = customer_enrichment_api.list_enrichment_jobs_for_team(
            db,
            team_id=2,
            status_filter=None,
            purpose=None,
            skip=0,
            limit=20,
        )

        assert len(rows) == 1
        assert total == 1
    finally:
        db.close()
        engine.dispose()


def test_enrichment_backfill_preview_returns_exact_partition_counts(monkeypatch):
    expected = {
        "industry_null": 5,
        "existing_jobs": 2,
        "would_schedule": 3,
        "filled_skip": 4,
        "invalid_non_null": 1,
        "other_available": True,
    }
    calls = []
    monkeypatch.setattr(
        customer_enrichment_api,
        "build_backfill_preview",
        lambda db, *, team_id: calls.append((db, team_id)) or expected,
    )

    response = customer_enrichment_api.get_enrichment_backfill_preview(
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert response.model_dump() == expected
    assert calls[0][1] == 2



def test_enrichment_backfill_preview_counts_invalid_non_null_as_filled_skip():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Industry.__table__, Customer.__table__, CustomerEnrichmentJob.__table__],
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        db.add_all(
            [
                Industry(level=1, code="software", name="Software", is_active=1),
                Industry(level=1, code="other", name="Other", is_active=1),
            ]
        )
        customers = [
            Customer(team_id=2, account_name="null-existing", city="X", creator_id="9"),
            Customer(team_id=2, account_name="null-new", city="X", creator_id="9"),
            Customer(
                team_id=2,
                account_name="valid-filled",
                city="X",
                creator_id="9",
                industry="software",
            ),
            Customer(
                team_id=2,
                account_name="invalid-filled",
                city="X",
                creator_id="9",
                industry="legacy",
            ),
        ]
        db.add_all(customers)
        db.flush()
        db.add(
            CustomerEnrichmentJob(
                team_id=2,
                customer_id=customers[0].id,
                purpose="HISTORICAL_BACKFILL",
                plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
                requested_fields_json=["industry"],
                status="QUEUED",
                available_at=customer_enrichment_api.business_now(),
                attempt_count=0,
                max_attempts=3,
                run_id="run-preview",
                graph_thread_id="thread-preview",
                requeue_count=0,
            )
        )
        db.flush()

        preview = customer_enrichment_api.build_backfill_preview(db, team_id=2)

        assert preview == {
            "industry_null": 2,
            "existing_jobs": 1,
            "would_schedule": 1,
            "filled_skip": 2,
            "invalid_non_null": 1,
            "other_available": True,
        }
    finally:
        db.close()
        engine.dispose()


def test_enrichment_backfill_preview_treats_blank_as_missing_once():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Industry.__table__, Customer.__table__, CustomerEnrichmentJob.__table__],
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        db.add_all(
            [
                Industry(level=1, code="software", name="Software", is_active=1),
                Industry(level=1, code="other", name="Other", is_active=1),
            ]
        )
        customers = [
            Customer(team_id=2, account_name="blank", city="X", creator_id="9", industry="  "),
            Customer(team_id=2, account_name="filled", city="X", creator_id="9", industry="software"),
        ]
        db.add_all(customers)
        db.flush()

        preview = customer_enrichment_api.build_backfill_preview(db, team_id=2)

        assert preview["industry_null"] == 1
        assert preview["would_schedule"] == 1
        assert preview["filled_skip"] == 1
        assert preview["invalid_non_null"] == 0
    finally:
        db.close()
        engine.dispose()


def test_enrichment_backfill_preview_reports_zero_when_plan_disables_backfill(monkeypatch):
    disabled = CustomerEnrichmentPlan(
        version="customer-initial-disabled",
        fields=("industry",),
        backfill_enabled=False,
    )
    monkeypatch.setattr(customer_enrichment_api, "ACTIVE_CUSTOMER_ENRICHMENT_PLAN", disabled)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Industry.__table__, Customer.__table__, CustomerEnrichmentJob.__table__],
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        db.add(Industry(level=1, code="other", name="Other", is_active=1))
        db.add(Customer(team_id=2, account_name="missing", city="X", creator_id="9"))
        db.flush()

        preview = customer_enrichment_api.build_backfill_preview(db, team_id=2)

        assert preview["industry_null"] == 1
        assert preview["would_schedule"] == 0
    finally:
        db.close()
        engine.dispose()

def test_requeue_rejects_non_exhausted_and_filled_customer(monkeypatch):
    non_exhausted = SimpleNamespace(
        status=CustomerEnrichmentJobStatus.QUEUED.value,
        customer_id=8,
        public_id="cej_8",
        plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
        requested_fields_json=["industry"],
    )
    customer = SimpleNamespace(id=8, team_id=2, industry=None)
    monkeypatch.setattr(
        customer_enrichment_api,
        "lock_enrichment_job_and_customer",
        lambda db, *, team_id, job_public_id: (non_exhausted, customer),
    )
    with pytest.raises(HTTPException) as conflict:
        customer_enrichment_api.requeue_enrichment_job(
            "cej_8", team_id=2, current_user=SimpleNamespace(id=9), db=MagicMock()
        )
    assert conflict.value.status_code == 409

    exhausted = SimpleNamespace(
        status=CustomerEnrichmentJobStatus.EXHAUSTED.value,
        customer_id=8,
        public_id="cej_8",
        plan_version=ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
        requested_fields_json=["industry"],
    )
    filled = SimpleNamespace(id=8, team_id=2, industry="software")
    monkeypatch.setattr(
        customer_enrichment_api,
        "lock_enrichment_job_and_customer",
        lambda db, *, team_id, job_public_id: (exhausted, filled),
    )
    with pytest.raises(HTTPException) as filled_conflict:
        customer_enrichment_api.requeue_enrichment_job(
            "cej_8", team_id=2, current_user=SimpleNamespace(id=9), db=MagicMock()
        )
    assert filled_conflict.value.status_code == 409


def test_requeue_rejects_exhausted_job_from_inactive_plan(monkeypatch):
    job = SimpleNamespace(
        status=CustomerEnrichmentJobStatus.EXHAUSTED.value,
        customer_id=8,
        public_id="cej_old",
        plan_version="customer-initial-old",
        requested_fields_json=["industry"],
    )
    customer = SimpleNamespace(id=8, team_id=2, industry=None)
    monkeypatch.setattr(
        customer_enrichment_api,
        "lock_enrichment_job_and_customer",
        lambda db, *, team_id, job_public_id: (job, customer),
    )
    class CRUD:
        def requeue_exhausted(self, db, **kwargs):
            del db, kwargs
            raise AssertionError("inactive plan must be rejected before requeue")

    monkeypatch.setattr(customer_enrichment_api, "customer_enrichment_job_crud", CRUD())

    with pytest.raises(HTTPException) as conflict:
        customer_enrichment_api.requeue_enrichment_job(
            "cej_old", team_id=2, current_user=SimpleNamespace(id=9), db=MagicMock()
        )

    assert conflict.value.status_code == 409


def test_requeue_resets_same_job_commits_then_kicks(monkeypatch):
    order = []
    job = SimpleNamespace(
        id=7,
        public_id="cej_7",
        team_id=2,
        customer_id=8,
        purpose="HISTORICAL_BACKFILL",
        plan_version="customer-initial-v1",
        requested_fields_json=["industry"],
        status=CustomerEnrichmentJobStatus.EXHAUSTED.value,
        attempt_count=3,
        max_attempts=3,
        requeue_count=4,
        profile_refresh_request_id=None,
        available_at=None,
        next_attempt_at=None,
        first_attempt_finished_at=None,
        created_time=None,
        updated_time=None,
    )
    customer = SimpleNamespace(id=8, public_id="cus_8", team_id=2, industry=None)

    class DB:
        def commit(self):
            order.append("commit")

        def rollback(self):
            order.append("rollback")

    class CRUD:
        def requeue_exhausted(self, db, **kwargs):
            del db, kwargs
            job.status = CustomerEnrichmentJobStatus.QUEUED.value
            job.requeue_count += 1
            return job

    monkeypatch.setattr(
        customer_enrichment_api,
        "lock_enrichment_job_and_customer",
        lambda db, *, team_id, job_public_id: (job, customer),
    )
    monkeypatch.setattr(customer_enrichment_api, "customer_enrichment_job_crud", CRUD())
    monkeypatch.setattr(
        customer_enrichment_api.customer_enrichment_job_service,
        "kick",
        lambda request: order.append(("kick", request.job_public_id)),
    )

    response = customer_enrichment_api.requeue_enrichment_job(
        "cej_7", team_id=2, current_user=SimpleNamespace(id=9), db=DB()
    )

    assert response.job_public_id == "cej_7"
    assert response.requeue_count == 5
    assert order == ["commit", ("kick", "cej_7")]


def test_reconciliation_endpoint_returns_counts_and_routes_require_edit_all(monkeypatch):
    monkeypatch.setattr(
        customer_enrichment_api.customer_enrichment_reconciliation_service,
        "reconcile_once",
        lambda db, **kwargs: CustomerEnrichmentReconciliationResult(
            scanned=4,
            jobs_created=1,
            gates_released=1,
            gates_cancelled=2,
            refreshes_repaired=1,
            errors=1,
            next_customer_id=22,
            dry_run=kwargs["dry_run"],
        ),
    )
    db = MagicMock()
    response = customer_enrichment_api.run_enrichment_reconciliation(
        customer_enrichment_api.CustomerEnrichmentReconciliationRequest(
            limit=10, after_customer_id=3, dry_run=True
        ),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=db,
    )
    assert response.model_dump() == {
        "scanned": 4,
        "jobs_created": 1,
        "gates_released": 1,
        "gates_cancelled": 2,
        "refreshes_repaired": 1,
        "errors": 1,
        "next_customer_id": 22,
        "dry_run": True,
    }
    assert db.commit.called is False

    permission_dependencies = [
        dependency.call
        for route in customer_enrichment_api.router.routes
        if isinstance(route, APIRoute)
        for dependency in route.dependant.dependencies
        if getattr(dependency.call, "__name__", "") == "permission_checker"
    ]
    assert len(permission_dependencies) == 4
    assert all(
        "customer:edit:all" in (dependency.__closure__[0].cell_contents,)
        for dependency in permission_dependencies
    )


def test_enrichment_router_is_registered_before_dynamic_customer_route():
    from app.main import app

    matches = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path in {"/api/v1/customers/enrichment/jobs", "/api/v1/customers/{customer_id}"}
    ]
    paths = [route.path for route in matches]
    assert paths.index("/api/v1/customers/enrichment/jobs") < paths.index(
        "/api/v1/customers/{customer_id}"
    )
    enrichment_route = next(
        route for route in matches if route.path == "/api/v1/customers/enrichment/jobs"
    )
    assert enrichment_route.endpoint is customer_enrichment_api.list_enrichment_jobs
