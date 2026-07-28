from types import SimpleNamespace

import pytest

import app.services.agent.confirmation_intent as confirmation_module
from app.services.agent.confirmation_intent import AgentConfirmationIntentService
from app.services.agent.input import AgentTurnInput
from app.services.agent.schemas import AgentConfirmationIntentDecision


def executable_task():
    return SimpleNamespace(
        id=1,
        state_json={"action": "create_customer_follow_up"},
        summary="请确认是否创建客户跟进记录",
        intent="CUSTOMER_FOLLOW_UP",
        target_type=None,
        target_id=None,
        input_json={},
    )


@pytest.mark.asyncio
async def test_confirmation_intent_accepts_structured_confirm_without_ai(monkeypatch):
    service = AgentConfirmationIntentService()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("AI should not be called for structured confirmation")

    monkeypatch.setattr(confirmation_module.agent_semantic_parser, "assess_confirmation_intent", fail_if_called)

    decision = await service.assess(
        None,
        team_id=1,
        turn_input=AgentTurnInput.confirm(source="im", provider="feishu"),
        task=executable_task(),
    )

    assert decision.intent == "confirm"
    assert decision.confidence == 1.0


@pytest.mark.asyncio
async def test_confirmation_intent_accepts_direct_text_without_ai(monkeypatch):
    service = AgentConfirmationIntentService()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("AI should not be called for direct confirmation text")

    monkeypatch.setattr(confirmation_module.agent_semantic_parser, "assess_confirmation_intent", fail_if_called)

    decision = await service.assess(
        None,
        team_id=1,
        turn_input=AgentTurnInput.text("确认"),
        task=executable_task(),
    )

    assert decision.intent == "confirm"


@pytest.mark.asyncio
async def test_confirmation_intent_uses_ai_for_semantic_text(monkeypatch):
    service = AgentConfirmationIntentService()

    async def fake_assess(*args, **kwargs):
        return AgentConfirmationIntentDecision(intent="confirm", confidence=0.91, reason="语义明确")

    monkeypatch.setattr(confirmation_module.agent_semantic_parser, "assess_confirmation_intent", fake_assess)

    decision = await service.assess(
        None,
        team_id=1,
        turn_input=AgentTurnInput.text("就按你说的来"),
        task=executable_task(),
    )

    assert decision.intent == "confirm"


@pytest.mark.asyncio
async def test_confirmation_intent_keeps_low_confidence_as_unknown(monkeypatch):
    service = AgentConfirmationIntentService()

    async def fake_assess(*args, **kwargs):
        return AgentConfirmationIntentDecision(intent="confirm", confidence=0.6, reason="不够确定")

    monkeypatch.setattr(confirmation_module.agent_semantic_parser, "assess_confirmation_intent", fake_assess)

    decision = await service.assess(
        None,
        team_id=1,
        turn_input=AgentTurnInput.text("笑脸"),
        task=executable_task(),
    )

    assert decision.intent == "unknown"
