"""Task 2.7: Glue web 同步路径端到端验证。

验证 Glue 核心路径能端到端跑通：
1. Happy path: IDLE → PREVIEW → CONFIRM → EXECUTE（无 500/TypeError）
2. Entity resolution path: IDLE → RESOLVING_ENTITY → PREVIEW（无 500）

由于 HTTP endpoint 测试需要大量 mock（Redis/DB/UserMapper），本测试直接验证 DialogueEngine
的核心路径逻辑，确保状态流转正确且不崩溃。
"""
from unittest.mock import MagicMock, AsyncMock
import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode
from app.glue.core.intent import IntentResult, MultiIntentResult
from app.glue.core.executor import PreviewResult, ExecutionResult
from app.glue.core.types import EntityResolveResult
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
async def test_e2e_happy_path_preview_then_execute(engine, idle_session, monkeypatch):
    """E2E happy path: IDLE → PREVIEW(带快照) → EXECUTE(成功)。

    模拟用户说"创建跟进"，进入 PREVIEW，然后确认执行。
    """
    # ===== 第一轮: IDLE → PREVIEW =====

    # Mock intent_detector.detect_multi 返回意图（槽位齐全）
    async def fake_detect_multi_round1(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.9,
                    reasoning="用户明确表示要跟进",
                    slots={"customer_id": 1, "content": "跟进内容"},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi_round1)

    # Mock preview 返回成功
    async def fake_preview(pending):
        return PreviewResult(
            success=True,
            message="将创建跟进记录",
            action_id="action-123",
            preview_data={"changes": [{"field": "content", "old": None, "new": "跟进内容"}]},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # 第一轮: 进入 PREVIEW
    result1 = await engine.dispatch(idle_session, "创建跟进记录")

    # 验证 PREVIEW 状态
    assert result1.action == DialogueAction.PREVIEW_ACTION
    assert result1.next_mode == SessionMode.PREVIEW
    assert result1.data.get("preview_snapshot") is not None
    assert result1.success is True

    # 更新 session 为 PREVIEW 模式
    idle_session.mode = SessionMode.PREVIEW
    idle_session.pending = PendingAction(
        action_id="action-123",
        intent_type="create_follow_up",
        slots={"customer_id": 1, "content": "跟进内容"},
        preview_snapshot=result1.data.get("preview_snapshot"),
    )

    # ===== 第二轮: PREVIEW → EXECUTE =====

    # Mock cancel_detector 首先返回不是取消（_handle_preview 先检查 cancel）
    async def fake_detect_cancel_round2(text):
        return CancelResult(is_cancel=False, confidence=0.9, reasoning="用户说确认，不是取消")

    monkeypatch.setattr(engine.cancel_detector, "detect", fake_detect_cancel_round2)

    # Mock confirm_detector.detect 返回确认
    async def fake_detect_confirm(text):
        return ConfirmationResult(is_confirm=True, confidence=0.9, reasoning="用户说确认")

    monkeypatch.setattr(engine.confirm_detector, "detect", fake_detect_confirm)

    # Mock execute 返回成功
    async def fake_execute(pending, action_id):
        return ExecutionResult(
            success=True,
            message="跟进记录已创建",
            action_id=action_id,
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    # 第二轮: 确认执行
    result2 = await engine.dispatch(idle_session, "确认")

    # 验证确认后进入 EXECUTE/EXECUTING
    assert result2.action == DialogueAction.EXECUTE_ACTION
    assert result2.success is True
    assert result2.next_mode == SessionMode.EXECUTING
    # "正在执行" 或类似提示
    assert "执行" in result2.message


@pytest.mark.asyncio
async def test_e2e_entity_resolution_path(engine, idle_session, monkeypatch):
    """E2E entity resolution path: IDLE → RESOLVING_ENTITY → PREVIEW（无 500）。

    模拟用户说"跟进张三"，需要实体消解，消解成功后进入 PREVIEW。
    """
    # ===== 第一轮: IDLE → RESOLVING_ENTITY =====

    # Mock intent 需要实体消解
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.9,
                    reasoning="用户要跟进客户",
                    slots={"content": "跟进内容"},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=True,
                    entity_type_hint="Customer",
                    entity_keyword="张三",
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    # 第一轮: 进入 RESOLVING_ENTITY
    result1 = await engine.dispatch(idle_session, "跟进张三")

    # 验证进入实体消解
    assert result1.action == DialogueAction.RESOLVE_ENTITY
    assert result1.next_mode == SessionMode.RESOLVING_ENTITY
    assert result1.success is True

    # 更新 session
    idle_session.mode = SessionMode.RESOLVING_ENTITY
    idle_session.entity_resolution_context = {"entity_type": "Customer", "keyword": "张三"}
    idle_session.pending = PendingAction(
        action_id="action-456",
        intent_type="create_follow_up",
        slots={"content": "跟进内容"},
    )

    # ===== 第二轮: RESOLVING_ENTITY → PREVIEW =====

    # Mock entity_resolver 消解成功
    async def fake_resolve(text, entity_type, session):
        return EntityResolveResult(
            entity_id=1,
            entity_type=entity_type,
            confidence=0.9,
        )

    monkeypatch.setattr(engine.entity_resolver, "resolve", fake_resolve)

    # Mock preview 成功
    async def fake_preview(pending):
        return PreviewResult(
            success=True,
            message="将为张三创建跟进",
            action_id="action-456",
            preview_data={"changes": [{"field": "content", "old": None, "new": "跟进内容"}]},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # 第二轮: 消解后进入 PREVIEW
    result2 = await engine.dispatch(idle_session, "跟进张三")

    # 验证不 500，进入 PREVIEW
    assert result2.action != DialogueAction.ERROR, f"不应 ERROR: {result2.message}"
    assert result2.success is True
    # 应该进入 PREVIEW 或 COLLECTING（如果还有缺失槽位）
    assert result2.next_mode in (SessionMode.PREVIEW, SessionMode.COLLECTING)


@pytest.mark.asyncio
async def test_e2e_preview_cancel_path(engine, idle_session, monkeypatch):
    """E2E preview cancel path: PREVIEW → CANCEL → IDLE。"""
    # 设置 session 为 PREVIEW 模式
    idle_session.mode = SessionMode.PREVIEW
    idle_session.pending = PendingAction(
        action_id="action-789",
        intent_type="create_follow_up",
        slots={"customer_id": 1, "content": "跟进内容"},
    )

    # Mock cancel_detector.detect 返回取消
    async def fake_detect_cancel(text):
        return CancelResult(is_cancel=True, confidence=0.9, reasoning="用户说取消")

    monkeypatch.setattr(engine.cancel_detector, "detect", fake_detect_cancel)

    # 取消
    result = await engine.dispatch(idle_session, "取消")

    # 验证取消成功
    assert result.action == DialogueAction.CANCEL_ACTION
    assert result.next_mode == SessionMode.IDLE
    assert result.success is True