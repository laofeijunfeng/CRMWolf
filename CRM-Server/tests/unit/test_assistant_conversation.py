"""Conversation public seam: routing, ownership, immutable tasks and replay."""
# ruff: noqa: RUF001 -- Tests use the exact Chinese UI copy.

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.schemas.assistant_conversation import ConversationChoiceRequest, ConversationDecision, ConversationTextRequest
from app.services.assistant import conversation as module
from app.services.assistant import conversation_router as router_module
from app.services.assistant.contracts import TaskDraft
from app.services.assistant.conversation import ConversationService
from app.services.assistant.conversation_router import (
    ROOT_UNDERSTANDING_TIMEOUT_SECONDS,
    ConversationRootClassifier,
)


@compiles(BigInteger, "sqlite")
def sqlite_integer(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                AssistantTask,
                AssistantAction,
                AssistantRequest,
                AssistantTurn,
                AssistantTurnEvent,
                AssistantConversation,
                AssistantConversationEntry,
            )
        ],
    )
    monkeypatch.setattr(module, "schedule_turn", lambda turn_id: None)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def decision(boundary="NEW", target=None, speech="ASSERT_EVENT", obj="CUSTOMER_ACTIVITY", operation="CREATE"):
    return ConversationDecision(
        semantic_plan={"speech_act": speech, "business_object": obj, "operation": operation, "confidence": 0.95},
        task_relation="CONTINUE_TASK" if boundary == "CONTINUE" else "NEW_TASK",
        route="QUERY" if speech == "ASK_FACT" else "WORKFLOW",
        boundary=boundary,
        target_task_public_id=target,
        confidence=0.95,
    )


class Classifier:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def classify(self, db, **kwargs):
        self.calls.append(kwargs)
        return self.value


def text(version, content="今天和睿狐科技电话沟通了部署", key="request-001"):
    return ConversationTextRequest(text=content, client_request_id=key, expected_version=version)


def task(db, **changes):
    data = {
        "team_id": 1,
        "user_id": 2,
        "goal": "旧的客户沟通",
        "status": "ACTIVE",
        "draft_json": TaskDraft().model_dump(mode="json"),
        "authority_json": {},
        "committed_json": [],
    }
    data.update(changes)
    result = AssistantTask(**data)
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def test_open_is_shared_by_owner_but_isolated_by_team_and_user(db):
    service = ConversationService(classifier=Classifier(decision()))
    one = service.open(db, team_id=1, user_id=2)
    assert service.open(db, team_id=1, user_id=2).public_id == one.public_id
    assert service.open(db, team_id=2, user_id=2).public_id != one.public_id
    assert service.open(db, team_id=1, user_id=3).public_id != one.public_id


async def test_new_turn_is_durable_and_retry_does_not_create_twice(db):
    classifier = Classifier(decision())
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    req = text(initial.version)
    first = await service.submit_text(db, team_id=1, user_id=2, request=req)
    second = await service.submit_text(db, team_id=1, user_id=2, request=req)
    assert first.submission.turn_id == second.submission.turn_id
    assert db.query(AssistantTask).count() == db.query(AssistantTurn).count() == 1
    assert len(classifier.calls) == 1
    assert service.read(db, team_id=1, user_id=2).messages[0].text == req.text


async def test_completed_task_does_not_swallow_next_communication(db):
    old = task(db, status="COMPLETED", committed_json=[{"kind": "customer_activity", "public_id": "act_old"}])
    service = ConversationService(classifier=Classifier(decision()))
    initial = service.open(db, team_id=1, user_id=2)
    result = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))
    assert result.submission.task_public_id != old.public_id
    db.refresh(old)
    assert old.status == "COMPLETED" and old.committed_json[0]["public_id"] == "act_old"


async def test_ambiguity_asks_once_without_writing_and_choice_consumes_original(db):
    old = task(db)
    classifier = Classifier(decision("AMBIGUOUS", old.public_id))
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    ambiguous = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))
    assert ambiguous.submission is None
    assert ambiguous.conversation.pending_choice is not None
    assert db.query(AssistantTurn).count() == 0
    choice = ConversationChoiceRequest(
        entry_id=ambiguous.conversation.pending_choice.entry_id,
        choice="NEW",
        expected_version=ambiguous.conversation.version,
        client_request_id="choice-001",
    )
    new = await service.choose(db, team_id=1, user_id=2, request=choice)
    replay = await service.choose(db, team_id=1, user_id=2, request=choice)
    assert new.submission.turn_id == replay.submission.turn_id
    assert len(classifier.calls) == 1
    assert db.query(AssistantTurn).count() == 1
    assert new.submission.task_public_id != old.public_id
    assert old.status == "ACTIVE"


@pytest.mark.parametrize(
    "speech,obj,operation",
    [
        ("ASK_FACT", "CUSTOMER_ACTIVITY", "READ"),
        ("REQUEST_ACTION", "PAYMENT_RECORD", "CREATE"),
        ("REQUEST_ACTION", "CONTRACT", "TRANSITION"),
    ],
)
async def test_query_and_unsupported_writes_never_create_activity_task(db, speech, obj, operation):
    service = ConversationService(classifier=Classifier(decision(speech=speech, obj=obj, operation=operation)))
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))
    assert response.submission is None
    assert db.query(AssistantTask).count() == db.query(AssistantTurn).count() == 0


async def test_root_cannot_route_to_another_team_task(db):
    foreign = task(db, team_id=9)
    service = ConversationService(classifier=Classifier(decision("CONTINUE", foreign.public_id)))
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))
    assert response.submission is None
    assert db.query(AssistantTurn).count() == 0
    assert all(t["public_id"] != foreign.public_id for t in service.classifier.calls[0]["tasks"])


async def test_choice_recovers_crash_after_claim_without_reclassifying(db, monkeypatch):
    from datetime import timedelta

    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    old = task(db)
    classifier = Classifier(decision("AMBIGUOUS", old.public_id))
    service = ConversationService(classifier=classifier)
    state = service.open(db, team_id=1, user_id=2)
    boundary = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    req = ConversationChoiceRequest(
        entry_id=boundary.conversation.pending_choice.entry_id,
        choice="NEW",
        expected_version=boundary.conversation.version,
        client_request_id="choice-crash",
    )
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    crud.claim(
        db,
        conv,
        key=req.client_request_id,
        payload={"operation": "choice", "entry_id": req.entry_id, "choice": "NEW"},
        text="另记一件",
        expected_version=req.expected_version,
        choice_id=req.entry_id,
    )
    conv.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()
    recovered = await service.choose(db, team_id=1, user_id=2, request=req)
    assert recovered.submission is not None
    assert db.query(AssistantTurn).count() == 1
    assert len(classifier.calls) == 1
    assert crud.owned_conversation(db, team_id=1, user_id=2).busy_entry_id is None


async def test_cancel_pending_boundary_preserves_previous_task_and_history(db):
    old = task(db)
    service = ConversationService(classifier=Classifier(decision("AMBIGUOUS", old.public_id)))
    initial = service.open(db, team_id=1, user_id=2)
    pending = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version))
    req = ConversationChoiceRequest(
        entry_id=pending.conversation.pending_choice.entry_id,
        choice="CANCEL",
        expected_version=pending.conversation.version,
        client_request_id="choice-cancel",
    )
    result = await service.choose(db, team_id=1, user_id=2, request=req)
    replay = await service.choose(db, team_id=1, user_id=2, request=req)
    assert result.conversation.pending_choice is None
    assert replay.conversation.messages == result.conversation.messages
    assert result.submission is None
    db.refresh(old)
    assert old.status == "ACTIVE"
    assert db.query(AssistantTurn).count() == 0
    assert any(m.text == text(0).text for m in result.conversation.messages)


async def test_resume_completed_item_without_new_facts_does_not_create_empty_task(db):
    from app.crud import assistant_conversation as crud

    old = task(db, status="COMPLETED", committed_json=[{"kind": "customer_activity", "public_id": "act_old"}])
    value = decision("CONTINUE", old.public_id).model_copy(update={"resume_only": True})
    service = ConversationService(classifier=Classifier(value))
    initial = service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    conv.focused_task_public_id = old.public_id
    db.commit()
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, "回到刚才那条", "resume-old")
    )
    assert response.submission is None
    assert db.query(AssistantTask).count() == 1
    assert response.conversation.focused_task.public_id == old.public_id


async def test_supplement_after_commit_inherits_only_authorized_customer_and_keeps_old_receipt(db, monkeypatch):
    from types import SimpleNamespace

    from app.crud import assistant_conversation as crud
    from app.services.assistant import customer_resolution

    old = task(
        db,
        status="COMPLETED",
        version=8,
        draft_json=TaskDraft(customer={"status": "ACCEPTED", "value": "睿狐科技"}).model_dump(mode="json"),
        authority_json={"customer_public_id": "cus_one"},
        committed_json=[{"kind": "customer_activity", "public_id": "act_old"}],
    )
    monkeypatch.setattr(
        customer_resolution,
        "resolve_customer_candidates_for_assistant",
        lambda *a, **kw: SimpleNamespace(customer=SimpleNamespace(public_id="cus_one", account_name="睿狐科技")),
    )
    service = ConversationService(classifier=Classifier(decision("CONTINUE", old.public_id, "PROVIDE_SUPPLEMENT")))
    initial = service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    conv.focused_task_public_id = old.public_id
    db.commit()
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, "补充：POC下周部署", "supplement-01")
    )
    assert response.submission.task_public_id != old.public_id
    new = crud.owned_task(db, conv, response.submission.task_public_id)
    assert new.authority_json["customer_public_id"] == "cus_one"
    assert new.draft_json["customer"]["value"] == "睿狐科技"
    assert new.committed_json == []
    db.refresh(old)
    assert old.version == 8 and old.committed_json == [{"kind": "customer_activity", "public_id": "act_old"}]


async def test_field_reply_uses_current_signed_wait_but_new_event_keeps_old_draft(db):
    old = task(
        db,
        waiting_type="FIELD",
        waiting_field="customer",
        waiting_json={"action_id": "signed-customer", "payload": {"question_id": "q_customer", "prompt": "客户名称？"}},
        version=3,
    )
    classifier = Classifier(
        decision("CONTINUE", old.public_id, "PROVIDE_SUPPLEMENT").model_copy(update={"field_answer": True})
    )
    service = ConversationService(classifier=classifier)
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(state.version, "睿狐科技", "field-reply")
    )
    assert response.submission.input.kind == "submit_field"
    assert response.submission.input.action_id == "signed-customer"
    assert response.submission.input.expected_version == 3
    classifier.value = decision()
    next_one = await service.submit_text(
        db, team_id=1, user_id=2, request=text(response.conversation.version, "今天与另一客户讨论采购", "another-event")
    )
    assert next_one.submission.task_public_id != old.public_id
    db.refresh(old)
    assert old.status == "ACTIVE" and old.waiting_field == "customer"


async def test_stale_window_and_changed_retry_are_rejected_without_duplicate_turn(db):
    from app.crud.assistant_conversation import ConversationConflict

    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    with pytest.raises(ConversationConflict):
        await service.submit_text(db, team_id=1, user_id=2, request=text(state.version, "另一件", "stale-window"))
    with pytest.raises(ConversationConflict):
        await service.submit_text(db, team_id=1, user_id=2, request=text(state.version, "换掉内容"))
    assert db.query(AssistantTurn).count() == 1


async def test_model_error_fails_closed_and_releases_conversation(db):
    from app.services.assistant.failure_contract import AssistantFailureCode
    from app.services.assistant.model_transport import AssistantLLMError

    class Broken:
        async def classify(self, *a, **kw):
            raise AssistantLLMError("model down", code=AssistantFailureCode.UPSTREAM_TIMEOUT)

    service = ConversationService(classifier=Broken())
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    assert response.submission is None
    assert db.query(AssistantTask).count() == 0
    assert db.query(AssistantTurn).count() == 0
    assert response.conversation.pending_choice is None
    assert response.conversation.has_pending_request is False
    message = response.conversation.messages[-1]
    assert message.text == "模型服务响应超时，本次没有写入客户活动。"
    assert message.ui is not None
    error = message.ui.blocks[0]
    assert error.type == "error"
    assert error.code == "UPSTREAM_TIMEOUT"
    assert error.title == "模型服务响应超时"
    assert error.retryable is True
    assert error.trace_id is not None
    assert message.ui.suggested_actions[0].action_id == f"retry:{error.trace_id}"
    entry = db.query(AssistantConversationEntry).one()
    assert entry.public_id == error.trace_id
    assert entry.error_code == "UPSTREAM_TIMEOUT"
    assert bool(entry.error_retryable) is True
    assert entry.state == "READY"
    assert entry.decision_json == {}
    refreshed = service.read(db, team_id=1, user_id=2)
    again = refreshed.messages[-1]
    assert again.ui is not None and again.ui.blocks[0].trace_id == entry.public_id
    assert "model down" not in again.text


def test_history_paginates_more_than_fifty_entries_without_cross_owner_data(db):
    from app.crud import assistant_conversation as crud

    service = ConversationService(classifier=Classifier(decision()))
    service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    for i in range(65):
        db.add(
            AssistantConversationEntry(
                conversation_id=conv.id,
                team_id=1,
                user_id=2,
                client_request_id=f"history-{i}",
                input_fingerprint="x",
                user_text=f"记录{i}",
                state="READY",
            )
        )
    db.add(
        AssistantConversationEntry(
            conversation_id=conv.id,
            team_id=9,
            user_id=2,
            client_request_id="foreign-owner",
            input_fingerprint="x",
            user_text="不能泄露",
            state="READY",
        )
    )
    db.commit()
    all_messages = []
    cursor = None
    while True:
        page = service.read(db, team_id=1, user_id=2, before=cursor)
        all_messages = page.messages + all_messages
        cursor = page.older_cursor
        if cursor is None:
            break
    assert [m.text for m in all_messages] == [f"记录{i}" for i in range(65)]


async def test_reopen_recovers_persisted_text_after_process_crash(db):
    from datetime import timedelta

    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    classifier = Classifier(decision())
    service = ConversationService(classifier=classifier)
    state = service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    crud.claim(
        db,
        conv,
        key="crashed-text",
        payload={"operation": "text", "text": "原句"},
        text="原句",
        expected_version=state.version,
    )
    assert service.open(db, team_id=1, user_id=2).has_pending_request
    conv.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()
    response = await service.resume(db, team_id=1, user_id=2)
    assert response.submission is not None
    assert not response.conversation.has_pending_request
    assert response.submission.input.text == "原句"
    assert db.query(AssistantTask).count() == 1
    assert not service.open(db, team_id=1, user_id=3).has_pending_request


async def test_command_recovers_after_acceptance_before_link_without_replaying_write(db, monkeypatch):
    from datetime import timedelta

    from app.crud import assistant_conversation as crud
    from app.schemas.assistant import SubmitInputRequest
    from app.schemas.assistant_conversation import ConversationCommandRequest
    from app.utils.time import business_now

    old = task(db)
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    original = module.accept_submit

    def accept_then_crash(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated process exit after commit")

    monkeypatch.setattr(module, "accept_submit", accept_then_crash)
    req = ConversationCommandRequest(
        task_public_id=old.public_id,
        expected_version=state.version,
        input=SubmitInputRequest(kind="cancel", client_request_id="cancel-crash"),
    )
    with pytest.raises(RuntimeError):
        await service.command(db, team_id=1, user_id=2, request=req)
    monkeypatch.setattr(module, "accept_submit", original)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    conv.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()
    response = await service.resume(db, team_id=1, user_id=2)
    assert response.submission.turn_id == db.query(AssistantTurn).one().public_id
    assert db.query(AssistantTurn).count() == 1
    assert not response.conversation.has_pending_request


def test_kind_change_is_versioned_durable_and_idempotent(db):
    from app.schemas.assistant_conversation import ConversationKindRequest

    old = task(db, version=3)
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    req = ConversationKindRequest(
        task_public_id=old.public_id,
        kind="ONLINE_MEETING",
        task_version=3,
        expected_version=state.version,
        client_request_id="kind-001",
    )
    result = service.change_kind(db, team_id=1, user_id=2, request=req)
    replay = service.change_kind(db, team_id=1, user_id=2, request=req)
    assert result.conversation.messages == replay.conversation.messages
    assert result.conversation.focused_task.activity_kind == "ONLINE_MEETING"
    assert any(m.text == "改为线上会议" for m in result.conversation.messages)
    assert "已切换为线上会议" in service.open(db, team_id=1, user_id=2).messages[-1].text
    assert db.query(AssistantAction).filter_by(action="change_kind").count() == 1


def test_stale_kind_change_releases_lease_without_changing_draft(db):
    from app.schemas.assistant_conversation import ConversationKindRequest

    old = task(db, version=3)
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    req = ConversationKindRequest(
        task_public_id=old.public_id,
        kind="ONLINE_MEETING",
        task_version=2,
        expected_version=state.version,
        client_request_id="kind-stale",
    )
    response = service.change_kind(db, team_id=1, user_id=2, request=req)
    assert not response.conversation.has_pending_request
    db.refresh(old)
    assert old.activity_kind is None and old.version == 3


def test_legacy_cards_require_real_frozen_payload_and_receipts_require_evidence(db):
    old = task(db)
    frozen = {
        "type": "CONFIRMATION",
        "field": "activity_write",
        "question_id": "q_frozen",
        "prompt": "确认旧稿？",
        "confirmation_payload": {
            "kind": "activity_write",
            "preview": {
                "customer_name": "旧客户",
                "activity_kind": "ONLINE_MEETING",
                "title": "原会议标题",
                "summary": "原整理稿",
                "content_json": {},
                "source_content": "原文",
                "score": 85,
                "score_reason": "完整",
            },
        },
    }
    actions = [
        {
            "actor": "USER", "action": "select_activity_kind", "input_json": {"kind": "ONLINE_MEETING"},
            "result_json": {},
        },
        {
            "actor": "USER", "action": "submit_field", "input_json": {"field": "customer", "text": "旧客户"},
            "result_json": {},
        },
        {
            "actor": "SYSTEM", "action": "freeze_activity", "event_type": "meeting_card",
            "result_json": {"confirmation": frozen},
        },
        {
            "actor": "SYSTEM", "action": "show_write_receipt", "event_type": "receipt",
            "result_json": {"label": "已记录这条客户活动。", "activity_public_id": "act_old"},
        },
        {"actor": "SYSTEM", "action": "missing_card", "event_type": "meeting_card", "result_json": {}},
    ]
    for data in actions:
        db.add(AssistantAction(team_id=1, task_id=old.id, **data))
    db.commit()
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    assert any(m.text == "线上会议" for m in state.messages)
    assert any(m.text == "客户名称：旧客户" for m in state.messages)
    cards = [m.task for m in state.messages if m.task is not None and m.task.waiting is not None]
    assert len(cards) == 1
    assert cards[0].waiting.confirmation_payload.preview.title == "原会议标题"
    assert any(m.outcome == "activity_written" for m in state.messages)
    assert any("暂时无法显示" in m.text for m in state.messages)


async def test_command_labels_never_expose_customer_or_kind_ids(db):
    from app.schemas.assistant import SubmitInputRequest
    from app.schemas.assistant_conversation import ConversationCommandRequest

    old = task(
        db,
        waiting_type="OBJECT_SELECTION",
        waiting_field="customer",
        version=2,
        waiting_json={
            "action_id": "choose-customer",
            "payload": {
                "question_id": "q_choose",
                "prompt": "选择客户",
                "candidates": [{"id": "cus_opaque", "account_name": "可读客户"}],
            },
        },
    )
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    request = ConversationCommandRequest(
        task_public_id=old.public_id,
        expected_version=state.version,
        input=SubmitInputRequest(
            kind="submit_field",
            choice="cus_opaque",
            action_id="choose-customer",
            expected_version=2,
            client_request_id="choose-customer-key",
        ),
    )
    response = await service.command(db, team_id=1, user_id=2, request=request)
    assert any(m.text == "可读客户" for m in response.conversation.messages)
    assert not any(m.text == "cus_opaque" for m in response.conversation.messages)


@pytest.mark.parametrize(
    "wait_type,field_name",
    [("FIELD", "next_action"), ("ACTIVITY_KIND", "activity_kind"), ("OBJECT_SELECTION", "customer")],
)
async def test_general_supplement_is_not_forced_into_a_waiting_field(db, wait_type, field_name):
    old = task(
        db,
        version=3,
        waiting_type=wait_type,
        waiting_field=field_name,
        waiting_json={"action_id": "old-question", "payload": {"question_id": "q_old", "prompt": "原问题"}},
    )
    service = ConversationService(classifier=Classifier(decision("CONTINUE", old.public_id, "PROVIDE_SUPPLEMENT")))
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(state.version, "补充一个背景：客户完成安全测评", "supplement-facts")
    )
    assert response.submission.task_public_id == old.public_id
    assert response.submission.input.kind == "text"
    assert response.submission.input.action_id is None
    db.refresh(old)
    assert old.waiting_type is None
    assert old.draft_json["next_action"]["status"] == "MISSING"


def test_bootstrapped_live_frozen_card_is_not_rendered_twice(db):
    preview = {
        "customer_name": "客户",
        "activity_kind": "ONLINE_MEETING",
        "title": "冻结标题",
        "summary": "冻结整理稿",
        "content_json": {},
        "source_content": "原文",
        "score": 85,
        "score_reason": "完整",
    }
    frozen = {
        "type": "CONFIRMATION",
        "field": "activity_write",
        "question_id": "q_live",
        "prompt": "确认？",
        "confirmation_payload": {"kind": "activity_write", "preview": preview},
    }
    old = task(
        db,
        version=3,
        waiting_type="CONFIRMATION",
        waiting_field="activity_write",
        waiting_json={"action_id": "live-card", "payload": frozen},
    )
    db.add(
        AssistantAction(
            team_id=1,
            task_id=old.id,
            actor="SYSTEM",
            action="freeze_activity",
            event_type="meeting_card",
            result_json={"confirmation": frozen},
        )
    )
    db.commit()
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    cards = [m for m in state.messages if m.task and m.task.waiting]
    assert len(cards) == 1
    assert cards[0].task.waiting.action_id == "live-card"


def test_proposal_confirmation_does_not_forge_another_activity_written_receipt(db):
    from app.crud import assistant_conversation as crud
    from app.services.assistant.presentation import task_view

    old = task(db, committed_json=[{"kind": "customer_activity", "public_id": "act_already"}])
    service = ConversationService(classifier=Classifier(decision()))
    service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    for i, field_name in enumerate(["activity_write", "proposal:customer_fact"]):
        request = AssistantRequest(
            team_id=1, user_id=2, client_request_id=f"event-req-{i}", input_fingerprint="x", task_id=old.id
        )
        db.add(request)
        db.flush()
        turn = AssistantTurn(
            team_id=1,
            user_id=2,
            task_id=old.id,
            request_id=request.id,
            input_json={"kind": "confirm"},
            status="SUCCEEDED",
        )
        db.add(turn)
        db.flush()
        entry = AssistantConversationEntry(
            conversation_id=conv.id,
            team_id=1,
            user_id=2,
            client_request_id=f"event-entry-{i}",
            input_fingerprint="x",
            user_text="确认",
            state="READY",
            command_json={"waiting_field": field_name},
            task_public_id=old.public_id,
            turn_public_id=turn.public_id,
        )
        db.add(entry)
        db.add(
            AssistantTurnEvent(
                turn_id=turn.id,
                seq=1,
                event="waiting",
                data_json={"task": task_view(old, db).model_dump(mode="json"), "message": f"结果{i}"},
            )
        )
    db.commit()
    messages = service.read(db, team_id=1, user_id=2).messages
    assert next(m for m in messages if m.text == "结果0").outcome == "activity_written"
    assert next(m for m in messages if m.text == "结果1").outcome is None


async def test_reclaimed_lease_fences_the_original_root_worker_before_task_dispatch(db):
    from datetime import timedelta

    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    old = task(db)

    class InterruptedRoot:
        async def classify(self, session, **kwargs):
            conv = crud.owned_conversation(session, team_id=1, user_id=2)
            conv.lease_expires_at = business_now() - timedelta(seconds=1)
            session.commit()
            restarted = ConversationService(classifier=Classifier(decision()))
            await restarted.resume(session, team_id=1, user_id=2)
            return decision("CONTINUE", old.public_id, "PROVIDE_SUPPLEMENT")

    service = ConversationService(classifier=InterruptedRoot())
    state = service.open(db, team_id=1, user_id=2)
    with pytest.raises(crud.ConversationConflict):
        await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    assert db.query(AssistantTask).count() == 2
    assert db.query(AssistantTurn).count() == 1
    assert not service.read(db, team_id=1, user_id=2).has_pending_request


class ReferencedDraftClassifier:
    """Root first extracts a customer, then binds only from server-supplied drafts."""

    def __init__(self, customer):
        self.customer = customer
        self.calls = []

    async def classify(self, db, **kwargs):
        self.calls.append(kwargs)
        match = next((item for item in kwargs["tasks"] if item["customer"] == self.customer), None)
        value = decision("CONTINUE", match["public_id"] if match else None, speech="PROVIDE_SUPPLEMENT")
        value.semantic_plan.customer_reference = self.customer
        value.resume_only = True
        return value


def older_customer_draft(db, customer="睿狐科技"):
    from app.services.assistant.contracts import DraftField

    old = task(
        db,
        goal=f"{customer}最早的沟通",
        draft_json=TaskDraft(customer=DraftField(status="ACCEPTED", value=customer)).model_dump(mode="json"),
    )
    for i in range(21):
        task(db, goal=f"其他客户{i}的沟通")
    return old


@pytest.mark.parametrize("customer", ["睿狐科技", "客户%_科技"])
async def test_explicit_customer_reference_resumes_older_than_recent_twenty(db, customer):
    old = older_customer_draft(db, customer)
    classifier = ReferencedDraftClassifier(customer)
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    result = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, f"接回{customer}那次沟通")
    )
    assert result.conversation.focused_task.public_id == old.public_id
    assert result.submission is None
    assert len(classifier.calls) == 2
    assert old.public_id not in {item["public_id"] for item in classifier.calls[0]["tasks"]}
    assert {item["public_id"] for item in classifier.calls[1]["tasks"]} == {old.public_id}
    assert db.query(AssistantTask).count() == 22
    assert db.query(AssistantTurn).count() == 0


@pytest.mark.parametrize("foreign_owner", [{"team_id": 2}, {"user_id": 3}])
async def test_missing_customer_reference_does_not_expose_foreign_drafts(db, foreign_owner):
    from app.services.assistant.contracts import DraftField

    foreign = task(
        db, **foreign_owner,
        draft_json=TaskDraft(customer=DraftField(status="ACCEPTED", value="外部客户")).model_dump(mode="json"),
    )
    own = task(db)
    classifier = ReferencedDraftClassifier("外部客户")
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    result = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, "接回外部客户那次沟通"))
    assert result.submission is None
    assert result.conversation.focused_task.public_id == own.public_id
    assert len(classifier.calls) == 1
    assert foreign.public_id not in {item["public_id"] for item in classifier.calls[0]["tasks"]}
    assert db.query(AssistantTurn).count() == 0


async def test_reference_binding_still_rejects_root_invented_or_foreign_id(db):
    old = older_customer_draft(db)
    foreign = task(db, team_id=2)
    classifier = ReferencedDraftClassifier("睿狐科技")
    original_classify = classifier.classify

    async def foreign_after_retrieval(session, **kwargs):
        value = await original_classify(session, **kwargs)
        if len(classifier.calls) == 2:
            value.target_task_public_id = foreign.public_id
        return value

    classifier.classify = foreign_after_retrieval
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    result = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, "接回睿狐科技那次沟通"))
    assert len(classifier.calls) == 2
    assert result.submission is None
    assert result.conversation.focused_task.public_id not in {old.public_id, foreign.public_id}
    assert db.query(AssistantTurn).count() == 0


async def test_retrieved_draft_binding_survives_process_loss_without_reclassifying(db, monkeypatch):
    from datetime import timedelta

    from app.utils.time import business_now

    old = older_customer_draft(db)
    classifier = ReferencedDraftClassifier("睿狐科技")
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)

    def process_loss(*args, **kwargs):
        raise RuntimeError("process lost after durable routing")

    monkeypatch.setattr(service, "_route", process_loss)
    with pytest.raises(RuntimeError, match="process lost"):
        await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, "接回睿狐科技那次沟通"))
    owned = db.query(AssistantConversation).filter_by(team_id=1, user_id=2).one()
    owned.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()
    restarted_classifier = Classifier(decision())
    restarted = ConversationService(classifier=restarted_classifier)
    result = await restarted.resume(db, team_id=1, user_id=2)
    assert result.conversation.focused_task.public_id == old.public_id
    assert result.submission is None
    assert restarted_classifier.calls == []
    assert len(classifier.calls) == 2
    assert db.query(AssistantTurn).count() == 0


async def test_reference_lookup_escapes_literal_sql_wildcards(db):
    older_customer_draft(db, "客户普通科技")
    classifier = ReferencedDraftClassifier("客户%_科技")
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    result = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, "接回客户%_科技那次沟通")
    )
    assert len(classifier.calls) == 1
    assert result.submission is None
    assert result.conversation.focused_task.public_id == initial.focused_task.public_id
    assert db.query(AssistantTurn).count() == 0


async def test_overfull_customer_reference_does_not_guess_from_truncated_drafts(db):
    from app.services.assistant.contracts import DraftField

    for i in range(21):
        task(
            db, goal=f"同名客户的沟通{i}",
            draft_json=TaskDraft(customer=DraftField(status="ACCEPTED", value="睿狐科技")).model_dump(mode="json"),
        )
    for i in range(21):
        task(db, goal=f"其他沟通{i}")
    classifier = ReferencedDraftClassifier("睿狐科技")
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    result = await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, "接回睿狐科技那次沟通"))
    assert len(classifier.calls) == 1
    assert result.submission is None
    assert result.conversation.focused_task.public_id == initial.focused_task.public_id
    assert db.query(AssistantTurn).count() == 0


def test_first_open_does_not_import_another_windows_accepted_input_twice(db, monkeypatch):
    import asyncio

    from app.crud import assistant_conversation as crud

    old = task(db, goal="原有旧稿")
    service = ConversationService(classifier=Classifier(decision()))
    bootstrap = crud.bootstrap_active
    content = "另一个窗口已经接受的新沟通"
    accepted_id = None

    def submit_from_second_window(session, conversation):
        nonlocal accepted_id
        with sessionmaker(bind=db.get_bind())() as second:
            opened = service.read(second, team_id=1, user_id=2)
            accepted = asyncio.run(
                service.submit_text(second, team_id=1, user_id=2, request=text(opened.version, content))
            )
            accepted_id = accepted.submission.task_public_id
        bootstrap(session, conversation)

    monkeypatch.setattr(crud, "bootstrap_active", submit_from_second_window)
    result = service.open(db, team_id=1, user_id=2)
    assert [m.text for m in result.messages if m.role == "user"].count(content) == 1
    assert result.focused_task.public_id == accepted_id
    assert db.query(AssistantConversationEntry).count() == 1
    assert db.query(AssistantTurn).count() == 1
    db.refresh(old)
    assert old.status == "ACTIVE"


def test_root_understanding_waits_150_seconds(monkeypatch):
    seen: dict[str, float] = {}

    class Transport:
        async def ainvoke_structured(self, **kwargs):
            seen["timeout_seconds"] = kwargs["timeout_seconds"]
            return decision(boundary="AMBIGUOUS", target="ast_written")

    monkeypatch.setattr(
        router_module,
        "team_model_credentials",
        lambda db, team_id: ("https://model.example", "not-a-real-key", "test-model"),
    )
    classifier = ConversationRootClassifier()
    classifier.transport = Transport()
    result = asyncio.run(
        classifier.classify(
            None,
            team_id=1,
            text="下午和对方技术经理通了电话，说POC下周可以部署。",
            tasks=[],
            focused_task_public_id=None,
            recent_messages=[],
        )
    )
    assert seen["timeout_seconds"] == ROOT_UNDERSTANDING_TIMEOUT_SECONDS == 150
    assert result.boundary == "AMBIGUOUS"


def test_single_broken_history_projection_keeps_other_entries_readable(db, monkeypatch):
    from app.crud import assistant_conversation as crud

    service = ConversationService(classifier=Classifier(decision()))
    service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    db.add_all(
        [
            AssistantConversationEntry(
                conversation_id=conv.id,
                team_id=1,
                user_id=2,
                client_request_id="history-good",
                input_fingerprint="x",
                user_text="正常历史",
                state="READY",
            ),
            AssistantConversationEntry(
                conversation_id=conv.id,
                team_id=1,
                user_id=2,
                client_request_id="history-broken",
                input_fingerprint="x",
                user_text="无法投影的原句",
                state="READY",
            ),
        ]
    )
    db.commit()
    original = ConversationService._messages

    def project(self, session, conversation, row):
        if row.user_text == "无法投影的原句":
            raise ValueError("malformed historical projection")
        return original(self, session, conversation, row)

    monkeypatch.setattr(ConversationService, "_messages", project)
    page = service.read(db, team_id=1, user_id=2)
    assert [message.text for message in page.messages] == [
        "正常历史",
        "无法投影的原句",
        "这条历史结果暂时无法显示，原记录仍保留。",
    ]
    assert page.messages[1].role == "user"
    assert page.messages[2].outcome == "failure"


def test_schema_mismatch_is_not_downgraded_to_a_broken_history_entry(db, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.crud import assistant_conversation as crud

    service = ConversationService(classifier=Classifier(decision()))
    service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    db.add(
        AssistantConversationEntry(
            conversation_id=conv.id,
            team_id=1,
            user_id=2,
            client_request_id="history-schema-error",
            input_fingerprint="x",
            user_text="结构错误不能伪装成坏历史",
            state="READY",
        )
    )
    db.commit()
    schema_error = OperationalError(
        "SELECT crm_assistant_conversations.version",
        {},
        RuntimeError(1054, "Unknown column 'crm_assistant_conversations.version'"),
    )
    monkeypatch.setattr(ConversationService, "_messages", lambda *args: (_ for _ in ()).throw(schema_error))
    with pytest.raises(OperationalError):
        service.read(db, team_id=1, user_id=2)



MONTH_TEXT = "叶老师反馈本月底会完成；等 30 号再联系叶老师"


def month_ambiguity(db):
    from datetime import datetime

    from app.services.assistant.contracts import DraftField
    from app.services.assistant.temporal_evidence import attach_model_evidence, find_time_spans, temporal_waiting

    spans = find_time_spans(MONTH_TEXT)
    mentions = []
    actions = []
    for index, span in enumerate(spans):
        mentions.append(
            {
                "raw_text": span.raw_text,
                "quote_start": span.start,
                "quote_end": span.end,
                "kind": span.kind,
                "role": "OTHER",
                "owner": "",
                "action_ref": f"a{index}",
                "confidence": 0.9,
            }
        )
        actions.append(
            {
                "action_ref": f"a{index}",
                "owner_role": "SALES",
                "owner_text": "我",
                "action_text": "完成准备" if span.kind == "MONTH_SEGMENT" else "联系叶老师",
                "action_status": "PLANNED",
                "evidence_quote": span.raw_text,
                "quote_start": span.start,
                "quote_end": span.end,
            }
        )
    draft = TaskDraft(
        content=DraftField(status="CANDIDATE", value=MONTH_TEXT),
        content_json={"content": MONTH_TEXT},
        source_segments=[MONTH_TEXT],
        quality_score=DraftField(status="CANDIDATE", value="80"),
    )
    attach_model_evidence(
        draft,
        segment_id="seg_month",
        segment_text=MONTH_TEXT,
        anchor=datetime(2026, 10, 27, 15, 0),
        mentions=mentions,
        actions=actions,
    )
    spec = temporal_waiting(draft)
    assert spec is not None
    row = task(
        db,
        goal=MONTH_TEXT,
        version=3,
        activity_kind="FOLLOW_UP",
        draft_json=draft.model_dump(mode="json"),
        waiting_type="FIELD",
        waiting_field="temporal_choice",
        waiting_json={
            "action_id": "awa_month",
            "payload": {
                "question_id": "q_month",
                "prompt": spec["prompt"],
                "candidates": spec["candidates"],
            },
        },
    )
    return row, spec


def temporal_command(version, public_id, key, *, choice=None, text_value=None, action_id="awa_month", task_version=3):
    from app.schemas.assistant import SubmitInputRequest
    from app.schemas.assistant_conversation import ConversationCommandRequest

    return ConversationCommandRequest(
        task_public_id=public_id,
        expected_version=version,
        input=SubmitInputRequest(
            kind="submit_field",
            choice=choice,
            text=text_value,
            action_id=action_id,
            expected_version=task_version,
            client_request_id=key,
        ),
    )


async def execute_accepted_turn(db, monkeypatch, turn_public_id):
    from sqlalchemy.orm import sessionmaker

    from app.services.assistant.coordinator import AssistantCoordinator
    from app.services.assistant.turns import execute_turn

    class NoChooser:
        async def choose(self, current):
            raise AssertionError(f"time choice must not replan task {current.public_id}")

    monkeypatch.setattr("app.api.assistant._coordinator", AssistantCoordinator(NoChooser()))
    turn = db.query(AssistantTurn).filter_by(public_id=turn_public_id).one()
    await execute_turn(turn.id, factory=sessionmaker(bind=db.get_bind()))
    db.expire_all()


def assert_october_follow_up(row):
    from datetime import datetime

    from app.services.assistant.task_state import load_draft, load_waiting
    from app.services.assistant.temporal_evidence import resolved_sales_follow_up, temporal_waiting

    draft = load_draft(row)
    assert temporal_waiting(draft) is None
    resolved, granularity = resolved_sales_follow_up(draft)
    assert (resolved, granularity) == (datetime(2026, 10, 30), "DATE")
    waiting = load_waiting(row)
    assert waiting is not None and waiting.field == "customer"
    assert waiting.prompt == "请提供客户准确名称。"


@pytest.mark.parametrize("answer", ["本月 30 号", "本月30号"])
async def test_temporal_month_text_maps_through_the_message_entry(db, monkeypatch, answer):
    row, _spec = month_ambiguity(db)
    service = ConversationService(
        classifier=Classifier(
            decision("CONTINUE", row.public_id, "PROVIDE_SUPPLEMENT").model_copy(update={"field_answer": True})
        )
    )
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(state.version, answer, f"month-text-{answer}")
    )
    assert response.submission is not None
    assert response.submission.input.kind == "submit_field"
    assert response.submission.input.choice is None
    assert response.submission.input.text == answer
    assert any(message.text == answer for message in response.conversation.messages)
    await execute_accepted_turn(db, monkeypatch, response.submission.turn_id)
    db.refresh(row)
    assert_october_follow_up(row)
    assert db.query(AssistantTurn).filter_by(public_id=response.submission.turn_id).one().status == "SUCCEEDED"


async def test_temporal_month_button_enters_a_durable_turn_and_keeps_the_label(db, monkeypatch):
    row, spec = month_ambiguity(db)
    choice_id = spec["candidates"][0]["id"]
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    request = temporal_command(state.version, row.public_id, "month-button", choice=choice_id)
    response = await service.command(db, team_id=1, user_id=2, request=request)
    replay = await service.command(db, team_id=1, user_id=2, request=request)
    assert response.submission is not None and replay.submission is not None
    assert response.submission.turn_id == replay.submission.turn_id
    assert response.submission.input.choice == choice_id
    assert db.query(AssistantTurn).count() == 1
    assert any(message.text == "本月30号" for message in response.conversation.messages)
    assert not any(message.text == choice_id for message in response.conversation.messages)
    await execute_accepted_turn(db, monkeypatch, response.submission.turn_id)
    db.refresh(row)
    assert_october_follow_up(row)
    assert row.waiting_field != "temporal_choice"


async def test_temporal_choice_failures_do_not_write_a_date(db, monkeypatch):
    from app.services.assistant.task_state import load_draft
    from app.services.assistant.temporal_evidence import resolved_sales_follow_up

    row, spec = month_ambiguity(db)
    choice_id = spec["candidates"][0]["id"]
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    rejected = [
        ("month-unknown", {"choice": "tm_missing:0"}),
        ("month-stale-action", {"choice": choice_id, "action_id": "awa_old"}),
        ("month-stale-version", {"choice": choice_id, "task_version": 2}),
        ("month-both", {"choice": choice_id, "text_value": "本月30号"}),
    ]
    for key, options in rejected:
        response = await service.command(
            db,
            team_id=1,
            user_id=2,
            request=temporal_command(state.version, row.public_id, key, **options),
        )
        assert response.submission is None
        assert any("这张卡片状态已变化" in message.text for message in response.conversation.messages)
        state = response.conversation
    assert db.query(AssistantTurn).count() == 0
    db.refresh(row)
    assert row.waiting_field == "temporal_choice" and row.version == 3
    resolved, granularity = resolved_sales_follow_up(load_draft(row))
    assert (resolved, granularity) == (None, "UNKNOWN")

    classifier = Classifier(
        decision("CONTINUE", row.public_id, "PROVIDE_SUPPLEMENT").model_copy(update={"field_answer": True})
    )
    service = ConversationService(classifier=classifier)
    opened = service.open(db, team_id=1, user_id=2)
    unmapped = await service.submit_text(
        db, team_id=1, user_id=2, request=text(opened.version, "2026-10-30", "month-unmapped")
    )
    assert unmapped.submission is not None
    await execute_accepted_turn(db, monkeypatch, unmapped.submission.turn_id)
    db.refresh(row)
    assert row.waiting_field == "temporal_choice" and row.version == 3
    draft = load_draft(row)
    resolved, granularity = resolved_sales_follow_up(draft)
    assert (resolved, granularity) == (None, "UNKNOWN")
    mentions = draft.content_json["temporal_evidence"]["mentions"]
    sales = next(item for item in mentions if item["raw_text"] == "30 号")
    assert sales["resolution_status"] == "AMBIGUOUS"
    assert sales["resolved_at"] is None


async def test_duplicate_temporal_labels_do_not_guess(db, monkeypatch):
    row = task(
        db,
        version=2,
        waiting_type="FIELD",
        waiting_field="temporal_choice",
        waiting_json={
            "action_id": "awa_dup",
            "payload": {
                "question_id": "q_dup",
                "prompt": "请选择时间",
                "candidates": [
                    {"id": "tm_one:0", "label": "本月30号"},
                    {"id": "tm_two:0", "label": "本月 30 号"},
                ],
            },
        },
    )
    service = ConversationService(
        classifier=Classifier(
            decision("CONTINUE", row.public_id, "PROVIDE_SUPPLEMENT").model_copy(update={"field_answer": True})
        )
    )
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version, "本月30号", "month-dup"))
    assert response.submission is not None
    await execute_accepted_turn(db, monkeypatch, response.submission.turn_id)
    db.refresh(row)
    assert row.waiting_field == "temporal_choice" and row.version == 2
    assert row.draft_json["next_follow_time"]["status"] == "MISSING"


async def test_other_waiting_inputs_keep_their_existing_constraints(db):
    content = task(
        db,
        version=2,
        waiting_type="FIELD",
        waiting_field="content",
        waiting_json={"action_id": "awa_content", "payload": {"question_id": "q_content", "prompt": "补充内容"}},
    )
    service = ConversationService(classifier=Classifier(decision()))
    state = service.open(db, team_id=1, user_id=2)
    rejected = await service.command(
        db,
        team_id=1,
        user_id=2,
        request=temporal_command(
            state.version,
            content.public_id,
            "content-choice",
            choice="本月30号",
            action_id="awa_content",
            task_version=2,
        ),
    )
    assert rejected.submission is None
    assert db.query(AssistantTurn).count() == 0

    kind = task(
        db,
        version=2,
        waiting_type="ACTIVITY_KIND",
        waiting_field="activity_kind",
        waiting_json={"action_id": "awa_kind", "payload": {"question_id": "q_kind", "prompt": "选择类型"}},
    )
    # The first open already focused the content task. Point the session at this card.
    from app.crud import assistant_conversation as crud

    conversation = crud.owned_conversation(db, team_id=1, user_id=2)
    conversation.focused_task_public_id = kind.public_id
    db.commit()
    state = service.open(db, team_id=1, user_id=2)
    rejected_kind = await service.command(
        db,
        team_id=1,
        user_id=2,
        request=temporal_command(
            state.version,
            kind.public_id,
            "kind-with-text",
            choice="FOLLOW_UP",
            text_value="普通跟进",
            action_id="awa_kind",
            task_version=2,
        ),
    )
    assert rejected_kind.submission is None

    action = task(
        db,
        version=2,
        waiting_type="FIELD",
        waiting_field="next_action",
        waiting_json={"action_id": "awa_action", "payload": {"question_id": "q_action", "prompt": "下一步"}},
    )
    conversation.focused_task_public_id = action.public_id
    db.commit()
    state = service.read(db, team_id=1, user_id=2)
    accepted = await service.command(
        db,
        team_id=1,
        user_id=2,
        request=temporal_command(
            state.version,
            action.public_id,
            "explicit-none",
            choice="EXPLICITLY_NONE",
            text_value="客户决定这次先不安排",
            action_id="awa_action",
            task_version=2,
        ),
    )
    assert accepted.submission is not None
    assert accepted.submission.input.choice == "EXPLICITLY_NONE"
    assert db.query(AssistantTurn).count() == 1


async def test_root_configuration_failure_has_no_retry_and_hides_provider_text(db, caplog):
    from app.services.assistant.failure_contract import AssistantFailureCode
    from app.services.assistant.model_transport import AssistantLLMError

    class Broken:
        async def classify(self, *a, **kw):
            raise AssistantLLMError(
                "AI 配置无效",
                code=AssistantFailureCode.CONFIGURATION_ERROR,
                cause=RuntimeError("https://secret.example sk-live"),
            )

    service = ConversationService(classifier=Broken())
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    message = response.conversation.messages[-1]
    assert message.text == "模型配置暂不可用，本次没有写入客户活动，请联系管理员。"
    assert message.ui is not None
    assert message.ui.blocks[0].retryable is False
    assert message.ui.suggested_actions == []
    assert "secret.example" not in message.text
    assert "sk-live" not in caplog.text
    assert db.query(AssistantTask).count() == 0


async def test_root_retry_reuses_the_same_entry_and_rejects_a_second_claim(db):
    from datetime import timedelta

    from app.crud.assistant_conversation import ConversationConflict
    from app.services.assistant.failure_contract import AssistantFailureCode
    from app.services.assistant.model_transport import AssistantLLMError
    from app.utils.time import business_now

    class Once:
        def __init__(self):
            self.calls = 0
            self.leases = []

        async def classify(self, db, **kwargs):
            from app.crud import assistant_conversation as crud

            self.calls += 1
            conversation = crud.owned_conversation(db, team_id=1, user_id=2)
            self.leases.append(conversation.lease_expires_at)
            if self.calls == 1:
                raise AssistantLLMError("down", code=AssistantFailureCode.UPSTREAM_UNAVAILABLE)
            return decision()

    classifier = Once()
    service = ConversationService(classifier=classifier)
    state = service.open(db, team_id=1, user_id=2)
    failed = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version, key="same-key"))
    entry = db.query(AssistantConversationEntry).one()
    original = (
        entry.public_id,
        entry.client_request_id,
        entry.input_fingerprint,
        entry.user_text,
        dict(entry.command_json),
    )
    assert failed.conversation.messages[-1].ui.suggested_actions[0].label == "重试"
    retried = await service.retry_entry(
        db, team_id=1, user_id=2, entry_id=entry.public_id, expected_version=failed.conversation.version
    )
    db.refresh(entry)
    assert db.query(AssistantConversationEntry).count() == 1
    assert (entry.public_id, entry.client_request_id, entry.input_fingerprint, entry.user_text) == original[:4]
    assert entry.command_json["operation"] == "text"
    assert entry.command_json["text"] == original[4]["text"]
    assert entry.error_code is None
    assert retried.submission is not None
    assert classifier.calls == 2
    assert all(item - business_now() <= timedelta(seconds=180) for item in classifier.leases)
    assert all(item - business_now() >= timedelta(seconds=120) for item in classifier.leases)
    with pytest.raises(ConversationConflict):
        await service.retry_entry(
            db, team_id=1, user_id=2, entry_id=entry.public_id, expected_version=retried.conversation.version
        )


async def test_root_retry_failure_updates_the_original_entry(db):
    from app.services.assistant.failure_contract import AssistantFailureCode
    from app.services.assistant.model_transport import AssistantLLMError

    class Always:
        async def classify(self, *a, **kw):
            raise AssistantLLMError("bad json", code=AssistantFailureCode.MODEL_OUTPUT_INVALID)

    service = ConversationService(classifier=Always())
    state = service.open(db, team_id=1, user_id=2)
    failed = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    entry = db.query(AssistantConversationEntry).one()
    again = await service.retry_entry(
        db, team_id=1, user_id=2, entry_id=entry.public_id, expected_version=failed.conversation.version
    )
    db.refresh(entry)
    assert db.query(AssistantConversationEntry).count() == 1
    assert entry.error_code == "MODEL_OUTPUT_INVALID"
    assert entry.state == "READY"
    assert again.conversation.has_pending_request is False
    assert again.conversation.messages[-1].text == "模型返回结果格式异常，本次没有写入客户活动。"
    assert db.query(AssistantTask).count() == 0


async def test_lost_root_lease_is_not_stored_as_model_failure(db):
    from datetime import timedelta

    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    class Slow:
        async def classify(self, *a, **kw):
            return decision()

    service = ConversationService(classifier=Slow())
    state = service.open(db, team_id=1, user_id=2)
    conversation = crud.owned_conversation(db, team_id=1, user_id=2)

    real_renew = crud.renew_model_lease

    def expire(db, conversation, entry, *, lease_version, seconds):
        conversation.lease_expires_at = business_now() - timedelta(seconds=1)
        db.commit()
        return real_renew(db, conversation, entry, lease_version=lease_version, seconds=seconds)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(crud, "renew_model_lease", expire)
    try:
        with pytest.raises(crud.ConversationConflict):
            await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    finally:
        monkeypatch.undo()
    entry = db.query(AssistantConversationEntry).one()
    assert entry.error_code is None
    assert entry.state == "ROUTING"
    assert conversation.busy_entry_id == entry.public_id
