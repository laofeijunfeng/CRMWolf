"""Task 2.6 (B5) / Task 3.3: PREVIEW 状态生成真实快照，风险分级门。

Task 3.3 后:
- LOW/MEDIUM + 高置信度 → 直接 EXECUTE（跳过 PREVIEW）
- HIGH 或低置信度 → PREVIEW（需要确认）

本测试验证 HIGH 风险或低置信度场景仍进入 PREVIEW 并生成快照。
"""
from unittest.mock import MagicMock, AsyncMock
import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode
from app.glue.core.executor import PreviewResult, ExecutionResult
from app.glue.core.intent import IntentResult, MultiIntentResult


@pytest.fixture
def engine():
    """DialogueEngine with mock db。"""
    return DialogueEngine(db=MagicMock(), tenant_id=1, user_id=2)


@pytest.fixture
def idle_session():
    """IDLE 模式 session（无 pending）。"""
    return GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.IDLE,
    )


@pytest.mark.asyncio
async def test_preview_generates_snapshot_for_high_risk(engine, idle_session, monkeypatch):
    """Task 3.3: HIGH 风险(win_opportunity) → 强制 PREVIEW，生成快照。"""
    captured = {}

    # Mock intent_detector.detect_multi 返回 HIGH 风险意图
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="win_opportunity",  # HIGH 风险
                    confidence=0.95,  # 即使高置信度也需确认
                    reasoning="用户确认赢单",
                    slots={"opportunity_id": 1},
                    missing_fields=[],  # 槽位齐全
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    # Mock action_executor.preview 返回预览结果
    async def fake_preview(pending):
        captured["called"] = True
        return PreviewResult(
            success=True,
            message="即将标记为赢单",
            action_id="test-action-123",
            preview_data={
                "changes": [{"field": "status", "old": "negotiation", "new": "won"}],
            },
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # 触发 HIGH 风险意图进入 PREVIEW
    result = await engine.dispatch(idle_session, "确认赢单")

    # 验证 preview 被调用
    assert captured.get("called") is True, "preview() 应被调用（HIGH 风险强制确认）"

    # 验证返回结果
    assert result.action == DialogueAction.PREVIEW_ACTION, f"应进入 PREVIEW，实际 {result.action}"
    assert result.next_mode == SessionMode.PREVIEW

    # 验证 preview_snapshot 不为空
    preview_snapshot = result.data.get("preview_snapshot")
    assert preview_snapshot is not None, "preview_snapshot 应存在"
    assert preview_snapshot.get("changes"), f"preview_snapshot.changes 应非空：{preview_snapshot}"
    assert preview_snapshot.get("message") == "即将标记为赢单"

    # 验证 outcome_type
    assert result.data.get("outcome_type") == "win"


@pytest.mark.asyncio
async def test_preview_generates_snapshot_for_low_confidence(engine, idle_session, monkeypatch):
    """Task 3.3: LOW 风险 + 低置信度 → PREVIEW，生成快照。"""
    captured = {}

    # Mock intent_detector.detect_multi 返回 LOW 风险意图（但低置信度）
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",  # LOW 风险
                    confidence=0.70,  # 低置信度 (< 0.85)
                    reasoning="用户可能要跟进？",
                    slots={"customer_id": 1, "content": "跟进内容"},
                    missing_fields=[],  # 槽位齐全
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    # Mock action_executor.preview 返回预览结果
    async def fake_preview(pending):
        captured["called"] = True
        return PreviewResult(
            success=True,
            message="将创建跟进记录",
            action_id="test-action-456",
            preview_data={
                "changes": [{"field": "content", "old": None, "new": "跟进内容"}],
            },
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    result = await engine.dispatch(idle_session, "跟进张三")

    # 低置信度需确认，应调用 preview
    assert captured.get("called") is True, "preview() 应被调用（低置信度需确认）"
    assert result.action == DialogueAction.PREVIEW_ACTION


@pytest.mark.asyncio
async def test_low_risk_high_confidence_auto_executes(engine, idle_session, monkeypatch):
    """Task 3.3: LOW 风险 + 高置信度 → 直接 EXECUTE，不调用 preview。"""
    from app.glue.core.executor import ExecutionResult

    preview_called = {}
    execute_called = {}

    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",  # LOW 风险
                    confidence=0.9,  # 高置信度 (>= 0.85)
                    reasoning="用户明确要跟进",
                    slots={"customer_id": 1, "content": "跟进内容"},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    async def fake_preview(pending):
        preview_called["called"] = True
        return PreviewResult(success=True, message="预览")

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    async def fake_execute(pending, action_id=None):
        execute_called["called"] = True
        return ExecutionResult(success=True, message="执行成功", action_id="test-123")

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    result = await engine.dispatch(idle_session, "跟进张三")

    # LOW + 高置信度应直接执行
    assert result.action == DialogueAction.EXECUTE_ACTION
    assert execute_called.get("called") is True, "execute() 应被调用"
    assert preview_called.get("called") is None, "preview() 不应被调用"


@pytest.mark.asyncio
async def test_preview_failure_returns_error(engine, idle_session, monkeypatch):
    """预览失败时应返回 ERROR（使用 HIGH 风险意图触发 PREVIEW）。"""
    # Mock intent_detector.detect_multi 返回 HIGH 风险意图
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="win_opportunity",  # HIGH 风险
                    confidence=0.9,
                    reasoning="用户确认赢单",
                    slots={"opportunity_id": 1},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    # Mock preview 返回失败
    async def fake_preview(pending):
        return PreviewResult(
            success=False,
            message="用户不存在",
            error="user_not_found",
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    result = await engine.dispatch(idle_session, "确认赢单")

    # 验证返回 ERROR
    assert result.action == DialogueAction.ERROR, f"预览失败应返回 ERROR，实际 {result.action}"
    assert result.success is False
    assert "用户不存在" in result.message or "预览" in result.message