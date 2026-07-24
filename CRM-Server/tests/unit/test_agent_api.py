"""CRM AI Agent API tests."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import agent as agent_api
from app.core.database import Base
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentTaskStatus,
    AgentToolCall,
)
from app.services.agent.schemas import AgentPendingInterruptionDecision, AgentSemanticParseResult
from app.services.agent.tools.base import AgentToolResult


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _build_client(monkeypatch):
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
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api.get_db] = lambda: Session()
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )
    monkeypatch.setattr(agent_api, "SessionLocal", lambda: Session())

    return TestClient(app), engine


class FakeSemanticParser:
    def __init__(self, result):
        self.results = result if isinstance(result, list) else [result]
        self.calls = []

    async def parse(self, db, *, team_id, user_message, memory=None, current_date=None):
        self.calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "memory": memory,
            "current_date": current_date,
        })
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return AgentSemanticParseResult.model_validate(self.results[index])


class FakePendingInterruptionParser:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    async def assess_pending_interruption(self, db, *, team_id, user_message, pending_task, memory=None, current_date=None):
        self.calls.append({
            "team_id": team_id,
            "user_message": user_message,
            "pending_task": pending_task,
            "memory": memory,
            "current_date": current_date,
        })
        return AgentPendingInterruptionDecision.model_validate(self.decision)


def test_agent_session_and_stream_api(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {"event": "agent_step", "step": "semantic_parse", "status": "started", "content": "AI 语义理解"}
            yield {"event": "tool_result", "tool_name": "get_customer_context", "success": True}
            yield {"event": "final", "content": f"已收到：{input_state['content']}"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        assert create_response.status_code == 201, create_response.text
        session = create_response.json()
        assert session["team_id"] == 1
        assert session["user_id"] == 2
        assert session["title"] == "跟进会话"

        list_response = client.get("/v1/agent/sessions")
        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["total"] == 1

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天和越秀金融沟通了项目进展"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text
        stream_text = stream_response.text
        assert '"event": "message"' in stream_text
        assert "今天和越秀金融沟通了项目进展" in stream_text

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assert messages_response.status_code == 200, messages_response.text
        messages_body = messages_response.json()
        assert messages_body["total"] == 2
        assert [item["role"] for item in messages_body["items"]] == ["USER", "ASSISTANT"]
        assistant_message = messages_body["items"][1]
        trace_events = assistant_message["payload_json"]["trace_events"]
        assert [event["event"] for event in trace_events] == ["agent_step", "tool_result"]
        assert trace_events[1]["tool_name"] == "get_customer_context"
    finally:
        engine.dispose()


def test_agent_stream_creates_waiting_task_and_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_follow_up",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "content": input_state["content"],
                    "next_action": "下周三继续跟进",
                    "next_follow_time_text": "下周三",
                    "next_follow_time_iso": "2026-07-29T09:00:00",
                },
            }
            yield {"event": "final", "content": "请确认是否创建这条跟进记录？"}

    class FakeToolService:
        async def create_customer_follow_up(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["customer_name"] == "越秀金融"
            assert kwargs["content"] == "今天和越秀金融的王总沟通了项目进展，下周三继续跟进"
            assert kwargs["next_follow_time"] == "2026-07-29T09:00:00"
            return AgentToolResult(
                tool_name="create_customer_follow_up",
                success=True,
                data={"id": 9001, "customer_id": 101},
                tool_call_id=7001,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "confirmation_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "跟进记录已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {"id": 9001, "customer_id": 101}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_defers_follow_up_next_task_until_after_follow_up_created(monkeypatch):
    customer = {"id": 101, "account_name": "汇川技术", "owner_info": {"id": 2}, "collaborator_infos": []}

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_follow_up",
                "customer": customer,
                "payload": {
                    "customer_id": 101,
                    "content": input_state["content"],
                    "method": "微信",
                    "_next_task": {
                        "action": "collect_opportunity_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": 101,
                            "opportunity": {"customer_id": 101, "purchase_type": "RENEWAL"},
                            "missing_fields": ["total_amount", "user_count", "license_type", "expected_closing_date"],
                        },
                        "content": "这条像续费商机，要不要我继续帮你补齐商机信息？",
                    },
                },
            }
            yield {"event": "final", "content": "请确认是否创建这条跟进记录？"}

    class FakeToolService:
        async def create_customer_follow_up(self, context, **kwargs):
            return AgentToolResult(
                tool_name="create_customer_follow_up",
                success=True,
                data={"id": 9001, "customer_id": 101},
                tool_call_id=7001,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_OPPORTUNITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": "汇川技术", "confidence": 0.95, "resolution_source": "MEMORY"},
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
        "evidence": [],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "跟进会话"}).json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天微信找了汇川技术沟通续费"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert "请确认是否创建这条跟进记录" in plan_response.text
        assert '"event": "final", "content": "请确认是否创建这条跟进记录？"' in plan_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert "跟进记录已创建" in confirm_response.text
        assert "要不要我继续帮你补齐商机信息" in confirm_response.text

        yes_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert yes_response.status_code == 200, yes_response.text
        assert "还需要补充" in yes_response.text
        assert "预计成交金额" in yes_response.text
    finally:
        engine.dispose()


def test_agent_stream_persists_current_customer_memory(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [{"id": 9}],
    }

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "business_context_loaded",
                "customer_id": customer["id"],
                "customer": customer,
            }
            yield {"event": "final", "content": "已加载客户上下文。"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "记忆会话"})
        session = create_response.json()

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "睿狐科技今天回了 5 万"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            saved_session = db.query(AgentSession).one()
            assert saved_session.context_json["current_customer"] == customer
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_restores_current_customer_memory_on_next_turn(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    captured_states = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            captured_states.append(input_state)
            if len(captured_states) == 1:
                yield {
                    "event": "business_context_loaded",
                    "customer_id": customer["id"],
                    "customer": customer,
                }
                yield {"event": "final", "content": "已识别广州睿狐科技有限公司。"}
            else:
                yield {"event": "final", "content": "已继承客户上下文。"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "记忆会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "睿狐科技今天回了 5 万"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "那帮我创建一个商机，5 万 100 人使用，订阅 1 年"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert captured_states[1]["session_context"]["current_customer"] == customer
    finally:
        engine.dispose()


def test_agent_stream_collects_opportunity_fields_without_rerunning_graph(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "total_amount": 50000,
                        "user_count": 100,
                        "license_type": "SUBSCRIPTION",
                        "subscription_years": 1,
                    },
                    "missing_fields": ["purchase_type", "expected_closing_date"],
                },
            }
            yield {"event": "final", "content": "请补充采购类型和预计成交日期。"}

    fake_graph = FakeGraphService()
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", fake_graph)
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_OPPORTUNITY",
        "intent_confidence": 0.95,
        "customer": {"name_text": "广州睿狐科技有限公司", "confidence": 0.95, "resolution_source": "MEMORY"},
        "follow_up": {},
        "payment": {},
        "opportunity": {
            "purchase_type": "NEW",
            "expected_closing_date_text": "下个月30号",
            "expected_closing_date": {
                "raw_text": "下个月30号",
                "kind": "EXPLICIT_DATE",
                "direction": "future",
                "date_text": "2026-08-30",
                "confidence": 0.9,
            },
        },
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["新购，下个月30号成交"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "商机会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "好的，帮我创建一个商机，5 万，100 人，1 年订阅"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "opportunity_fields_required"' in first_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            saved_session = db.query(AgentSession).one()
            assert saved_session.context_json["current_pending_task"]["action"] == "collect_opportunity_fields"
        finally:
            db.close()

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "新购的，预计下个月 30 号成"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "opportunity_fields_completed"' in second_response.text
        assert "商机信息已补齐" in second_response.text
        assert len(fake_graph.calls) == 1

        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.state_json["action"] == "create_opportunity"
            saved_session = db.query(AgentSession).one()
            assert saved_session.context_json["current_pending_task"]["action"] == "create_opportunity"
            opportunity = task.state_json["payload"]["opportunity"]
            assert opportunity["total_amount"] == 50000
            assert opportunity["user_count"] == 100
            assert opportunity["license_type"] == "SUBSCRIPTION"
            assert opportunity["subscription_years"] == 1
            assert opportunity["purchase_type"] == "NEW"
            assert opportunity["expected_closing_date"] == "2026-08-30"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_follow_up_quality_fields_without_rerunning_graph(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州凡亚信息科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        def __init__(self):
            self.calls = []

        async def stream_events(self, input_state):
            self.calls.append(input_state)
            yield {
                "event": "follow_up_quality_required",
                "action": "collect_follow_up_quality_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "content": "凡亚信息今天反馈项目没进展",
                    "method": "AI录入",
                    "next_action": None,
                    "next_follow_time_text": None,
                    "next_follow_time_iso": None,
                },
                "content": "下一步计划什么时候、由谁、跟凡亚信息做什么跟进？",
            }
            yield {"event": "final", "content": "下一步计划什么时候、由谁、跟凡亚信息做什么跟进？"}

    class FakeQualityEvaluator:
        def __init__(self):
            self.calls = []

        async def evaluate_with_metadata(self, db, *, team_id, user_message, semantic_result, memory=None, current_date=None):
            self.calls.append({
                "team_id": team_id,
                "user_message": user_message,
                "semantic_result": semantic_result,
                "memory": memory,
                "current_date": current_date,
            })
            return SimpleNamespace(
                result=SimpleNamespace(
                    passed=True,
                    score=72,
                    suggested_revision="凡亚信息反馈项目暂无进展，计划本月底再联系客户，确认后续推动方式，并争取安排现场拜访。",
                    model_dump=lambda exclude_none=True: {"passed": True, "score": 72},
                )
            )

    fake_graph = FakeGraphService()
    fake_quality = FakeQualityEvaluator()
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", fake_graph)
    monkeypatch.setattr(agent_api, "agent_follow_up_quality_evaluator", fake_quality)
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CUSTOMER_FOLLOW_UP",
        "intent_confidence": 0.95,
        "customer": {"name_text": "广州凡亚信息科技有限公司", "confidence": 0.95, "resolution_source": "MEMORY"},
        "follow_up": {
            "content": "这个月底我会再联系下客户，确认下具体如何推动项目，争取能去现场拜访",
            "method": "AI录入",
            "next_action": "这个月底再联系客户，确认如何推动项目，争取现场拜访",
            "next_follow_time_text": "这个月底",
            "next_follow_time": {
                "raw_text": "这个月底",
                "kind": "MONTH_END",
                "direction": "current",
                "confidence": 0.9,
            },
        },
        "payment": {},
        "opportunity": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "customer_member": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["这个月底我会再联系下客户"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进质量会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "凡亚信息今天反馈项目没进展"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "follow_up_quality_required"' in first_response.text
        assert '"task_id": 1' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "这个月底我会再联系下客户，确认下具体如何推动项目，争取能去现场拜访",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert len(fake_graph.calls) == 1
        assert "跟进内容已补齐" in second_response.text
        assert "广州凡亚信息科技有限公司" in second_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.WAITING_USER
            assert task.state_json["action"] == "create_customer_follow_up"
            assert task.state_json["customer"] == customer
            assert task.input_json["content"] == "凡亚信息反馈项目暂无进展，计划本月底再联系客户，确认后续推动方式，并争取安排现场拜访。"
            assert "补充：" not in task.input_json["content"]
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_keeps_collected_opportunity_fields_across_turns(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "青岛四方阿尔斯通铁路运输设备有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }

    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "opportunity_fields_required",
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer["id"],
                    "opportunity": {
                        "customer_id": customer["id"],
                        "purchase_type": "RENEWAL",
                    },
                    "missing_fields": ["total_amount", "user_count", "license_type", "expected_closing_date"],
                },
            }
            yield {"event": "final", "content": "还需要补充商机信息。"}

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser([
        {
            "intent": "CREATE_OPPORTUNITY",
            "intent_confidence": 0.95,
            "customer": {"name_text": "青岛四方", "confidence": 0.95, "resolution_source": "MEMORY"},
            "follow_up": {},
            "payment": {},
            "opportunity": {
                "total_amount": 100000,
                "user_count": 15,
                "license_type": "PERPETUAL",
                "expected_closing_date_text": "9 月底",
                "expected_closing_date": {"raw_text": "9 月底", "kind": "UNKNOWN", "confidence": 0.4},
            },
            "contact": {},
            "invoice_title": {},
            "deployment_info": {},
            "business_signals": [],
            "requested_actions": [],
            "missing_fields": ["expected_closing_date"],
            "need_clarification": False,
            "clarification_question": None,
            "evidence": ["10 万预算，15 个用户，买断使用，预计 9 月底能成交"],
        },
        {
            "intent": "CREATE_OPPORTUNITY",
            "intent_confidence": 0.95,
            "customer": {"name_text": "青岛四方", "confidence": 0.95, "resolution_source": "MEMORY"},
            "follow_up": {},
            "payment": {},
            "opportunity": {
                "expected_closing_date_text": "9 月 30 号",
                "expected_closing_date": {
                    "raw_text": "9 月 30 号",
                    "kind": "MONTH_DAY",
                    "month": 9,
                    "day": 30,
                    "confidence": 0.95,
                },
            },
            "contact": {},
            "invoice_title": {},
            "deployment_info": {},
            "business_signals": [],
            "requested_actions": [],
            "missing_fields": [],
            "need_clarification": False,
            "clarification_question": None,
            "evidence": ["9 月 30 号"],
        },
    ]))

    client, engine = _build_client(monkeypatch)
    try:
        session = client.post("/v1/agent/sessions", json={"title": "商机会话"}).json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给青岛四方创建续费商机"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "客户总共是 10 万预算，计划采购 15 个用户，买断使用，预计是 9 月底能成交"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert "还需要补充" in second_response.text
        assert "预计成交日期" in second_response.text

        third_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "9 月 30 号"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert third_response.status_code == 200, third_response.text
        assert '"event": "opportunity_fields_completed"' in third_response.text
        assert "商机信息已补齐" in third_response.text
        assert "预计成交金额" not in third_response.text
        assert "采购用户数" not in third_response.text
        assert "授权模式" not in third_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            opportunity = task.state_json["payload"]["opportunity"]
            assert opportunity["total_amount"] == 100000
            assert opportunity["user_count"] == 15
            assert opportunity["license_type"] == "PERPETUAL"
            assert opportunity["purchase_type"] == "RENEWAL"
            assert opportunity["expected_closing_date"] == "2026-09-30"
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_interrupts_pending_task_for_clear_new_customer_flow(monkeypatch):
    customer = {
        "id": 101,
        "account_name": "广州睿狐科技有限公司",
        "owner_info": {"id": 2},
        "collaborator_infos": [],
    }
    captured_states = []

    class FakeGraphService:
        async def stream_events(self, input_state):
            captured_states.append(input_state)
            if len(captured_states) == 1:
                yield {
                    "event": "opportunity_fields_required",
                    "action": "collect_opportunity_fields",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer["id"],
                        "opportunity": {
                            "customer_id": customer["id"],
                            "total_amount": 50000,
                            "user_count": 100,
                            "license_type": "SUBSCRIPTION",
                            "subscription_years": 1,
                        },
                        "missing_fields": ["purchase_type", "expected_closing_date"],
                    },
                }
                yield {"event": "final", "content": "请补充采购类型和预计成交日期。"}
            else:
                yield {"event": "final", "content": "已切换处理汇川技术的跟进。"}

    fake_parser = FakePendingInterruptionParser({
        "decision": "START_NEW_FLOW",
        "confidence": 0.92,
        "detected_customer_name": "汇川技术",
        "detected_intent": "CUSTOMER_FOLLOW_UP",
        "is_field_supplement": False,
        "reason": "本轮明确提到不同客户，并描述新的跟进记录。",
        "question": None,
    })
    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", fake_parser)

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "切换会话"})
        session = create_response.json()

        first_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "好的，帮我创建一个商机，5 万，100 人，1 年订阅"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert first_response.status_code == 200, first_response.text
        assert '"event": "opportunity_fields_required"' in first_response.text

        second_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天微信找了汇川技术的沟通续费方面的事宜，本月底会对接采购",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert second_response.status_code == 200, second_response.text
        assert '"event": "pending_task_interrupted"' in second_response.text
        assert "我先切过来处理" in second_response.text
        assert captured_states[1]["content"] == "今天微信找了汇川技术的沟通续费方面的事宜，本月底会对接采购"
        assert fake_parser.calls[0]["pending_task"]["state"]["action"] == "collect_opportunity_fields"

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.SUSPENDED
            saved_session = db.query(AgentSession).one()
            assert "current_pending_task" not in saved_session.context_json
            assert saved_session.context_json["suspended_pending_tasks"][0]["id"] == task.id
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_resolves_customer_selection_before_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "customer_selection_required",
                "action": "select_customer_for_follow_up",
                "customers": [
                    {"id": 101, "account_name": "越秀金融"},
                    {"id": 102, "account_name": "越秀金融科技"},
                ],
                "payload": {
                    "content": input_state["content"],
                    "next_action": "下周三继续跟进",
                    "next_follow_time_text": "下周三",
                    "next_follow_time_iso": "2026-07-29T09:00:00",
                },
            }
            yield {"event": "final", "content": "我找到了多个可能的客户，请回复序号或客户名称确认。"}

    class FakeToolService:
        async def create_customer_follow_up(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 102
            assert kwargs["customer_name"] == "越秀金融科技"
            assert kwargs["content"] == "今天和越秀金融的王总沟通了项目进展，下周三继续跟进"
            assert kwargs["next_follow_time"] == "2026-07-29T09:00:00"
            return AgentToolResult(
                tool_name="create_customer_follow_up",
                success=True,
                data={"id": 9002, "customer_id": 102},
                tool_call_id=7002,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "customer_selection_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        select_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "2"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert select_response.status_code == 200, select_response.text
        assert '"event": "customer_selected"' in select_response.text
        assert "请确认是否创建这条跟进记录" in select_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "跟进记录已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.target_id == 102
            assert task.result_json == {"id": 9002, "customer_id": 102}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_contact_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "contact_fields_required",
                "action": "collect_contact_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "contact": {"name": "王总", "is_decision_maker": False},
                    "missing_fields": ["mobile", "position", "gender"],
                },
            }
            yield {"event": "final", "content": "还需要补充：手机号、职务、性别。"}

    class FakeToolService:
        async def create_contact(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["contact"] == {
                "name": "王总",
                "is_decision_maker": False,
                "mobile": "13800138000",
                "position": "总经理",
                "gender": "1",
            }
            return AgentToolResult(
                tool_name="create_contact",
                success=True,
                data={"id": 8001, "customer_id": 101, "name": "王总"},
                tool_call_id=7101,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_CONTACT",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {},
        "contact": {"mobile": "13800138000", "position": "总经理", "gender": "1"},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["手机号13800138000，职务总经理，男"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "联系人会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建联系人王总"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "contact_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "手机号13800138000，职务总经理，男"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "contact_fields_completed"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "联系人已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {"id": 8001, "customer_id": 101, "name": "王总"}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_invoice_title_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "invoice_title_fields_required",
                "action": "collect_invoice_title_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "invoice_title": {"title_type": "COMPANY"},
                    "missing_fields": ["title", "taxpayer_id"],
                    "set_default": False,
                },
            }
            yield {"event": "final", "content": "还需要补充：开票抬头、纳税人识别号。"}

    class FakeToolService:
        async def create_invoice_title(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["invoice_title"] == {
                "title_type": "COMPANY",
                "title": "越秀金融控股有限公司",
                "taxpayer_id": "91440000123456789X",
            }
            assert kwargs["set_default"] is True
            return AgentToolResult(
                tool_name="create_invoice_title",
                success=True,
                data={
                    "invoice_title": {
                        "id": 6001,
                        "customer_id": 101,
                        "title": "越秀金融控股有限公司",
                    },
                    "set_default": True,
                },
                tool_call_id=7201,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_INVOICE_TITLE",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {},
        "contact": {},
        "invoice_title": {
            "title": "越秀金融控股有限公司",
            "taxpayer_id": "91440000123456789X",
            "set_default": True,
        },
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["抬头是越秀金融控股有限公司，税号91440000123456789X，设为默认"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "发票抬头会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建发票抬头"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "invoice_title_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "抬头是越秀金融控股有限公司，税号91440000123456789X，设为默认",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "invoice_title_fields_completed"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "发票抬头已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {
                "invoice_title": {
                    "id": 6001,
                    "customer_id": 101,
                    "title": "越秀金融控股有限公司",
                },
                "set_default": True,
            }
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_customer_member_selection_loads_member_candidates(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "customer_selection_required",
                "action": "select_customer_for_customer_member",
                "customers": [
                    {"id": 101, "account_name": "越秀金融控股有限公司"},
                    {"id": 102, "account_name": "越秀金融租赁有限公司"},
                ],
                "payload": {
                    "customer_member": {"user_name": "张三", "member_role": "PRESALES"},
                    "missing_fields": [],
                },
            }
            yield {"event": "final", "content": "我找到了多个可能的客户，请回复序号确认。"}

    class FakeAPIClient:
        async def request(self, method, path, authorization, **kwargs):
            assert method == "GET"
            assert path == "/v1/customers/101/member-candidates"
            assert authorization == "Bearer test-token"
            return [{"id": 301, "name": "张三", "already_member": False}]

    class FakeToolService:
        def __init__(self):
            self.api_client = FakeAPIClient()

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", FakeToolService)

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "客户成员会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融添加售前张三"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "customer_selection_required"' in plan_response.text

        select_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "1"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert select_response.status_code == 200, select_response.text
        assert '"event": "customer_selected"' in select_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.WAITING_USER
            assert task.state_json["action"] == "collect_customer_member_fields"
            assert task.state_json["payload"]["customer_id"] == 101
            assert task.state_json["payload"]["member_candidates"] == [
                {"id": 301, "name": "张三", "already_member": False}
            ]
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_deployment_info_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "deployment_info_fields_required",
                "action": "collect_deployment_info_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "deployment_info": {"customer_id": 101, "is_default": False},
                    "missing_fields": ["deployment_name", "server_address", "authorized_users"],
                },
            }
            yield {"event": "final", "content": "还需要补充：部署名称、服务器地址、授权人数。"}

    class FakeToolService:
        async def create_deployment_info(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["deployment_info"] == {
                "customer_id": 101,
                "is_default": True,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
            }
            return AgentToolResult(
                tool_name="create_deployment_info",
                success=True,
                data={
                    "id": 6101,
                    "customer_id": 101,
                    "deployment_name": "生产环境",
                },
                tool_call_id=7301,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())
    monkeypatch.setattr(agent_api, "agent_semantic_parser", FakeSemanticParser({
        "intent": "CREATE_DEPLOYMENT_INFO",
        "intent_confidence": 0.95,
        "customer": {"name_text": "越秀金融", "confidence": 0.95},
        "follow_up": {},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {
            "deployment_name": "生产环境",
            "server_address": "https://crm.example.com",
            "authorized_users": 100,
            "is_default": True,
        },
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": ["部署名称是生产环境，服务器地址 https://crm.example.com，授权人数100，设为默认"],
    }))

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "部署信息会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建部署信息"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "deployment_info_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "部署名称是生产环境，服务器地址 https://crm.example.com，授权人数100，设为默认",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "deployment_info_fields_completed"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "部署信息已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {
                "id": 6101,
                "customer_id": 101,
                "deployment_name": "生产环境",
            }
        finally:
            db.close()
    finally:
        engine.dispose()
