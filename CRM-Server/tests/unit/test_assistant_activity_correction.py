"""A3: natural-language corrections refreeze the same card in exactly one version."""

from __future__ import annotations

import pytest

from app.models.assistant import AssistantAction
from app.models.assistant_turn import AssistantTurn
from app.models.customer_activity import CustomerActivity
from app.schemas.assistant_conversation import ConversationDecision, ConversationTextRequest
from app.services.assistant import turns
from app.services.assistant.coordinator import AssistantCoordinator
from app.services.assistant.task_state import load_authority, load_waiting

from tests.unit.test_assistant_activity_edit_version import confirmation_db  # noqa: F401 -- shared fixture
from tests.unit.test_assistant_activity_edit_version import persisted_temporal_confirmation

CORRECTION_TEXT = "日期不对，是2026年12月7日"
CORRECTION_QUOTE = "2026年12月7日"
NEW_WAIT = "2026-12-07T09:00:00"
UNCHANGED_FACTS = (
    "team_id", "user_id", "customer_public_id", "customer_name", "activity_kind", "source_segments",
    "source_content", "title", "summary", "next_action", "channel_status",
)


class Classifier:
    def __init__(self, value: ConversationDecision) -> None:
        self.value = value
        self.calls: list[dict[str, object]] = []

    async def classify(self, db, *, team_id, text, tasks, focused_task_public_id, recent_messages):
        self.calls.append({"text": text, "tasks": [item["public_id"] for item in tasks]})
        return self.value


def correction_decision(task, *, field="next_follow_time", new_value=CORRECTION_QUOTE,
                        quote=CORRECTION_QUOTE, route="WORKFLOW", correction=True) -> ConversationDecision:
    return ConversationDecision(
        semantic_plan={
            "speech_act": "CORRECT", "business_object": "CUSTOMER_ACTIVITY", "operation": "CREATE",
            "confidence": 0.95,
        },
        task_relation="CONTINUE_TASK", route=route, boundary="CONTINUE",
        target_task_public_id=task.public_id, confidence=0.95,
        correction={"field": field, "new_value": new_value, "quote": quote} if correction else None,
    )


async def _send_correction(session, monkeypatch, *, task, decision, text=CORRECTION_TEXT, key="a3-correction"):
    from app.services.assistant import conversation as conversation_module

    monkeypatch.setattr(conversation_module, "schedule_turn", lambda *args, **kwargs: None)
    service = conversation_module.ConversationService(classifier=Classifier(decision))
    conversation = service.open(session, team_id=1, user_id=2)
    reply = await service.submit_text(
        session, team_id=1, user_id=2,
        request=ConversationTextRequest(text=text, client_request_id=key, expected_version=conversation.version),
    )
    return service, reply


def _turn(session, reply) -> AssistantTurn:
    assert reply.submission is not None, "the correction must be accepted for execution"
    turn = session.query(AssistantTurn).filter_by(public_id=reply.submission.turn_id).one()
    return turn


@pytest.mark.asyncio
async def test_natural_language_correction_refreezes_exactly_one_version(confirmation_db, monkeypatch):
    session, factory, _permissions = confirmation_db
    task, _coordinator, gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    before = task.version
    old_waiting = load_waiting(task)
    old_command = dict(load_authority(task).frozen_activity_command)
    gate_calls = len(gate.calls)

    _service, reply = await _send_correction(
        session, monkeypatch, task=task, decision=correction_decision(task),
    )
    turn = _turn(session, reply)
    await turns.execute_turn(turn.id, factory=factory)
    session.expire_all()
    session.refresh(task)

    waiting = load_waiting(task)
    command = load_authority(task).frozen_activity_command
    assert session.get(AssistantTurn, turn.id).status == "SUCCEEDED"
    assert waiting.type == "CONFIRMATION" and waiting.field == "activity_write"
    assert task.version == before + 1 and waiting.expected_version == task.version
    assert waiting.action_id != old_waiting.action_id
    assert command["next_follow_time"] == NEW_WAIT
    assert command["next_follow_time_text"] == CORRECTION_QUOTE
    assert command["fingerprint"] != old_command["fingerprint"]
    # Only the corrected field moved; the frozen facts and the evidence stay identical.
    assert {key: command[key] for key in UNCHANGED_FACTS} == {key: old_command[key] for key in UNCHANGED_FACTS}
    # One edit is one scoring pass and one authority advance, with no classification or structure rerun.
    assert len(gate.calls) == gate_calls + 1
    assert session.query(CustomerActivity).count() == 0 and task.committed_json == []
    audit = session.query(AssistantAction).filter_by(action="correct_activity_draft").one()
    assert audit.input_json == {
        "fields": ["next_follow_time"], "values": {"next_follow_time": CORRECTION_QUOTE}, "quote": CORRECTION_QUOTE,
    }

    stale = old_waiting
    with pytest.raises(turns.AssistantStateConflict):
        turns.accept_submit(
            session,
            task=task, key="a3-stale-card",
            input_data={"kind": "confirm", "text": None, "choice": "confirm"},
            action_id=stale.action_id, expected_version=stale.expected_version,
        )


@pytest.mark.asyncio
async def test_correction_keeps_follow_up_context_in_the_same_advance(confirmation_db, monkeypatch):
    from app.services.assistant import conversation as conversation_module
    from tests.unit.test_assistant_follow_up_context import Context

    session, factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    before = task.version
    context = Context()
    monkeypatch.setattr(
        "app.api.assistant._coordinator",
        AssistantCoordinator(
            _coordinator._next_action_chooser, structurer=_coordinator._structurer,
            quality_gate=_coordinator._quality_gate, writer=_coordinator._writer, follow_up=context,
        ),
    )

    _service, reply = await _send_correction(
        session, monkeypatch, task=task, decision=correction_decision(task), key="a3-context-correction",
    )
    turn = _turn(session, reply)
    await turns.execute_turn(turn.id, factory=factory)
    session.expire_all()
    session.refresh(task)

    waiting = load_waiting(task)
    command = load_authority(task).frozen_activity_command
    assert session.get(AssistantTurn, turn.id).status == "SUCCEEDED"
    assert task.version == before + 1 and waiting.expected_version == task.version
    assert command["next_follow_time"] == NEW_WAIT
    assert context.reads == 1
    assert command["context_status"] == "暂无可验证的历史对比"
    assert command["context_evidence"][0]["summary"] == "报价后说下周答复"
    assert "opportunity_public_id" not in (task.authority_json or {})
    assert session.query(CustomerActivity).count() == 0
    assert conversation_module.QUERY_REFUSAL_LINKS


async def _refusal(session, reply) -> tuple[str, object]:
    assert reply.submission is None, "a question or refusal must not execute a turn"
    message = reply.conversation.messages[-1]
    return message.text, message


@pytest.mark.asyncio
async def test_unclear_correction_asks_once_and_keeps_the_active_card(confirmation_db, monkeypatch):
    session, _factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    before = task.version
    turns_before = session.query(AssistantTurn).count()

    _service, reply = await _send_correction(
        session, monkeypatch, task=task,
        decision=correction_decision(task, route="CLARIFY", correction=False),
        text="不对，重新弄一下", key="a3-unclear",
    )

    text, message = await _refusal(session, reply)
    from app.services.assistant.conversation import CORRECTION_UNCLEAR_MESSAGE

    assert text == CORRECTION_UNCLEAR_MESSAGE
    assert message.task is not None and message.task.waiting is not None
    assert message.task.waiting.field == "activity_write"
    interaction = message.ui.blocks[-1]
    assert interaction.type == "interaction" and interaction.state == "ACTIVE"
    session.expire_all()
    session.refresh(task)
    assert task.version == before
    assert session.query(AssistantTurn).count() == turns_before
    assert session.query(AssistantAction).filter_by(action="correct_activity_draft").count() == 0


@pytest.mark.asyncio
async def test_correction_quote_that_is_not_in_the_message_is_asked_not_applied(confirmation_db, monkeypatch):
    session, _factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    before = task.version

    _service, reply = await _send_correction(
        session, monkeypatch, task=task,
        decision=correction_decision(task, new_value="2026年12月9日", quote="2026年12月9日"),
        text="日期不对", key="a3-ungrounded",
    )

    text, _message = await _refusal(session, reply)
    from app.services.assistant.conversation import CORRECTION_UNCLEAR_MESSAGE

    assert text == CORRECTION_UNCLEAR_MESSAGE
    session.expire_all()
    session.refresh(task)
    assert task.version == before and load_waiting(task).type == "CONFIRMATION"


@pytest.mark.asyncio
async def test_correction_of_a_field_that_cannot_change_here_is_refused(confirmation_db, monkeypatch):
    session, _factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    before = task.version

    _service, reply = await _send_correction(
        session, monkeypatch, task=task,
        decision=correction_decision(task, field="customer", new_value="另一个客户", quote="另一个客户"),
        text="客户不对，应该是另一个客户", key="a3-not-editable",
    )

    text, message = await _refusal(session, reply)
    assert text == "这项不能在这里修改；这次没有写入。"
    assert message.ui.blocks[-1].state == "ACTIVE"
    session.expire_all()
    session.refresh(task)
    assert task.version == before
    assert session.query(AssistantAction).filter_by(action="correct_activity_draft").count() == 0


def test_same_day_occurrence_never_freezes_at_midnight(monkeypatch):
    """A same-day phrase ("今天"/"刚刚") means the report time, not 00:00."""
    from datetime import datetime

    from app.services.assistant import activity_edit

    fixed = datetime(2026, 11, 24, 15, 42, 10)
    monkeypatch.setattr(activity_edit, "business_now", lambda: fixed)
    content = {"temporal_evidence": {
        "version": "temporal-evidence-v1",
        "mentions": [{
            "mention_id": "m1", "raw_text": "刚刚", "kind": "RELATIVE_DAY", "role": "OTHER",
            "source_segment_id": "seg_1", "quote_start": 0, "quote_end": 2, "anchor_at": "2026-11-24T15:00:00",
            "resolution_status": "RESOLVED", "granularity": "DATE", "state": "ACTIVE",
            "communication_time": True, "resolved_at": "2026-11-24T00:00:00",
        }],
        "actions": [],
    }}
    assert activity_edit.communication_time_evidence(content) == (fixed.replace(second=0), "DATETIME")

    # A dated occurrence keeps its own date at the recorded granularity.
    dated = {"temporal_evidence": {
        "version": "temporal-evidence-v1",
        "mentions": [{
            "mention_id": "m2", "raw_text": "昨天", "kind": "RELATIVE_DAY", "role": "OTHER",
            "source_segment_id": "seg_1", "quote_start": 0, "quote_end": 2, "anchor_at": "2026-11-24T15:00:00",
            "resolution_status": "RESOLVED", "granularity": "DATE", "state": "ACTIVE",
            "communication_time": True, "resolved_at": "2026-11-23T00:00:00",
        }],
        "actions": [],
    }}
    assert activity_edit.communication_time_evidence(dated) == (datetime(2026, 11, 23), "DATE")
