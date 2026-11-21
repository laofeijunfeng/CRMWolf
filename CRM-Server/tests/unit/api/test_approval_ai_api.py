"""Approval AI endpoint scope and SSE stability tests."""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import approval_ai as approval_ai_module
from app.api.approval_ai import parse_approval_flow
from app.core.database import Base
from app.models.approval import ApprovalFlow, ApprovalNode
from app.models.role import Role
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.schemas.approval_ai import ApprovalAIParseRequest


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _ai_create_request(*, role: str, user_id: int | None = None):
    approver_users = [{"role": role, "user_id": user_id}] if user_id is not None else None
    return approval_ai_module.ApprovalAICreateRequest(
        flow_name="自定义角色流程",
        flow_code=f"CUSTOM_{role}_{user_id or 'ALL'}",
        nodes=[
            {
                "node_name": "自定义审批",
                "node_code": "CUSTOM_APPROVAL",
                "node_order": 1,
                "approver_roles": None if user_id is not None else [role],
                "approver_users": approver_users,
            }
        ],
    )


def _ai_role_db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Role.__table__, UserRole.__table__, ApprovalFlow.__table__, ApprovalNode.__table__],
    )
    return engine, sessionmaker(bind=engine)()


@pytest.mark.asyncio
async def test_ai_create_accepts_custom_role_linked_to_current_team():
    engine, db = _ai_role_db()
    try:
        user = User(id=1, email="custom@example.com", name="自定义角色成员", status=UserStatus.ACTIVE)
        role = Role(id=1, name="自定义审阅人", code="CUSTOM_REVIEWER")
        db.add_all([user, role])
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id, team_id=101))
        db.commit()

        result = await approval_ai_module.create_approval_flow_from_ai(
            _ai_create_request(role=role.code),
            current_user=user,
            team_id=101,
            db=db,
        )

        assert result["success"] is True
        assert result["data"]["nodes"][0]["approver_roles"] == [role.code]
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_ai_create_rejects_role_not_linked_to_current_team():
    engine, db = _ai_role_db()
    try:
        user = User(id=1, email="custom@example.com", name="其他团队成员", status=UserStatus.ACTIVE)
        role = Role(id=1, name="其他团队审阅人", code="OTHER_TEAM_REVIEWER")
        db.add_all([user, role])
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id, team_id=202))
        db.commit()

        with pytest.raises(HTTPException, match="不属于当前团队"):
            await approval_ai_module.create_approval_flow_from_ai(
                _ai_create_request(role=role.code),
                current_user=user,
                team_id=101,
                db=db,
            )
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_ai_create_rejects_selected_member_without_current_team_role():
    engine, db = _ai_role_db()
    try:
        team_member = User(id=1, email="team-role@example.com", name="团队角色成员", status=UserStatus.ACTIVE)
        selected = User(id=2, email="selected@example.com", name="跨团队指定成员", status=UserStatus.ACTIVE)
        role = Role(id=1, name="团队审阅人", code="TEAM_REVIEWER")
        db.add_all([team_member, selected, role])
        db.flush()
        db.add_all([
            UserRole(user_id=team_member.id, role_id=role.id, team_id=101),
            UserRole(user_id=selected.id, role_id=role.id, team_id=202),
        ])
        db.commit()

        with pytest.raises(HTTPException, match="不属于角色"):
            await approval_ai_module.create_approval_flow_from_ai(
                _ai_create_request(role=role.code, user_id=selected.id),
                current_user=team_member,
                team_id=101,
                db=db,
            )
    finally:
        db.close()
        engine.dispose()


def test_sse_json_encoder_used():
    """SSEJsonEncoder 可导入：处理 LangChain BaseMessage，普通 dict 正常序列化。"""
    from langchain_core.messages import HumanMessage

    from app.utils.sse_encoder import SSEJsonEncoder

    assert isinstance(SSEJsonEncoder(), json.JSONEncoder)

    # 普通 dict（审批 AI 事件的真实形态）应可直接序列化
    payload = {"event": "parsed", "flow": {"min_amount": 100000.0, "max_amount": None}}
    json.dumps(payload, cls=SSEJsonEncoder)  # 不抛异常

    # BaseMessage（SSEJsonEncoder 的核心职责）应被转为可序列化 dict
    msg = HumanMessage(content="你好")
    json_str = json.dumps({"message": msg}, cls=SSEJsonEncoder, ensure_ascii=False)
    assert "你好" in json_str


async def test_sse_stream_ends_with_done_event(monkeypatch):
    """SSE 流始终以 done 事件结束（成功路径，success=True）。"""
    # mock parser service：yield status + parsed
    async def fake_stream(db, user_message, team_id):
        yield {"event": "status", "message": "正在分析..."}
        yield {"event": "parsed", "flow": {"flow_name": "测试"}, "thinking_process": "..."}

    monkeypatch.setattr(
        approval_ai_module.approval_ai_parser_service,
        "parse_approval_flow_stream",
        fake_stream,
    )

    # mock SessionLocal 避免真实 DB 连接
    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(approval_ai_module, "SessionLocal", lambda: FakeSession())

    resp = await parse_approval_flow(
        ApprovalAIParseRequest(content="测试"),
        current_user=object(),
        team_id=1,
    )

    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
    body = "".join(chunks)

    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    assert data_lines, "SSE 流应至少产生数据行"
    # done 必须是最后一个 data 事件
    assert '"event": "done"' in data_lines[-1]
    # parsed 事件后 success 应为 True
    done_payload = json.loads(data_lines[-1][len("data: "):])
    assert done_payload["event"] == "done"
    assert done_payload["success"] is True


async def test_sse_stream_emits_done_on_parser_exception(monkeypatch):
    """parser service 抛异常时，SSE 流仍以 done 事件结束（success=False）。"""
    async def broken_stream(db, user_message, team_id):
        yield {"event": "status", "message": "正在分析..."}
        raise RuntimeError("upstream blew up")
        yield  # pragma: no cover  - 让它成为 async generator

    monkeypatch.setattr(
        approval_ai_module.approval_ai_parser_service,
        "parse_approval_flow_stream",
        broken_stream,
    )

    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(approval_ai_module, "SessionLocal", lambda: FakeSession())

    resp = await parse_approval_flow(
        ApprovalAIParseRequest(content="测试"),
        current_user=object(),
        team_id=1,
    )

    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
    body = "".join(chunks)

    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    # 应有 error 事件 + 末尾 done（success=False）
    events = [json.loads(line[len("data: "):]) for line in data_lines]
    event_types = [e.get("event") for e in events]
    assert "error" in event_types
    assert event_types[-1] == "done"
    done_payload = events[-1]
    assert done_payload["success"] is False
