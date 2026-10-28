"""Durable assistant turn acceptance, lease claim, execution and event replay."""
# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from contextlib import suppress
from contextvars import ContextVar
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.assistant import AssistantTask, AssistantTaskStatus
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.services.assistant.coordinator import AssistantInput
from app.services.assistant.events import ProgressReporter, TurnStage
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.task_state import InvalidTaskTransitionError, TaskStateConflictError, load_waiting
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
_active: set[asyncio.Task[None]] = set()
_workers: dict[int, tuple[int, asyncio.Task[None]]] = {}
_execution_lease: ContextVar[tuple[int, str, int] | None] = ContextVar("assistant_execution_lease", default=None)


class AssistantRequestConflict(ValueError):
    pass


class AssistantStateConflict(ValueError):
    pass


class AssistantUnknownCommitResultError(RuntimeError):
    """TRD §8 UNKNOWN_COMMIT_RESULT: CRM command outcome cannot be proven."""

    error_code = "UNKNOWN_COMMIT_RESULT"


class AssistantConfigurationError(RuntimeError):
    """TRD §8 CONFIGURATION_ERROR: a required runtime seam is absent."""

    error_code = "CONFIGURATION_ERROR"


def classify_turn_error(exc: Exception) -> str:
    """Map one exception to the TRD §8 closed error-code taxonomy."""

    if isinstance(exc, AssistantLLMError):
        return "AI_UNAVAILABLE"
    if isinstance(exc, (AssistantStateConflict, TaskStateConflictError, InvalidTaskTransitionError)):
        return "STATE_CONFLICT"
    if isinstance(exc, AssistantUnknownCommitResultError):
        return "UNKNOWN_COMMIT_RESULT"
    if isinstance(exc, AssistantConfigurationError):
        return "CONFIGURATION_ERROR"
    return "RETRYABLE_DEPENDENCY_FAILURE"


def fingerprint(value: dict[str, object]) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _request(db: Session, *, team_id: int, user_id: int, key: str) -> AssistantRequest | None:
    return db.query(AssistantRequest).filter_by(team_id=team_id, user_id=user_id, client_request_id=key).one_or_none()


def accept_create(db: Session, *, team_id: int, user_id: int, key: str, goal: str) -> AssistantTask:
    from app.services.assistant.contracts import TaskDraft

    goal = goal.strip()
    digest = fingerprint({"operation": "create", "goal": goal})
    previous = _request(db, team_id=team_id, user_id=user_id, key=key)
    if previous:
        if previous.input_fingerprint != digest or previous.turn_id is not None:
            raise AssistantRequestConflict("请求标识已被其他内容占用")
        return db.get(AssistantTask, previous.task_id)
    task = AssistantTask(
        team_id=team_id,
        user_id=user_id,
        status=AssistantTaskStatus.ACTIVE,
        goal=goal,
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={},
        committed_json=[],
    )
    db.add(task)
    db.flush()
    db.add(
        AssistantRequest(
            team_id=team_id,
            user_id=user_id,
            client_request_id=key,
            input_fingerprint=digest,
            task_id=task.id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = _request(db, team_id=team_id, user_id=user_id, key=key)
        if previous is None or previous.input_fingerprint != digest or previous.turn_id is not None:
            raise AssistantRequestConflict("请求标识已被其他内容占用") from None
        return db.get(AssistantTask, previous.task_id)
    db.refresh(task)
    return task


def accept_submit(
    db: Session,
    *,
    task: AssistantTask,
    key: str,
    input_data: dict[str, object],
    action_id: str | None,
    expected_version: int | None,
) -> tuple[AssistantTurn, bool]:
    normalized = {
        "operation": "submit",
        "task_id": task.public_id,
        **input_data,
        "action_id": action_id,
        "expected_version": expected_version,
    }
    digest = fingerprint(normalized)
    previous = _request(db, team_id=task.team_id, user_id=task.user_id, key=key)
    if previous is not None:
        if previous.input_fingerprint != digest or previous.turn_id is None or previous.task_id != task.id:
            raise AssistantRequestConflict("请求标识已被其他内容占用")
        return db.get(AssistantTurn, previous.turn_id), False
    if task.status != AssistantTaskStatus.ACTIVE:
        raise AssistantStateConflict("任务已结束，无法继续提交")
    waiting = load_waiting(task)
    kind = input_data["kind"]
    choice = input_data.get("choice")
    text = input_data.get("text")
    if waiting is not None and kind != "cancel":
        if not waiting.action_id or action_id != waiting.action_id or expected_version != waiting.expected_version:
            raise AssistantStateConflict("等待动作已过期，请读取最新任务")
        allowed = {
            "ACTIVITY_KIND": "submit_field",
            "OBJECT_SELECTION": "submit_field",
            "FIELD": "submit_field",
            "CONFIRMATION": "confirm",
        }
        if kind != allowed[waiting.type]:
            raise AssistantStateConflict("当前输入不符合等待动作")
        if waiting.type == "ACTIVITY_KIND":
            options = {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}
            if (
                choice not in options
                or (waiting.candidates and choice not in {candidate.get("id") for candidate in waiting.candidates})
                or text is not None
            ):
                raise AssistantStateConflict("请选择当前签发的活动类型")
        elif waiting.type == "OBJECT_SELECTION":
            if (
                not isinstance(choice, str)
                or choice not in {candidate.get("id") for candidate in waiting.candidates}
                or text is not None
            ):
                raise AssistantStateConflict("请选择当前签发的客户")
        elif waiting.type == "FIELD":
            if choice == "EXPLICITLY_NONE":
                if waiting.field != "next_action" or not isinstance(text, str) or not text.strip():
                    raise AssistantStateConflict("请说明这条没有下一步行动的原因")
            elif choice is not None or not isinstance(text, str) or not text.strip():
                raise AssistantStateConflict("请回复当前字段内容")
        elif choice not in {"confirm", "reject"} or text is not None:
            raise AssistantStateConflict("请选择确认或拒绝当前动作")
    elif waiting is None and (
        action_id is not None or expected_version is not None or kind in {"confirm", "submit_field"}
    ):
        raise AssistantStateConflict("没有待回复的动作")
    if kind == "cancel" and (choice is not None or text is not None):
        raise AssistantStateConflict("取消动作不接受其他回复")
    if task.active_turn_id is not None:
        raise AssistantStateConflict("前一轮尚在处理，请稍后补读")
    request = AssistantRequest(
        team_id=task.team_id,
        user_id=task.user_id,
        client_request_id=key,
        input_fingerprint=digest,
        task_id=task.id,
    )
    db.add(request)
    turn: AssistantTurn | None = None
    try:
        db.flush()
        turn = AssistantTurn(
            team_id=task.team_id,
            user_id=task.user_id,
            task_id=task.id,
            request_id=request.id,
            input_json=normalized,
            status="PENDING",
        )
        db.add(turn)
        db.flush()
        locked = db.execute(
            update(AssistantTask)
            .where(
                AssistantTask.id == task.id,
                AssistantTask.team_id == task.team_id,
                AssistantTask.status == AssistantTaskStatus.ACTIVE,
                AssistantTask.version == task.version,
                AssistantTask.active_turn_id.is_(None),
            )
            .values(active_turn_id=turn.id)
            .execution_options(synchronize_session=False)
        )
        if locked.rowcount != 1:
            db.rollback()
            raise AssistantStateConflict("任务状态已变化，请读取最新任务")
        request.turn_id = turn.id
        add_event(db, turn, "accepted", {"turn_id": turn.public_id})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        previous = _request(db, team_id=task.team_id, user_id=task.user_id, key=key)
        if previous is None:
            # The constraint that failed was not the request key; surface it.
            raise exc
        if previous.input_fingerprint != digest or previous.turn_id is None or previous.task_id != task.id:
            raise AssistantRequestConflict("请求标识已被其他内容占用") from None
        return db.get(AssistantTurn, previous.turn_id), False
    return turn, True


def add_event(db: Session, turn: AssistantTurn, event: str, data: dict[str, object]) -> None:
    seq = turn.next_seq
    db.add(AssistantTurnEvent(turn_id=turn.id, seq=seq, event=event, data_json={**data, "seq": seq}))
    turn.next_seq = seq + 1


def claim(db: Session, *, turn_id: int, owner: str) -> int | None:
    now = business_now()
    changed = db.execute(
        update(AssistantTurn)
        .where(
            AssistantTurn.id == turn_id,
            or_(
                AssistantTurn.status == "PENDING",
                (AssistantTurn.status == "RUNNING") & (AssistantTurn.lease_expires_at < now),
            ),
        )
        .values(
            status="RUNNING",
            lease_owner=owner,
            lease_version=AssistantTurn.lease_version + 1,
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
            attempts=AssistantTurn.attempts + 1,
            last_modified_time=now,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    turn = db.get(AssistantTurn, turn_id)
    return turn.lease_version if turn is not None else None


def task_has_customer_activity(task: AssistantTask) -> bool:
    """A committed activity receipt means this task already wrote CRM state."""

    return any(
        isinstance(item, dict) and item.get("kind") == "customer_activity" for item in (task.committed_json or [])
    )


def live_worker(turn_id: int, lease_version: int) -> bool:
    worker = _workers.get(turn_id)
    return worker is not None and worker[0] == lease_version and not worker[1].done()


def latest_error_retryable(db: Session, turn: AssistantTurn) -> bool:
    event = (
        db.query(AssistantTurnEvent)
        .filter_by(turn_id=turn.id, event="error")
        .order_by(AssistantTurnEvent.seq.desc())
        .first()
    )
    data = event.data_json if event is not None else None
    return isinstance(data, dict) and data.get("retryable") is True


def reprocess_allowed(db: Session, task: AssistantTask, turn: AssistantTurn) -> bool:
    """Server decision for the separate reprocess action. Sync never uses it."""

    if task.status != AssistantTaskStatus.ACTIVE or task_has_customer_activity(task):
        return False
    if task.active_turn_id not in (None, turn.id):
        return False
    if turn.status == "FAILED":
        return latest_error_retryable(db, turn)
    expired = (
        turn.status == "RUNNING"
        and turn.lease_expires_at is not None
        and turn.lease_expires_at < business_now()
    )
    return expired and not live_worker(turn.id, turn.lease_version)


def _log_retry(db: Session, task: AssistantTask, turn: AssistantTurn, result: str) -> None:
    request = db.get(AssistantRequest, turn.request_id)
    client_request_id = request.client_request_id if request is not None else ""
    from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry

    conversation_id = (
        db.query(AssistantConversation.public_id)
        .join(AssistantConversationEntry, AssistantConversationEntry.conversation_id == AssistantConversation.id)
        .filter(
            AssistantConversationEntry.turn_public_id == turn.public_id,
            AssistantConversationEntry.team_id == turn.team_id,
            AssistantConversationEntry.user_id == turn.user_id,
        )
        .limit(1)
        .scalar()
    )
    logger.info(
        "assistant_turn_retry result=%s client_request_id=%s conversation=%s task=%s turn=%s "
        "lease_version=%s attempts=%s last_seq=%s event_name=retry",
        result,
        client_request_id,
        conversation_id or "",
        task.public_id,
        turn.public_id,
        turn.lease_version,
        turn.attempts,
        max(turn.next_seq - 1, 0),
    )


def retry_owned_turn(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    task_public_id: str,
    turn_public_id: str,
    expected_lease_version: int,
) -> tuple[AssistantTask, AssistantTurn, bool] | None:
    """Restart only an eligible failed or expired turn. A live lease is read-only."""

    owned = (
        db.query(AssistantTask, AssistantTurn)
        .join(AssistantTurn, AssistantTurn.task_id == AssistantTask.id)
        .filter(
            AssistantTask.public_id == task_public_id,
            AssistantTask.team_id == team_id,
            AssistantTask.user_id == user_id,
            AssistantTurn.public_id == turn_public_id,
            AssistantTurn.team_id == team_id,
            AssistantTurn.user_id == user_id,
        )
        .one_or_none()
    )
    if owned is None:
        return None
    task, turn = owned
    if turn.lease_version != expected_lease_version or not reprocess_allowed(db, task, turn):
        _log_retry(db, task, turn, "denied")
        return task, turn, False
    now = business_now()
    status_filter = (
        AssistantTurn.status == "FAILED"
        if turn.status == "FAILED"
        else (AssistantTurn.status == "RUNNING") & (AssistantTurn.lease_expires_at < now)
    )
    changed = db.execute(
        update(AssistantTurn)
        .where(
            AssistantTurn.id == turn.id,
            AssistantTurn.team_id == team_id,
            AssistantTurn.user_id == user_id,
            status_filter,
            AssistantTurn.lease_version == expected_lease_version,
        )
        .values(
            status="PENDING",
            lease_owner=None,
            lease_expires_at=None,
            lease_version=AssistantTurn.lease_version + 1,
            last_modified_time=now,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        db.refresh(turn)
        db.refresh(task)
        _log_retry(db, task, turn, "denied_conflict")
        return task, turn, False
    claimed = db.execute(
        update(AssistantTask)
        .where(
            AssistantTask.id == task.id,
            AssistantTask.team_id == team_id,
            AssistantTask.user_id == user_id,
            AssistantTask.status == AssistantTaskStatus.ACTIVE,
            or_(AssistantTask.active_turn_id.is_(None), AssistantTask.active_turn_id == turn.id),
        )
        .values(active_turn_id=turn.id)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        db.refresh(turn)
        db.refresh(task)
        _log_retry(db, task, turn, "denied_task_owner")
        return task, turn, False
    db.commit()
    db.refresh(turn)
    db.refresh(task)
    _log_retry(db, task, turn, "restarted")
    return task, turn, True


def renew_lease(factory: sessionmaker, *, turn_id: int, owner: str, version: int) -> bool:
    """Extend only a live lease still owned by this worker."""

    with factory() as db:
        now = business_now()
        changed = db.execute(
            update(AssistantTurn)
            .where(
                AssistantTurn.id == turn_id,
                AssistantTurn.status == "RUNNING",
                AssistantTurn.lease_owner == owner,
                AssistantTurn.lease_version == version,
                AssistantTurn.lease_expires_at > now,
            )
            .values(lease_expires_at=now + timedelta(seconds=LEASE_SECONDS), last_modified_time=now)
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            db.rollback()
            return False
        db.commit()
        return True


def assert_owned_execution_lease(db: Session, task: AssistantTask) -> None:
    """Fence a non-transactional CRM command before committing its durable claim."""

    turn_id = task.active_turn_id
    if turn_id is None:
        return
    lease = _execution_lease.get()
    if lease is None or lease[0] != turn_id:
        raise AssistantStateConflict("当前轮次未持有 CRM 命令执行权")
    _, owner, version = lease
    now = business_now()
    changed = db.execute(
        update(AssistantTurn)
        .where(
            AssistantTurn.id == turn_id,
            AssistantTurn.task_id == task.id,
            AssistantTurn.team_id == task.team_id,
            AssistantTurn.user_id == task.user_id,
            AssistantTurn.status == "RUNNING",
            AssistantTurn.lease_owner == owner,
            AssistantTurn.lease_version == version,
            AssistantTurn.lease_expires_at > now,
        )
        .values(lease_expires_at=now + timedelta(seconds=LEASE_SECONDS), last_modified_time=now)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise AssistantStateConflict("当前轮次执行权已失效")


async def _keep_lease(
    factory: sessionmaker, *, turn_id: int, owner: str, version: int, worker: asyncio.Task[None]
) -> None:
    while True:
        await asyncio.sleep(max(0.1, LEASE_SECONDS / 3))
        try:
            if not renew_lease(factory, turn_id=turn_id, owner=owner, version=version):
                logger.warning("assistant turn lost its execution lease: id=%s", turn_id)
                worker.cancel()
                return
        except Exception:
            logger.exception("assistant turn lease renewal failed: id=%s", turn_id)


class DurableProgressReporter(ProgressReporter):
    """Commit progress independently of the model and task transaction."""

    def __init__(self, factory: sessionmaker, *, turn_id: int, owner: str, version: int) -> None:
        self.factory = factory
        self.turn_id = turn_id
        self.owner = owner
        self.version = version

    def _record(self, payload: dict[str, object]) -> None:
        try:
            with self.factory() as db:
                now = business_now()
                changed = db.execute(
                    update(AssistantTurn)
                    .where(
                        AssistantTurn.id == self.turn_id,
                        AssistantTurn.status == "RUNNING",
                        AssistantTurn.lease_owner == self.owner,
                        AssistantTurn.lease_version == self.version,
                        AssistantTurn.lease_expires_at > now,
                    )
                    .values(next_seq=AssistantTurn.next_seq + 1)
                    .execution_options(synchronize_session=False)
                )
                if changed.rowcount != 1:
                    db.rollback()
                    return
                next_seq = db.execute(
                    select(AssistantTurn.next_seq).where(AssistantTurn.id == self.turn_id)
                ).scalar_one()
                seq = next_seq - 1
                db.add(
                    AssistantTurnEvent(turn_id=self.turn_id, seq=seq, event="stage", data_json={**payload, "seq": seq})
                )
                db.commit()
        except Exception:
            logger.exception("assistant stage persistence failed: turn=%s", self.turn_id)

    def stage_start(self, stage: TurnStage) -> None:
        self._record({"stage": stage.name, "phase": "start"})

    def stage_done(self, stage: TurnStage, *, ms: int, score: int | None = None) -> None:
        payload: dict[str, object] = {"stage": stage.name, "phase": "done", "ms": ms}
        if score is not None:
            payload["score"] = score
        self._record(payload)


def events_after(db: Session, *, turn_id: int, seq: int) -> list[AssistantTurnEvent]:
    return (
        db.query(AssistantTurnEvent)
        .filter(AssistantTurnEvent.turn_id == turn_id, AssistantTurnEvent.seq > seq)
        .order_by(AssistantTurnEvent.seq)
        .all()
    )


async def execute_turn(turn_id: int, *, factory: sessionmaker | None = None) -> None:
    from app.api.assistant import _coordinator
    from app.services.assistant.presentation import task_view

    followup_turn_id: int | None = None

    factory = factory or SessionLocal
    owner = uuid.uuid4().hex
    db = factory()
    heartbeat: asyncio.Task[None] | None = None
    lease_token = None
    try:
        version = claim(db, turn_id=turn_id, owner=owner)
        if version is None:
            return
        turn = db.get(AssistantTurn, turn_id)
        if turn is None:
            return
        worker = asyncio.current_task()
        if worker is not None:
            _workers[turn_id] = (version, worker)
        lease_token = _execution_lease.set((turn_id, owner, version))
        try:
            task = db.get(AssistantTask, turn.task_id)
            if task is None or task.team_id != turn.team_id or task.user_id != turn.user_id:
                raise AssistantStateConflict("任务已失效")
            heartbeat = asyncio.create_task(
                _keep_lease(factory, turn_id=turn_id, owner=owner, version=version, worker=asyncio.current_task())
            )
            data = turn.input_json
            reporter = DurableProgressReporter(factory, turn_id=turn_id, owner=owner, version=version)
            outcome = await _coordinator.handle_task(
                db,
                task,
                AssistantInput(kind=str(data["kind"]), text=data.get("text"), choice=data.get("choice")),
                reporter=reporter,
            )
            now = business_now()
            fence = db.execute(
                update(AssistantTurn)
                .where(
                    AssistantTurn.id == turn_id,
                    AssistantTurn.status == "RUNNING",
                    AssistantTurn.lease_owner == owner,
                    AssistantTurn.lease_version == version,
                    AssistantTurn.lease_expires_at > now,
                )
                .values(status="SUCCEEDED", lease_owner=None, lease_expires_at=None, last_modified_time=now)
                .execution_options(synchronize_session=False)
            )
            if fence.rowcount != 1:
                db.rollback()
                return
            released = db.execute(
                update(AssistantTask)
                .where(
                    AssistantTask.id == turn.task_id,
                    AssistantTask.active_turn_id == turn_id,
                )
                .values(active_turn_id=None)
                .execution_options(synchronize_session=False)
            )
            if released.rowcount != 1:
                raise AssistantStateConflict("任务轮次归属已变化")
            followup = None
            if getattr(outcome, "start_followup", False):
                if (
                    outcome.task.status != AssistantTaskStatus.ACTIVE
                    or load_waiting(outcome.task) is not None
                    or not any(item.get("kind") == "customer_activity" for item in outcome.task.committed_json or [])
                ):
                    raise AssistantStateConflict("活动后续轮次只能在已提交活动后创建")
                internal_input = {"kind": "continue_proposals", "text": None, "choice": None}
                request = AssistantRequest(
                    team_id=turn.team_id,
                    user_id=turn.user_id,
                    client_request_id=f"internal-followup-{uuid.uuid4().hex}",
                    input_fingerprint=fingerprint(
                        {"operation": "internal_followup", "task_id": outcome.task.public_id, **internal_input}
                    ),
                    task_id=turn.task_id,
                )
                db.add(request)
                db.flush()
                followup = AssistantTurn(
                    team_id=turn.team_id,
                    user_id=turn.user_id,
                    task_id=turn.task_id,
                    request_id=request.id,
                    input_json=internal_input,
                    status="PENDING",
                )
                db.add(followup)
                db.flush()
                request.turn_id = followup.id
                add_event(db, followup, "accepted", {"turn_id": followup.public_id})
                claimed = db.execute(
                    update(AssistantTask)
                    .where(
                        AssistantTask.id == turn.task_id,
                        AssistantTask.active_turn_id.is_(None),
                        AssistantTask.status == AssistantTaskStatus.ACTIVE,
                    )
                    .values(active_turn_id=followup.id)
                    .execution_options(synchronize_session=False)
                )
                if claimed.rowcount != 1:
                    raise AssistantStateConflict("活动后续轮次无法领取任务")
            db.refresh(turn)
            db.refresh(outcome.task)
            data = {"task": task_view(outcome.task, db).model_dump(mode="json"), "message": outcome.reply.message}
            if followup is not None:
                data["next_turn_id"] = followup.public_id
            add_event(db, turn, "waiting", data)
            db.commit()
            logger.info(
                "assistant_turn_terminal result=succeeded task=%s turn=%s lease_version=%s attempts=%s "
                "last_seq=%s event_name=waiting",
                outcome.task.public_id,
                turn.public_id,
                version,
                turn.attempts,
                max(turn.next_seq - 1, 0),
            )
            if followup is not None:
                followup_turn_id = followup.id
            return
        except asyncio.CancelledError:
            db.rollback()
            return
        except Exception as exc:
            db.rollback()
            logger.exception("assistant durable turn failed: id=%s", turn_id)
            turn = db.get(AssistantTurn, turn_id)
            if turn is None or turn.lease_owner != owner or turn.lease_version != version:
                return
            code = classify_turn_error(exc)
            now = business_now()
            fence = db.execute(
                update(AssistantTurn)
                .where(
                    AssistantTurn.id == turn_id,
                    AssistantTurn.status == "RUNNING",
                    AssistantTurn.lease_owner == owner,
                    AssistantTurn.lease_version == version,
                    AssistantTurn.lease_expires_at > now,
                )
                .values(
                    status="FAILED",
                    lease_owner=None,
                    lease_expires_at=None,
                    last_error_code=code,
                    last_modified_time=now,
                )
                .execution_options(synchronize_session=False)
            )
            if fence.rowcount == 1:
                db.execute(
                    update(AssistantTask)
                    .where(
                        AssistantTask.id == turn.task_id,
                        AssistantTask.active_turn_id == turn_id,
                    )
                    .values(active_turn_id=None)
                    .execution_options(synchronize_session=False)
                )
                add_event(
                    db,
                    turn,
                    "error",
                    {
                        "code": code,
                        "retryable": code == "RETRYABLE_DEPENDENCY_FAILURE",
                        "message": "处理未完成，请查看最新任务状态后重试"
                        if code == "RETRYABLE_DEPENDENCY_FAILURE"
                        else "处理未完成，结果待核对，请查看最新任务状态。",
                    },
                )
                db.commit()
                failed_task = db.get(AssistantTask, turn.task_id)
                logger.info(
                    "assistant_turn_terminal result=failed task=%s turn=%s lease_version=%s attempts=%s "
                    "last_seq=%s event_name=error code=%s",
                    failed_task.public_id if failed_task is not None else "",
                    turn.public_id,
                    version,
                    turn.attempts,
                    max(turn.next_seq - 1, 0),
                    code,
                )
            else:
                db.rollback()
    finally:
        if lease_token is not None:
            _execution_lease.reset(lease_token)
        registered = _workers.get(turn_id)
        if registered is not None and registered[1] is asyncio.current_task():
            del _workers[turn_id]
        if heartbeat is not None:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
        db.close()
        if followup_turn_id is not None:
            schedule_turn(followup_turn_id, factory=factory)


def schedule_turn(turn_id: int, *, factory: sessionmaker | None = None) -> None:
    runner = asyncio.create_task(execute_turn(turn_id, factory=factory))
    _active.add(runner)
    runner.add_done_callback(_active.discard)


async def recover_turns(*, limit: int = 30) -> int:
    db = SessionLocal()
    try:
        now = business_now()
        ids = [
            row[0]
            for row in db.query(AssistantTurn.id)
            .filter(
                or_(
                    AssistantTurn.status == "PENDING",
                    (AssistantTurn.status == "RUNNING") & (AssistantTurn.lease_expires_at < now),
                )
            )
            .order_by(AssistantTurn.id)
            .limit(limit)
            .all()
        ]
    finally:
        db.close()
    for turn_id in ids:
        schedule_turn(turn_id)
    return len(ids)
