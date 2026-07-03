"""Task 2.6 (B5): PREVIEW 状态生成真实快照，不再恒空。

executor.preview() 已实现但 dialogue.py 从不调用，导致 PendingAction.preview_snapshot
永远空 dict，用户看不到预览内容。修复后应调用 preview() 并填充 preview_snapshot。
"""
from unittest.mock import MagicMock, AsyncMock
import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode
from app.glue.core.executor import PreviewResult
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
async def test_preview_generates_snapshot(engine, idle_session, monkeypatch):
    """B5: preview() 被调用，preview_snapshot 不再恒空。"""
    captured = {}

    # Mock intent_detector.detect_multi 返回单意图结果（槽位齐全）
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.9,
                    reasoning="用户明确表示要跟进",
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
            action_id="test-action-123",
            preview_data={
                "changes": [{"field": "content", "old": None, "new": "跟进内容"}],
            },
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # 触发 slots 齐全的意图进入 PREVIEW
    result = await engine.dispatch(idle_session, "跟进张三，刚通了电话")

    # 验证 preview 被调用
    assert captured.get("called") is True, "preview() 应被调用"

    # 验证返回结果
    assert result.action == DialogueAction.PREVIEW_ACTION, f"应进入 PREVIEW，实际 {result.action}"
    assert result.next_mode == SessionMode.PREVIEW

    # 验证 preview_snapshot 不为空
    preview_snapshot = result.data.get("preview_snapshot")
    assert preview_snapshot is not None, "preview_snapshot 应存在"
    assert preview_snapshot.get("changes"), f"preview_snapshot.changes 应非空：{preview_snapshot}"
    assert preview_snapshot.get("message") == "将创建跟进记录"


@pytest.mark.asyncio
async def test_preview_failure_returns_error(engine, idle_session, monkeypatch):
    """预览失败时应返回 ERROR 而非空 PREVIEW。"""
    # Mock intent_detector.detect_multi 返回单意图结果
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.9,
                    reasoning="用户明确表示要跟进",
                    slots={"customer_id": 1},
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

    result = await engine.dispatch(idle_session, "跟进张三")

    # 验证返回 ERROR
    assert result.action == DialogueAction.ERROR, f"预览失败应返回 ERROR，实际 {result.action}"
    assert result.success is False
    assert "用户不存在" in result.message or "预览" in result.message