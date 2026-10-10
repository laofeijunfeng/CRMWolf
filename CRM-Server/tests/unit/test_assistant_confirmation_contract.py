"""Assistant 2.0 confirmation writes exactly the frozen, authorized activity."""
# ruff: noqa: RUF001

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent
from app.models.team import Team, UserTeam
from app.models.user import User
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.real_writer import RealActivityWriter


@compiles(BigInteger, "sqlite")
def _bigint_as_int(element, compiler, **kwargs):
    return "INTEGER"


class NoChooser:
    async def choose(self, task):
        raise AssertionError("an already scored draft must not call chooser")


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant-confirmation.db'}")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_indexes(conn, cursor, statement, parameters, context, executemany):
        return ("SELECT 1", ()) if statement.startswith("CREATE INDEX") else (statement, parameters)

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProduct.__table__,
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerLegacySourceProgress.__table__,
            CustomerActivityDeletionTombstone.__table__,
            AssistantTask.__table__,
            AssistantAction.__table__,
            AssistantRequest.__table__,
            AssistantTurn.__table__,
            AssistantTurnEvent.__table__,
            User.__table__,
            Team.__table__,
            UserTeam.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
        ],
    )
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service.infer_for_customer", lambda *args: None)
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service.record_event", lambda *args, **kw: None)
    monkeypatch.setattr(
        "app.crud.operation_log.operation_log_crud.create", lambda db, obj_in, team_id=None, commit=True: None
    )
    monkeypatch.setattr(
        "app.services.customer_vector_document_service.customer_vector_document_service.upsert_customer_activity",
        lambda db, activity, commit=True: None,
    )
    permissions = [SimpleNamespace(code="customer:activity:create")]
    monkeypatch.setattr(
        "app.services.assistant.customer_resolution.permission_crud.get_user_permissions", lambda *args: permissions
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session, factory, permissions
    finally:
        session.close()
        engine.dispose()


def prepared(db):
    session, _, _ = db
    customer = Customer(
        team_id=1, account_name="睿狐科技", public_id="cus_confirmed", city="上海", creator_id="2", owner_id="2"
    )
    session.add(customer)
    source = "王总明确说POC通过，周五发验收报告"
    canonical = {
        "content": "POC已通过；王总周五发送验收报告",
        "customer_feedback": "王总确认POC通过",
        "current_progress": "POC完成",
        "risks": [],
        "next_action": "王总周五发送验收报告",
        "next_follow_time_text": "周五",
    }
    draft = TaskDraft(
        customer=DraftField(status="CANDIDATE", value="睿狐科技"),
        content=DraftField(status="CANDIDATE", value=canonical["content"]),
        next_action=DraftField(status="CANDIDATE", value=canonical["next_action"]),
        next_follow_time=DraftField(status="CANDIDATE", value="周五"),
        content_json=canonical,
        source_segments=[source],
        score_reason="事实与行动明确",
        score_detail={"rubric": "follow_up", "score": 85},
        quality_score=DraftField(status="CANDIDATE", value="85"),
    )
    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录跟进",
        activity_kind="FOLLOW_UP",
        draft_json=draft.model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    session.add(task)
    session.commit()
    return task, customer, draft


async def freeze(db):
    session, _, _ = db
    task, customer, draft = prepared(db)
    outcome = await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
        session, task, AssistantInput(kind="text")
    )
    return outcome, customer, draft


@pytest.mark.asyncio
async def test_confirmation_freezes_exact_canonical_payload_then_writes_one_committed_activity(db):
    session, factory, _ = db
    outcome, customer, draft = await freeze(db)
    waiting = outcome.reply.waiting
    assert waiting is not None and waiting.type == "CONFIRMATION"
    frozen = outcome.task.authority_json["frozen_activity_command"]
    assert frozen["customer_public_id"] == customer.public_id
    assert frozen["content_json"] == draft.content_json
    assert frozen["source_content"] == draft.source_segments[0]
    assert frozen["score"] == 85
    assert frozen["submission_id"] and len(frozen["fingerprint"]) == 64
    assert waiting.fingerprint == frozen["fingerprint"]
    assert waiting.confirmation_payload.preview.content_json == draft.content_json
    session.commit()

    confirmed = await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
        session, outcome.task, AssistantInput(kind="confirm", choice="confirm")
    )
    assert confirmed.start_followup is True
    assert confirmed.task.waiting_type is None
    session.commit()
    with factory() as independent:
        activities = independent.query(CustomerActivity).all()
        assert len(activities) == 1
        activity = activities[0]
        assert activity.customer_id == customer.id
        assert activity.submission_source == "ASSISTANT_2"
        assert activity.submission_id == frozen["submission_id"]
        assert activity.submission_fingerprint == frozen["fingerprint"]
        assert json.loads(activity.content_json) == draft.content_json
        assert activity.source_content == draft.source_segments[0]
        assert (activity.effectiveness_score, activity.effectiveness_reason) == (85, draft.score_reason)
        assert confirmed.task.committed_json == [
            {"kind": "customer_activity", "public_id": str(activity.id), "customer_id": customer.id}
        ]


@pytest.mark.asyncio
async def test_confirmation_records_choice_and_receipt_once_for_the_same_request(db):
    session, _, _ = db
    outcome, _, _ = await freeze(db)
    session.commit()
    coordinator = AssistantCoordinator(NoChooser(), writer=RealActivityWriter())
    first = await coordinator.handle_task(session, outcome.task, AssistantInput(kind="confirm", choice="confirm"))
    session.commit()
    events = (
        session.query(AssistantAction)
        .filter(AssistantAction.event_type.is_not(None))
        .order_by(AssistantAction.id)
        .all()
    )
    visible = [(event.event_type, event.result_json.get("label")) for event in events]
    assert ("user_choice", "确认") in visible
    assert ("receipt", "已记录这条客户活动。") in visible
    assert first.reply.message == "已记录这条客户活动。"


@pytest.mark.asyncio
async def test_revoked_permission_retires_confirmation_without_business_write(db):
    session, factory, permissions = db
    outcome, _, _ = await freeze(db)
    session.commit()
    permissions.clear()
    confirmed = await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
        session, outcome.task, AssistantInput(kind="confirm", choice="confirm")
    )
    session.commit()
    assert confirmed.start_followup is False
    assert confirmed.task.last_error_code == "PERMISSION_DENIED"
    assert confirmed.task.waiting_type is None
    with factory() as independent:
        assert independent.query(CustomerActivity).count() == 0


@pytest.mark.asyncio
async def test_rollback_after_activity_write_cannot_leave_half_receipt(db, monkeypatch):
    session, factory, _ = db
    outcome, _, _ = await freeze(db)
    session.commit()

    def fail_receipt(*args, **kwargs):
        raise RuntimeError("receipt write failed")

    monkeypatch.setattr("app.services.assistant.confirmation.apply_task_update", fail_receipt)
    with pytest.raises(RuntimeError, match="receipt write failed"):
        await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
            session, outcome.task, AssistantInput(kind="confirm", choice="confirm")
        )
    session.rollback()
    with factory() as independent:
        assert independent.query(CustomerActivity).count() == 0
        task = independent.get(AssistantTask, outcome.task.id)
        assert task.waiting_type == "CONFIRMATION"
        assert task.committed_json == []


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_activity_and_receipt(db, monkeypatch):
    """C1: a same-command audit failure must abort the whole activity commit."""

    session, factory, _ = db
    outcome, _, _ = await freeze(db)
    session.commit()

    def failing_audit_create(*args, **kwargs):
        raise ValueError("audit builder exploded")

    # Fail inside the real log() call chain so its exception swallowing is exercised.
    monkeypatch.setattr("app.crud.operation_log.operation_log_crud.create", failing_audit_create)
    with pytest.raises(ValueError, match="audit builder exploded"):
        await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
            session, outcome.task, AssistantInput(kind="confirm", choice="confirm")
        )
    session.rollback()
    with factory() as independent:
        assert independent.query(CustomerActivity).count() == 0
        task = independent.get(AssistantTask, outcome.task.id)
        assert task.waiting_type == "CONFIRMATION"
        assert task.committed_json == []
        assert task.authority_json["frozen_activity_command"]["execution_status"] == "PENDING"


@pytest.mark.asyncio
async def test_evidence_failure_rolls_back_activity_and_receipt(db, monkeypatch):
    """C1: a same-command evidence failure must abort the whole activity commit."""
    session, factory, _ = db
    outcome, _, _ = await freeze(db)
    session.commit()

    def failing_upsert(*args, **kwargs):
        raise ValueError("evidence builder exploded")

    # Fail inside the real evidence helper so its exception swallowing is exercised.
    monkeypatch.setattr(
        "app.services.customer_vector_document_service.customer_vector_document_service.upsert_customer_activity",
        failing_upsert,
    )
    with pytest.raises(ValueError, match="evidence builder exploded"):
        await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
            session, outcome.task, AssistantInput(kind="confirm", choice="confirm")
        )
    session.rollback()
    with factory() as independent:
        assert independent.query(CustomerActivity).count() == 0
        task = independent.get(AssistantTask, outcome.task.id)
        assert task.waiting_type == "CONFIRMATION"
        assert task.committed_json == []
        assert task.authority_json["frozen_activity_command"]["execution_status"] == "PENDING"


@pytest.mark.asyncio
async def test_legacy_source_still_tolerates_audit_failure(db, monkeypatch):
    """Old sources keep best-effort audit; only ASSISTANT_2 is strict."""

    session, factory, _ = db
    customer = Customer(
        team_id=1, account_name="旧来源客户", public_id="cus_legacy", city="上海", creator_id="2", owner_id="2"
    )
    session.add(customer)
    session.commit()

    def failing_audit_create(*args, **kwargs):
        raise ValueError("audit builder exploded")

    monkeypatch.setattr("app.crud.operation_log.operation_log_crud.create", failing_audit_create)
    from app.crud.customer_activity import customer_activity_crud
    from app.schemas.customer_activity import CustomerActivityCreate

    created = customer_activity_crud.create(
        db=session,
        obj_in=CustomerActivityCreate(
            activity_kind="FOLLOW_UP",
            title="旧活动",
            summary="旧活动",
            source_content="旧来源活动内容",
        ),
        customer_id=customer.id,
        creator_id="2",
        team_id=1,
    )
    assert created.id is not None
    with factory() as independent:
        assert independent.query(CustomerActivity).count() == 1


class RecordingStructurer:
    def __init__(self):
        self.calls = []

    async def structure(self, db, *, team_id, kind, user_text):
        from app.services.assistant.llm_contracts import StructureDraftResult

        self.calls.append(user_text)
        return StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content="交付延迟风险",
            content_json={
                "content": "交付延迟风险",
                "risks": ["交付延迟"],
            },
            structuring_model="qwen3-structurer",
        )


class RecordingGate:
    def __init__(self):
        self.calls = []

    async def evaluate(self, db, **kwargs):
        from app.services.assistant.quality_gate import QualityGateOutcome

        self.calls.append(kwargs)
        return QualityGateOutcome(
            True,
            78,
            "补充事实明确",
            None,
            None,
            {"facts": 78, "model_name": "qwen3-max", "structured_output": "json_object"},
        )


@pytest.mark.asyncio
async def test_field_supplement_merges_canonical_facts_and_freezes_rescored_full_source(db):
    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.task_state import TaskUpdate, apply_task_update

    session, _, _ = db
    task, customer, initial = prepared(db)
    stale = initial.model_copy(deep=True)
    stale.quality_score = DraftField(status="MISSING")
    stale.score_reason = None
    stale.score_detail = {}
    task = apply_task_update(
        session,
        task,
        TaskUpdate(
            draft=stale,
            waiting=TaskWaiting(type="FIELD", field="content", question_id="q_gap", prompt="补充事实"),
            action_actor="SYSTEM",
            action_name="ask_quality_gap",
        ),
    ).task
    structurer, gate = RecordingStructurer(), RecordingGate()
    outcome = await AssistantCoordinator(NoChooser(), structurer=structurer, quality_gate=gate).handle_task(
        session, task, AssistantInput(kind="submit_field", text="补充：交付组说接口集成有延期风险")
    )

    waiting = outcome.reply.waiting
    assert waiting is not None and waiting.type == "CONFIRMATION"
    frozen = outcome.task.authority_json["frozen_activity_command"]
    assert frozen["customer_public_id"] == customer.public_id
    assert frozen["source_segments"] == [initial.source_segments[0], "补充：交付组说接口集成有延期风险"]
    assert frozen["score"] == 78
    assert "POC已通过" in frozen["content_json"]["content"]
    assert "交付延迟风险" in frozen["content_json"]["content"]
    assert frozen["content_json"]["risks"] == ["交付延迟"]
    assert gate.calls[0]["user_text"] == "\n".join(frozen["source_segments"])
    assert gate.calls[0]["content_json"] == frozen["content_json"]

    # TRD 4.4: the frozen command must carry scoring model metadata.
    assert frozen["model_metadata"] == {
        "model_name": "qwen3-max",
        "structured_output": "json_object",
        "structuring_model_name": "qwen3-structurer",
    }
    assert structurer.calls == ["补充：交付组说接口集成有延期风险"]


@pytest.mark.asyncio
async def test_kind_selection_prepares_frozen_confirmation_without_chooser(db):
    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.llm_contracts import StructureDraftResult
    from app.services.assistant.quality_gate import QualityGateOutcome
    from app.services.assistant.task_state import TaskUpdate, apply_task_update

    session, _, _ = db
    task, customer, initial = prepared(db)
    initial.quality_score = DraftField(status="MISSING")
    initial.score_reason = None
    initial.score_detail = {}
    task = apply_task_update(
        session,
        task,
        TaskUpdate(
            draft=initial,
            waiting=TaskWaiting(
                type="ACTIVITY_KIND", field="activity_kind", question_id="q_kind", prompt="请选择活动类型"
            ),
            action_actor="SYSTEM",
            action_name="ask_activity_kind",
        ),
    ).task

    class Structurer:
        async def structure(self, db, *, team_id, kind, user_text):
            return StructureDraftResult(
                kind_confirmed=kind,
                content=initial.content.value or "",
                content_json=initial.content_json,
                customer_name=customer.account_name,
            )

    class Gate:
        async def evaluate(self, db, **kwargs):
            return QualityGateOutcome(True, 83, "完整", None, None, {})

    outcome = await AssistantCoordinator(NoChooser(), structurer=Structurer(), quality_gate=Gate()).handle_task(
        session, task, AssistantInput(kind="submit_field", choice="FOLLOW_UP")
    )
    assert outcome.reply.waiting and outcome.reply.waiting.type == "CONFIRMATION"
    assert outcome.task.authority_json["frozen_activity_command"]["customer_public_id"] == customer.public_id


@pytest.mark.asyncio
async def test_explicit_absence_preserves_user_reason_without_inventing_next_action(db):
    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.task_state import TaskUpdate, apply_task_update

    session, _, _ = db
    task, _, draft = prepared(db)
    draft.next_action = DraftField(status="MISSING")
    draft.content_json["next_action"] = ""
    draft.quality_score = DraftField(status="MISSING")
    task = apply_task_update(
        session,
        task,
        TaskUpdate(
            draft=draft,
            waiting=TaskWaiting(type="FIELD", field="next_action", question_id="q_none", prompt="下一步？"),
            action_actor="SYSTEM",
            action_name="ask_quality_gap",
        ),
    ).task

    class AbsenceStructurer(RecordingStructurer):
        async def structure(self, db, *, team_id, kind, user_text):
            from app.services.assistant.llm_contracts import StructureDraftResult

            return StructureDraftResult(kind_confirmed=kind, content="", content_json={"content": ""})

    result = await AssistantCoordinator(
        NoChooser(), structurer=AbsenceStructurer(), quality_gate=RecordingGate()
    ).handle_task(
        session,
        task,
        AssistantInput(kind="submit_field", choice="EXPLICITLY_NONE", text="等待客户内部审批，批准前不安排新动作"),
    )
    assert result.reply.waiting and result.reply.waiting.type == "CONFIRMATION"
    frozen = result.task.authority_json["frozen_activity_command"]
    assert frozen["content_json"]["next_action"] == ""
    assert frozen["content_json"]["next_action_absence_reason"] == "等待客户内部审批，批准前不安排新动作"
    assert frozen["next_action"] is None
    assert frozen["source_segments"][-1] == "等待客户内部审批，批准前不安排新动作"


@pytest.mark.asyncio
async def test_customer_permission_denial_is_not_relabelled_as_bad_name(db, monkeypatch):
    from app.services.assistant.customer_resolution import CustomerResolution

    session, factory, _ = db
    task, _, _ = prepared(db)
    monkeypatch.setattr(
        "app.services.assistant.coordinator.resolve_customer_candidates_for_assistant",
        lambda *args, **kwargs: CustomerResolution("PERMISSION_DENIED", None, []),
    )
    outcome = await AssistantCoordinator(NoChooser()).handle_task(session, task, AssistantInput(kind="text"))

    assert outcome.task.last_error_code == "PERMISSION_DENIED"
    assert outcome.task.waiting_type is None
    assert "权限" in outcome.reply.message
    assert "准确名称" not in outcome.reply.message
    with factory() as independent:
        assert independent.query(CustomerActivity).count() == 0


@pytest.mark.asyncio
async def test_customer_not_found_requests_correction_without_write(db, monkeypatch):
    from app.services.assistant.customer_resolution import CustomerResolution

    session, _, _ = db
    task, _, _ = prepared(db)
    monkeypatch.setattr(
        "app.services.assistant.coordinator.resolve_customer_candidates_for_assistant",
        lambda *args, **kwargs: CustomerResolution("NOT_FOUND", None, []),
    )
    outcome = await AssistantCoordinator(NoChooser()).handle_task(session, task, AssistantInput(kind="text"))

    assert outcome.task.last_error_code == "NOT_FOUND"
    assert outcome.reply.waiting and outcome.reply.waiting.field == "customer"
    assert "未找到" in outcome.reply.message


@pytest.mark.asyncio
async def test_confirmation_freezes_parseable_user_time_and_writes_it(db):
    from datetime import datetime

    session, factory, _ = db
    task, _, draft = prepared(db)
    draft.next_follow_time = DraftField(status="ACCEPTED", value="2026-10-09 10:30")
    draft.content_json["next_follow_time_text"] = "2026-10-09 10:30"
    task.draft_json = draft.model_dump(mode="json")
    session.commit()

    frozen_outcome = await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
        session,
        task,
        AssistantInput(kind="text"),
    )
    frozen = frozen_outcome.task.authority_json["frozen_activity_command"]
    assert frozen["next_follow_time"] == "2026-10-09T10:30:00"
    assert frozen["next_follow_time_text"] == "2026-10-09 10:30"
    assert frozen_outcome.reply.waiting.confirmation_payload.preview.next_follow_time == frozen["next_follow_time"]
    session.commit()

    await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
        session,
        frozen_outcome.task,
        AssistantInput(kind="confirm", choice="confirm"),
    )
    session.commit()
    with factory() as independent:
        activity = independent.query(CustomerActivity).one()
        assert activity.next_follow_time == datetime(2026, 10, 9, 10, 30)
        assert activity.next_follow_time_source == "USER"


@pytest.mark.asyncio
async def test_unparseable_time_asks_only_for_time_before_freezing(db):
    session, _, _ = db
    task, _, draft = prepared(db)
    draft.next_follow_time = DraftField(status="CANDIDATE", value="月底左右")
    draft.content_json["next_follow_time_text"] = "月底左右"
    task.draft_json = draft.model_dump(mode="json")
    session.commit()

    outcome = await AssistantCoordinator(NoChooser()).handle_task(session, task, AssistantInput(kind="text"))
    assert outcome.reply.waiting and outcome.reply.waiting.type == "FIELD"
    assert outcome.reply.waiting.field == "next_follow_time"
    assert outcome.task.authority_json.get("frozen_activity_command") is None


@pytest.mark.asyncio
async def test_relative_weekday_uses_creation_anchor_not_confirmation_clock(db):
    from datetime import datetime

    session, _, _ = db
    task, _, _ = prepared(db)
    task.created_time = datetime(2026, 9, 28, 14)
    session.commit()
    outcome = await AssistantCoordinator(NoChooser()).handle_task(session, task, AssistantInput(kind="text"))
    frozen = outcome.task.authority_json["frozen_activity_command"]
    assert frozen["next_follow_time_text"] == "周五"
    assert frozen["next_follow_time"] == "2026-10-02T09:00:00"


@pytest.mark.asyncio
async def test_corrected_time_is_rescored_before_new_confirmation(db):
    from app.services.assistant.task_state import TaskUpdate, apply_task_update

    session, _, _ = db
    task, _, draft = prepared(db)
    draft.next_follow_time = DraftField(status="CANDIDATE", value="月底左右")
    draft.content_json["next_follow_time_text"] = "月底左右"
    task = apply_task_update(
        session,
        task,
        TaskUpdate(
            draft=draft,
            action_actor="SYSTEM",
            action_name="prepare_time_gap",
        ),
    ).task
    gap = await AssistantCoordinator(NoChooser()).handle_task(session, task, AssistantInput(kind="text"))
    assert gap.reply.waiting and gap.reply.waiting.field == "next_follow_time"
    result = await AssistantCoordinator(
        NoChooser(), structurer=RecordingStructurer(), quality_gate=RecordingGate()
    ).handle_task(
        session,
        gap.task,
        AssistantInput(kind="submit_field", text="2026-10-09 10:30"),
    )
    assert result.reply.waiting and result.reply.waiting.type == "CONFIRMATION"
    frozen = result.task.authority_json["frozen_activity_command"]
    assert frozen["next_follow_time_text"] == "2026-10-09 10:30"
    assert frozen["next_follow_time"] == "2026-10-09T10:30:00"
    assert frozen["score"] == 78


@pytest.mark.asyncio
async def test_meeting_explicit_none_survives_rescore_freeze_and_real_activity_write(db):
    from datetime import datetime

    from app.services.assistant.action_evidence import SourceSegment, reconcile_action_evidence
    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.llm_contracts import StructureDraftResult
    from app.services.assistant.proposals import offer_next_proposal
    from app.services.assistant.task_state import TaskUpdate, apply_task_update
    from app.services.assistant.turns import accept_submit

    session, factory, _ = db
    task, _, draft = prepared(db)
    original, reason = "我下周三发方案", "客户等待内部预算批准，批准前暂无下一步"
    task.activity_kind = "ONLINE_MEETING"
    draft.source_segments = [original]
    draft.source_records = [
        SourceSegment(segment_id="seg_initial", text=original, recorded_at=datetime(2026, 10, 8, 23, 59))
    ]
    draft.content_json = {
        "meeting_subject": "虚构采购评估",
        "key_minutes": ["预算仍待批准"],
        "next_step_summary": "我发方案",
        "action_items": [{"item_id": "act_initial", "owner": "我", "action": "发方案", "due_date": "下周三"}],
    }
    draft.next_action = DraftField(status="CANDIDATE", value="我发方案")
    draft.next_follow_time = DraftField(status="CANDIDATE", value="下周三")
    reconcile_action_evidence(draft, "ONLINE_MEETING")
    draft.quality_score = DraftField(status="MISSING")
    task = apply_task_update(
        session,
        task,
        TaskUpdate(
            draft=draft,
            waiting=TaskWaiting(type="FIELD", field="next_action", question_id="q_none_chain", prompt="下一步？"),
            action_actor="SYSTEM",
            action_name="ask_next_action",
        ),
    ).task
    session.commit()
    waiting = task.waiting_json
    turn, _ = accept_submit(
        session,
        task=task,
        key="none-chain-answer",
        input_data={"kind": "submit_field", "choice": "EXPLICITLY_NONE", "text": reason},
        action_id=waiting["action_id"],
        expected_version=task.version,
    )
    turn.created_time = datetime(2026, 10, 10, 8)
    session.commit()
    session.refresh(task)

    class StaleStructurer:
        calls = 0

        async def structure(self, db, *, team_id, kind, user_text):
            self.calls += 1
            return StructureDraftResult(
                kind_confirmed=kind,
                content="预算仍待批准",
                next_action="我发方案",
                next_follow_time_text="下周三",
                content_json=draft.content_json,
            )

    structurer, gate = StaleStructurer(), RecordingGate()
    coordinator = AssistantCoordinator(
        NoChooser(), structurer=structurer, quality_gate=gate, writer=RealActivityWriter()
    )
    frozen = await coordinator.handle_task(
        session, task, AssistantInput(kind="submit_field", choice="EXPLICITLY_NONE", text=reason)
    )
    command = frozen.task.authority_json["frozen_activity_command"]
    assert command["content_json"]["action_items"] == []
    assert command["content_json"]["next_action_absence_reason"] == reason
    assert command["next_action"] is None and command["next_follow_time"] is None
    assert command["source_segments"] == [original, reason]
    assert gate.calls[0]["content_json"] == command["content_json"]
    accepted = TaskDraft.model_validate(frozen.task.draft_json)
    assert len(accepted.source_records) == 2
    assert accepted.source_records[-1].turn_id == turn.public_id
    session.commit()
    written = await coordinator.handle_task(session, frozen.task, AssistantInput(kind="confirm", choice="confirm"))
    session.commit()
    finished, _, offered = await offer_next_proposal(session, written.task)
    session.commit()
    assert not offered and finished.status == "COMPLETED"
    assert structurer.calls == 1 and len(gate.calls) == 1
    with factory() as independent:
        activity = independent.query(CustomerActivity).one()
        content = json.loads(activity.content_json)
        assert content["action_items"] == [] and content["next_action_absence_reason"] == reason
        assert content["action_evidence"][0]["state"] == "EXPLICITLY_NONE"
        assert content["action_evidence"][0]["evidence_quote"] == original
        assert activity.next_follow_time is None
        assert activity.source_content == f"{original}\n{reason}"
        assert independent.query(FollowUpTask).count() == 0
        assert independent.query(FollowUpTaskEvent).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deadline,expected,granularity",
    [
        ("下周三下午三点", "2026-10-14T15:00:00", "DATETIME"),
        ("下周三", "2026-10-14T23:59:59", "DATE"),
    ],
)
async def test_follow_up_accepted_date_survives_cross_night_supplement_and_real_task(
    db, monkeypatch, deadline, expected, granularity
):
    from datetime import datetime

    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor
    from app.services.assistant.intake_flow import intake_step
    from app.services.assistant.llm_contracts import StructureDraftResult
    from app.services.assistant.proposals import offer_next_proposal, settle_proposal
    from app.services.assistant.turns import accept_submit

    session, factory, permissions = db
    permissions.append(SimpleNamespace(code="customer:edit:own"))
    session.add_all(
        [
            User(id=2, name="虚构销售", email="assistant-chain@example.invalid"),
            Team(id=1, name="隔离验收团队", code="ACPT01", owner_id=2),
            UserTeam(user_id=2, team_id=1),
        ]
    )
    task, customer, _ = prepared(db)
    task.draft_json = TaskDraft().model_dump(mode="json")
    session.commit()
    original, supplement = f"我{deadline}发方案", "补充：客户确认预算已批准"

    class Structurer:
        async def structure(self, db, *, team_id, kind, user_text):
            return StructureDraftResult(
                kind_confirmed=kind,
                content="虚构采购预算已批准",
                customer_name=customer.account_name,
                next_action="我发方案",
                next_follow_time_text=deadline,
                content_json={
                    "content": "虚构采购预算已批准",
                    "next_action": "我发方案",
                    "next_follow_time_text": deadline,
                },
            )

    structurer, gate = Structurer(), RecordingGate()
    first, _ = accept_submit(
        session,
        task=task,
        key="chain-source",
        input_data={"kind": "text", "text": original},
        action_id=None,
        expected_version=None,
    )
    first.created_time = datetime(2026, 10, 8, 23, 59)
    session.commit()
    session.refresh(task)
    task, _, _, failed = await intake_step(session, task, original, structurer, gate)
    assert not failed
    first.status, task.active_turn_id = "SUCCEEDED", None
    session.commit()
    second, _ = accept_submit(
        session,
        task=task,
        key="chain-supplement",
        input_data={"kind": "text", "text": supplement},
        action_id=None,
        expected_version=None,
    )
    second.created_time = datetime(2026, 10, 10, 8)
    session.commit()
    session.refresh(task)
    monkeypatch.setattr("app.utils.time.business_now", lambda: datetime(2026, 10, 10, 8))
    task, _, _, failed = await intake_step(session, task, supplement, structurer, gate)
    assert not failed
    second.status, task.active_turn_id = "SUCCEEDED", None
    session.commit()
    coordinator = AssistantCoordinator(NoChooser(), writer=RealActivityWriter())
    frozen = await coordinator.handle_task(session, task, AssistantInput(kind="text"))
    command = frozen.task.authority_json["frozen_activity_command"]
    assert command["source_segments"] == [original, supplement]
    assert command["score"] == 78
    preview = frozen.reply.waiting.confirmation_payload.preview.model_dump()
    assert preview["next_follow_time_granularity"] == granularity
    session.commit()
    written = await coordinator.handle_task(session, frozen.task, AssistantInput(kind="confirm", choice="confirm"))
    session.commit()
    offered, _, active = await offer_next_proposal(session, written.task)
    assert active and offered.waiting_field == "proposal:follow_up_task_create"
    proposal = offered.waiting_json["payload"]["confirmation_payload"]["candidate"]
    assert proposal["due_date_granularity"] == granularity
    settled, _, _ = await settle_proposal(session, offered, accepted=True, executor=RealCRMProposalExecutor())
    session.commit()
    finished, _, active = await offer_next_proposal(session, settled)
    session.commit()
    assert not active and finished.status == "COMPLETED"
    assert len(gate.calls) == 2
    with factory() as independent:
        activity = independent.query(CustomerActivity).one()
        task_row = independent.query(FollowUpTask).one()
        assert independent.query(FollowUpTaskEvent).one().task_id == task_row.id
        assert task_row.title == "发方案" and task_row.due_at == datetime.fromisoformat(expected)
        assert (task_row.due_at_text, task_row.due_at_granularity, task_row.due_at_timezone) == (
            deadline,
            granularity,
            "Asia/Shanghai",
        )
        assert task_row.source_activity_id == activity.id
        assert task_row.evidence_json["anchor_at"] == "2026-10-08T23:59:00"
        assert task_row.evidence_json["evidence_quote"] == original
        assert task_row.evidence_json["parser_version"] == "assistant-date-v1"
        assert activity.source_content == f"{original}\n{supplement}"
