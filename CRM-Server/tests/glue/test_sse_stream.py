"""Task 3.1: Glue SSE 流式化——事件契约对齐 ReAct（兼容前端）。

前端依赖事件：start/result/complete/error
Phase 3.1 MVP: 基于 dispatch() 包装，先实现基础事件。

确保 Glue SSE 输出的事件格式与 ReAct 兼容，前端无需改动。
"""
from unittest.mock import MagicMock
import pytest

from app.glue.core.dialogue import DialogueEngine
from app.glue.core.session import GlueSession
from app.glue.config import SessionMode
from app.glue.core.intent import IntentResult, MultiIntentResult
from app.glue.core.executor import PreviewResult, ExecutionResult
from app.glue.core.confirm import ConfirmationResult
from app.glue.core.cancel import CancelResult


@pytest.fixture
def engine():
    """DialogueEngine with mock db。"""
    return DialogueEngine(db=MagicMock(), tenant_id=1, user_id=2)


@pytest.fixture
def idle_session():
    """IDLE 模式 session。"""
    return GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.IDLE,
    )


@pytest.mark.asyncio
async def test_glue_sse_emits_start_result_complete(engine, idle_session, monkeypatch):
    """Glue SSE 必须发出 start/result/complete 事件（兼容前端）。"""
    from app.glue.core.sse_streamer import GlueSSEStreamer

    # Mock intent detection
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.9,
                    reasoning="用户要跟进",
                    slots={"customer_id": 1, "content": "跟进内容"},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    # Mock preview (LOW risk, auto execute)
    async def fake_preview(pending):
        return PreviewResult(
            success=True,
            message="将创建跟进",
            action_id="test-action",
            preview_data={"changes": []},
            requires_confirmation=False,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # Mock execute
    async def fake_execute(pending, action_id):
        return ExecutionResult(
            success=True,
            message="跟进已创建",
            action_id=action_id,
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    streamer = GlueSSEStreamer()
    events = []
    async for ev in streamer.stream(engine, idle_session, "sess-1", "创建跟进"):
        events.append(ev)

    joined = "".join(events)

    # 必须有 start 事件
    assert "event: start" in joined, "必须有 start 事件"
    assert '"session_id"' in joined or 'session_id' in joined, "start 必须含 session_id"

    # 必须有 result 事件
    assert "event: result" in joined, "必须有 result 事件"
    assert '"success"' in joined or 'success' in joined, "result 必须含 success"
    assert '"is_partial"' in joined or 'is_partial' in joined, "result 必须含 is_partial"

    # 必须有 complete 事件
    assert "event: complete" in joined, "必须有 complete 事件"


@pytest.mark.asyncio
async def test_glue_sse_error_event_on_exception(engine, idle_session, monkeypatch):
    """Glue SSE 异常时必须发出 error 事件（不崩溃）。"""
    from app.glue.core.sse_streamer import GlueSSEStreamer

    # Mock intent detection 抛出异常
    async def fake_detect_multi_error(text, session, auth_token=None):
        raise RuntimeError("AI service unavailable")

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi_error)

    streamer = GlueSSEStreamer()
    events = []
    async for ev in streamer.stream(engine, idle_session, "sess-1", "创建跟进"):
        events.append(ev)

    joined = "".join(events)

    # 必须有 start 和 error 事件
    assert "event: start" in joined
    assert "event: error" in joined, "异常时必须发出 error 事件"
    assert '"message"' in joined or 'message' in joined, "error 必须含 message"


@pytest.mark.asyncio
async def test_glue_sse_preview_confirm_path(engine, monkeypatch):
    """Glue SSE PREVIEW → 确认 → EXECUTE 路径测试。"""
    from app.glue.core.sse_streamer import GlueSSEStreamer

    # 创建 PREVIEW 模式 session
    preview_session = GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.PREVIEW,
    )
    from app.glue.core.session import PendingAction
    preview_session.pending = PendingAction(
        action_id="preview-action",
        intent_type="create_follow_up",
        slots={"customer_id": 1, "content": "跟进"},
    )

    # Mock cancel detector (not cancel)
    async def fake_detect_cancel(text):
        return CancelResult(is_cancel=False, confidence=0.9)

    monkeypatch.setattr(engine.cancel_detector, "detect", fake_detect_cancel)

    # Mock confirm detector (is confirm)
    async def fake_detect_confirm(text):
        return ConfirmationResult(is_confirm=True, confidence=0.9)

    monkeypatch.setattr(engine.confirm_detector, "detect", fake_detect_confirm)

    # Mock execute
    async def fake_execute(pending, action_id):
        return ExecutionResult(
            success=True,
            message="跟进已创建",
            action_id=action_id,
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    streamer = GlueSSEStreamer()
    events = []
    async for ev in streamer.stream(engine, preview_session, "sess-2", "确认"):
        events.append(ev)

    joined = "".join(events)

    # 必须有完整事件序列
    assert "event: start" in joined
    assert "event: result" in joined
    assert "event: complete" in joined
    assert '"success": true' in joined.lower() or '"success":true' in joined.lower()