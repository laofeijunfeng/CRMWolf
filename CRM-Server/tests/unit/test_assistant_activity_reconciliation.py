"""CRM-171: fail-closed UNKNOWN_COMMIT_RESULT and deterministic read-only activity reconciliation."""
# ruff: noqa: RUF001

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.exc import DataError, OperationalError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
from app.models.assistant_follow_up_projection_job import AssistantFollowUpProjectionJob
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent, FollowUpTaskProjectionTrigger
from app.models.team import Team, UserTeam
from app.models.user import User
from app.models.user_role import UserRole
from app.services.assistant import conversation as conversation_module
from app.services.assistant.confirmation import (
    build_confirmation_waiting_from_command,
    reconcile_unknown_activity,
)
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.conversation import ConversationService
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.failure_contract import AssistantStageFailure
from app.services.assistant.real_writer import RealActivityWriter
from app.services.assistant.task_state import TaskStateConflictError
from app.services.assistant.turns import AssistantActivityCommitUnknownError, accept_submit, execute_turn


@compiles(BigInteger, "sqlite")
def _bigint_as_int(element, compiler, **kwargs):
    return "INTEGER"


class NoChooser:
    async def choose(self, task):
        raise AssertionError("chooser must not run during activity reconciliation tests")


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_indexes(conn, cursor, statement, parameters, context, executemany):
        return ("SELECT 1", ()) if statement.startswith("CREATE INDEX") else (statement, parameters)

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Team.__table__,
            UserTeam.__table__,
            Role.__table__,
            Permission.__table__,
            RolePermission.__table__,
            UserRole.__table__,
            Customer.__table__,
            CustomerProduct.__table__,
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerLegacySourceProgress.__table__,
            CustomerActivityDeletionTombstone.__table__,
            AssistantTask.__table__,
            AssistantConversation.__table__,
            AssistantConversationEntry.__table__,
            AssistantAction.__table__,
            AssistantRequest.__table__,
            AssistantTurn.__table__,
            AssistantTurnEvent.__table__,
            FollowUpTask.__table__,
            AssistantFollowUpProjectionJob.__table__,
            FollowUpTaskEvent.__table__,
        ],
    )
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service.infer_for_customer", lambda *args: None)
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service.record_event", lambda *args, **kw: None)
    monkeypatch.setattr(
        "app.crud.operation_log.operation_log_crud.create",
        lambda db, obj_in, team_id=None, commit=True: None,
    )
    monkeypatch.setattr(
        "app.services.customer_vector_document_service.customer_vector_document_service.upsert_customer_activity",
        lambda db, activity, commit=True: None,
    )
    permissions = [SimpleNamespace(code="customer:activity:create")]
    monkeypatch.setattr(
        "app.services.assistant.customer_resolution.permission_crud.get_user_permissions",
        lambda *args: permissions,
    )
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda *args: permissions,
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    try:
        yield SimpleNamespace(db=session, factory=factory, client=client, permissions=permissions)
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def _seed_users_and_customer(db) -> tuple[User, User, Customer]:
    owner = User(id=2, email="owner@example.com", name="Owner", status="active")
    operator = User(id=9, email="op@example.com", name="Operator", status="active")
    team = Team(id=1, name="Alpha", code="ALPHA", owner_id=owner.id)
    db.add_all(
        [
            team,
            owner,
            operator,
            UserTeam(user_id=owner.id, team_id=1, current_team=True),
            UserTeam(user_id=operator.id, team_id=1, current_team=True),
        ]
    )
    customer = Customer(
        team_id=1,
        account_name="睿狐科技",
        public_id="cus_reconcile",
        city="上海",
        creator_id=str(owner.id),
        owner_id=str(owner.id),
    )
    db.add(customer)
    db.commit()
    return owner, operator, customer


def _auth_headers(user_id: int, team_id: int = 1) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}", "X-Team-Id": str(team_id)}


async def _freeze_task(db, customer: Customer) -> tuple[AssistantTask, dict[str, object]]:
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
        channel_kind="PHONE_FOLLOW_UP",
        channel_status="selected",
        channel_source="user",
        customer=DraftField(status="CANDIDATE", value=customer.account_name),
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
    db.add(task)
    db.commit()
    outcome = await AssistantCoordinator(NoChooser(), writer=RealActivityWriter()).handle_task(
        db, task, AssistantInput(kind="text")
    )
    db.commit()
    frozen = outcome.task.authority_json["frozen_activity_command"]
    assert isinstance(frozen, dict)
    return outcome.task, frozen


def _mark_task_unknown(db, task: AssistantTask, frozen: dict[str, object]) -> AssistantAction:
    task.waiting_type = None
    task.waiting_field = None
    task.waiting_json = None
    task.last_error_code = "UNKNOWN_COMMIT_RESULT"
    task.version += 1
    action = AssistantAction(
        team_id=task.team_id,
        task_id=task.id,
        actor="SYSTEM",
        action="activity_commit_unknown",
        input_json={"submission_id": frozen["submission_id"]},
        result_json={
            "retryable": False,
            "code": "UNKNOWN_COMMIT_RESULT",
            "status": "UNKNOWN",
            "submission_id": frozen["submission_id"],
        },
        event_type="error",
    )
    db.add(action)
    db.commit()
    db.refresh(task)
    db.refresh(action)
    return action


def _seed_committed_activity(
    db,
    customer: Customer,
    frozen: dict[str, object],
    *,
    submission_source: str = "ASSISTANT_2",
    fingerprint: str | None = None,
    customer_id: int | None = None,
) -> CustomerActivity:
    activity = CustomerActivity(
        team_id=1,
        customer_id=customer.id if customer_id is None else customer_id,
        activity_kind=str(frozen["activity_kind"]),
        title="睿狐科技电话沟通",
        summary="POC已通过",
        content_json=json.dumps(frozen["content_json"], ensure_ascii=False),
        source_content=str(frozen["source_content"]),
        submission_source=submission_source,
        submission_id=str(frozen["submission_id"]),
        submission_fingerprint=str(frozen["fingerprint"]) if fingerprint is None else fingerprint,
        creator_id="2",
        owner_id="2",
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@pytest.mark.asyncio
async def test_real_writer_pre_commit_data_error_fails_closed_without_unknown(env, monkeypatch):
    _, _, customer = _seed_users_and_customer(env.db)
    task, frozen = await _freeze_task(env.db, customer)

    def _raise_data_error(*args, **kwargs):
        raise DataError("INSERT", {}, Exception("value too long"))

    monkeypatch.setattr(
        "app.services.customer_activity_write_service.customer_activity_write_service.create_final_from_assistant2",
        _raise_data_error,
    )

    with pytest.raises(AssistantStageFailure) as exc_info:
        await RealActivityWriter().write_activity(env.db, task=task, command=frozen)

    assert exc_info.value.retryable is False
    assert exc_info.value.stage == "write"
    assert env.db.query(CustomerActivity).count() == 0


@pytest.mark.asyncio
async def test_real_writer_pre_commit_transient_error_is_retryable_when_not_persisted(env, monkeypatch):
    _, _, customer = _seed_users_and_customer(env.db)
    task, frozen = await _freeze_task(env.db, customer)

    def _raise_operational(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("database locked"))

    monkeypatch.setattr(
        "app.services.customer_activity_write_service.customer_activity_write_service.create_final_from_assistant2",
        _raise_operational,
    )

    with pytest.raises(AssistantStageFailure) as exc_info:
        await RealActivityWriter().write_activity(env.db, task=task, command=frozen)

    assert exc_info.value.retryable is True
    assert exc_info.value.stage == "write"


@pytest.mark.asyncio
async def test_real_writer_pre_commit_error_after_row_persisted_recovers_or_marks_unknown(env, monkeypatch):
    _, _, customer = _seed_users_and_customer(env.db)
    task, frozen = await _freeze_task(env.db, customer)
    persisted = _seed_committed_activity(env.db, customer, frozen)

    def _raise_after_commit(*args, **kwargs):
        raise OperationalError("COMMIT", {}, Exception("connection reset"))

    monkeypatch.setattr(
        "app.services.customer_activity_write_service.customer_activity_write_service.create_final_from_assistant2",
        _raise_after_commit,
    )

    result = await RealActivityWriter().write_activity(env.db, task=task, command=frozen)
    assert result.success is True
    assert result.activity_public_id == str(persisted.id)

    # Corrupt fingerprint on persisted row -> must fail closed as unknown
    persisted.submission_fingerprint = "0" * 64
    env.db.commit()
    with pytest.raises(AssistantActivityCommitUnknownError):
        await RealActivityWriter().write_activity(env.db, task=task, command=frozen)


@pytest.mark.asyncio
async def test_turn_commit_failure_after_confirm_closes_as_unknown_commit_result(env, monkeypatch):
    _, _, customer = _seed_users_and_customer(env.db)
    task, frozen = await _freeze_task(env.db, customer)
    waiting_action_id = task.waiting_json["action_id"]
    turn, created = accept_submit(
        env.db,
        task=task,
        key="req-confirm-commit-fail",
        input_data={"kind": "confirm", "choice": "confirm"},
        action_id=waiting_action_id,
        expected_version=task.version,
    )
    assert created is True

    commit_state: dict[str, object] = {"target_db": None, "failed": False}

    class StagedWriter:
        async def write_activity(self, db, *, task, command):
            from app.services.assistant.confirmation import WriteActivityResult

            commit_state["target_db"] = db
            return WriteActivityResult(
                success=True,
                activity_public_id="999",
                error_code=None,
                customer_id=customer.id,
                follow_up_projection=None,
            )

    monkeypatch.setattr(
        "app.api.assistant._coordinator",
        AssistantCoordinator(NoChooser(), writer=StagedWriter()),
    )

    original_commit = env.db.__class__.commit

    def _fail_turn_commit(self):
        if self is commit_state["target_db"] and not commit_state["failed"]:
            commit_state["failed"] = True
            raise OperationalError("COMMIT", {}, Exception("lost connection on commit"))
        return original_commit(self)

    monkeypatch.setattr(env.db.__class__, "commit", _fail_turn_commit)

    await execute_turn(turn.id, factory=env.factory)
    with env.factory() as verify_db:
        reloaded_task = verify_db.get(AssistantTask, task.id)
        reloaded_turn = verify_db.get(AssistantTurn, turn.id)
        unknown_action = (
            verify_db.query(AssistantAction)
            .filter_by(task_id=task.id, action="activity_commit_unknown")
            .one()
        )
        assert reloaded_task is not None
        assert reloaded_task.last_error_code == "UNKNOWN_COMMIT_RESULT"
        assert reloaded_task.waiting_type is None
        assert reloaded_task.active_turn_id is None
        assert reloaded_turn is not None
        assert reloaded_turn.status == "FAILED"
        assert reloaded_turn.last_error_code == "UNKNOWN_COMMIT_RESULT"
        assert unknown_action.result_json["status"] == "UNKNOWN"
        assert unknown_action.result_json["submission_id"] == frozen["submission_id"]


@pytest.mark.asyncio
async def test_reconcile_written_settles_receipt_creates_followup_and_entry_without_writing(env, monkeypatch):
    _, _, customer = _seed_users_and_customer(env.db)
    service = ConversationService()
    conv_view = service.open(env.db, team_id=1, user_id=2)
    task, frozen = await _freeze_task(env.db, customer)
    conv = env.db.query(AssistantConversation).filter_by(public_id=conv_view.public_id).one()
    conv.focused_task_public_id = task.public_id
    env.db.commit()

    unknown_action = _mark_task_unknown(env.db, task, frozen)
    activity = _seed_committed_activity(env.db, customer, frozen)
    fut = FollowUpTask(
        team_id=1,
        customer_id=customer.id,
        owner_id="2",
        creator_id="2",
        source_type="CUSTOMER_ACTIVITY",
        source_activity_id=activity.id,
        title="发验收报告",
        status="OPEN",
        source_key=f"activity:{activity.id}",
        task_hash="a" * 64,
        due_at=datetime(2026, 12, 1, 10, 0, 0),
    )
    env.db.add(fut)
    env.db.flush()
    proj_job = AssistantFollowUpProjectionJob(
        team_id=1,
        activity_id=activity.id,
        activity_revision=1,
        trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
        status="COMPLETED",
        result_json={"created_task_ids": [fut.id], "projection_run_id": 42},
    )
    env.db.add(proj_job)
    env.db.commit()

    def _forbid_write(*args, **kwargs):
        raise AssertionError("reconciliation MUST NOT execute target-service writes")

    monkeypatch.setattr(
        "app.services.customer_activity_write_service.customer_activity_write_service.create_final_from_assistant2",
        _forbid_write,
    )

    result = reconcile_unknown_activity(env.db, task, actor_type="USER", actor_id=2, reason="user_refresh")
    env.db.commit()

    assert result.outcome == "WRITTEN"
    assert result.followup_turn_id is not None
    assert result.followup_turn_public_id is not None
    assert result.task.last_error_code is None
    assert result.task.waiting_type is None
    assert result.task.committed_json == [
        {
            "kind": "customer_activity",
            "public_id": str(activity.id),
            "customer_id": customer.id,
            "customer_public_id": customer.public_id,
        }
    ]
    assert result.task.authority_json["confirmation_receipt"] == frozen["submission_id"]
    assert result.task.authority_json["frozen_activity_command"]["execution_status"] == "SUCCEEDED"

    env.db.refresh(unknown_action)
    assert unknown_action.result_json["status"] == "RECONCILED"
    assert unknown_action.result_json["activity_public_id"] == str(activity.id)

    receipt_actions = (
        env.db.query(AssistantAction)
        .filter_by(task_id=task.id, action="show_write_receipt")
        .all()
    )
    assert len(receipt_actions) == 1
    assert receipt_actions[0].result_json["label"] == "活动已写入，跟进任务已生成"
    assert receipt_actions[0].result_json["follow_up_projection_task_public_id"] == fut.public_id

    entries = [
        row
        for row in env.db.query(AssistantConversationEntry).filter_by(conversation_id=conv.id).all()
        if (row.command_json or {}).get("operation") == "reconcile_activity"
    ]
    assert len(entries) == 1
    assert entries[0].user_text == ""
    assert entries[0].turn_public_id == result.followup_turn_public_id

    replayed = service.read(env.db, team_id=1, user_id=2)
    assert all(msg.text != "" for msg in replayed.messages if msg.role == "user")
    written_msgs = [msg for msg in replayed.messages if msg.outcome == "activity_written"]
    assert len(written_msgs) == 1
    assert written_msgs[0].projection is not None
    assert written_msgs[0].projection.activity_public_id == str(activity.id)


@pytest.mark.asyncio
async def test_reconcile_not_written_restores_confirmation_waiting_and_clears_error(env):
    _, _, customer = _seed_users_and_customer(env.db)
    service = ConversationService()
    conv_view = service.open(env.db, team_id=1, user_id=2)
    task, frozen = await _freeze_task(env.db, customer)
    conv = env.db.query(AssistantConversation).filter_by(public_id=conv_view.public_id).one()
    conv.focused_task_public_id = task.public_id
    env.db.commit()

    unknown_action = _mark_task_unknown(env.db, task, frozen)

    result = reconcile_unknown_activity(env.db, task, actor_type="USER", actor_id=2, reason="user_refresh")
    env.db.commit()

    assert result.outcome == "NOT_WRITTEN"
    assert result.followup_turn_id is None
    assert result.task.last_error_code is None
    assert result.task.waiting_type == "CONFIRMATION"
    assert result.task.waiting_field == "activity_write"
    assert result.task.waiting_json["payload"]["fingerprint"] == frozen["fingerprint"]

    env.db.refresh(unknown_action)
    assert unknown_action.result_json["status"] == "RECONCILED_NOT_WRITTEN"

    replayed = service.read(env.db, team_id=1, user_id=2)
    assert replayed.focused_task is not None
    assert replayed.focused_task.reconciliation_required is False
    assert replayed.focused_task.waiting is not None
    assert replayed.focused_task.waiting.type == "CONFIRMATION"
    assert any(msg.id.startswith("current:") and msg.task and msg.task.waiting for msg in replayed.messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["fingerprint", "source", "customer"])
async def test_reconcile_still_unknown_on_identity_mismatch(env, mismatch):
    _, _, customer = _seed_users_and_customer(env.db)
    other_customer = Customer(
        team_id=1,
        account_name="其他客户",
        public_id="cus_other",
        city="北京",
        creator_id="2",
        owner_id="2",
    )
    env.db.add(other_customer)
    env.db.commit()

    task, frozen = await _freeze_task(env.db, customer)
    unknown_action = _mark_task_unknown(env.db, task, frozen)
    _seed_committed_activity(
        env.db,
        customer,
        frozen,
        submission_source="FORM" if mismatch == "source" else "ASSISTANT_2",
        fingerprint="f" * 64 if mismatch == "fingerprint" else None,
        customer_id=other_customer.id if mismatch == "customer" else customer.id,
    )

    result = reconcile_unknown_activity(env.db, task, actor_type="USER", actor_id=2, reason="user_refresh")
    assert result.outcome == "STILL_UNKNOWN"
    assert result.task.last_error_code == "UNKNOWN_COMMIT_RESULT"
    assert result.task.waiting_type is None
    env.db.refresh(unknown_action)
    assert unknown_action.result_json["status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_reconcile_endpoint_written_noop_and_conflict_handling(env, monkeypatch):
    owner, operator, customer = _seed_users_and_customer(env.db)
    task, frozen = await _freeze_task(env.db, customer)
    _mark_task_unknown(env.db, task, frozen)
    _seed_committed_activity(env.db, customer, frozen)

    scheduled: list[int] = []
    monkeypatch.setattr("app.api.assistant.schedule_turn", lambda turn_id, **kw: scheduled.append(turn_id))

    # Non-owner gets 404
    foreign = env.client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/reconcile",
        headers=_auth_headers(operator.id),
    )
    assert foreign.status_code == 404

    # Owner reconciles WRITTEN
    first = env.client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/reconcile",
        headers=_auth_headers(owner.id),
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["outcome"] == "WRITTEN"
    assert body["followup_turn_id"] is not None
    assert body["task"]["reconciliation_required"] is False
    assert len(scheduled) == 1

    # Second reconcile is NOOP
    second = env.client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/reconcile",
        headers=_auth_headers(owner.id),
    )
    assert second.status_code == 200
    assert second.json()["outcome"] == "NOOP"

    # Concurrent TaskStateConflictError when task is already reconciled -> NOOP
    monkeypatch.setattr(
        "app.services.assistant.confirmation.reconcile_unknown_activity",
        lambda *a, **kw: (_ for _ in ()).throw(TaskStateConflictError("version mismatch")),
    )
    concurrent_noop = env.client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/reconcile",
        headers=_auth_headers(owner.id),
    )
    assert concurrent_noop.status_code == 200
    assert concurrent_noop.json()["outcome"] == "NOOP"

    # Concurrent TaskStateConflictError while task is STILL unknown -> 409 STATE_CONFLICT
    task.last_error_code = "UNKNOWN_COMMIT_RESULT"
    task.active_turn_id = None
    env.db.commit()
    conflict = env.client.post(
        f"/api/v1/assistant/tasks/{task.public_id}/reconcile",
        headers=_auth_headers(owner.id),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "STATE_CONFLICT"


@pytest.mark.asyncio
async def test_conversation_open_auto_reconciles_written_and_not_written(env, monkeypatch):
    _, _, customer = _seed_users_and_customer(env.db)
    scheduled: list[int] = []
    monkeypatch.setattr(conversation_module, "schedule_turn", lambda turn_id, **kw: scheduled.append(turn_id))
    service = ConversationService()

    # Case 1: NOT_WRITTEN restores confirmation card on open
    initial = service.open(env.db, team_id=1, user_id=2)
    task1, frozen1 = await _freeze_task(env.db, customer)
    conv = env.db.query(AssistantConversation).filter_by(public_id=initial.public_id).one()
    conv.focused_task_public_id = task1.public_id
    env.db.commit()
    _mark_task_unknown(env.db, task1, frozen1)

    view1 = service.open(env.db, team_id=1, user_id=2)
    assert view1.focused_task is not None
    assert view1.focused_task.reconciliation_required is False
    assert view1.focused_task.waiting is not None
    assert view1.focused_task.waiting.type == "CONFIRMATION"
    assert scheduled == []

    # Case 2: WRITTEN settles receipt and schedules follow-up turn on open
    _mark_task_unknown(env.db, task1, frozen1)
    _seed_committed_activity(env.db, customer, frozen1)
    view2 = service.open(env.db, team_id=1, user_id=2)
    assert view2.focused_task is not None
    assert view2.focused_task.reconciliation_required is False
    assert len(scheduled) == 1
    assert all(msg.text != "" for msg in view2.messages if msg.role == "user")


@pytest.mark.asyncio
async def test_unknown_commands_lists_and_adjudicates_activity_commit_unknown(env, monkeypatch):
    owner, operator, customer = _seed_users_and_customer(env.db)
    task, frozen = await _freeze_task(env.db, customer)
    unknown_action = _mark_task_unknown(env.db, task, frozen)

    scheduled: list[int] = []
    monkeypatch.setattr("app.api.assistant.schedule_turn", lambda turn_id, **kw: scheduled.append(turn_id))

    # Owner sees own unresolved activity_commit_unknown via GET /unknown-commands
    owner_list = env.client.get("/api/v1/assistant/unknown-commands", headers=_auth_headers(owner.id))
    assert owner_list.status_code == 200
    items = owner_list.json()
    assert len(items) == 1
    assert items[0]["kind"] == "customer_activity"
    assert items[0]["status"] == "UNKNOWN"
    assert items[0]["action_public_id"] == unknown_action.public_id
    assert items[0]["submission_id"] == frozen["submission_id"]

    # Non-operator cannot adjudicate
    forbidden = env.client.post(
        f"/api/v1/assistant/unknown-commands/{unknown_action.public_id}/adjudicate",
        headers=_auth_headers(owner.id),
        json={"decision": "REJECTED", "reason": "未写入"},
    )
    assert forbidden.status_code == 403

    # Grant operator permission
    env.permissions.append(SimpleNamespace(code="assistant:commands:reconcile:team"))

    # Operator sees team-wide unresolved activity_commit_unknown
    op_list = env.client.get("/api/v1/assistant/unknown-commands", headers=_auth_headers(operator.id))
    assert op_list.status_code == 200
    assert len(op_list.json()) == 1

    # Adjudicating SUCCEEDED when activity is NOT written -> 409
    mismatch_succ = env.client.post(
        f"/api/v1/assistant/unknown-commands/{unknown_action.public_id}/adjudicate",
        headers=_auth_headers(operator.id),
        json={"decision": "SUCCEEDED", "reason": "误判已写入"},
    )
    assert mismatch_succ.status_code == 409

    # Adjudicating REJECTED when activity is NOT written -> 200 and restores confirmation
    rejected = env.client.post(
        f"/api/v1/assistant/unknown-commands/{unknown_action.public_id}/adjudicate",
        headers=_auth_headers(operator.id),
        json={"decision": "REJECTED", "reason": "核对无记录"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    env.db.refresh(task)
    assert task.last_error_code is None
    assert task.waiting_type == "CONFIRMATION"

    # Re-adjudicating already-resolved action -> 409
    repeat_reject = env.client.post(
        f"/api/v1/assistant/unknown-commands/{unknown_action.public_id}/adjudicate",
        headers=_auth_headers(operator.id),
        json={"decision": "REJECTED", "reason": "重复核对"},
    )
    assert repeat_reject.status_code == 409

    # Now test SUCCEEDED path with a new unknown action + committed activity
    task2, frozen2 = await _freeze_task(env.db, customer)
    unknown_action2 = _mark_task_unknown(env.db, task2, frozen2)
    _seed_committed_activity(env.db, customer, frozen2)

    # Adjudicating REJECTED when activity IS written -> 409
    mismatch_rej = env.client.post(
        f"/api/v1/assistant/unknown-commands/{unknown_action2.public_id}/adjudicate",
        headers=_auth_headers(operator.id),
        json={"decision": "REJECTED", "reason": "误判未写入"},
    )
    assert mismatch_rej.status_code == 409

    # Adjudicating SUCCEEDED when activity IS written -> 200, settles receipt, schedules followup
    succeeded = env.client.post(
        f"/api/v1/assistant/unknown-commands/{unknown_action2.public_id}/adjudicate",
        headers=_auth_headers(operator.id),
        json={"decision": "SUCCEEDED", "reason": "核对目标活动存在"},
    )
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["status"] == "SUCCEEDED"
    assert len(scheduled) == 1

    # No open unknown commands left
    final_list = env.client.get("/api/v1/assistant/unknown-commands", headers=_auth_headers(operator.id))
    assert final_list.status_code == 200
    assert final_list.json() == []


def test_build_confirmation_waiting_from_command_restores_expected_preview():
    task = AssistantTask(
        id=1,
        public_id="t_confirm",
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        version=3,
        goal="g",
    )
    command = {
        "customer_name": "睿狐科技",
        "customer_public_id": "cus_1",
        "channel_kind": "PHONE_FOLLOW_UP",
        "content_json": {"content": "沟通完成"},
        "source_content": "原文",
        "score": 88,
        "score_reason": "信息完整",
        "fingerprint": "a" * 64,
    }
    waiting = build_confirmation_waiting_from_command(task, command)
    assert waiting.type == "CONFIRMATION"
    assert waiting.field == "activity_write"
    assert waiting.fingerprint == "a" * 64
    assert waiting.confirmation_payload is not None
    assert waiting.confirmation_payload.preview.customer_name == "睿狐科技"
