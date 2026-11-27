"""/v1/assistant routes: thin transport over the Agent 2.0 coordinator."""
# ruff: noqa: RUF001, B008

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.assistant_conversation import ConversationConflict
from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_turn import AssistantTurn
from app.models.team import UserTeam
from app.schemas.assistant import (
    AssistantTaskReconcileResponse,
    AssistantTaskView,
    AssistantTurnEventView,
    AssistantTurnView,
    CreateTaskRequest,
    PendingEntityDraftView,
    RetryTurnRequest,
    SubmitInputRequest,
)
from app.schemas.assistant_conversation import (
    ConversationChoiceRequest,
    ConversationCommandRequest,
    ConversationEntryRetryRequest,
    ConversationFocusRequest,
    ConversationKindRequest,
    ConversationReply,
    ConversationRequestStatus,
    ConversationTextRequest,
    ConversationView,
)
from app.services.assistant.conversation import ConversationService
from app.services.assistant.coordinator import (
    AssistantCoordinator,
)
from app.services.assistant.intent import judge_intent, open_verdict_task
from app.services.assistant.model_transport import AssistantLLMError
from app.services.assistant.presentation import task_view
from app.services.assistant.turns import (
    AssistantRequestConflict,
    AssistantStateConflict,
    accept_submit,
    events_after,
    replayed_create,
    reprocess_allowed,
    retry_owned_turn,
    schedule_turn,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.orm import Session

    from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/v1/assistant",
    tags=["CRM Sales Assistant"],
)


def _build_coordinator() -> AssistantCoordinator:
    """Production assembly: real chooser, structurer, gate, and writer."""

    from app.services.assistant.chooser import AgentLLMChooser
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor
    from app.services.assistant.follow_up_context import RealFollowUpContext
    from app.services.assistant.intake import RealKindStructurer
    from app.services.assistant.quality_gate import QualityGate
    from app.services.assistant.real_writer import RealActivityWriter

    return AssistantCoordinator(
        next_action_chooser=AgentLLMChooser(),
        structurer=RealKindStructurer(),
        writer=RealActivityWriter(),
        proposal_executor=RealCRMProposalExecutor(),
        quality_gate=QualityGate(),
        follow_up=RealFollowUpContext(),
    )


_coordinator = _build_coordinator()


def _list_view(task: AssistantTask, db: Session) -> dict[str, object]:
    """Keep unreadable rows identifiable without exposing unvalidated stored JSON."""
    try:
        return task_view(task, db).model_dump(mode="json")
    except ValueError:
        # A null draft deliberately remains unreadable to the strict client row
        # parser, which counts/skips this row instead of losing the entire list.
        # Never return raw draft/waiting/authority JSON on this recovery path.
        return {
            "public_id": task.public_id,
            "status": task.status,
            "task_kind": task.task_kind,
            "goal": task.goal,
            "activity_kind": task.activity_kind,
            "draft": None,
            "waiting": None,
            "committed": [],
            "budget_steps": task.budget_steps,
            "budget_max_steps": task.budget_max_steps,
            "version": task.version,
            "last_modified_time": task.last_modified_time.isoformat() if task.last_modified_time else None,
            "processing_turn_id": None,
            "processing_turn_status": None,
            "reprocess_turn_id": None,
            "follow_up_disposition": None,
            "proposal_outcome": None,
            "reconciliation_required": True,
            "profile_proposals": None,
        }

def _owned_task(db: Session, *, team_id: int, user_id: int, public_id: str) -> AssistantTask:
    task = db.query(AssistantTask).filter_by(public_id=public_id).one_or_none()
    if task is None or task.team_id != team_id or task.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


@router.post("/tasks", response_model=AssistantTaskView, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: CreateTaskRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTaskView:
    try:
        task = replayed_create(
            db, team_id=team_id, user_id=current_user.id, key=request.client_request_id, goal=request.goal
        )
        if task is None:
            # The direct intake obeys the same verdict as the conversation root; no second rule set.
            try:
                decision = await _conversation_service.classifier.classify(
                    db,
                    team_id=team_id,
                    text=request.goal,
                    tasks=[],
                    focused_task_public_id=None,
                    recent_messages=[],
                )
            except AssistantLLMError as exc:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
            verdict = judge_intent(decision.semantic_plan, decision.confidence)
            if verdict.route == "refuse":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": verdict.message,
                        "links": [link.model_dump(mode="json") for link in verdict.links],
                    },
                )
            task = open_verdict_task(
                db,
                team_id=team_id,
                user_id=current_user.id,
                key=request.client_request_id,
                goal=request.goal,
                verdict=verdict,
            )
    except AssistantRequestConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return task_view(task, db)


@router.get("/tasks/{public_id}", response_model=AssistantTaskView)
def get_task(
    public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTaskView:
    return task_view(_owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id), db)


@router.get("/tasks", response_model=list[dict[str, object]])
async def list_tasks(
    status_filter: str | None = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """List this user's tasks, newest first, optionally by status."""

    query = db.query(AssistantTask).filter_by(team_id=team_id, user_id=current_user.id)
    if status_filter is not None:
        query = query.filter_by(status=status_filter)
    tasks = query.order_by(AssistantTask.id.desc()).limit(50).all()
    return [_list_view(task, db) for task in tasks]


@router.get("/pending-drafts", response_model=list[PendingEntityDraftView])
async def list_pending_drafts(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[PendingEntityDraftView]:
    """This user's unfinished direct-create drafts (「待补充」), most recently touched first."""

    from app.services.assistant.entity_tasks import pending_drafts

    return pending_drafts(db, team_id=team_id, user_id=current_user.id)


@router.get("/tasks/latest/active", response_model=AssistantTaskView | None)
def latest_active_task(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTaskView | None:
    """The one in-flight task to resume in the UI, if any; parked drafts stay in 「待补充」."""

    task = (
        db.query(AssistantTask)
        .filter_by(team_id=team_id, user_id=current_user.id, status="ACTIVE")
        .filter(or_(AssistantTask.waiting_type.is_(None), AssistantTask.waiting_type != "ENTITY_DEFERRED"))
        .order_by(AssistantTask.id.desc())
        .first()
    )
    return task_view(task, db) if task is not None else None


class ChangeKindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=32)


@router.post("/tasks/{public_id}/change-kind", response_model=AssistantTaskView)
async def change_kind(
    public_id: str,
    request: ChangeKindRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTaskView:
    """Reset the activity kind and structured slots so the turn re-classifies.

    Only allowed before a committed activity and without a running turn.
    The next text submission re-runs classification with the new kind hint.
    """

    from app.services.assistant.task_operations import reset_activity_kind
    from app.services.assistant.task_state import InvalidTaskTransitionError, TaskStateConflictError

    if request.kind not in {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="未知活动类型")
    task = _owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id)
    try:
        updated = reset_activity_kind(db, task, request.kind)
        db.commit()
    except (TaskStateConflictError, InvalidTaskTransitionError) as exc:
        db.rollback()
        db.expire_all()
        latest = _owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code":"STATE_CONFLICT", "message":str(exc), "task":task_view(latest, db).model_dump(mode="json")
        }) from exc
    return task_view(updated, db)


@router.post("/tasks/{public_id}/reconcile", response_model=AssistantTaskReconcileResponse)
def reconcile_task(
    public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTaskReconcileResponse:
    """Deterministically reconcile an UNKNOWN_COMMIT_RESULT task via read-only readback."""
    from sqlalchemy.orm import sessionmaker

    from app.services.assistant.confirmation import RECONCILE_NOOP_MESSAGE, reconcile_unknown_activity
    from app.services.assistant.task_operations import activity_commit_is_unknown
    from app.services.assistant.task_state import TaskStateConflictError

    task = _owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id)
    try:
        result = reconcile_unknown_activity(
            db,
            task,
            actor_type="USER",
            actor_id=int(current_user.id),
            reason="user_refresh",
        )
        if result.outcome in {"WRITTEN", "NOT_WRITTEN"}:
            db.commit()
            if result.followup_turn_id is not None:
                schedule_turn(
                    result.followup_turn_id,
                    factory=sessionmaker(bind=db.get_bind(), autoflush=False),
                )
    except TaskStateConflictError as exc:
        db.rollback()
        db.expire_all()
        latest = _owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id)
        if not activity_commit_is_unknown(latest):
            return AssistantTaskReconcileResponse(
                outcome="NOOP",
                task=task_view(latest, db),
                message=RECONCILE_NOOP_MESSAGE,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT",
                "message": str(exc),
                "task": task_view(latest, db).model_dump(mode="json"),
            },
        ) from exc
    return AssistantTaskReconcileResponse(
        outcome=result.outcome,
        task=task_view(result.task, db),
        message=result.message,
        followup_turn_id=result.followup_turn_public_id,
    )


@router.get("/tasks/{public_id}/actions", response_model=list[dict[str, object]])
async def list_task_actions(
    public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Append-only action log of one owned task, oldest first."""

    task = _owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id)
    actions = db.query(AssistantAction).filter_by(task_id=task.id).order_by(AssistantAction.id.asc()).all()
    return [
        {
            "actor": action.actor,
            "action": action.action,
            "input": action.input_json,
            "result": action.result_json,
            "event_type": action.event_type,
            "event_key": action.event_key,
            "correlation_id": action.correlation_id,
            "created_time": action.created_time.isoformat(),
        }
        for action in actions
    ]


@router.get("/unknown-commands", response_model=list[dict[str, object]])
async def list_unknown_commands(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Owner-scoped unresolved claims; team operators also see CLAIMED within their team."""

    from app.crud.permission import permission_crud
    from app.services.assistant.proposals import list_unresolved_command_claims

    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, int(current_user.id), team_id)
    }
    if "assistant:commands:reconcile:team" in permission_codes:
        return list_unresolved_command_claims(db, team_id=team_id, include_claimed=True)
    from fastapi import HTTPException, status

    membership = (
        db.query(UserTeam.id)
        .filter(UserTeam.user_id == int(current_user.id), UserTeam.team_id == team_id)
        .first()
    )
    if membership is not None:
        # Team members see their own unresolved commands only (TRD §7.1).
        return list_unresolved_command_claims(db, team_id=team_id, owner_user_id=int(current_user.id))
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有核对助手命令的权限")


class CommandAdjudicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["SUCCEEDED", "REJECTED"]
    reason: str = Field(min_length=1)


@router.post("/unknown-commands/{action_public_id}/adjudicate", response_model=dict[str, object])
async def adjudicate_unknown_command(
    action_public_id: str,
    payload: CommandAdjudicationRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Operator-only readback; no target-service write or retry is permitted."""

    from app.crud.permission import permission_crud
    from app.services.assistant.proposals import adjudicate_proposal_claim
    from app.services.assistant.task_state import TaskStateConflictError

    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, int(current_user.id), team_id)
    }
    if "assistant:commands:reconcile:team" not in permission_codes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有裁决助手命令的权限")

    action = (
        db.query(AssistantAction)
        .filter(
            AssistantAction.public_id == action_public_id,
            AssistantAction.team_id == team_id,
            AssistantAction.action.in_(("proposal_command_claim", "activity_commit_unknown")),
        )
        .one_or_none()
    )
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="命令记录不存在")

    if action.action == "activity_commit_unknown":
        from sqlalchemy.orm import sessionmaker

        from app.services.assistant.confirmation import reconcile_unknown_activity

        if (action.result_json or {}).get("status") in {"RECONCILED", "RECONCILED_NOT_WRITTEN"}:
            raise HTTPException(status_code=409, detail="该命令已结算，不可裁决。")
        task = db.query(AssistantTask).filter_by(id=action.task_id, team_id=team_id).one_or_none()
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        try:
            result = reconcile_unknown_activity(
                db,
                task,
                actor_type="OPERATOR",
                actor_id=int(current_user.id),
                reason=payload.reason,
                expected_decision=payload.decision,
            )
            db.commit()
            if result.followup_turn_id is not None:
                schedule_turn(
                    result.followup_turn_id,
                    factory=sessionmaker(bind=db.get_bind(), autoflush=False),
                )
        except (TaskStateConflictError, ValueError) as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(exc) or "无法核对当前命令，结果仍待核对。") from exc
        return {
            "action_public_id": action_public_id,
            "status": payload.decision,
            "outcome": result.outcome,
            "task_public_id": result.task.public_id,
            "followup_turn_id": result.followup_turn_public_id,
        }

    if payload.decision == "REJECTED":
        # No durable producer can prove that an unresolved claim never entered CRM.
        raise HTTPException(status_code=409, detail="没有确定未执行的证据，结果仍待核对。")
    try:
        await adjudicate_proposal_claim(db, action, operator_id=int(current_user.id), reason=payload.reason)
        db.commit()
    except (TaskStateConflictError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="无法核对当前命令，结果仍待核对。") from exc
    return {"action_public_id": action_public_id, "status": payload.decision}


@router.get("/tasks/{public_id}/turns/{turn_id}", response_model=AssistantTurnView)
def read_turn(
    public_id: str,
    turn_id: str,
    after_seq: int = 0,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTurnView:
    task = _owned_task(db, team_id=team_id, user_id=current_user.id, public_id=public_id)
    turn = (
        db.query(AssistantTurn)
        .filter_by(
            public_id=turn_id,
            task_id=task.id,
            team_id=team_id,
            user_id=current_user.id,
        )
        .one_or_none()
    )
    if turn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="轮次不存在")
    from app.services.assistant.turns import close_overdue_turn

    if close_overdue_turn(db, task, turn):
        db.refresh(turn)
        db.refresh(task)
    return AssistantTurnView(
        turn_id=turn.public_id,
        status=turn.status,
        lease_version=turn.lease_version,
        reprocess_allowed=reprocess_allowed(db, task, turn),
        events=[
            AssistantTurnEventView(seq=event.seq, event=event.event, data=event.data_json)
            for event in events_after(db, turn_id=turn.id, seq=max(after_seq, 0))
        ],
        task=task_view(task, db),
    )


@router.post("/tasks/{public_id}/turns/{turn_id}/retry", response_model=AssistantTurnView)
def retry_turn(
    public_id: str,
    turn_id: str,
    request: RetryTurnRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTurnView:
    result = retry_owned_turn(
        db,
        team_id=team_id,
        user_id=int(current_user.id),
        task_public_id=public_id,
        turn_public_id=turn_id,
        expected_lease_version=request.expected_lease_version,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="轮次不存在")
    task, turn, restarted = result
    if restarted:
        from sqlalchemy.orm import sessionmaker

        schedule_turn(turn.id, factory=sessionmaker(bind=db.get_bind(), autoflush=False))
    return AssistantTurnView.model_validate(
        {
            "turn_id": turn.public_id,
            "status": turn.status,
            "lease_version": turn.lease_version,
            "reprocess_allowed": reprocess_allowed(db, task, turn),
            "events": [
                AssistantTurnEventView(seq=event.seq, event=event.event, data=event.data_json)
                for event in events_after(db, turn_id=turn.id, seq=request.after_seq)
            ],
            "task": task_view(task, db),
        }
    )


@router.post("/tasks/{public_id}/submit")
def submit_input(
    public_id: str,
    request: SubmitInputRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Accept and commit a turn before emitting any SSE bytes."""
    from app.services.assistant.events import encode_sse

    user_id = current_user.id
    task = _owned_task(db, team_id=team_id, user_id=user_id, public_id=public_id)
    try:
        turn, created = accept_submit(
            db,
            task=task,
            key=request.client_request_id,
            input_data=request.turn_input(),
            action_id=request.action_id,
            expected_version=request.expected_version,
        )
    except (AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        db.expire_all()
        latest = _owned_task(db, team_id=team_id, user_id=user_id, public_id=public_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATE_CONFLICT" if isinstance(exc, AssistantStateConflict) else "REQUEST_CONFLICT",
                "message": str(exc),
                "task": task_view(latest, db).model_dump(mode="json"),
            },
        ) from exc
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    if created:
        schedule_turn(turn.id, factory=factory)

    def poll(seq: int) -> tuple[list[tuple[int, str, dict[str, object]]], bool] | None:
        from app.services.assistant.turns import close_overdue_turn

        with factory() as stream_db:
            current = stream_db.get(AssistantTurn, turn.id)
            if current is None or current.team_id != team_id or current.user_id != user_id:
                return None
            task_row = stream_db.get(AssistantTask, current.task_id)
            if (
                task_row is not None
                and task_row.team_id == team_id
                and close_overdue_turn(stream_db, task_row, current)
            ):
                stream_db.refresh(current)
            emitted = events_after(stream_db, turn_id=current.id, seq=seq)
            return [(event.seq, event.event, event.data_json) for event in emitted], current.status in {
                "SUCCEEDED",
                "FAILED",
            }

    async def stream() -> AsyncIterator[str]:
        seq = 0
        while True:
            polled = await run_in_threadpool(poll, seq)
            if polled is None:
                return
            frames, finished = polled
            for next_seq, name, payload in frames:
                seq = next_seq
                yield encode_sse(name, payload)
            if finished:
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# Conversation endpoints intentionally retain the existing task submit transport:
# the service has already accepted its deterministic durable turn before SSE replay.
_conversation_service = ConversationService()


@router.post('/conversation/open', response_model=ConversationView)
def open_conversation(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationView:
    return _conversation_service.open(db, team_id=team_id, user_id=int(current_user.id))


@router.get('/conversation', response_model=ConversationView)
def get_conversation(
    before: int | None = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationView:
    try:
        return _conversation_service.read(db, team_id=team_id, user_id=int(current_user.id), before=before)
    except ConversationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/conversation/requests/{client_request_id}", response_model=ConversationRequestStatus)
def get_conversation_request(
    client_request_id: str = Path(min_length=8, max_length=128),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationRequestStatus:
    """Read-only: whether a request whose response was lost landed. Never resends it."""
    try:
        return _conversation_service.request_status(
            db, team_id=team_id, user_id=int(current_user.id), client_request_id=client_request_id
        )
    except ConversationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/conversation/messages', response_model=ConversationReply)
async def conversation_text(
    request: ConversationTextRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return await _conversation_service.submit_text(
            db, team_id=team_id, user_id=int(current_user.id), request=request
        )
    except (ConversationConflict, AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/conversation/choices', response_model=ConversationReply)
async def conversation_choice(
    request: ConversationChoiceRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return await _conversation_service.choose(db, team_id=team_id, user_id=int(current_user.id), request=request)
    except (ConversationConflict, AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/conversation/commands', response_model=ConversationReply)
async def conversation_command(
    request: ConversationCommandRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return await _conversation_service.command(db, team_id=team_id, user_id=int(current_user.id), request=request)
    except (ConversationConflict, AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/conversation/entries/{entry_id}/retry", response_model=ConversationReply)
async def retry_conversation_entry(
    entry_id: str,
    request: ConversationEntryRetryRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return await _conversation_service.retry_entry(
            db,
            team_id=team_id,
            user_id=int(current_user.id),
            entry_id=entry_id,
            expected_version=request.expected_version,
        )
    except (ConversationConflict, AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/conversation/resume", response_model=ConversationReply)
async def resume_conversation(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return await _conversation_service.resume(db, team_id=team_id, user_id=int(current_user.id))
    except (ConversationConflict, AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/conversation/focus", response_model=ConversationReply)
def conversation_focus(
    request: ConversationFocusRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return _conversation_service.focus(db, team_id=team_id, user_id=int(current_user.id), request=request)
    except ConversationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/conversation/change-kind", response_model=ConversationReply)
def conversation_change_kind(
    request: ConversationKindRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationReply:
    try:
        return _conversation_service.change_kind(db, team_id=team_id, user_id=int(current_user.id), request=request)
    except (ConversationConflict, AssistantRequestConflict, AssistantStateConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
