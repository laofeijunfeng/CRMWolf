"""Backend business-scenario acceptance tests.

These tests exercise real FastAPI routes and ORM state transitions while
stubbing only unstable external boundaries such as LLM parsing and Feishu
notifications. They are intentionally broader than narrow unit tests: each
parameterized case represents one CRM workflow scenario.
"""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import agent as agent_api
from app.api import approvals as approvals_api
from app.api import business_journey_board as business_journey_board_api
from app.api import license_application as license_api
from app.api import payments as payments_api
from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.core import database, deps
from app.core.database import Base
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentTaskStatus,
    AgentToolCall,
    AgentMemoryEntry,
)
from app.models.approval import Approval, ApprovalFlow, ApprovalNode, ApprovalRecord, ApprovalStatus
from app.models.contract import Contract, ContractStatus
from app.models.customer import Contact, Customer, CustomerMember
from app.models.customer_fact import CustomerFact, CustomerFactReviewAudit, CustomerFactRevision, CustomerFactSource
from app.models.customer_intelligence_run import CustomerIntelligenceRun
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyEventType
from app.models.deployment import DeploymentInfo
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceTitle, InvoiceType
from app.models.license_application import LicenseApplication, LicenseApplicationStatus
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.schemas.approval import ApprovalActionRequest
from app.models.approval import ApprovalAction
from app.services.agent.schemas import AgentFollowUpQualityResult, AgentSemanticParseResult
from app.services.agent.tools.base import AgentToolResult


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _create_checkpoint_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE crm_langgraph_checkpoints (
                thread_id VARCHAR(191) NOT NULL,
                checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
                checkpoint_id VARCHAR(191) NOT NULL,
                parent_checkpoint_id VARCHAR(191),
                checkpoint_type VARCHAR(100) NOT NULL,
                checkpoint_blob BLOB NOT NULL,
                metadata_type VARCHAR(100) NOT NULL,
                metadata_blob BLOB NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE crm_langgraph_checkpoint_blobs (
                thread_id VARCHAR(191) NOT NULL,
                checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
                channel VARCHAR(191) NOT NULL,
                version VARCHAR(191) NOT NULL,
                serde_type VARCHAR(100) NOT NULL,
                `blob` BLOB NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
            )
        """))
        conn.execute(text("""
            CREATE TABLE crm_langgraph_checkpoint_writes (
                thread_id VARCHAR(191) NOT NULL,
                checkpoint_ns VARCHAR(191) NOT NULL DEFAULT '',
                checkpoint_id VARCHAR(191) NOT NULL,
                task_id VARCHAR(191) NOT NULL,
                write_idx INTEGER NOT NULL,
                task_path VARCHAR(255) NOT NULL DEFAULT '',
                channel VARCHAR(191) NOT NULL,
                serde_type VARCHAR(100) NOT NULL,
                `blob` BLOB NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
            )
        """))


class FakeSemanticParser:
    def __init__(self, result):
        self.results = result if isinstance(result, list) else [result]
        self.calls = []

    async def parse(self, db, *, team_id, user_message, memory=None, current_date=None):
        self.calls.append({"team_id": team_id, "user_message": user_message, "memory": memory})
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return AgentSemanticParseResult.model_validate(self.results[index])


class FakeQualityEvaluator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def evaluate_with_metadata(self, db, *, team_id, user_message, semantic_result, memory=None, current_date=None):
        self.calls.append({"team_id": team_id, "user_message": user_message, "semantic_result": semantic_result})
        quality = AgentFollowUpQualityResult.model_validate(self.result)

        class Envelope:
            quality_source = "scenario_fake_quality"
            model = "scenario-model"
            fallback_reason = None
            fallback_error = None

            def __init__(self, result):
                self.result = result

        return Envelope(quality)


@pytest.fixture()
def scenario_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__,
        Role.__table__,
        UserRole.__table__,
        Permission.__table__,
        RolePermission.__table__,
        Customer.__table__,
        Contact.__table__,
        CustomerMember.__table__,
        CustomerDealJourney.__table__,
        CustomerDealJourneyEvent.__table__,
        Opportunity.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceTitle.__table__,
        InvoiceApplication.__table__,
        DeploymentInfo.__table__,
        LicenseApplication.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
        AgentSession.__table__,
        AgentMessage.__table__,
        AgentTask.__table__,
        AgentToolCall.__table__,
        AgentIdempotencyKey.__table__,
        AgentMemoryEntry.__table__,
        CustomerVectorDocument.__table__,
        CustomerFact.__table__,
        CustomerFactSource.__table__,
        CustomerFactRevision.__table__,
        CustomerFactReviewAudit.__table__,
        CustomerIntelligenceRun.__table__,
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
        _create_checkpoint_tables(engine)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name
    Session = sessionmaker(bind=engine)
    db = Session()

    current_user = SimpleNamespace(id=1, name="财务张", status="active")
    db.add(User(id=1, email="finance@example.com", name="财务张", status=UserStatus.ACTIVE))
    db.commit()

    permissions = {
        "customer:view:all",
        "customer:edit:all",
        "payment:view:all",
        "payment:submit",
        "payment:record:edit",
        "payment:record:delete",
        "sales_dashboard:view:all",
    }

    def _permission_stub(_db, user_id, team_id=None):
        return [SimpleNamespace(code=code) for code in permissions]

    monkeypatch.setattr("app.core.deps.permission_crud.get_user_permissions", _permission_stub)
    monkeypatch.setattr("app.api.payments.permission_crud.get_user_permissions", _permission_stub)
    monkeypatch.setattr("app.api.approvals.feishu_notification_service.notify_approval_pending", AsyncMock(return_value=None))
    monkeypatch.setattr("app.api.payments.feishu_notification_service.notify_approval_pending", AsyncMock(return_value=None))

    app = FastAPI()
    app.include_router(agent_api.router)
    app.include_router(approvals_api.router)
    app.include_router(business_journey_board_api.router)
    app.include_router(payments_api.router)
    app.include_router(license_api.router)

    for module in (database, deps, agent_api, approvals_api, business_journey_board_api, payments_api, license_api):
        if hasattr(module, "get_db"):
            app.dependency_overrides[module.get_db] = lambda: db
        if hasattr(module, "get_current_user_team"):
            app.dependency_overrides[module.get_current_user_team] = lambda: 1
        if hasattr(module, "get_current_active_user"):
            app.dependency_overrides[module.get_current_active_user] = lambda: current_user

    monkeypatch.setattr(agent_api, "SessionLocal", lambda: Session())
    monkeypatch.setattr("app.services.agent.checkpointer.agent_checkpoint_saver.engine", engine)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            db=db,
            engine=engine,
            Session=Session,
            permissions=permissions,
            current_user=current_user,
            monkeypatch=monkeypatch,
        )

    db.close()
    engine.dispose()


def seed_customer(env, name="广州睿狐科技有限公司"):
    customer = Customer(
        team_id=1,
        account_name=name,
        city="广州",
        owner_id="1",
        creator_id="1",
        source="客户推荐",
    )
    env.db.add(customer)
    env.db.commit()
    return customer


def seed_opportunity(env, customer):
    opp = Opportunity(
        team_id=1,
        opportunity_number="OPP202608030001",
        opportunity_name=f"{customer.account_name}-CRM 项目",
        customer_id=customer.id,
        total_amount=Decimal("100000"),
        user_count=100,
        unit_price=Decimal("1000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=date(2026, 9, 30),
        owner_id="1",
        creator_id="1",
    )
    env.db.add(opp)
    env.db.commit()
    return opp


def seed_contract_plan_record(env, *, creator_id="1", amount=Decimal("50000")):
    customer = seed_customer(env)
    opportunity = seed_opportunity(env, customer)
    contract = Contract(
        team_id=1,
        contract_number=f"C-2026-{customer.id:03d}",
        contract_name=f"{customer.account_name} 合同",
        customer_id=customer.id,
        opportunity_id=opportunity.id,
        signing_contact_id=1,
        user_count=100,
        total_amount=Decimal("100000"),
        license_type="SUBSCRIPTION",
        subscription_years=1,
        standard_unit_price=Decimal("1000"),
        status=ContractStatus.SIGNED,
        owner_id="1",
        creator_id="1",
    )
    env.db.add(contract)
    env.db.flush()
    plan = PaymentPlan(
        team_id=1,
        contract_id=contract.id,
        plan_number=f"PP-2026-{contract.id:03d}",
        stage_name="首付款",
        planned_amount=Decimal("50000"),
        due_date=date(2026, 8, 15),
        status=PaymentPlanStatus.PENDING,
    )
    env.db.add(plan)
    env.db.flush()
    record = PaymentRecord(
        team_id=1,
        record_number=f"PR-2026-{plan.id:03d}",
        payment_plan_id=plan.id,
        actual_amount=amount,
        actual_payer_name=customer.account_name,
        payment_date=date(2026, 7, 25),
        creator_id=str(creator_id),
        creator_name="财务张" if str(creator_id) == "1" else "销售李",
        confirmation_status=PaymentConfirmationStatus.PENDING,
    )
    env.db.add(record)
    env.db.commit()
    return customer, opportunity, contract, plan, record


def seed_invoice(env, *, applicant_id="1"):
    customer, opportunity, contract, plan, record = seed_contract_plan_record(env, creator_id=applicant_id)
    invoice = InvoiceApplication(
        team_id=1,
        application_number=f"INV-2026-{record.id:03d}",
        customer_id=customer.id,
        contract_id=contract.id,
        opportunity_id=opportunity.id,
        payment_plan_id=plan.id,
        payment_record_id=record.id,
        invoice_amount=Decimal("50000"),
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.DRAFT,
        applicant_id=str(applicant_id),
        invoice_title_type="COMPANY",
        invoice_title_text=customer.account_name,
        invoice_taxpayer_id="91440101TESTCRM",
    )
    env.db.add(invoice)
    env.db.commit()
    return invoice


def seed_license(env, *, applicant_id="1"):
    customer = seed_customer(env)
    application = LicenseApplication(
        team_id=1,
        application_number=f"LIC-2026-{customer.id:03d}",
        customer_id=customer.id,
        expiry_date=date(2027, 12, 31),
        license_type="TRIAL",
        authorized_users=10,
        applicant_id=str(applicant_id),
        remark="客户申请试用 desktop,web,branch 模块",
        status=LicenseApplicationStatus.DRAFT,
    )
    env.db.add(application)
    env.db.commit()
    return application


def seed_flow(env, business_type, role_code="FINANCE", flow_code=None):
    flow = ApprovalFlow(
        team_id=1,
        flow_name=f"{business_type} 审批流",
        flow_code=flow_code or f"{business_type}_FLOW",
        business_type=business_type,
        is_active=1,
    )
    env.db.add(flow)
    env.db.flush()
    node = ApprovalNode(
        team_id=1,
        flow_id=flow.id,
        node_name="财务审批",
        node_code=role_code,
        node_order=1,
        approve_role=role_code,
        is_required=1,
    )
    env.db.add(node)
    env.db.commit()
    return flow, node


def seed_role(env, role_code="FINANCE"):
    role = Role(name=role_code, code=role_code)
    env.db.add(role)
    env.db.flush()
    env.db.add(UserRole(user_id=1, role_id=role.id, team_id=1))
    env.db.commit()
    return role


def submit_approval(env, entity_type, entity_id):
    response = env.client.post(f"/v1/approvals/{entity_type}/{entity_id}/submit", json={"comment": "请审批"})
    assert response.status_code == 200, response.text
    return response


def current_approval(env, entity_type, entity_id):
    return env.db.query(Approval).filter(
        Approval.business_type == entity_type,
        Approval.business_id == entity_id,
    ).one()


def agent_session(env, title="业务验收会话"):
    response = env.client.post("/v1/agent/sessions", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def post_agent(env, session_id, content):
    return env.client.post(
        "/v1/agent/chat/stream",
        json={"session_id": session_id, "content": content},
        headers={"Authorization": "Bearer scenario-token"},
    )


def assert_sse_contains(response, *snippets):
    assert response.status_code == 200, response.text
    for snippet in snippets:
        assert snippet in response.text


def _semantic(intent="CREATE_OPPORTUNITY", customer_name="广州睿狐科技有限公司"):
    return {
        "intent": intent,
        "intent_confidence": 0.95,
        "customer": {"name_text": customer_name, "confidence": 0.9, "resolution_source": "EXPLICIT"},
        "follow_up": {},
        "payment": {},
        "opportunity": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["scenario"],
    }


def run_agent_session_created(env):
    session = agent_session(env, "客户跟进")
    response = env.client.get("/v1/agent/sessions")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == session["title"]


def run_agent_stream_persists_messages(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {"event": "agent_step", "step": "semantic_parse", "content": "理解业务语义"}
            yield {"event": "final", "content": f"已收到：{input_state['content']}"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    session = agent_session(env)
    response = post_agent(env, session["id"], "今天和客户确认了试用范围")
    assert_sse_contains(response, "已收到", "今天和客户确认了试用范围")
    messages = env.client.get(f"/v1/agent/sessions/{session['id']}/messages").json()
    assert [item["role"] for item in messages["items"]] == ["USER", "ASSISTANT"]


def run_agent_requires_follow_up_confirmation(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_activity",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {"customer_id": 101, "content": input_state["content"]},
            }
            yield {"event": "final", "content": "请确认是否创建跟进记录？"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    session = agent_session(env)
    response = post_agent(env, session["id"], "今天和越秀金融沟通预算")
    assert_sse_contains(response, "confirmation_required", "task_id")
    task = env.db.query(AgentTask).one()
    assert task.status == AgentTaskStatus.WAITING_USER


def run_agent_confirm_executes_follow_up(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_activity",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {"customer_id": 101, "content": input_state["content"]},
            }
            yield {"event": "final", "content": "请确认是否创建跟进记录？"}

    class FakeTools:
        async def create_customer_activity(self, context, **kwargs):
            return AgentToolResult("create_customer_activity", True, {"id": 9001, "customer_id": kwargs["customer_id"]}, 7001)

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    env.monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeTools())
    session = agent_session(env)
    post_agent(env, session["id"], "今天和越秀金融沟通预算")
    response = post_agent(env, session["id"], "是")
    assert_sse_contains(response, "task_completed", "客户活动已记录")
    assert env.db.query(AgentTask).one().status == AgentTaskStatus.COMPLETED


def run_agent_reject_cancels_waiting_task(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {"event": "confirmation_required", "action": "create_customer_activity", "payload": {"content": input_state["content"]}}
            yield {"event": "final", "content": "请确认是否创建跟进记录？"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    session = agent_session(env)
    post_agent(env, session["id"], "记录一条跟进")
    response = post_agent(env, session["id"], "先不处理")
    assert_sse_contains(response, "task_cancelled")
    assert env.db.query(AgentTask).one().status == AgentTaskStatus.SUSPENDED


def run_agent_opportunity_missing_fields_form(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {
                "event": "opportunity_fields_required",
                "payload": {"missing_fields": ["total_amount", "user_count", "license_type", "expected_closing_date", "purchase_type"]},
                "content": "还需要补充商机信息",
            }
            yield {"event": "final", "content": "还需要补充商机信息"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    session = agent_session(env)
    response = post_agent(env, session["id"], "帮客户创建商机")
    assert_sse_contains(response, "opportunity_fields_required", '"type": "form"', "预计成交日期")


def run_agent_collects_opportunity_fields_without_rerun(env):
    calls = []
    customer = {"id": 101, "account_name": "广州睿狐科技有限公司", "owner_info": {"id": 1}, "collaborator_infos": []}

    class FakeGraph:
        async def stream_events(self, input_state):
            calls.append(input_state)
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": 101,
                    "opportunity": {"customer_id": 101, "total_amount": 50000, "user_count": 100, "license_type": "SUBSCRIPTION"},
                    "missing_fields": ["purchase_type", "expected_closing_date", "subscription_years", "procurement_method_id"],
                },
            }
            yield {"event": "final", "content": "请补充采购类型、预计成交日期、订阅年限和采购方式。"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    env.monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        **_semantic(),
        "opportunity": {
            "purchase_type": "NEW",
            "subscription_years": 1,
            "procurement_method_id": 1,
            "expected_closing_date": {
                "raw_text": "8月30号",
                "kind": "EXPLICIT_DATE",
                "direction": "future",
                "date_text": "2026-08-30",
                "confidence": 0.9,
            },
        },
    }))
    session = agent_session(env)
    post_agent(env, session["id"], "帮客户建 5 万商机")
    response = post_agent(env, session["id"], "新购，订阅 1 年，8月30号成交，procurement_method_id=1")
    assert_sse_contains(response, "confirmation_required", "商机信息齐了")
    assert len(calls) == 1


def run_agent_customer_context_memory(env):
    customer = {"id": 101, "account_name": "广州睿狐科技有限公司", "owner_info": {"id": 1}, "collaborator_infos": []}
    states = []

    class FakeGraph:
        async def stream_events(self, input_state):
            states.append(input_state)
            if len(states) == 1:
                yield {"event": "business_context_loaded", "customer_id": 101, "customer": customer}
            yield {"event": "final", "content": "已加载客户上下文"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    session = agent_session(env)
    post_agent(env, session["id"], "睿狐科技今天回了 5 万")
    post_agent(env, session["id"], "那继续建一个商机")
    assert states[1]["session_context"]["current_customer"] == customer


def run_agent_customer_selection_required(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {
                "event": "customer_selection_required",
                "content": "找到多个客户，请选择",
                "customers": [
                    {"id": 1, "account_name": "广州睿狐科技有限公司"},
                    {"id": 2, "account_name": "深圳睿狐科技有限公司"},
                ],
            }
            yield {"event": "final", "content": "找到多个客户，请选择"}

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    session = agent_session(env)
    response = post_agent(env, session["id"], "睿狐科技")
    assert_sse_contains(response, "customer_selection_required", '"type": "choice"', "深圳睿狐科技有限公司")


def run_agent_lead_follow_up_quality_chain(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_lead",
                "payload": {
                    "lead": {"lead_name": "广州睿狐科技", "city": "广州", "contact_name": "王总", "contact_phone": "13800138000"},
                    "lead_follow_up": {"content": "客户有明确兴趣", "next_action": "下周三电话跟进"},
                },
            }
            yield {"event": "final", "content": "请确认是否创建线索？"}

    class FakeTools:
        async def create_lead(self, context, **kwargs):
            return AgentToolResult("create_lead", True, {"id": 8101}, 7001)

        async def create_lead_follow_up(self, context, **kwargs):
            return AgentToolResult("create_lead_follow_up", True, {"id": 8201}, 7002)

    quality = FakeQualityEvaluator({
        "score": 86,
        "passed": True,
        "reason": "达标",
        "missing_aspects": [],
        "supplement_question": None,
        "suggested_revision": "客户有明确兴趣，计划下周三电话跟进。",
        "principle_scores": {},
    })
    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    env.monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeTools())
    env.monkeypatch.setattr(agent_api, "agent_follow_up_quality_evaluator", quality)
    session = agent_session(env)
    post_agent(env, session["id"], "创建线索并记录跟进")
    response = post_agent(env, session["id"], "是")
    assert_sse_contains(response, "线索已创建", "next_task_id")
    assert len(quality.calls) == 1


def run_agent_opportunity_completion_terminal(env):
    class FakeGraph:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_opportunity",
                "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
                "payload": {
                    "opportunity": {
                        "customer_id": 101,
                        "total_amount": 50000,
                        "user_count": 20,
                        "license_type": "SUBSCRIPTION",
                        "subscription_years": 1,
                        "purchase_type": "NEW",
                        "expected_closing_date": "2026-08-31",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建商机？"}

    class FakeTools:
        async def create_opportunity(self, context, **kwargs):
            return AgentToolResult("create_opportunity", True, {"id": 3001}, 7001)

    env.monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraph())
    env.monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeTools())
    session = agent_session(env)
    post_agent(env, session["id"], "创建商机")
    response = post_agent(env, session["id"], "是")
    assert_sse_contains(response, "task_completed", "商机已创建")
    assert "继续处理" not in response.text


def run_approval_invoice_submit_pending(env):
    seed_flow(env, BusinessType.INVOICE)
    invoice = seed_invoice(env)
    response = submit_approval(env, "INVOICE", invoice.id)
    assert response.json()["status"] == "PENDING"
    env.db.refresh(invoice)
    assert invoice.approval_phase == ApprovalPhase.PENDING_REVIEW


def run_approval_invalid_entity_rejected(env):
    response = env.client.post("/v1/approvals/UNKNOWN/1/submit", json={"comment": "请审批"})
    assert response.status_code in (400, 422)


def run_approval_invoice_detail_visible_to_submitter(env):
    seed_flow(env, BusinessType.INVOICE)
    invoice = seed_invoice(env)
    submit = submit_approval(env, "INVOICE", invoice.id)
    response = env.client.get(f"/v1/approvals/INVOICE/{invoice.id}/detail")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == submit.json()["approval_id"]


def run_approval_detail_forbidden_for_unrelated_user(env):
    seed_flow(env, BusinessType.INVOICE)
    invoice = seed_invoice(env)
    submit_approval(env, "INVOICE", invoice.id)
    env.current_user.id = 99
    env.current_user.name = "无关用户"
    response = env.client.get(f"/v1/approvals/INVOICE/{invoice.id}/detail")
    assert response.status_code == 403, response.text


def run_approval_cancel_by_submitter(env):
    seed_flow(env, BusinessType.INVOICE)
    invoice = seed_invoice(env)
    submit_approval(env, "INVOICE", invoice.id)
    response = env.client.post(f"/v1/approvals/INVOICE/{invoice.id}/cancel")
    assert response.status_code == 200, response.text
    assert "撤回" in response.json()["message"]


def run_approval_role_mismatch_blocks_approve(env):
    seed_flow(env, BusinessType.INVOICE, role_code="FINANCE")
    invoice = seed_invoice(env)
    submit_approval(env, "INVOICE", invoice.id)
    response = env.client.post(f"/v1/approvals/INVOICE/{invoice.id}/approve", json={"action": "APPROVE", "comment": "同意"})
    assert response.status_code == 403, response.text


def run_approval_self_invoice_without_perm_blocks(env):
    seed_flow(env, BusinessType.INVOICE)
    seed_role(env, "FINANCE")
    invoice = seed_invoice(env, applicant_id="1")
    submit_approval(env, "INVOICE", invoice.id)
    response = env.client.post(f"/v1/approvals/INVOICE/{invoice.id}/approve", json={"action": "APPROVE", "comment": "同意"})
    assert response.status_code == 403, response.text
    assert "自己创建的发票" in response.json()["detail"]


def run_approval_self_invoice_with_perm_passes(env):
    seed_flow(env, BusinessType.INVOICE)
    seed_role(env, "FINANCE")
    env.permissions.add("invoice:approve:own")
    invoice = seed_invoice(env, applicant_id="1")
    submit_approval(env, "INVOICE", invoice.id)
    approval = current_approval(env, BusinessType.INVOICE, invoice.id)
    response = env.client.post(
        f"/v1/approvals/INVOICE/{invoice.id}/approve",
        json={"action": "APPROVE", "comment": "同意开票", "updated_time": approval.updated_time.isoformat()},
    )
    assert response.status_code == 200, response.text
    env.db.refresh(invoice)
    assert invoice.status == InvoiceApplicationStatus.APPROVED
    assert invoice.reviewer_id == "1"


def run_approval_non_self_invoice_without_own_perm_passes(env):
    seed_flow(env, BusinessType.INVOICE)
    seed_role(env, "FINANCE")
    invoice = seed_invoice(env, applicant_id="2")
    submit_approval(env, "INVOICE", invoice.id)
    approval = current_approval(env, BusinessType.INVOICE, invoice.id)
    response = env.client.post(
        f"/v1/approvals/INVOICE/{invoice.id}/approve",
        json={"action": "APPROVE", "comment": "同意开票", "updated_time": approval.updated_time.isoformat()},
    )
    assert response.status_code == 200, response.text


def run_approval_invoice_reject_updates_status(env):
    seed_flow(env, BusinessType.INVOICE)
    seed_role(env, "FINANCE")
    invoice = seed_invoice(env, applicant_id="2")
    submit_approval(env, "INVOICE", invoice.id)
    response = env.client.post(f"/v1/approvals/INVOICE/{invoice.id}/approve", json={"action": "REJECT", "comment": "资料不完整"})
    assert response.status_code == 200, response.text
    env.db.refresh(invoice)
    assert invoice.status == InvoiceApplicationStatus.REJECTED


def run_approval_bulk_partial_success(env):
    seed_flow(env, BusinessType.INVOICE)
    seed_role(env, "FINANCE")
    invoice = seed_invoice(env, applicant_id="2")
    submit_approval(env, "INVOICE", invoice.id)
    approval = current_approval(env, BusinessType.INVOICE, invoice.id)
    response = env.client.post(
        "/v1/approvals/bulk-approve",
        json={
            "entity_type": "INVOICE",
            "ids": [invoice.id, 888888],
            "action": "APPROVE",
            "comment": "批量通过",
            "updated_times": {str(invoice.id): approval.updated_time.isoformat()},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["success_count"] == 1
    assert response.json()["failed"][0]["id"] == 888888


def run_approval_optimistic_lock_conflict(env):
    seed_flow(env, BusinessType.INVOICE)
    seed_role(env, "FINANCE")
    invoice = seed_invoice(env, applicant_id="2")
    submit_approval(env, "INVOICE", invoice.id)
    approval = current_approval(env, BusinessType.INVOICE, invoice.id)
    original_updated_time = approval.updated_time
    approvals_api.approval_crud.approve(
        env.db,
        approval,
        ApprovalActionRequest(action=ApprovalAction.APPROVE, comment="他人已处理", updated_time=original_updated_time),
        approver_id="2",
        approver_name="其他财务",
    )
    env.db.refresh(approval)
    if approval.updated_time == original_updated_time:
        approval.updated_time = original_updated_time + timedelta(seconds=1)
        env.db.commit()
    response = env.client.post(
        "/v1/approvals/bulk-approve",
        json={
            "entity_type": "INVOICE",
            "ids": [invoice.id],
            "action": "APPROVE",
            "comment": "批量通过",
            "updated_times": {str(invoice.id): original_updated_time.isoformat()},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["failed"][0]["reason"] == "已被他人处理"


def run_opportunity_approval_starts_business_journey_board(env):
    seed_flow(env, BusinessType.OPPORTUNITY)
    customer = seed_customer(env)
    opportunity = seed_opportunity(env, customer)

    submit_approval(env, "OPPORTUNITY", opportunity.id)

    before_approval = env.client.get("/v1/business-journey-board/")
    assert before_approval.status_code == 200, before_approval.text
    assert before_approval.json()["summary"]["total_count"] == 0

    approval = current_approval(env, BusinessType.OPPORTUNITY, opportunity.id)
    approvals_api.approval_crud.approve(
        env.db,
        approval,
        ApprovalActionRequest(action=ApprovalAction.APPROVE, comment="同意"),
        approver_id="2",
        approver_name="销售总监",
    )

    event = env.db.query(CustomerDealJourneyEvent).filter(
        CustomerDealJourneyEvent.source_type == "opportunity",
        CustomerDealJourneyEvent.source_id == opportunity.id,
        CustomerDealJourneyEvent.event_type == DealJourneyEventType.OPPORTUNITY_APPROVED,
    ).one()
    assert event.deal_journey_id == opportunity.deal_journey_id

    response = env.client.get("/v1/business-journey-board/")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["total_count"] == 1
    assert body["columns"][0]["cards"][0]["journey_id"] == opportunity.deal_journey_id


def run_payment_submit_approval_creates_instance(env):
    seed_flow(env, BusinessType.PAYMENT)
    _, _, _, _, record = seed_contract_plan_record(env, creator_id="2")
    response = env.client.post(f"/v1/payments/records/{record.id}/submit-approval")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PENDING"
    env.db.refresh(record)
    assert record.confirmation_status == PaymentConfirmationStatus.PENDING


def run_payment_submit_without_flow_configuration_error(env):
    _, _, _, _, record = seed_contract_plan_record(env)
    response = env.client.post(f"/v1/payments/records/{record.id}/submit-approval")
    assert response.status_code == 400, response.text
    assert "未找到匹配的回款审批流程" in response.json()["detail"]


def run_payment_record_update_after_withdraw_allowed(env):
    flow, node = seed_flow(env, BusinessType.PAYMENT)
    _, _, _, _, record = seed_contract_plan_record(env)
    approval = Approval(
        team_id=1,
        business_type=BusinessType.PAYMENT,
        business_id=record.id,
        flow_id=flow.id,
        current_node_id=node.id,
        status=ApprovalStatus.CANCELLED,
        submitter_id="1",
        submitter_name="财务张",
    )
    env.db.add(approval)
    env.db.flush()
    record.approval_id = approval.id
    record.approval_phase = ApprovalPhase.DRAFT
    env.db.commit()
    response = env.client.put(
        f"/v1/payments/payment-records/{record.id}",
        json={"actual_amount": 30000, "actual_payer_name": "北京智云悟飞科技有限公司", "payment_date": "2026-07-24"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["actual_amount"] == 30000


def run_payment_record_update_pending_forbidden(env):
    flow, node = seed_flow(env, BusinessType.PAYMENT)
    _, _, _, _, record = seed_contract_plan_record(env)
    approval = Approval(
        team_id=1,
        business_type=BusinessType.PAYMENT,
        business_id=record.id,
        flow_id=flow.id,
        current_node_id=node.id,
        status=ApprovalStatus.PENDING,
        submitter_id="1",
        submitter_name="财务张",
    )
    env.db.add(approval)
    env.db.flush()
    record.approval_id = approval.id
    record.approval_phase = ApprovalPhase.PENDING_REVIEW
    env.db.commit()
    response = env.client.put(f"/v1/payments/payment-records/{record.id}", json={"actual_amount": 30000, "payment_date": "2026-07-24"})
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "审批中的回款记录不能修改"


def run_license_create_and_list(env):
    customer = seed_customer(env)
    response = env.client.post(
        "/v1/license-applications/",
        json={"customer_id": customer.id, "license_type": "TRIAL", "expiry_date": "2027-12-31", "remark": "客户试用申请"},
    )
    assert response.status_code == 201, response.text
    list_response = env.client.get(f"/v1/license-applications/?customer_id={customer.id}")
    assert list_response.status_code == 200, list_response.text
    assert len(list_response.json()) == 1


def run_license_submit_creates_approval(env):
    seed_flow(env, BusinessType.LICENSE, role_code="TEAM_OWNER")
    application = seed_license(env)
    response = env.client.post(f"/v1/license-applications/{application.id}/submit")
    assert response.status_code == 200, response.text
    env.db.refresh(application)
    assert application.status == LicenseApplicationStatus.PENDING_REVIEW
    assert application.approval_id is not None


def run_license_submit_without_flow_configuration_error(env):
    application = seed_license(env)
    response = env.client.post(f"/v1/license-applications/{application.id}/submit")
    assert response.status_code == 400, response.text
    assert "未找到匹配的License审批流程" in response.json()["detail"]


AGENT_SCENARIOS = [
    ("agent_session_created", run_agent_session_created),
    ("agent_stream_persists_messages", run_agent_stream_persists_messages),
    ("agent_requires_follow_up_confirmation", run_agent_requires_follow_up_confirmation),
    ("agent_confirm_executes_follow_up", run_agent_confirm_executes_follow_up),
    ("agent_reject_cancels_waiting_task", run_agent_reject_cancels_waiting_task),
    ("agent_opportunity_missing_fields_form", run_agent_opportunity_missing_fields_form),
    ("agent_collects_opportunity_fields_without_rerun", run_agent_collects_opportunity_fields_without_rerun),
    ("agent_customer_context_memory", run_agent_customer_context_memory),
    ("agent_customer_selection_required", run_agent_customer_selection_required),
    ("agent_lead_follow_up_quality_chain", run_agent_lead_follow_up_quality_chain),
    ("agent_opportunity_completion_terminal", run_agent_opportunity_completion_terminal),
]

APPROVAL_SCENARIOS = [
    ("approval_invoice_submit_pending", run_approval_invoice_submit_pending),
    ("approval_invalid_entity_rejected", run_approval_invalid_entity_rejected),
    ("approval_invoice_detail_visible_to_submitter", run_approval_invoice_detail_visible_to_submitter),
    ("approval_detail_forbidden_for_unrelated_user", run_approval_detail_forbidden_for_unrelated_user),
    ("approval_cancel_by_submitter", run_approval_cancel_by_submitter),
    ("approval_role_mismatch_blocks_approve", run_approval_role_mismatch_blocks_approve),
    ("approval_self_invoice_without_perm_blocks", run_approval_self_invoice_without_perm_blocks),
    ("approval_self_invoice_with_perm_passes", run_approval_self_invoice_with_perm_passes),
    ("approval_non_self_invoice_without_own_perm_passes", run_approval_non_self_invoice_without_own_perm_passes),
    ("approval_invoice_reject_updates_status", run_approval_invoice_reject_updates_status),
    ("approval_bulk_partial_success", run_approval_bulk_partial_success),
    ("approval_optimistic_lock_conflict", run_approval_optimistic_lock_conflict),
    ("opportunity_approval_starts_business_journey_board", run_opportunity_approval_starts_business_journey_board),
]

PAYMENT_LICENSE_SCENARIOS = [
    ("payment_submit_approval_creates_instance", run_payment_submit_approval_creates_instance),
    ("payment_submit_without_flow_configuration_error", run_payment_submit_without_flow_configuration_error),
    ("payment_record_update_after_withdraw_allowed", run_payment_record_update_after_withdraw_allowed),
    ("payment_record_update_pending_forbidden", run_payment_record_update_pending_forbidden),
    ("license_create_and_list", run_license_create_and_list),
    ("license_submit_creates_approval", run_license_submit_creates_approval),
    ("license_submit_without_flow_configuration_error", run_license_submit_without_flow_configuration_error),
]


@pytest.mark.parametrize("scenario_name,runner", AGENT_SCENARIOS, ids=[name for name, _ in AGENT_SCENARIOS])
def test_agent_backend_business_scenarios(scenario_env, scenario_name, runner):
    runner(scenario_env)


@pytest.mark.parametrize("scenario_name,runner", APPROVAL_SCENARIOS, ids=[name for name, _ in APPROVAL_SCENARIOS])
def test_approval_backend_business_scenarios(scenario_env, scenario_name, runner):
    runner(scenario_env)


@pytest.mark.parametrize("scenario_name,runner", PAYMENT_LICENSE_SCENARIOS, ids=[name for name, _ in PAYMENT_LICENSE_SCENARIOS])
def test_payment_license_backend_business_scenarios(scenario_env, scenario_name, runner):
    runner(scenario_env)
