"""Task 2.7 / Task 3.3: Glue web 同步路径端到端验证。

验证 Glue 核心路径能端到端跑通：
1. Happy path (HIGH risk): IDLE → PREVIEW → CONFIRM → EXECUTING（无 500/TypeError）
2. Auto-exec path (LOW risk): IDLE → EXECUTE（跳过 PREVIEW）
3. Entity resolution path: IDLE → RESOLVING_ENTITY → PREVIEW（无 500）

Task 3.3 后，LOW/MEDIUM + 高置信度会跳过 PREVIEW 直接执行。
本测试使用 HIGH 风险意图验证 PREVIEW → CONFIRM → EXECUTE 流程。
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
async def test_e2e_high_risk_preview_then_execute(engine, idle_session, monkeypatch):
    """E2E HIGH risk path: IDLE → PREVIEW(带快照) → EXECUTING(确认后执行)。

    Task 3.3: HIGH 风险(win_opportunity) 强制 PREVIEW，用户确认后进入 EXECUTING。
    """
    # ===== 第一轮: IDLE → PREVIEW =====

    # Mock intent_detector.detect_multi 返回 HIGH 风险意图
    async def fake_detect_multi_round1(text, session, auth_token=None):
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

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi_round1)

    # Mock preview 返回成功
    async def fake_preview(pending):
        return PreviewResult(
            success=True,
            message="即将标记为赢单",
            action_id="action-123",
            preview_data={"changes": [{"field": "status", "old": "negotiation", "new": "won"}]},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # 第一轮: 进入 PREVIEW（HIGH 风险强制确认）
    result1 = await engine.dispatch(idle_session, "确认赢单")

    # 验证 PREVIEW 状态
    assert result1.action == DialogueAction.PREVIEW_ACTION
    assert result1.next_mode == SessionMode.PREVIEW
    assert result1.data.get("preview_snapshot") is not None
    assert result1.success is True
    assert result1.data.get("outcome_type") == "win"

    # 更新 session 为 PREVIEW 模式
    idle_session.mode = SessionMode.PREVIEW
    idle_session.pending = PendingAction(
        action_id="action-123",
        intent_type="win_opportunity",
        slots={"opportunity_id": 1},
        preview_snapshot=result1.data.get("preview_snapshot"),
    )

    # ===== 第二轮: PREVIEW → EXECUTING =====

    # Mock cancel_detector 首先返回不是取消（_handle_preview 先检查 cancel）
    async def fake_detect_cancel_round2(text):
        return CancelResult(is_cancel=False, confidence=0.9, reasoning="用户说确认，不是取消")

    monkeypatch.setattr(engine.cancel_detector, "detect", fake_detect_cancel_round2)

    # Mock confirm_detector.detect 返回确认
    async def fake_detect_confirm(text):
        return ConfirmationResult(is_confirm=True, confidence=0.9, reasoning="用户说确认")

    monkeypatch.setattr(engine.confirm_detector, "detect", fake_detect_confirm)

    # 第二轮: 确认后进入 EXECUTING
    result2 = await engine.dispatch(idle_session, "确认")

    # 验证确认后进入 EXECUTING
    assert result2.action == DialogueAction.EXECUTE_ACTION
    assert result2.success is True
    assert result2.next_mode == SessionMode.EXECUTING
    # "正在执行" 或类似提示
    assert "执行" in result2.message


@pytest.mark.asyncio
async def test_e2e_low_risk_auto_execute(engine, idle_session, monkeypatch):
    """E2E LOW risk path: IDLE → EXECUTE（跳过 PREVIEW）。

    Task 3.3: LOW 风险(create_follow_up) + 高置信度 → 直接执行。
    """
    execute_called = {}

    # Mock intent_detector.detect_multi 返回 LOW 风险意图
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",  # LOW 风险
                    confidence=0.9,  # 高置信度
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

    # Mock execute 返回成功
    async def fake_execute(pending, action_id=None):
        execute_called["called"] = True
        return ExecutionResult(
            success=True,
            message="跟进记录已创建",
            action_id="create_follow_up",
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    result = await engine.dispatch(idle_session, "创建跟进记录")

    # LOW + 高置信度应直接执行
    assert result.action == DialogueAction.EXECUTE_ACTION
    assert result.success is True
    assert result.next_mode == SessionMode.IDLE  # 执行完成后回到 IDLE
    assert execute_called.get("called") is True


@pytest.mark.asyncio
async def test_e2e_entity_resolution_path(engine, idle_session, monkeypatch):
    """E2E entity resolution path (HIGH risk): IDLE → RESOLVING_ENTITY → PREVIEW（无 500）。

    Task 3.3: LOW 风险实体消解后会直接执行，所以用 HIGH 风险测试 PREVIEW 流程。
    """
    # ===== 第一轮: IDLE → RESOLVING_ENTITY =====

    # Mock intent 需要实体消解（HIGH 风险）
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="win_opportunity",  # HIGH 风险
                    confidence=0.9,
                    reasoning="用户确认赢单",
                    slots={},  # 需要 opportunity_id
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=True,
                    entity_type_hint="Opportunity",
                    entity_keyword="那个商机",
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    # 第一轮: 进入 RESOLVING_ENTITY
    result1 = await engine.dispatch(idle_session, "确认那个商机赢单")

    # 验证进入实体消解
    assert result1.action == DialogueAction.RESOLVE_ENTITY
    assert result1.next_mode == SessionMode.RESOLVING_ENTITY
    assert result1.success is True

    # 更新 session
    idle_session.mode = SessionMode.RESOLVING_ENTITY
    idle_session.entity_resolution_context = {"entity_type": "Opportunity", "keyword": "那个商机"}
    idle_session.pending = PendingAction(
        action_id="action-456",
        intent_type="win_opportunity",
        slots={},
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
            message="即将标记为赢单",
            action_id="action-456",
            preview_data={"changes": [{"field": "status", "old": "negotiation", "new": "won"}]},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    # 第二轮: 消解后进入 PREVIEW（HIGH 风险强制确认）
    result2 = await engine.dispatch(idle_session, "确认那个商机赢单")

    # 验证不 500，进入 PREVIEW（HIGH 风险强制确认）
    assert result2.action != DialogueAction.ERROR, f"不应 ERROR: {result2.message}"
    assert result2.success is True
    assert result2.action == DialogueAction.PREVIEW_ACTION, f"HIGH 风险应进入 PREVIEW，实际 {result2.action}"
    assert result2.next_mode == SessionMode.PREVIEW


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