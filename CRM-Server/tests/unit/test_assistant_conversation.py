"""Conversation public seam: routing, ownership, immutable tasks and replay."""
# ruff: noqa: RUF001 -- Tests use the exact Chinese UI copy.

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
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
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.models.sales_commitment import FollowUpTask
from app.schemas.assistant_conversation import (
    ConversationAttachmentRef,
    ConversationChoiceRequest,
    ConversationDecision,
    ConversationPaginationRequest,
    ConversationTextRequest,
)
from app.services.agent.query.agent import CRMQueryAgentResponse, CRMQueryAgentResult, CRMQueryAgentTrace
from app.services.agent.query.cursor import decode_offset_cursor, encode_offset_cursor
from app.services.agent.query.schemas import CRMQueryResult, CRMQuerySpec, EntityRef
from app.services.assistant import conversation as module
from app.services.assistant import conversation_router as router_module
from app.services.assistant import failure_contract, model_transport
from app.services.assistant.contracts import TaskDraft
from app.services.assistant.conversation import ConversationService
from app.services.assistant.conversation_router import ConversationRootClassifier


@compiles(BigInteger, "sqlite")
def sqlite_integer(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    tables = [
        model.__table__
        for model in (
            AssistantTask,
            AssistantAction,
            AssistantRequest,
            AssistantTurn,
            AssistantTurnEvent,
            AssistantConversation,
            AssistantConversationEntry,
            Customer,
            CustomerMember,
            CustomerProduct,
            CustomerActivity,
            FollowUpTask,
            Opportunity,
        )
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name
    monkeypatch.setattr(module, "schedule_turn", lambda turn_id: None)
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda *_args, **_kwargs: [
            SimpleNamespace(code="customer:view:all"),
            SimpleNamespace(code="customer:activity:create"),
        ],
    )
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


QUERY_MODEL_CONFIG = object()


@pytest.fixture
def query_model(monkeypatch):
    """Resolve the team's query model without a configured provider."""

    monkeypatch.setattr(
        "app.services.agent.application.load_agent_model_configs",
        lambda _db, *, team_id: (None, QUERY_MODEL_CONFIG),
    )
    return QUERY_MODEL_CONFIG


class QueryAgent:
    """Shared CRMQueryAgentExecutor seam: records each turn and answers from ``respond``."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    async def execute(self, request, *, runtime):
        self.calls.append((request, runtime))
        return self.respond(request)


class CustomerPages:
    """Deterministic CRMQueryExecutor seam over ``total`` customers."""

    def __init__(self, total=12):
        self.total = total
        self.calls = []

    async def execute(self, spec, context):
        self.calls.append((spec, context))
        return customer_page(decode_offset_cursor(spec.cursor), total=self.total)


def customer_page(offset, *, total=12, page_size=10):
    refs = [
        EntityRef(
            ref_id=f"eref_customer_cus_{index:02d}",
            resource="customer",
            public_id=f"cus_{index:02d}",
            display_name=f"客户{index:02d}",
        )
        for index in range(offset, min(offset + page_size, total))
    ]
    end = offset + len(refs)
    return CRMQueryResult(
        query_id="query_customers",
        resource="customer",
        status="SUCCESS" if refs else "EMPTY",
        executed_query=CRMQuerySpec(
            resource="customer",
            projection=["account_name"],
            page_size=page_size,
            cursor=encode_offset_cursor(offset) if offset else None,
        ),
        rows=[{"public_id": ref.public_id, "account_name": ref.display_name} for ref in refs],
        entity_refs=refs,
        total=total,
        next_cursor=encode_offset_cursor(end) if end < total else None,
    )


def answered(text, *, query_results=(), entity_refs=()):
    return CRMQueryAgentResult(
        response=CRMQueryAgentResponse(status="ANSWERED", answer=text, evidence_refs=["query_customers"]),
        query_results=list(query_results),
        authoritative_entity_refs=list(entity_refs),
        trace=CRMQueryAgentTrace(
            model="test-model", tool_call_count=1, total_entity_count=0, elapsed_ms=1, stop_reason="COMPLETED"
        ),
    )


class _NoopVisionExtractor:
    async def extract(self, db, *, team_id, user_id, attachments, user_text):
        return ""


def query_service(agent, pages=None):
    return ConversationService(
        classifier=Classifier(decision(speech="ASK_FACT", obj="CUSTOMER", operation="READ")),
        query_executor=agent,
        query_spec_executor=pages,
        vision_extractor=_NoopVisionExtractor(),
    )


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
async def test_query_and_unsupported_writes_never_create_activity_task(db, query_model, speech, obj, operation):
    service = ConversationService(
        classifier=Classifier(decision(speech=speech, obj=obj, operation=operation)),
        query_executor=QueryAgent(lambda _request: answered("最近没有新的跟进记录。")),
    )
    initial = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version), authorization="Bearer caller-token"
    )
    assert response.submission is None
    assert db.query(AssistantTask).count() == db.query(AssistantTurn).count() == 0
    reply = response.conversation.messages[-1]
    assert "AI Agent" not in reply.text
    assert reply.ui is not None
    assert reply.ui.suggested_actions == []
    if operation == "READ":
        assert reply.ui.metadata.route == "QUERY"
        assert [block.type for block in reply.ui.blocks] == ["process", "text"]
    else:
        assert [block.type for block in reply.ui.blocks] == ["text"]

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
            "actor": "USER",
            "action": "select_activity_kind",
            "input_json": {"kind": "ONLINE_MEETING"},
            "result_json": {},
        },
        {
            "actor": "USER",
            "action": "submit_field",
            "input_json": {"field": "customer", "text": "旧客户"},
            "result_json": {},
        },
        {
            "actor": "SYSTEM",
            "action": "freeze_activity",
            "event_type": "meeting_card",
            "result_json": {"confirmation": frozen},
        },
        {
            "actor": "SYSTEM",
            "action": "show_write_receipt",
            "event_type": "receipt",
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
    legacy = [m for m in state.messages if ":legacy:" in m.id and m.role == "assistant"]
    assert [m.outcome for m in legacy if m.task is None] == ["activity_written", None]


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

async def test_root_supplement_preserves_an_unknown_activity_wait_and_allows_new_focus(db):
    old = task(
        db, version=3, waiting_type="FIELD", waiting_field="next_action", last_error_code="UNKNOWN_COMMIT_RESULT",
        waiting_json={"action_id": "old-question", "payload": {"question_id": "q_old", "prompt": "原问题"}},
    )
    classifier = Classifier(decision("CONTINUE", old.public_id, "PROVIDE_SUPPLEMENT"))
    service = ConversationService(classifier=classifier)
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    assert response.submission is None
    assert response.conversation.focused_task.reconciliation_required
    db.refresh(old)
    assert old.version == 3 and old.waiting_json["action_id"] == "old-question"
    assert db.query(AssistantTurn).count() == 0

    classifier.value = decision()
    new = await service.submit_text(db, team_id=1, user_id=2,
                                    request=text(response.conversation.version, key="independent-request"))
    assert new.submission.task_public_id != old.public_id



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
    for i, field_name in enumerate(["activity_write", "proposal:follow_up_task_create"]):
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
            input_json={"kind": "confirm", "choice": "confirm"},
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


def test_post_write_proposal_warning_is_not_normal_completion(db):
    from app.crud import assistant_conversation as crud
    from app.services.assistant.presentation import task_view

    receipt = {"kind": "customer_activity", "public_id": "1"}
    row = task(db, committed_json=[receipt])
    service = ConversationService(classifier=Classifier(decision()))
    service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    snapshot = task_view(row, db).model_dump(mode="json")
    previous = None
    for i, (kind, event_snapshot, message) in enumerate([
        ("confirm", snapshot, "活动已记录"),
        ("continue_proposals", {**snapshot, "status": "COMPLETED", "proposal_outcome": "proposal_failed"},
         "活动已记录。本次没能生成后续建议，可在客户页手动处理。"),
    ]):
        request = AssistantRequest(
            team_id=1, user_id=2, client_request_id=f"proposal-req-{i}", input_fingerprint="x", task_id=row.id
        )
        db.add(request)
        db.flush()
        turn = AssistantTurn(
            team_id=1, user_id=2, task_id=row.id, request_id=request.id,
            input_json={"kind": kind, "choice": "confirm" if kind == "confirm" else None}, status="SUCCEEDED",
        )
        db.add(turn)
        db.flush()
        if previous is None:
            db.add(AssistantConversationEntry(
                conversation_id=conv.id, team_id=1, user_id=2, client_request_id="proposal-entry",
                input_fingerprint="x", user_text="确认", state="READY", command_json={"waiting_field": "activity_write"},
                task_public_id=row.public_id, turn_public_id=turn.public_id,
            ))
        else:
            previous.data_json = {**previous.data_json, "next_turn_id": turn.public_id}
        previous = AssistantTurnEvent(
            turn_id=turn.id, seq=1, event="waiting", data_json={"task": event_snapshot, "message": message},
        )
        db.add(previous)
    db.commit()

    messages = service.read(db, team_id=1, user_id=2).messages
    assert any(m.outcome == "activity_written" for m in messages)
    assert not any(m.outcome in {"task_completed", "failure"} for m in messages)
    warning = next(m for m in messages if m.outcome == "proposal_unavailable")
    assert warning.task.committed[0].public_id == "1"
    assert warning.ui is not None and warning.ui.state == "final"
    assert len(warning.ui.blocks) == 1
    notice = warning.ui.blocks[0]
    assert notice.type == "notice" and notice.tone == "warning" and notice.code == "PROPOSAL_UNAVAILABLE"


def test_structured_disposition_event_preserves_batch_projection_and_activity_receipt(db):
    from app.crud import assistant_conversation as crud
    from app.services.assistant.presentation import task_view

    old = task(
        db,
        version=4,
        authority_json={
            "open_follow_up_batch": {
                "disposition_batch_id": "afb_stable",
                "status": "DONE",
                "activity_id": "act_source",
                "items": [
                    {"item_id": "i1", "task_public_id": "fut_one", "disposition": "complete"},
                    {"item_id": "i2", "task_public_id": "fut_two", "disposition": "hold"},
                ],
            },
            "activity_public_id": "act_source",
        },
        committed_json=[{"kind": "customer_activity", "public_id": "act_source"}],
    )
    service = ConversationService(classifier=Classifier(decision()))
    service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    request = AssistantRequest(
        team_id=1, user_id=2, client_request_id="projection-event", input_fingerprint="x", task_id=old.id
    )
    db.add(request)
    db.flush()
    turn = AssistantTurn(
        team_id=1, user_id=2, task_id=old.id, request_id=request.id,
        input_json={"kind": "confirm", "choice": "confirm"}, status="SUCCEEDED",
    )
    db.add(turn)
    db.flush()
    db.add(
        AssistantConversationEntry(
            conversation_id=conv.id, team_id=1, user_id=2,
            client_request_id="projection-entry", input_fingerprint="x",
            user_text="确认", state="READY", command_json={"waiting_field": "follow_up_disposition"},
            task_public_id=old.public_id, turn_public_id=turn.public_id,
        )
    )
    db.add(
        AssistantTurnEvent(
            turn_id=turn.id, seq=1, event="waiting",
            data_json={
                "task": task_view(old, db).model_dump(mode="json"),
                "message": "跟进结果",
                "card": "follow_up_disposition",
            },
        )
    )
    db.commit()

    message = next(m for m in service.read(db, team_id=1, user_id=2).messages if m.text == "跟进结果")
    assert message.projection is not None
    assert message.projection.activity_public_id is None
    assert message.projection.disposition is not None
    assert message.projection.disposition.task_public_id == old.public_id
    assert message.projection.disposition.batch_id == "afb_stable"
    assert message.projection.disposition.item_ids == ["i1", "i2"]
    assert message.projection.disposition.card_role == "FINAL"
    assert message.projection.disposition.version == 4


async def test_reclaimed_lease_fences_the_original_root_worker_before_task_dispatch(db):
    from datetime import timedelta

    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    old = task(db)
    deadlines = []
    reclaimed_leases = []

    class ReclaimedRoot(Classifier):
        async def classify(self, session, **kwargs):
            deadlines.append(failure_contract.capture_attempt_deadline())
            reclaimed_leases.append(crud.owned_conversation(session, team_id=1, user_id=2).lease_expires_at)
            return await super().classify(session, **kwargs)

    class InterruptedRoot:
        async def classify(self, session, **kwargs):
            conv = crud.owned_conversation(session, team_id=1, user_id=2)
            deadlines.append(failure_contract.capture_attempt_deadline())
            conv.lease_expires_at = business_now() - timedelta(seconds=1)
            session.commit()
            restarted = ConversationService(classifier=ReclaimedRoot(decision()))
            await restarted.resume(session, team_id=1, user_id=2)
            return decision("CONTINUE", old.public_id, "PROVIDE_SUPPLEMENT")

    service = ConversationService(classifier=InterruptedRoot())
    state = service.open(db, team_id=1, user_id=2)
    with pytest.raises(crud.ConversationConflict):
        await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    assert db.query(AssistantTask).count() == 2
    assert db.query(AssistantTurn).count() == 1
    assert not service.read(db, team_id=1, user_id=2).has_pending_request
    original, reclaimed = deadlines
    assert original is not None and original == reclaimed
    assert reclaimed_leases == [original + timedelta(seconds=5)]


async def test_expired_root_reclaim_does_not_restart_the_model(db):
    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    class InterruptedRoot:
        async def classify(self, *_args, **_kwargs):
            raise asyncio.CancelledError

    service = ConversationService(classifier=InterruptedRoot())
    state = service.open(db, team_id=1, user_id=2)
    with pytest.raises(asyncio.CancelledError):
        await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))

    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    entry = db.query(AssistantConversationEntry).one()
    stages = entry.command_json["root_stages"]
    expired = (business_now() - timedelta(seconds=6)).isoformat()
    entry.command_json = {**entry.command_json, "root_deadline": expired}
    conv.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()

    classifier = Classifier(decision())
    result = await ConversationService(classifier=classifier).resume(db, team_id=1, user_id=2)
    assert classifier.calls == []
    assert result.submission is None
    assert result.conversation.messages[-1].error_code == "UPSTREAM_TIMEOUT"
    db.refresh(entry)
    assert entry.command_json["root_deadline"] == expired
    assert entry.command_json["root_stages"] == stages
    assert not result.conversation.has_pending_request
    assert db.query(AssistantTask).count() == 0


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
        db,
        **foreign_owner,
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
            db,
            goal=f"同名客户的沟通{i}",
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


def test_root_understanding_uses_remaining_budget_for_both_calls(monkeypatch):
    started_at = datetime(2026, 1, 1, 9)
    elapsed = 5
    timeouts = []
    original_client = httpx.AsyncClient

    def respond(request):
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"choices": [{"message": {
            "content": decision(boundary="AMBIGUOUS", target="ast_written").model_dump_json(),
        }}]})

    monkeypatch.setattr(
        router_module,
        "team_model_credentials",
        lambda db, team_id: ("https://model.example", "not-a-real-key", "test-model"),
    )
    monkeypatch.setattr(router_module, "team_output_mode", lambda db, team_id: "json_object")
    monkeypatch.setattr(
        model_transport.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr(failure_contract, "business_now", lambda: started_at + timedelta(seconds=elapsed))
    monkeypatch.setattr(model_transport, "monotonic", lambda: float(elapsed))
    classifier = ConversationRootClassifier()

    async def classify_twice():
        nonlocal elapsed
        token = failure_contract.bind_attempt_deadline(started_at)
        try:
            kwargs = dict(team_id=1, text="下午和对方技术经理通了电话，说POC下周可以部署。", tasks=[],
                          focused_task_public_id=None, recent_messages=[])
            first = await classifier.classify(None, **kwargs)
            elapsed = 160
            second = await classifier.classify(None, **kwargs)
            assert first.boundary == second.boundary == "AMBIGUOUS"
        finally:
            failure_contract.reset_attempt_deadline(token)

    asyncio.run(classify_twice())
    assert timeouts == [175, 20]


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
    assert [message.text for message in page.messages][:2] == ["正常历史", "无法投影的原句"]
    assert len(page.messages) == 3
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
                "temporal_target": {
                    "mention_id": spec["mention_id"],
                    "business_action_id": spec["business_action_id"],
                    "reason": spec["reason"],
                },
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


async def test_independent_action_supplement_does_not_answer_pending_date(db):
    row, _spec = month_ambiguity(db)
    original_draft = dict(row.draft_json)
    service = ConversationService(classifier=Classifier(decision("CONTINUE", row.public_id, "PROVIDE_SUPPLEMENT")))
    opened = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(
        db,
        team_id=1,
        user_id=2,
        request=text(opened.version, "另外客户12月6号付款", "independent-customer-action"),
    )
    assert response.submission is not None
    assert response.submission.input.kind == "text"
    assert response.submission.input.action_id is None
    db.refresh(row)
    assert row.waiting_type is None
    assert row.draft_json == original_draft


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
    assert_october_follow_up(row)


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
    assert row.waiting_field == "content"
    assert row.waiting_json["action_id"] != "awa_dup"
    assert row.committed_json == []
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


@pytest.mark.parametrize("code", ["REQUEST_PROTOCOL_ERROR", "AUTHENTICATION_ERROR"])
async def test_root_provider_rejection_keeps_code_and_denies_retry(db, code):
    from app.crud.assistant_conversation import ConversationConflict
    from app.services.assistant.failure_contract import AssistantFailureCode
    from app.services.assistant.model_transport import AssistantLLMError

    class Broken:
        async def classify(self, *args, **kwargs):
            raise AssistantLLMError("https://secret.example sk-live", code=AssistantFailureCode(code))

    service = ConversationService(classifier=Broken())
    state = service.open(db, team_id=1, user_id=2)
    response = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    message = response.conversation.messages[-1]
    entry = db.query(AssistantConversationEntry).one()
    assert entry.error_code == message.error_code == code
    assert message.ui is not None
    error = message.ui.blocks[0]
    assert error.type == "error" and error.code == code and error.retryable is False
    assert message.ui.suggested_actions == []
    assert "secret.example" not in message.text and "sk-live" not in message.text
    with pytest.raises(ConversationConflict):
        await service.retry_entry(
            db, team_id=1, user_id=2, entry_id=entry.public_id, expected_version=response.conversation.version
        )
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
            self.deadlines = []

        async def classify(self, db, **kwargs):
            from app.crud import assistant_conversation as crud

            self.calls += 1
            conversation = crud.owned_conversation(db, team_id=1, user_id=2)
            self.leases.append(conversation.lease_expires_at)
            self.deadlines.append(failure_contract.capture_attempt_deadline())
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
    first, retry = classifier.deadlines
    assert first is not None and retry is not None and retry > first
    assert classifier.leases == [deadline + timedelta(seconds=5) for deadline in (first, retry)]
    assert entry.command_json["root_stages"] == [
        {"stage": "route", "phase": "start"},
        {"stage": "route", "phase": "done", "ms": entry.command_json["root_stages"][-1]["ms"]},
    ]
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

    real_save = crud.save

    def expire(db, conversation, entry, **kwargs):
        conversation.lease_expires_at = business_now() - timedelta(seconds=1)
        db.commit()
        return real_save(db, conversation, entry, **kwargs)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(crud, "save", expire)
    try:
        with pytest.raises(crud.ConversationConflict):
            await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    finally:
        monkeypatch.undo()
    entry = db.query(AssistantConversationEntry).one()
    assert entry.error_code is None
    assert entry.state == "ROUTING"
    assert conversation.busy_entry_id == entry.public_id


async def test_root_timeout_records_a_failed_route_stage_and_retry_replays_it(db):
    """W1-6/A9: progress must say the route attempt failed, not only the generic failure text."""
    from app.services.assistant.failure_contract import AssistantFailureCode
    from app.services.assistant.model_transport import AssistantLLMError

    class Fails:
        def __init__(self):
            self.calls = 0

        async def classify(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise AssistantLLMError("模型服务响应超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)
            return decision()

    classifier = Fails()
    service = ConversationService(classifier=classifier)
    state = service.open(db, team_id=1, user_id=2)
    failed = await service.submit_text(db, team_id=1, user_id=2, request=text(state.version))
    entry = db.query(AssistantConversationEntry).one()
    assert failed.submission is None
    assert entry.command_json["root_stages"] == [
        {"stage": "route", "phase": "start"},
        {"stage": "route", "phase": "failed", "ms": entry.command_json["root_stages"][-1]["ms"]},
    ]

    retried = await service.retry_entry(
        db, team_id=1, user_id=2, entry_id=entry.public_id, expected_version=failed.conversation.version
    )
    db.refresh(entry)
    assert retried.submission is not None
    # A retry is a fresh attempt window, so only its own stages remain.
    assert [(item["stage"], item["phase"]) for item in entry.command_json["root_stages"]] == [
        ("route", "start"), ("route", "done"),
    ]


async def test_request_status_answers_lost_response_without_writing(db):
    """CRM-167: after a lost response the client asks; the answer never resends or advances anything."""
    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    classifier = Classifier(decision())
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    req = text(initial.version, key="request-lost")

    unknown = service.request_status(db, team_id=1, user_id=2, client_request_id="request-lost")
    assert unknown.state == "none"
    assert unknown.conversation.version == initial.version

    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    crud.claim(
        db,
        conv,
        key=req.client_request_id,
        payload={"operation": "text", "text": req.text},
        text=req.text,
        expected_version=req.expected_version,
    )
    running = service.request_status(db, team_id=1, user_id=2, client_request_id="request-lost")
    assert running.state == "running"
    assert running.conversation.has_pending_request

    conv.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()
    stalled = service.request_status(db, team_id=1, user_id=2, client_request_id="request-lost")
    assert stalled.state == "not_saved"
    assert stalled.conversation.version == running.conversation.version
    assert classifier.calls == []
    assert db.query(AssistantTurn).count() == 0

    # Resending the same key resumes the stalled entry instead of creating another one.
    resumed = await service.submit_text(db, team_id=1, user_id=2, request=req)
    assert resumed.submission is not None
    assert db.query(AssistantConversationEntry).count() == 1
    turn = db.query(AssistantTurn).one()
    assert turn.status == "PENDING"
    assert service.request_status(db, team_id=1, user_id=2, client_request_id="request-lost").state == "running"

    turn.status = "SUCCEEDED"
    db.commit()
    saved = service.request_status(db, team_id=1, user_id=2, client_request_id="request-lost")
    assert saved.state == "saved"
    assert saved.conversation.messages[0].text == req.text
    assert len(classifier.calls) == 1


async def test_request_status_never_offers_a_resend_the_server_would_refuse(db):
    """A stored entry is only not_saved when crud.claim would resume that same key."""
    from app.crud import assistant_conversation as crud
    from app.utils.time import business_now

    service = ConversationService(classifier=Classifier(decision()))
    initial = service.open(db, team_id=1, user_id=2)
    conv = crud.owned_conversation(db, team_id=1, user_id=2)
    entry, _, _ = crud.claim(
        db,
        conv,
        key="request-orphan",
        payload={"operation": "text", "text": "今天和睿狐科技电话沟通了部署"},
        text="今天和睿狐科技电话沟通了部署",
        expected_version=initial.version,
    )
    conv.lease_expires_at = None
    db.commit()
    assert service.request_status(db, team_id=1, user_id=2, client_request_id="request-orphan").state == "running"

    conv.busy_entry_id = None
    conv.lease_expires_at = business_now() - timedelta(seconds=1)
    db.commit()
    assert entry.state == "ROUTING"
    assert service.request_status(db, team_id=1, user_id=2, client_request_id="request-orphan").state == "running"


async def test_request_status_is_owner_scoped(db):
    from app.crud.assistant_conversation import ConversationConflict

    service = ConversationService(classifier=Classifier(decision()))
    initial = service.open(db, team_id=1, user_id=2)
    await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, key="request-mine"))
    service.open(db, team_id=1, user_id=3)
    assert service.request_status(db, team_id=1, user_id=3, client_request_id="request-mine").state == "none"
    service.open(db, team_id=2, user_id=2)
    assert service.request_status(db, team_id=2, user_id=2, client_request_id="request-mine").state == "none"
    with pytest.raises(ConversationConflict):
        service.request_status(db, team_id=9, user_id=9, client_request_id="request-mine")


async def test_stale_second_request_is_rejected_and_reports_none(db):
    """Two tabs sending from the same version: the stale one stores nothing, so it may be resent."""
    from app.crud.assistant_conversation import ConversationConflict

    service = ConversationService(classifier=Classifier(decision()))
    initial = service.open(db, team_id=1, user_id=2)
    await service.submit_text(db, team_id=1, user_id=2, request=text(initial.version, key="request-first"))
    with pytest.raises(ConversationConflict):
        await service.submit_text(
            db, team_id=1, user_id=2, request=text(initial.version, "另一件事", key="request-stale")
        )
    db.rollback()
    assert db.query(AssistantConversationEntry).count() == 1
    assert service.request_status(db, team_id=1, user_id=2, client_request_id="request-stale").state == "none"


async def test_double_click_with_same_key_saves_once(db):
    classifier = Classifier(decision())
    service = ConversationService(classifier=classifier)
    initial = service.open(db, team_id=1, user_id=2)
    req = text(initial.version, key="request-double")
    results = await asyncio.gather(
        service.submit_text(db, team_id=1, user_id=2, request=req),
        service.submit_text(db, team_id=1, user_id=2, request=req),
        return_exceptions=True,
    )
    failures = [item for item in results if isinstance(item, BaseException)]
    assert len(failures) < len(results)
    assert all("仍在处理中" in str(item) for item in failures)
    assert db.query(AssistantConversationEntry).count() == 1
    assert db.query(AssistantTurn).count() == 1
    assert len(classifier.calls) == 1


async def test_query_route_lists_customers_and_paginates_by_server_action(db, query_model):
    agent = QueryAgent(lambda _request: answered("已找到客户", query_results=[customer_page(0)]))
    pages = CustomerPages()
    service = query_service(agent, pages)
    initial = service.open(db, team_id=1, user_id=2)
    first = await service.submit_text(
        db,
        team_id=1,
        user_id=2,
        request=ConversationTextRequest(
            text="查看我的客户列表",
            expected_version=initial.version,
            client_request_id="query-customers-001",
        ),
        authorization="Bearer caller-token",
    )
    assert first.submission is None
    request, runtime = agent.calls[0]
    assert request.text == "查看我的客户列表"
    assert (request.principal.team_id, request.principal.user_id) == (1, 2)
    assert request.selected_entity is None
    assert runtime.authorization == "Bearer caller-token"
    assert runtime.query_model_config is query_model

    reply = first.conversation.messages[-1]
    assert reply.ui is not None and reply.ui.metadata.route == "QUERY"
    blocks = {block.type: block for block in reply.ui.blocks}
    process_items = [(item.key, item.status) for item in blocks["process"].items]
    assert process_items == [("route", "COMPLETED"), ("query", "COMPLETED")]
    entity_list = blocks["entity_list"]
    assert (entity_list.total, len(entity_list.items)) == (12, 10)
    pagination = blocks["pagination"]
    assert pagination.result_set_id == entity_list.result_set_id
    assert (pagination.range_start, pagination.range_end, pagination.total) == (1, 10, 12)
    assert pagination.previous_action_id is None and pagination.next_action_id is not None

    page2_request = ConversationPaginationRequest(
        action_id=pagination.next_action_id,
        expected_version=first.conversation.version,
        client_request_id="query-customers-page2",
    )
    page2 = await service.paginate(
        db, team_id=1, user_id=2, request=page2_request, authorization="Bearer caller-token"
    )
    spec, context = pages.calls[0]
    assert spec.cursor == encode_offset_cursor(10)
    assert (context.team_id, context.user_id, context.authorization) == (1, 2, "Bearer caller-token")
    page2_blocks = {block.type: block for block in page2.conversation.messages[-1].ui.blocks}
    assert [item.entity_ref.public_id for item in page2_blocks["entity_list"].items] == ["cus_10", "cus_11"]
    assert page2_blocks["entity_list"].result_set_id == entity_list.result_set_id
    page2_pagination = page2_blocks["pagination"]
    assert (page2_pagination.range_start, page2_pagination.range_end, page2_pagination.total) == (11, 12, 12)
    assert page2_pagination.previous_action_id is not None and page2_pagination.next_action_id is None

    replay = await service.paginate(
        db, team_id=1, user_id=2, request=page2_request, authorization="Bearer caller-token"
    )
    assert replay.conversation.version == page2.conversation.version
    assert len(pages.calls) == 1

    page1 = await service.paginate(
        db,
        team_id=1,
        user_id=2,
        request=ConversationPaginationRequest(
            action_id=page2_pagination.previous_action_id,
            expected_version=page2.conversation.version,
            client_request_id="query-customers-page1",
        ),
        authorization="Bearer caller-token",
    )
    assert pages.calls[1][0].cursor is None
    page1_pagination = next(b for b in page1.conversation.messages[-1].ui.blocks if b.type == "pagination")
    assert (page1_pagination.range_start, page1_pagination.range_end) == (1, 10)
    assert len(agent.calls) == 1

    with pytest.raises(module.crud.ConversationConflict):
        await service.paginate(
            db,
            team_id=1,
            user_id=2,
            request=ConversationPaginationRequest(
                action_id="pg_unknown_action",
                expected_version=page1.conversation.version,
                client_request_id="query-customers-invalid",
            ),
            authorization="Bearer caller-token",
        )


async def test_mentioned_customer_query_binds_selected_entity_and_attachments_validate(db, query_model):
    db.add(
        Customer(
            public_id="cus_mention_01",
            team_id=1,
            account_name="星海科技有限公司",
            industry="互联网",
            city="杭州",
            status=0,
            creator_id="2",
        )
    )
    db.commit()

    agent = QueryAgent(lambda request: answered("客户概览如下", entity_refs=[request.selected_entity]))
    service = query_service(agent)
    initial = service.open(db, team_id=1, user_id=2)
    reply = await service.submit_text(
        db,
        team_id=1,
        user_id=2,
        request=ConversationTextRequest(
            text="查看客户概览",
            expected_version=initial.version,
            client_request_id="query-mention-001",
            mentioned_customer_public_id="cus_mention_01",
            attachments=[
                ConversationAttachmentRef(
                    file_url="https://files.example.com/a.png",
                    file_name="a.png",
                    mime_type="image/png",
                    size_bytes=2048,
                )
            ],
        ),
        authorization="Bearer caller-token",
    )
    selected = agent.calls[0][0].selected_entity
    assert (selected.resource, selected.public_id, selected.display_name) == (
        "customer",
        "cus_mention_01",
        "星海科技有限公司",
    )
    message = reply.conversation.messages[-1]
    assert message.ui is not None and message.ui.metadata.route == "QUERY"
    entity_list = next(block for block in message.ui.blocks if block.type == "entity_list")
    assert [item.entity_ref.public_id for item in entity_list.items] == ["cus_mention_01"]
    assert all(block.type != "pagination" for block in message.ui.blocks)

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ConversationTextRequest(
            text="too many",
            expected_version=0,
            client_request_id="attach-limit-001",
            attachments=[
                ConversationAttachmentRef(
                    file_url=f"https://files.example.com/{i}.png",
                    file_name=f"{i}.png",
                    mime_type="image/png",
                    size_bytes=1024,
                )
                for i in range(4)
            ],
        )


async def test_query_carries_caller_permissions_and_hidden_mention_never_reaches_engine(db, monkeypatch, query_model):
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda *_args, **_kwargs: [SimpleNamespace(code="customer:view:own")],
    )
    shared_customer = Customer(
        public_id="cus_perm_shared",
        team_id=1,
        account_name="协作客户",
        city="杭州",
        status=0,
        creator_id="3",
        owner_id="3",
    )
    hidden_customer = Customer(
        public_id="cus_perm_hidden",
        team_id=1,
        account_name="他人客户",
        city="北京",
        status=0,
        creator_id="3",
        owner_id="3",
    )
    db.add_all([shared_customer, hidden_customer])
    db.flush()
    db.add(
        CustomerMember(
            team_id=1,
            customer_id=shared_customer.id,
            user_id="2",
            access_level="VIEW",
            created_by="3",
            is_active=True,
        )
    )
    db.commit()

    agent = QueryAgent(lambda request: answered("客户概览如下", entity_refs=[request.selected_entity]))
    service = query_service(agent)
    initial = service.open(db, team_id=1, user_id=2)

    denied = await service.submit_text(
        db,
        team_id=1,
        user_id=2,
        request=ConversationTextRequest(
            text="查看这个客户概览",
            expected_version=initial.version,
            client_request_id="perm-mention-denied-001",
            mentioned_customer_public_id="cus_perm_hidden",
        ),
        authorization="Bearer caller-token",
    )
    denied_message = denied.conversation.messages[-1]
    assert "暂无查看权限" in denied_message.text
    assert "他人客户" not in denied_message.text
    assert all(block.type != "entity_list" for block in denied_message.ui.blocks)
    assert agent.calls == []

    await service.submit_text(
        db,
        team_id=1,
        user_id=2,
        request=ConversationTextRequest(
            text="查看这个客户概览",
            expected_version=denied.conversation.version,
            client_request_id="perm-mention-member-001",
            mentioned_customer_public_id="cus_perm_shared",
        ),
        authorization="Bearer caller-token",
    )
    request, runtime = agent.calls[0]
    assert request.selected_entity.public_id == "cus_perm_shared"
    assert request.principal.permission_codes == ["customer:view:own"]
    assert runtime.permission_codes == frozenset({"customer:view:own"})


class QueryEngineDown(RuntimeError):
    pass


def unconfigured_query_model(_db, *, team_id):
    from fastapi import HTTPException

    raise HTTPException(status_code=503, detail="AI 模型未配置")


def engine_down(_request):
    raise QueryEngineDown("upstream unavailable")


@pytest.mark.parametrize(
    "authorization,load_model,respond",
    [
        (None, None, None),
        ("Bearer caller-token", unconfigured_query_model, None),
        ("Bearer caller-token", None, engine_down),
    ],
    ids=["missing-bearer", "model-unconfigured", "engine-error"],
)
async def test_query_failure_fails_closed_without_write_copy_or_error_code(
    db, monkeypatch, query_model, authorization, load_model, respond
):
    if load_model is not None:
        monkeypatch.setattr("app.services.agent.application.load_agent_model_configs", load_model)
    agent = QueryAgent(respond or (lambda _request: answered("不应出现")))
    service = query_service(agent)
    initial = service.open(db, team_id=1, user_id=2)
    reply = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, "查看我的客户"), authorization=authorization
    )
    message = reply.conversation.messages[-1]
    assert message.ui is not None and message.ui.metadata.route == "QUERY"
    blocks = {block.type: block for block in message.ui.blocks}
    process_items = [(item.key, item.status) for item in blocks["process"].items]
    assert process_items == [("route", "COMPLETED"), ("query", "FAILED")]
    assert blocks["error"].title == "查询没完成"
    assert "客户活动" not in message.text
    assert "不应出现" not in message.text
    assert all(entry.error_code is None for entry in db.query(AssistantConversationEntry))
    assert len(agent.calls) == (1 if respond is not None else 0)


async def test_query_clarification_answers_with_text_and_no_pagination(db, query_model):
    clarification = CRMQueryAgentResult(
        response=CRMQueryAgentResponse(
            status="CLARIFICATION_REQUIRED", clarification_question="你想看哪个城市的客户？"
        ),
        trace=CRMQueryAgentTrace(
            model="test-model", tool_call_count=0, total_entity_count=0, elapsed_ms=1, stop_reason="COMPLETED"
        ),
    )
    service = query_service(QueryAgent(lambda _request: clarification))
    initial = service.open(db, team_id=1, user_id=2)
    reply = await service.submit_text(
        db, team_id=1, user_id=2, request=text(initial.version, "查看客户"), authorization="Bearer caller-token"
    )
    message = reply.conversation.messages[-1]
    assert message.text == "你想看哪个城市的客户？"
    assert [block.type for block in message.ui.blocks] == ["process", "text"]


async def test_workflow_mention_does_not_bind_unauthorized_customer(db, monkeypatch):
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda *_args, **_kwargs: [SimpleNamespace(code="customer:view:own")],
    )
    db.add(
        Customer(
            public_id="cus_wf_hidden",
            team_id=1,
            account_name="不可写客户",
            city="北京",
            status=0,
            creator_id="3",
            owner_id="3",
        )
    )
    db.commit()

    service = ConversationService(classifier=Classifier(decision()))
    initial = service.open(db, team_id=1, user_id=2)
    reply = await service.submit_text(
        db,
        team_id=1,
        user_id=2,
        request=ConversationTextRequest(
            text="今天电话沟通了方案",
            expected_version=initial.version,
            client_request_id="perm-wf-mention-001",
            mentioned_customer_public_id="cus_wf_hidden",
        ),
    )
    assert reply.submission is not None
    created_task = db.query(AssistantTask).filter_by(public_id=reply.submission.task_public_id).one()
    assert created_task.authority_json.get("customer_public_id") is None
