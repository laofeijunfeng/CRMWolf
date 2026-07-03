"""Task 2.2 (B2): EXECUTE 分支不再 TypeError。

dialogue.py:733 调 execute(pending) 缺少 action_id 参数，
而 ActionExecutor.execute(pending, action_id) 需要 action_id 用于审计归因。
修复后应传入 pending.action_id。
"""
from unittest.mock import MagicMock, AsyncMock

import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode
from app.glue.core.executor import ExecutionResult


@pytest.fixture
def engine():
    """DialogueEngine with mock db。"""
    return DialogueEngine(db=MagicMock(), tenant_id=1, user_id=2)


@pytest.fixture
def executing_session():
    """EXECUTING 模式 session，带待执行的 pending action。"""
    return GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.EXECUTING,
        pending=PendingAction(
            action_id="test-action-123",  # 必须有 action_id
            intent_type="create_follow_up",
            slots={"customer_id": 1, "content": "跟进内容"},
            missing_slots=[],
            preview_snapshot={"changes": [{"field": "content", "new": "跟进内容"}]},
        ),
    )


@pytest.mark.asyncio
async def test_execute_branch_does_not_typeerror(engine, executing_session, monkeypatch):
    """B2: execute(pending) 缺 action_id 已修，EXECUTING 分支不再 TypeError。"""
    captured = {}

    async def fake_execute(pending, action_id):
        """捕获 execute 调用参数，验证 action_id 非空。"""
        captured["action_id"] = action_id
        captured["pending_action_id"] = pending.action_id
        assert action_id, "action_id 不能为空"
        return ExecutionResult(
            success=True,
            message="跟进已创建",
            action_id=action_id,
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    result = await engine.dispatch(executing_session, "确认")

    # 验证 execute 被调用且 action_id 正确传入
    assert captured.get("action_id") == "test-action-123", \
        f"execute 应收到 action_id，实际收到: {captured}"
    assert result.action != DialogueAction.ERROR, \
        f"EXECUTE 不应 ERROR: {result.message}"
    assert result.success, f"执行应成功: {result.message}"