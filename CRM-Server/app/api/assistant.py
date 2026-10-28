"""/v1/assistant routes: thin transport over the Agent 2.0 coordinator."""
# ruff: noqa: RUF001, B008

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.assistant_conversation import ConversationConflict
from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_turn import AssistantTurn
from app.models.team import UserTeam
from app.schemas.assistant import (
    AssistantTaskView,
    AssistantTurnEventView,
    AssistantTurnView,
    CreateTaskRequest,
    RetryTurnRequest,
    SubmitInputRequest,
)
from app.schemas.assistant_conversation import (
    ConversationChoiceRequest,
    ConversationCommandRequest,
    ConversationKindRequest,
    ConversationReply,
    ConversationTextRequest,
    ConversationView,
)
from app.services.assistant.conversation import ConversationService
from app.services.assistant.coordinator import (
    AssistantCoordinator,
)
from app.services.assistant.presentation import task_view
from app.services.assistant.turns import (
    AssistantRequestConflict,
    AssistantStateConflict,
    accept_create,
    accept_submit,
    events_after,
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
    from app.services.assistant.intake import RealKindStructurer
    from app.services.assistant.quality_gate import QualityGate
    from app.services.assistant.real_writer import RealActivityWriter

    return AssistantCoordinator(
        next_action_chooser=AgentLLMChooser(),
        structurer=RealKindStructurer(),
        writer=RealActivityWriter(),
        proposal_executor=RealCRMProposalExecutor(),
        quality_gate=QualityGate(),
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
        task = accept_create(
            db,
            team_id=team_id,
            user_id=current_user.id,
            key=request.client_request_id,
            goal=request.goal,
        )
    except AssistantRequestConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return task_view(task, db)


@router.get("/tasks/{public_id}", response_model=AssistantTaskView)
async def get_task(
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


@router.get("/tasks/latest/active", response_model=AssistantTaskView | None)
async def latest_active_task(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AssistantTaskView | None:
    """The one in-flight task to resume in the UI, if any."""

    task = (
        db.query(AssistantTask)
        .filter_by(team_id=team_id, user_id=current_user.id, status="ACTIVE")
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


@router.post("/unknown-commands/{action_public_id}/adjudicate", response_model=dict[str, object])
async def adjudicate_unknown_command(
    action_public_id: str,
    payload: dict[str, object],
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Operator-only manual adjudication; evidence rules per TRD §7.1 decision 3."""

    from fastapi import HTTPException, status

    from app.crud.permission import permission_crud
    from app.models.assistant import AssistantAction

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
            AssistantAction.action == "proposal_command_claim",
        )
        .one_or_none()
    )
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="命令记录不存在")

    result = dict(action.result_json or {})
    if result.get("status") not in {"UNKNOWN", "CLAIMED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"该命令已终态 {result.get('status')}，不可裁决"
        )

    decision = str(payload.get("decision") or "")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="裁决必须提供理由")

    if decision == "SUCCEEDED":
        command_id = str(result.get("command_id") or "")
        if not command_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="老格式 claim 无 command_id，不能判成功；保持 UNKNOWN",
            )
        from app.models.assistant_crm_effect import AssistantCRMEffect

        effect = (
            db.query(AssistantCRMEffect)
            .filter(
                AssistantCRMEffect.team_id == team_id,
                AssistantCRMEffect.command_id == command_id,
            )
            .first()
        )
        if effect is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="缺少 (team,command_id,effect_kind) 精确目标回执；不能凭相似对象判成功，保持 UNKNOWN",
            )
        new_status = "SUCCEEDED"
    elif decision == "REJECTED":
        if result.get("started"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="目标可能已提交（STARTED），无确定回滚证明；不能判拒绝，保持 UNKNOWN",
            )
        new_status = "REJECTED"
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="decision 只支持 SUCCEEDED/REJECTED"
        )

    result.update(
        {
            "status": new_status,
            "adjudicated_by": int(current_user.id),
            "adjudication_reason": reason,
        }
    )
    action.result_json = result
    db.commit()
    # Adjudication never retries the command (TRD §7.1).
    return {"action_public_id": action_public_id, "status": new_status}


@router.get("/tasks/{public_id}/turns/{turn_id}", response_model=AssistantTurnView)
async def read_turn(
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
async def retry_turn(
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
async def submit_input(
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
            input_data={"kind": request.kind, "text": request.text, "choice": request.choice},
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

    async def stream() -> AsyncIterator[str]:

        seq = 0
        while True:
            with factory() as stream_db:
                current = stream_db.get(AssistantTurn, turn.id)
                if current is None or current.team_id != team_id or current.user_id != user_id:
                    return
                emitted = events_after(stream_db, turn_id=current.id, seq=seq)
                frames = [(event.seq, event.event, event.data_json) for event in emitted]
                finished = current.status in {"SUCCEEDED", "FAILED"}
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
