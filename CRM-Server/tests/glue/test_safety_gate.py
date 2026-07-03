"""Task 3.3: SafetyGateway 风险分级门。

测试风险分级决策：
- LOW + confidence >= 0.85 → 自动执行
- MEDIUM + confidence >= 0.90 → 自动执行
- HIGH → 强制确认
- 不达标 → 需要确认（PREVIEW）
"""
from unittest.mock import MagicMock, AsyncMock
import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode
from app.glue.core.intent import IntentResult, MultiIntentResult
from app.glue.core.executor import PreviewResult, ExecutionResult


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


# ==================== SafetyGateway.assess() Tests ====================

@pytest.mark.asyncio
async def test_safety_gateway_assess_low_risk():
    """LOW 风险意图应返回 LOW 等级。"""
    from app.glue.core.safety import SafetyGateway

    gateway = SafetyGateway()
    result = await gateway.assess("create_follow_up", confidence=0.9)

    assert result.level == "LOW"
    assert result.confidence == 0.9
    assert result.outcome_type == "generic"
    assert result.auto_execute is True  # LOW + confidence >= 0.85


@pytest.mark.asyncio
async def test_safety_gateway_assess_medium_risk():
    """MEDIUM 风险意图应返回 MEDIUM 等级。"""
    from app.glue.core.safety import SafetyGateway

    gateway = SafetyGateway()
    result = await gateway.assess("update_amount", confidence=0.92)

    assert result.level == "MEDIUM"
    assert result.confidence == 0.92
    assert result.outcome_type == "generic"
    assert result.auto_execute is True  # MEDIUM + confidence >= 0.90


@pytest.mark.asyncio
async def test_safety_gateway_assess_high_risk():
    """HIGH 风险意图应返回 HIGH 等级，强制确认。"""
    from app.glue.core.safety import SafetyGateway

    gateway = SafetyGateway()
    result = await gateway.assess("win_opportunity", confidence=0.95)

    assert result.level == "HIGH"
    assert result.confidence == 0.95
    assert result.outcome_type == "win"
    assert result.auto_execute is False  # HIGH 强制确认


@pytest.mark.asyncio
async def test_safety_gateway_assess_lose_outcome_type():
    """lose_opportunity 应返回 outcome_type='lose'。"""
    from app.glue.core.safety import SafetyGateway

    gateway = SafetyGateway()
    result = await gateway.assess("lose_opportunity", confidence=0.88)

    assert result.level == "HIGH"
    assert result.outcome_type == "lose"
    assert result.auto_execute is False


@pytest.mark.asyncio
async def test_safety_gateway_assess_low_confidence_needs_confirm():
    """低置信度即使 LOW 风险也需确认。"""
    from app.glue.core.safety import SafetyGateway

    gateway = SafetyGateway()
    result = await gateway.assess("create_follow_up", confidence=0.70)

    assert result.level == "LOW"
    assert result.auto_execute is False  # confidence < 0.85


@pytest.mark.asyncio
async def test_safety_gateway_assess_medium_low_confidence_needs_confirm():
    """MEDIUM 风险低置信度需确认。"""
    from app.glue.core.safety import SafetyGateway

    gateway = SafetyGateway()
    result = await gateway.assess("update_amount", confidence=0.85)

    assert result.level == "MEDIUM"
    assert result.auto_execute is False  # confidence < 0.90


# ==================== DialogueEngine Integration Tests ====================

@pytest.mark.asyncio
async def test_low_risk_high_confidence_auto_executes(engine, idle_session, monkeypatch):
    """create_follow_up(LOW) + confidence 0.9 → 不等用户确认直接 EXECUTE。

    Task 3.3: LOW + confidence >= 0.85 应自动执行，跳过 PREVIEW。
    """
    captured = {}

    # Mock intent_detector.detect_multi 返回单意图结果（槽位齐全，高置信度）
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.9,  # HIGH confidence
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

    # Mock action_executor.execute 返回成功结果
    async def fake_execute(pending, action_id=None):
        captured["execute_called"] = True
        return ExecutionResult(
            success=True,
            message="跟进记录已创建",
            action_id="test-action-123",
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    # 触发意图处理
    result = await engine.dispatch(idle_session, "跟进张三，刚通了电话")

    # 验证：直接 EXECUTE，不等 PREVIEW
    assert result.action == DialogueAction.EXECUTE_ACTION, f"LOW+高置信度应直接 EXECUTE，实际 {result.action}"
    assert result.success is True
    assert captured.get("execute_called") is True, "execute() 应被调用"


@pytest.mark.asyncio
async def test_medium_risk_high_confidence_auto_executes(engine, idle_session, monkeypatch):
    """update_amount(MEDIUM) + confidence 0.92 → 自动执行。

    Task 3.3: MEDIUM + confidence >= 0.90 应自动执行。
    """
    captured = {}

    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="update_amount",
                    confidence=0.92,  # MEDIUM threshold
                    reasoning="用户要修改金额",
                    slots={"opportunity_id": 1, "amount": 50000},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    async def fake_execute(pending, action_id=None):
        captured["execute_called"] = True
        return ExecutionResult(
            success=True,
            message="金额已更新",
            action_id="test-action-456",
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    result = await engine.dispatch(idle_session, "把金额改成5万")

    assert result.action == DialogueAction.EXECUTE_ACTION, f"MEDIUM+高置信度应直接 EXECUTE，实际 {result.action}"
    assert captured.get("execute_called") is True


@pytest.mark.asyncio
async def test_high_risk_forces_confirm(engine, idle_session, monkeypatch):
    """win_opportunity(HIGH) → 必须等用户确认。

    Task 3.3: HIGH 风险必须确认，应进入 PREVIEW。
    """
    captured = {}

    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="win_opportunity",
                    confidence=0.95,  # 即使高置信度
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

    # Mock preview 返回结果
    async def fake_preview(pending):
        captured["preview_called"] = True
        return PreviewResult(
            success=True,
            message="即将标记为赢单",
            action_id="test-action-789",
            preview_data={"changes": [{"field": "status", "old": "negotiation", "new": "won"}]},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    result = await engine.dispatch(idle_session, "确认赢单")

    # HIGH 风险应进入 PREVIEW
    assert result.action == DialogueAction.PREVIEW_ACTION, f"HIGH 风险应进入 PREVIEW，实际 {result.action}"
    assert result.next_mode == SessionMode.PREVIEW
    assert captured.get("preview_called") is True, "preview() 应被调用"
    # outcome_type 应为 "win"
    assert result.data.get("outcome_type") == "win", f"outcome_type 应为 'win'，实际 {result.data}"


@pytest.mark.asyncio
async def test_low_risk_low_confidence_needs_confirm(engine, idle_session, monkeypatch):
    """LOW 风险但低置信度 → 需要确认。

    Task 3.3: LOW + confidence < 0.85 需确认。
    """
    captured = {}

    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",
                    confidence=0.70,  # 低于 0.85
                    reasoning="可能要跟进？不确定",
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
        captured["preview_called"] = True
        return PreviewResult(
            success=True,
            message="将创建跟进记录",
            action_id="test-action-111",
            preview_data={},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    result = await engine.dispatch(idle_session, "跟进张三")

    # 低置信度需确认
    assert result.action == DialogueAction.PREVIEW_ACTION, f"低置信度应进入 PREVIEW，实际 {result.action}"
    assert captured.get("preview_called") is True


@pytest.mark.asyncio
async def test_outcome_type_generic_for_normal_intent(engine, idle_session, monkeypatch):
    """普通意图的 outcome_type 应为 'generic'。"""
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="create_follow_up",  # LOW 风险，非 win/lose
                    confidence=0.70,  # 低置信度触发 PREVIEW
                    reasoning="跟进意图",
                    slots={"customer_id": 1, "content": "跟进"},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    async def fake_preview(pending):
        return PreviewResult(
            success=True,
            message="将创建跟进记录",
            action_id="test-action-222",
            preview_data={},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    result = await engine.dispatch(idle_session, "跟进张三")

    assert result.data.get("outcome_type") == "generic", f"outcome_type 应为 'generic'，实际 {result.data}"


@pytest.mark.asyncio
async def test_outcome_type_lose_for_lose_opportunity(engine, idle_session, monkeypatch):
    """lose_opportunity 的 outcome_type 应为 'lose'。"""
    async def fake_detect_multi(text, session, auth_token=None):
        return MultiIntentResult(
            is_multi=False,
            intents=[
                IntentResult(
                    intent="lose_opportunity",  # HIGH 风险
                    confidence=0.88,
                    reasoning="输单意图",
                    slots={"opportunity_id": 1},
                    missing_fields=[],
                    missing_slots=[],
                    needs_entity_resolution=False,
                )
            ],
            reasoning="单意图",
        )

    monkeypatch.setattr(engine.intent_detector, "detect_multi", fake_detect_multi)

    async def fake_preview(pending):
        return PreviewResult(
            success=True,
            message="即将标记为输单",
            action_id="test-action-333",
            preview_data={},
            requires_confirmation=True,
        )

    monkeypatch.setattr(engine.action_executor, "preview", fake_preview)

    result = await engine.dispatch(idle_session, "这个商机输了")

    assert result.data.get("outcome_type") == "lose", f"outcome_type 应为 'lose'，实际 {result.data}"