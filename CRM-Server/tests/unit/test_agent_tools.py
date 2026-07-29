"""CRM AI Agent tool adapter tests."""
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger
import pytest

from app.core.database import Base
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentToolCall,
    AgentToolCallStatus,
)
from app.models.customer import Customer, CustomerMember
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.middleware import build_langchain_hitl_middleware
from app.services.agent.tool_registry import AgentToolRegistry
from app.services.agent.tools.service import CRMAgentToolService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


class FakeCRMAPIClient:
    def __init__(self) -> None:
        self.calls = []

    async def request(self, method, path, authorization, *, params=None, json=None):
        self.calls.append({
            "method": method,
            "path": path,
            "authorization": authorization,
            "params": params,
            "json": json,
        })
        if method == "GET" and path == "/v1/customers/":
            return {"items": [{"id": 101, "account_name": "越秀金融"}], "total": 1}
        if method == "GET" and path == "/v1/customers/101":
            return {"id": 101, "account_name": "越秀金融"}
        if method == "POST" and path == "/v1/customer-follow-ups/101":
            return {
                "id": 9001,
                "customer_id": 101,
                "content": json["content"],
                "next_follow_time": "2026-07-29T00:00:00",
            }
        if method == "POST" and path == "/v1/leads/":
            return {"id": 8101, "status": 0, **json}
        if method == "POST" and path == "/v1/customers/":
            return {"id": 9101, "status": 0, **json}
        if method == "POST" and path == "/v1/leads/8101/follow-ups":
            return {"id": 8201, "lead_id": 8101, **json}
        if method == "POST" and path == "/v1/invoice-titles":
            return {"id": 6001, "customer_id": params["customer_id"], **json, "is_default": False}
        if method == "PATCH" and path == "/v1/invoice-titles/6001/set-default":
            return {"id": 6001, "customer_id": 101, "title": "越秀金融控股有限公司", "is_default": True}
        if method == "POST" and path == "/v1/deployment-infos/":
            return {"id": 6101, **json}
        if method == "POST" and path == "/v1/customers/101/members":
            return {"id": 6201, "customer_id": 101, **json}
        if method == "POST" and path == "/v1/opportunities/":
            return {"id": 7101, **json, "approval_phase": "pending_review"}
        if method == "GET" and (path == "/v1/opportunities/" or path.startswith("/v1/opportunities/?customer_id=")):
            customer_id = params["customer_id"] if params else int(path.rsplit("=", 1)[1])
            return {
                "items": [{
                    "id": 7101,
                    "customer_id": customer_id,
                    "status": 0,
                    "approval_phase": "approved",
                }],
                "total": 1,
            }
        if method == "GET" and path == "/v1/opportunities/7101":
            return {
                "id": 7101,
                "customer_id": 101,
                "status": 0,
                "approval_phase": "approved",
                "current_stage_snapshot": {"procurement_stage_template_id": 11, "stage_name": "立项"},
            }
        if method == "GET" and path == "/v1/opportunities/7101/procurement-stages":
            return [
                {"id": 11, "stage_name": "立项", "sort_order": 1, "is_current": True, "can_skip": False},
                {"id": 12, "stage_name": "招标准备", "sort_order": 2, "is_current": False, "can_skip": False},
            ]
        if method == "POST" and path == "/v1/opportunities/7101/move-stage":
            return {
                "id": 7101,
                "current_stage_snapshot": {"procurement_stage_template_id": json["stage_template_id"], "stage_name": "招标准备"},
            }
        if method == "POST" and path == "/v1/payments/contracts/201/payment-plans":
            return [{"id": 301, "contract_id": 201, **json["plans"][0]}]
        if method == "POST" and path == "/v1/payments/payment-plans/301/records":
            return {"id": 401, "payment_plan_id": 301, **json}
        return {}


def _db_session(extra_tables=None):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        AgentSession.__table__,
        AgentMessage.__table__,
        AgentTask.__table__,
        AgentToolCall.__table__,
        AgentIdempotencyKey.__table__,
    ]
    if extra_tables:
        tables.extend(extra_tables)
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    return engine, session


def _context(db):
    return AgentToolContext(
        db=db,
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test-token",
    )


def _confirmed_context(db):
    context = _context(db)
    context.task_id = 99
    context.confirmed_by_user = True
    context.hitl_decision = "approve"
    context.allowed_tool_names = ["create_customer_follow_up"]
    context.allowed_customer_ids = [101]
    return context


def _confirmed_context_for(db, tool_name, customer_id=101):
    context = _context(db)
    context.task_id = 99
    context.confirmed_by_user = True
    context.hitl_decision = "approve"
    context.allowed_tool_names = [tool_name]
    context.allowed_customer_ids = [customer_id]
    return context


def _grant_permissions(db, user_id, team_id, permission_codes):
    user = User(id=user_id, email=f"user{user_id}@example.com", name=f"User {user_id}")
    role = Role(id=100 + user_id, name=f"role-{user_id}", code=f"role-{user_id}")
    db.add_all([user, role])
    db.flush()
    for index, code in enumerate(permission_codes, start=1):
        permission = Permission(
            id=user_id * 1000 + index,
            name=f"{code}-{user_id}",
            code=code,
            resource=code.split(":", 1)[0],
            action="view",
            scope=code.rsplit(":", 1)[-1],
        )
        db.add(permission)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.add(UserRole(user_id=user_id, role_id=role.id, team_id=team_id))
    db.commit()


@pytest.mark.asyncio
async def test_agent_tool_search_customers_calls_existing_api_and_audits():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.search_customers(_context(db), "越秀金融", limit=5)

        assert result.success is True
        assert result.data["total"] == 1
        assert fake_client.calls == [{
            "method": "GET",
            "path": "/v1/customers/",
            "authorization": "Bearer test-token",
            "params": {"keyword": "越秀金融", "limit": 5, "scope": "accessible"},
            "json": None,
        }]

        tool_call = db.query(AgentToolCall).one()
        assert tool_call.tool_name == "search_customers"
        assert tool_call.status == AgentToolCallStatus.SUCCESS
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_search_creation_duplicates_returns_visible_customer_name_without_api_call():
    engine, db = _db_session([
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Customer.__table__,
        CustomerMember.__table__,
    ])
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        _grant_permissions(db, user_id=2, team_id=1, permission_codes=["customer:view:own"])
        db.add(Customer(
            id=101,
            team_id=1,
            account_name="东风康明斯发动机有限公司",
            city="襄阳",
            owner_id="2",
            creator_id="2",
        ))
        db.commit()

        result = await service.search_creation_duplicates(
            _context(db),
            customer_keywords=["东风康明斯"],
            lead_keywords=[],
            limit=5,
        )

        assert result.success is True
        assert result.data["customers"] == [{
            "id": 101,
            "account_name": "东风康明斯发动机有限公司",
            "visible": True,
        }]
        assert result.data["hidden_customer_count"] == 0
        assert fake_client.calls == []
        assert db.query(AgentToolCall).one().tool_name == "search_creation_duplicates"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_search_creation_duplicates_hides_team_customer_without_view_access():
    engine, db = _db_session([
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Customer.__table__,
        CustomerMember.__table__,
    ])
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        _grant_permissions(db, user_id=2, team_id=1, permission_codes=["customer:view:own"])
        db.add(Customer(
            id=101,
            team_id=1,
            account_name="东风康明斯发动机有限公司",
            city="襄阳",
            owner_id="9",
            creator_id="9",
        ))
        db.commit()

        result = await service.search_creation_duplicates(
            _context(db),
            customer_keywords=["东风康明斯"],
            lead_keywords=[],
            limit=5,
        )

        assert result.success is True
        assert result.data["customers"] == []
        assert result.data["hidden_customer_count"] == 1
        assert "东风康明斯发动机有限公司" not in str(result.data)
        assert fake_client.calls == []
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_search_creation_duplicates_matches_visible_lead_by_keyword():
    engine, db = _db_session([
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Lead.__table__,
    ])
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        _grant_permissions(db, user_id=2, team_id=1, permission_codes=["lead:view:own"])
        db.add(Lead(
            id=201,
            team_id=1,
            lead_name="湖北康明斯项目",
            source=LeadSource.OTHER,
            city="襄阳",
            contact_name="赵坤",
            contact_phone="18707276297",
            owner_id="2",
            creator_id="2",
            status=LeadStatus.NEW,
        ))
        db.commit()

        result = await service.search_creation_duplicates(
            _context(db),
            customer_keywords=[],
            lead_keywords=["18707276297"],
            limit=5,
        )

        assert result.success is True
        assert result.data["leads"] == [{
            "id": 201,
            "lead_name": "湖北康明斯项目",
            "contact_name": "赵坤",
            "contact_phone": "18707276297",
            "visible": True,
        }]
        assert result.data["hidden_lead_count"] == 0
        assert fake_client.calls == []
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_search_creation_duplicates_ignores_converted_and_invalid_leads():
    engine, db = _db_session([
        User.__table__,
        Role.__table__,
        Permission.__table__,
        RolePermission.__table__,
        UserRole.__table__,
        Lead.__table__,
    ])
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        _grant_permissions(db, user_id=2, team_id=1, permission_codes=["lead:view:all"])
        db.add_all([
            Lead(
                id=201,
                team_id=1,
                lead_name="东风康明斯",
                source=LeadSource.OTHER,
                city="襄阳",
                contact_name="赵坤",
                contact_phone="18707276297",
                owner_id="2",
                creator_id="2",
                status=LeadStatus.CONVERTED,
            ),
            Lead(
                id=202,
                team_id=1,
                lead_name="湖北康明斯",
                source=LeadSource.OTHER,
                city="襄阳",
                contact_name="赵坤",
                contact_phone="18707276297",
                owner_id="2",
                creator_id="2",
                status=LeadStatus.INVALID,
            ),
        ])
        db.commit()

        result = await service.search_creation_duplicates(
            _context(db),
            customer_keywords=[],
            lead_keywords=["东风康明斯", "湖北康明斯"],
            limit=5,
        )

        assert result.success is True
        assert result.data["leads"] == []
        assert result.data["hidden_lead_count"] == 0
        assert fake_client.calls == []
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_get_customer_context_fetches_opportunities_through_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.get_customer_context(_context(db), 101)

        assert result.success is True
        assert result.data["customer"]["id"] == 101
        paths = [call["path"] for call in fake_client.calls]
        assert "/v1/opportunities/?customer_id=101" in paths
        assert "/v1/opportunities/7101/procurement-stages" in paths
        assert "/v1/customers/101/contracts" in paths
        assert result.data["active_opportunity_stage_context"][0]["procurement_stages"][1]["id"] == 12
        assert db.query(AgentToolCall).one().tool_name == "get_customer_context"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_move_opportunity_stage_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.move_opportunity_stage(
            _confirmed_context_for(db, "move_opportunity_stage"),
            opportunity_id=7101,
            stage_template_id=12,
            idempotency_suffix="task-001",
        )

        assert result.success is True
        assert fake_client.calls[0] == {
            "method": "POST",
            "path": "/v1/opportunities/7101/move-stage",
            "authorization": "Bearer test-token",
            "params": None,
            "json": {"stage_template_id": 12},
        }
        assert db.query(AgentToolCall).one().tool_name == "move_opportunity_stage"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_follow_up_is_idempotent():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    context = _context(db)
    try:
        first = await service.create_customer_follow_up(
            context,
            customer_id=101,
            customer_name="越秀金融",
            content="今天和王总沟通了项目进展",
            next_action="下周三确认进展",
            next_follow_time="2026-07-29T09:00:00",
            idempotency_suffix="msg-001",
        )
        second = await service.create_customer_follow_up(
            context,
            customer_id=101,
            customer_name="越秀金融",
            content="今天和王总沟通了项目进展",
            next_action="下周三确认进展",
            next_follow_time="2026-07-29T09:00:00",
            idempotency_suffix="msg-001",
        )

        assert first.success is True
        assert second.success is True
        assert second.idempotent_replay is True
        assert len(fake_client.calls) == 1
        assert fake_client.calls[0]["path"] == "/v1/customer-follow-ups/101"
        assert fake_client.calls[0]["json"]["next_follow_time"] == "2026-07-29T09:00:00"
        assert db.query(AgentIdempotencyKey).count() == 1
        assert db.query(AgentToolCall).count() == 1
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_lead_calls_existing_lead_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_lead",
            _confirmed_context_for(db, "create_lead"),
            {
                "lead": {
                    "lead_name": "广州睿狐科技",
                    "source": "其他",
                    "city": "广州",
                    "contact_name": "王总",
                    "contact_phone": "13800138000",
                    "company_scale": "51-200人",
                },
                "idempotency_suffix": "task-lead-001",
            },
        )

        assert result.success is True
        assert fake_client.calls == [{
            "method": "POST",
            "path": "/v1/leads/",
            "authorization": "Bearer test-token",
            "params": None,
            "json": {
                "lead_name": "广州睿狐科技",
                "source": "其他",
                "city": "广州",
                "contact_name": "王总",
                "contact_phone": "13800138000",
                "company_scale": "51-200人",
            },
        }]
        assert db.query(AgentToolCall).one().tool_name == "create_lead"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_customer_calls_existing_customer_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_customer",
            _confirmed_context_for(db, "create_customer"),
            {
                "customer": {
                    "account_name": "广州睿狐科技",
                    "source": "其他",
                    "city": "广州",
                    "primary_contact": {
                        "name": "王总",
                        "mobile": "13800138000",
                        "position": "CTO",
                        "gender": "1",
                    },
                },
                "idempotency_suffix": "task-002",
            },
        )

        assert result.success is True
        assert fake_client.calls[0] == {
            "method": "POST",
            "path": "/v1/customers/",
            "authorization": "Bearer test-token",
            "params": None,
            "json": {
                "account_name": "广州睿狐科技",
                "source": "其他",
                "city": "广州",
                "primary_contact": {
                    "name": "王总",
                    "mobile": "13800138000",
                    "position": "CTO",
                    "gender": "1",
                },
            },
        }
        assert db.query(AgentToolCall).one().tool_name == "create_customer"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_lead_follow_up_calls_existing_lead_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_lead_follow_up",
            _confirmed_context_for(db, "create_lead_follow_up"),
            {
                "lead_id": 8101,
                "content": "客户对 CRM 感兴趣",
                "method": "电话",
                "next_action": "下周三再联系",
                "next_follow_time": "2026-07-29T09:00:00",
            },
        )

        assert result.success is True
        assert fake_client.calls[0]["method"] == "POST"
        assert fake_client.calls[0]["path"] == "/v1/leads/8101/follow-ups"
        assert fake_client.calls[0]["json"]["next_follow_time"] == "2026-07-29T09:00:00"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_invoice_title_calls_existing_api_and_sets_default():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.create_invoice_title(
            _context(db),
            customer_id=101,
            invoice_title={
                "title_type": "COMPANY",
                "title": "越秀金融控股有限公司",
                "taxpayer_id": "91440000123456789X",
            },
            set_default=True,
        )

        assert result.success is True
        assert result.data["set_default"] is True
        assert fake_client.calls == [
            {
                "method": "POST",
                "path": "/v1/invoice-titles",
                "authorization": "Bearer test-token",
                "params": {"customer_id": 101},
                "json": {
                    "title_type": "COMPANY",
                    "title": "越秀金融控股有限公司",
                    "taxpayer_id": "91440000123456789X",
                },
            },
            {
                "method": "PATCH",
                "path": "/v1/invoice-titles/6001/set-default",
                "authorization": "Bearer test-token",
                "params": None,
                "json": None,
            },
        ]
        assert db.query(AgentToolCall).one().tool_name == "create_invoice_title"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_deployment_info_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.create_deployment_info(
            _context(db),
            deployment_info={
                "customer_id": 101,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
                "is_default": True,
            },
        )

        assert result.success is True
        assert result.data["id"] == 6101
        assert fake_client.calls == [{
            "method": "POST",
            "path": "/v1/deployment-infos/",
            "authorization": "Bearer test-token",
            "params": None,
            "json": {
                "customer_id": 101,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
                "is_default": True,
            },
        }]
        assert db.query(AgentToolCall).one().tool_name == "create_deployment_info"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_payment_plan_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_payment_plan",
            _confirmed_context_for(db, "create_payment_plan"),
            {
                "contract_id": 201,
                "stage_name": "AI登记回款计划",
                "planned_amount": 300000,
                "due_date": "2026-07-24",
            },
        )

        assert result.success is True
        assert fake_client.calls[0]["method"] == "POST"
        assert fake_client.calls[0]["path"] == "/v1/payments/contracts/201/payment-plans"
        assert fake_client.calls[0]["json"]["plans"][0]["planned_amount"] == 300000
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_opportunity_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_opportunity",
            _confirmed_context_for(db, "create_opportunity"),
            {
                "opportunity": {
                    "customer_id": 101,
                    "opportunity_name": "广州睿狐科技 100人订阅1年商机",
                    "total_amount": 50000,
                    "user_count": 100,
                    "license_type": "SUBSCRIPTION",
                    "subscription_years": 1,
                    "purchase_type": "NEW",
                    "expected_closing_date": "2026-08-31",
                },
            },
        )

        assert result.success is True
        assert fake_client.calls[0]["method"] == "POST"
        assert fake_client.calls[0]["path"] == "/v1/opportunities/"
        assert fake_client.calls[0]["json"]["customer_id"] == 101
        assert fake_client.calls[0]["json"]["total_amount"] == 50000
        assert "opportunity_name" not in fake_client.calls[0]["json"]
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_payment_record_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_payment_record",
            _confirmed_context_for(db, "create_payment_record"),
            {
                "payment_plan_id": 301,
                "actual_amount": 300000,
                "payment_date": "2026-07-24",
                "commission_member_id": "9",
            },
        )

        assert result.success is True
        assert fake_client.calls[0]["method"] == "POST"
        assert fake_client.calls[0]["path"] == "/v1/payments/payment-plans/301/records"
        assert fake_client.calls[0]["json"]["commission_member_id"] == "9"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_customer_member_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.create_customer_member(
            _context(db),
            customer_id=101,
            member={
                "user_id": "9",
                "member_role": "PRESALES",
                "access_level": "FOLLOW_UP",
            },
        )

        assert result.success is True
        assert result.data["id"] == 6201
        assert fake_client.calls == [{
            "method": "POST",
            "path": "/v1/customers/101/members",
            "authorization": "Bearer test-token",
            "params": None,
            "json": {
                "user_id": "9",
                "member_role": "PRESALES",
                "access_level": "FOLLOW_UP",
            },
        }]
        assert db.query(AgentToolCall).one().tool_name == "create_customer_member"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_registry_exposes_langchain_structured_tools():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        tools = {tool.name: tool for tool in registry.to_langchain_tools(_context(db))}
        assert "search_customers" in tools

        result = await tools["search_customers"].ainvoke({"keyword": "越秀金融", "limit": 5})

        assert result["event"] == "tool_result"
        assert result["tool_name"] == "search_customers"
        assert result["success"] is True
        assert fake_client.calls[0]["path"] == "/v1/customers/"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_registry_exposes_readonly_langchain_tools_only():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        tools = {
            tool.name: tool
            for tool in registry.to_readonly_langchain_tools(
                _context(db),
                allowed_tool_names=["search_customers", "create_customer_follow_up"],
            )
        }

        assert set(tools) == {"search_customers"}
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_registry_blocks_write_without_hitl_confirmation():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        with pytest.raises(Exception) as exc_info:
            await registry.execute(
                "create_customer_follow_up",
                _context(db),
                {"customer_id": 101, "content": "客户项目还在评估"},
            )

        assert "HITL approve" in str(exc_info.value)
        assert fake_client.calls == []
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_registry_allows_confirmed_write():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    registry = AgentToolRegistry(tool_service=service)
    try:
        result = await registry.execute(
            "create_customer_follow_up",
            _confirmed_context(db),
            {"customer_id": 101, "content": "客户项目还在评估"},
        )

        assert result.success is True
        assert fake_client.calls[0]["path"] == "/v1/customer-follow-ups/101"
    finally:
        db.close()
        engine.dispose()


def test_agent_langchain_hitl_middleware_is_built_from_write_tools():
    middleware = build_langchain_hitl_middleware()

    assert middleware
