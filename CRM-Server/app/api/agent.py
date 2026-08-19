"""CRM AI Agent API."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user, get_current_user_team, security
from app.crud.agent import agent_message_crud, agent_session_crud, agent_workflow_action_crud
from app.models.user import User
from app.schemas.agent import (
    AgentAsyncOperationResponse,
    AgentChatRequest,
    AgentCreateSessionRequest,
    AgentMessageResponse,
    AgentRuntimeActionSummaryResponse,
    AgentRuntimeCheckpointStateResponse,
    AgentRuntimeHistoryItemResponse,
    AgentRuntimeHistoryResponse,
    AgentRuntimeOverviewResponse,
    AgentSessionResponse,
    AgentWorkflowActionResponse,
    AgentWorkflowActionRetryRequest,
    AgentWorkflowDetailResponse,
    AgentWorkflowGraphEdgeResponse,
    AgentWorkflowGraphNodeResponse,
    AgentWorkflowRecoveryScanRequest,
    AgentWorkflowRecoveryScanResponse,
    AgentWorkflowRetryRequest,
)
from app.schemas.common import PaginatedResponse
from app.services.agent import (
    action_workflow,
    confirmation_intent,
    field_common,
    follow_up_fields,
    selection,
    session_state,
    task_execution,
)
from app.services.agent import application as agent_application_module
from app.services.agent import interactions as agent_interactions
from app.services.agent.application import agent_application_service
from app.services.agent.async_operation_service import (
    TERMINAL_OPERATION_STATUSES,
    AgentAsyncOperationProjection,
    agent_async_operation_service,
)
from app.services.agent.graph import crm_agent_graph_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.interactions import (
    _interaction_for_event as _service_interaction_for_event,
)
from app.services.agent.interactions import (
    _procurement_method_options,
)
from app.services.agent.interactions import (
    _with_interaction as _service_with_interaction,
)
from app.services.agent.quality import agent_follow_up_quality_evaluator
from app.services.agent.root_runtime import agent_root_runtime
from app.services.agent.semantic import agent_semantic_parser
from app.services.agent.session_state import (
    _build_session_create,
    _get_owned_session,
)
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.workflow_recovery_service import agent_workflow_recovery_service
from app.services.customer_activity_post_commit_operation_projector import (
    customer_activity_post_commit_operation_projector,
)
from app.services.customer_intelligence_operation_projector import (
    customer_intelligence_operation_projector,
)
from app.utils.sse_encoder import SSEJsonEncoder

router = APIRouter(prefix="/v1/agent", tags=["CRM AI Agent"])
logger = logging.getLogger(__name__)


_WORKFLOW_TERMINAL_STATUSES = {"EXECUTED", "SKIPPED", "FAILED", "CANCELLED", "BLOCKED"}


def _read_repair_customer_intelligence_operations(
    db: Session,
    operations: list[AgentAsyncOperationProjection],
) -> bool:
    repaired = False
    for operation in operations:
        if (
            operation.operation_type != "customer_intelligence_refresh"
            or operation.status in TERMINAL_OPERATION_STATUSES
        ):
            continue
        try:
            projected = customer_intelligence_operation_projector.project_request(
                db,
                team_id=operation.team_id,
                request_id=operation.request_id,
                operation_public_id=operation.public_id,
            )
            if projected is not None:
                db.commit()
                repaired = True
        except Exception as exc:
            db.rollback()
            logger.exception(
                "读取 Agent 异步操作时修复客户智能投影失败: operation_public_id=%s",
                operation.public_id,
            )
            persisted_operation = agent_async_operation_service.get_for_update(
                db,
                team_id=operation.team_id,
                request_id=operation.request_id,
                operation_public_id=operation.public_id,
            )
            if persisted_operation is None:
                continue
            agent_async_operation_service.record_projection_warning(
                db,
                persisted_operation,
                run_id=0,
                run_status="UNKNOWN",
                error_message=str(exc),
            )
            db.commit()
            repaired = True
    return repaired


def _read_repair_customer_activity_post_commit_operations(
    db: Session,
    operations: list[AgentAsyncOperationProjection],
) -> bool:
    repaired = False
    for operation in operations:
        if (
            operation.operation_type != "customer_activity_post_commit"
            or operation.status in TERMINAL_OPERATION_STATUSES
        ):
            continue
        try:
            projected = customer_activity_post_commit_operation_projector.project_request(
                db,
                team_id=operation.team_id,
                request_id=operation.request_id,
                operation_public_id=operation.public_id,
            )
            if projected is not None:
                db.commit()
                repaired = True
        except Exception:
            db.rollback()
            logger.exception(
                "读取 Agent 异步操作时修复客户活动后提交投影失败: operation_public_id=%s",
                operation.public_id,
            )
    return repaired


def _encode_sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, cls=SSEJsonEncoder)}\n\n"


def _authorization_header(credentials: HTTPAuthorizationCredentials) -> str:
    return f"{credentials.scheme} {credentials.credentials}"


def _sync_legacy_agent_overrides() -> None:
    """Keep legacy API-level monkeypatch hooks wired to service modules."""
    agent_application_module.SessionLocal = SessionLocal
    agent_application_module.crm_agent_graph_service = crm_agent_graph_service
    agent_root_runtime.new_flow_graph_service = crm_agent_graph_service
    task_execution.CRMAgentToolService = CRMAgentToolService
    selection.CRMAgentToolService = CRMAgentToolService
    field_common.agent_semantic_parser = agent_semantic_parser
    session_state.agent_semantic_parser = agent_semantic_parser
    follow_up_fields.agent_follow_up_quality_evaluator = agent_follow_up_quality_evaluator
    if hasattr(agent_semantic_parser, "assess_confirmation_intent"):
        confirmation_intent.agent_semantic_parser = agent_semantic_parser


def _interaction_for_event(event: dict, *, db: Optional[Session] = None, team_id: Optional[int] = None) -> Optional[dict]:
    agent_interactions._procurement_method_options = _procurement_method_options
    return _service_interaction_for_event(event, db=db, team_id=team_id)


def _with_interaction(event: dict, *, db: Optional[Session] = None, team_id: Optional[int] = None) -> dict:
    agent_interactions._procurement_method_options = _procurement_method_options
    return _service_with_interaction(event, db=db, team_id=team_id)


@router.post("/sessions", response_model=AgentSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_session(
    request: AgentCreateSessionRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    session = agent_session_crud.create(
        db,
        _build_session_create(request, team_id=team_id, user_id=current_user.id),
    )
    return session


@router.get("/sessions", response_model=PaginatedResponse[AgentSessionResponse])
async def list_agent_sessions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    session_status: Optional[str] = Query(None, description="会话状态"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    skip = (page - 1) * page_size
    items, total = agent_session_crud.list_by_user(
        db,
        team_id=team_id,
        user_id=current_user.id,
        status=session_status,
        skip=skip,
        limit=page_size,
    )
    return PaginatedResponse[AgentSessionResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/actions", response_model=PaginatedResponse[AgentWorkflowActionResponse])
async def list_agent_actions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    session_id: Optional[int] = Query(None, description="Agent会话ID"),
    workflow_id: Optional[str] = Query(None, description="Agent工作流ID"),
    action_status: Optional[str] = Query(None, description="动作状态"),
    source_type: Optional[str] = Query(None, description="动作来源"),
    target_type: Optional[str] = Query(None, description="目标业务对象类型"),
    target_id: Optional[int] = Query(None, description="目标业务对象ID"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if session_id is not None:
        _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    skip = (page - 1) * page_size
    total = agent_workflow_action_crud.count_actions(
        db,
        team_id=team_id,
        user_id=current_user.id,
        session_id=session_id,
        workflow_id=workflow_id,
        status=action_status,
        source_type=source_type,
        target_type=target_type,
        target_id=target_id,
    )
    items = agent_workflow_action_crud.list_actions(
        db,
        team_id=team_id,
        user_id=current_user.id,
        session_id=session_id,
        workflow_id=workflow_id,
        status=action_status,
        source_type=source_type,
        target_type=target_type,
        target_id=target_id,
        skip=skip,
        limit=page_size,
    )
    return PaginatedResponse[AgentWorkflowActionResponse](
        items=[_action_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/workflows/{workflow_id}", response_model=AgentWorkflowDetailResponse)
async def get_agent_workflow_detail(
    workflow_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    actions = agent_workflow_action_crud.list_by_workflow(
        db,
        workflow_id=workflow_id,
        team_id=team_id,
        user_id=current_user.id,
        include_system_actions=True,
    )
    if not actions:
        raise HTTPException(status_code=404, detail="Agent workflow not found")
    return _workflow_detail_response(workflow_id, actions)


@router.post("/workflows/{workflow_id}/retry", response_model=AgentWorkflowDetailResponse)
async def retry_agent_workflow(
    workflow_id: str,
    request: AgentWorkflowRetryRequest | None = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    actions = agent_workflow_action_crud.list_by_workflow(
        db,
        workflow_id=workflow_id,
        team_id=team_id,
        user_id=current_user.id,
        include_system_actions=True,
    )
    if not actions:
        raise HTTPException(status_code=404, detail="Agent workflow not found")
    session = None
    try:
        session_id = _workflow_session_id(actions)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if session_id is not None:
        session = _get_owned_session(
            db,
            team_id=team_id,
            user_id=current_user.id,
            session_id=session_id,
        )
    retry_request = request or AgentWorkflowRetryRequest()
    try:
        refreshed_actions = await agent_root_runtime.retry_workflow(
            db=db,
            workflow_id=workflow_id,
            actions=actions,
            session=session,
            team_id=team_id,
            user_id=current_user.id,
            authorization=_authorization_header(credentials),
            retry_source=retry_request.retry_source,
            reason=retry_request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _workflow_detail_response(workflow_id, refreshed_actions)


@router.post("/workflow-recovery/scan", response_model=AgentWorkflowRecoveryScanResponse)
async def scan_agent_workflow_recovery(
    request: AgentWorkflowRecoveryScanRequest | None = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    scan_request = request or AgentWorkflowRecoveryScanRequest()
    return await agent_workflow_recovery_service.recover_once(
        db,
        limit=scan_request.limit,
        dry_run=True,
        safe_action_types=scan_request.safe_action_types,
        team_id=team_id,
        user_id=current_user.id,
    )


@router.post(
    "/workflows/{workflow_id}/actions/{action_id}/retry",
    response_model=AgentWorkflowActionResponse,
)
async def retry_agent_workflow_action(
    workflow_id: str,
    action_id: str,
    request: AgentWorkflowActionRetryRequest | None = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    action = agent_workflow_action_crud.get_by_workflow_action(
        db,
        workflow_id=workflow_id,
        action_id=action_id,
        team_id=team_id,
        user_id=current_user.id,
        include_system_actions=True,
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Agent workflow action not found")
    retry_request = request or AgentWorkflowActionRetryRequest()
    session = None
    if action.session_id is not None:
        session = _get_owned_session(
            db,
            team_id=team_id,
            user_id=current_user.id,
            session_id=action.session_id,
        )
    try:
        action_result = await agent_root_runtime.retry_workflow_action(
            db=db,
            action=action,
            session=session,
            team_id=team_id,
            user_id=current_user.id,
            authorization=_authorization_header(credentials),
            retry_source=retry_request.retry_source,
            reason=retry_request.reason,
        )
        return _action_response(action_result)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/operations", response_model=list[AgentAsyncOperationResponse])
async def list_agent_async_operations(
    session_id: int,
    limit: int = Query(50, ge=1, le=100, description="异步操作数量"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    operations = agent_async_operation_service.list_session_projections(
        db,
        team_id=team_id,
        user_id=current_user.id,
        session_id=session_id,
        limit=limit,
    )
    if (
        _read_repair_customer_intelligence_operations(db, operations)
        or _read_repair_customer_activity_post_commit_operations(db, operations)
        or agent_async_operation_service.repair_unanchored_customer_activity_post_commit_sources(db, operations)
    ):
        operations = agent_async_operation_service.list_session_projections(
            db,
            team_id=team_id,
            user_id=current_user.id,
            session_id=session_id,
            limit=limit,
        )
    return operations


@router.get("/operations/{operation_public_id}", response_model=AgentAsyncOperationResponse)
async def get_agent_async_operation(
    operation_public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    operation = agent_async_operation_service.get_projection(
        db,
        team_id=team_id,
        user_id=current_user.id,
        public_id=operation_public_id,
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Agent async operation not found")
    if (
        _read_repair_customer_intelligence_operations(db, [operation])
        or _read_repair_customer_activity_post_commit_operations(db, [operation])
        or agent_async_operation_service.repair_unanchored_customer_activity_post_commit_sources(db, [operation])
    ):
        operation = agent_async_operation_service.get_projection(
            db,
            team_id=team_id,
            user_id=current_user.id,
            public_id=operation_public_id,
        )
        if operation is None:
            raise HTTPException(status_code=404, detail="Agent async operation not found")
    return operation


@router.get("/sessions/{session_id}/messages", response_model=PaginatedResponse[AgentMessageResponse])
async def list_agent_messages(
    session_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=200, description="每页数量"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    skip = (page - 1) * page_size
    items, total = agent_message_crud.list_by_session(
        db,
        session_id=session_id,
        team_id=team_id,
        user_id=current_user.id,
        skip=skip,
        limit=page_size,
    )
    return PaginatedResponse[AgentMessageResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/sessions/{session_id}/actions", response_model=PaginatedResponse[AgentWorkflowActionResponse])
async def list_agent_workflow_actions(
    session_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    action_status: Optional[str] = Query(None, description="动作状态"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    skip = (page - 1) * page_size
    total = agent_workflow_action_crud.count_by_session(
        db,
        session_id=session_id,
        team_id=team_id,
        user_id=current_user.id,
        status=action_status,
    )
    items = agent_workflow_action_crud.list_by_session(
        db,
        session_id=session_id,
        team_id=team_id,
        user_id=current_user.id,
        status=action_status,
        skip=skip,
        limit=page_size,
    )
    return PaginatedResponse[AgentWorkflowActionResponse](
        items=[_action_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/sessions/{session_id}/runtime/overview", response_model=AgentRuntimeOverviewResponse)
async def get_agent_runtime_overview(
    session_id: int,
    recent_action_limit: int = Query(10, ge=1, le=50, description="最近动作数量"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    session = _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    state = await agent_root_runtime.current_checkpoint_state(
        team_id=team_id,
        user_id=current_user.id,
        session_id=session.id,
        session_key=session.session_key,
    )
    action_counts = agent_workflow_action_crud.count_by_status_for_session(
        db,
        session_id=session.id,
        team_id=team_id,
        user_id=current_user.id,
        include_system_actions=True,
    )
    recent_actions = agent_workflow_action_crud.list_actions(
        db,
        team_id=team_id,
        user_id=current_user.id,
        session_id=session.id,
        skip=0,
        limit=recent_action_limit,
    )
    current_interrupt = state.get("current_interrupt") if isinstance(state, dict) else None
    checkpoint_id = state.get("checkpoint_id") if isinstance(state, dict) else None
    runtime_status = state.get("runtime_status") if isinstance(state, dict) else None
    return AgentRuntimeOverviewResponse(
        session_id=session.id,
        session_key=session.session_key,
        runtime_status=runtime_status if isinstance(runtime_status, str) else None,
        checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
        has_interrupt=bool(current_interrupt),
        current_interrupt=current_interrupt if isinstance(current_interrupt, dict) else None,
        action_summary=AgentRuntimeActionSummaryResponse(
            total=sum(action_counts.values()),
            by_status=action_counts,
            waiting_action_count=action_counts.get("WAITING_USER", 0),
            failed_action_count=action_counts.get("FAILED", 0),
            blocked_action_count=action_counts.get("BLOCKED", 0),
        ),
        recent_actions=recent_actions,
        values=state,
    )


@router.get("/sessions/{session_id}/runtime/state", response_model=AgentRuntimeCheckpointStateResponse)
async def get_agent_runtime_state(
    session_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    session = _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    state = await agent_root_runtime.current_checkpoint_state(
        team_id=team_id,
        user_id=current_user.id,
        session_id=session.id,
        session_key=session.session_key,
    )
    return AgentRuntimeCheckpointStateResponse(
        session_id=session.id,
        session_key=session.session_key,
        values=state,
    )


@router.get("/sessions/{session_id}/runtime/history", response_model=AgentRuntimeHistoryResponse)
async def list_agent_runtime_history(
    session_id: int,
    before_checkpoint_id: Optional[str] = Query(None, description="从指定checkpoint之前继续读取"),
    limit: int = Query(20, ge=1, le=100, description="返回checkpoint数量"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    session = _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    history = await agent_root_runtime.state_history(
        team_id=team_id,
        user_id=current_user.id,
        session_id=session.id,
        session_key=session.session_key,
        before_checkpoint_id=before_checkpoint_id,
        limit=limit,
    )
    items = [AgentRuntimeHistoryItemResponse(**item) for item in history]
    return AgentRuntimeHistoryResponse(
        session_id=session.id,
        session_key=session.session_key,
        items=items,
        total=len(items),
        before_checkpoint_id=before_checkpoint_id,
        limit=limit,
    )


@router.get(
    "/sessions/{session_id}/runtime/checkpoints/{checkpoint_id}",
    response_model=AgentRuntimeCheckpointStateResponse,
)
async def get_agent_runtime_checkpoint_state(
    session_id: int,
    checkpoint_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    session = _get_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    state = await agent_root_runtime.checkpoint_state_at(
        checkpoint_id=checkpoint_id,
        team_id=team_id,
        user_id=current_user.id,
        session_id=session.id,
        session_key=session.session_key,
    )
    return AgentRuntimeCheckpointStateResponse(
        session_id=session.id,
        session_key=session.session_key,
        checkpoint_id=checkpoint_id,
        values=state,
    )


@router.post("/chat/stream")
async def stream_agent_chat(
    request: AgentChatRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    user_id = current_user.id
    _sync_legacy_agent_overrides()

    async def generate_sse():
        async for event in agent_application_service.stream_chat_events(
            content=request.content,
            team_id=team_id,
            user_id=user_id,
            authorization=_authorization_header(credentials),
            session_id=request.session_id,
            session_key=request.session_key,
            turn_input=AgentTurnInput.text(
                request.content,
                metadata=request.interaction_metadata or {},
            ),
        ):
            yield _encode_sse(event)

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _action_status_counts(actions: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        status = getattr(action, "status", None)
        if isinstance(status, str):
            counts[status] = counts.get(status, 0) + 1
    return counts


def _workflow_detail_response(workflow_id: str, actions: list[object]) -> AgentWorkflowDetailResponse:
    action_counts = _action_status_counts(actions)
    return AgentWorkflowDetailResponse(
        workflow_id=workflow_id,
        workflow_status=_derive_workflow_status(actions),
        status_reason=_derive_workflow_status_reason(actions),
        action_summary=AgentRuntimeActionSummaryResponse(
            total=sum(action_counts.values()),
            by_status=action_counts,
            waiting_action_count=action_counts.get("WAITING_USER", 0),
            failed_action_count=action_counts.get("FAILED", 0),
            blocked_action_count=action_counts.get("BLOCKED", 0),
        ),
        nodes=_workflow_nodes(actions),
        edges=_workflow_edges(actions),
        actions=[_action_response(action) for action in actions],
    )


def _action_response(action: object) -> AgentWorkflowActionResponse:
    capability = action_workflow.action_capability(getattr(action, "action_type", None))
    response = AgentWorkflowActionResponse.model_validate(action)
    return response.model_copy(update={
        "capability": {
            "action_type": capability.action_type,
            "tool_name": capability.tool_name,
            "is_write": capability.is_write,
            "requires_confirmation": capability.requires_confirmation,
            "requires_user_authorization": capability.requires_user_authorization,
            "allows_background_recovery": capability.allows_background_recovery,
            "parallel_safe": capability.parallel_safe,
            "requires_idempotency_key": capability.requires_idempotency_key,
            "required_payload_fields": sorted(capability.required_payload_fields),
            "flags": sorted(capability.flags),
        },
    })


def _workflow_session_id(actions: list[object]) -> int | None:
    session_ids = {
        getattr(action, "session_id", None)
        for action in actions
        if isinstance(getattr(action, "session_id", None), int)
    }
    if len(session_ids) > 1:
        raise ValueError("Agent workflow actions span multiple sessions")
    if len(session_ids) == 1:
        return next(iter(session_ids))
    return None


def _derive_workflow_status(actions: list[object]) -> str:
    if any(getattr(action, "status", None) == "BLOCKED" for action in actions):
        return "BLOCKED"
    if any(getattr(action, "status", None) == "FAILED" and getattr(action, "blocking", False) for action in actions):
        return "FAILED"
    if any(getattr(action, "status", None) == "WAITING_USER" for action in actions):
        return "WAITING_USER"
    if any(getattr(action, "status", None) in {"PLANNED", "RUNNING"} for action in actions):
        return "RUNNING"
    if actions and all(getattr(action, "status", None) in _WORKFLOW_TERMINAL_STATUSES for action in actions):
        if any(getattr(action, "status", None) == "FAILED" for action in actions):
            return "COMPLETED_WITH_ERRORS"
        return "COMPLETED"
    return "UNKNOWN"


def _derive_workflow_status_reason(actions: list[object]) -> str | None:
    for status in ("BLOCKED", "FAILED", "WAITING_USER"):
        matching = [action for action in actions if getattr(action, "status", None) == status]
        if matching:
            action_ids = ", ".join(str(getattr(action, "action_id", "")) for action in matching[:3])
            return f"{status}: {action_ids}"
    return None


def _workflow_nodes(actions: list[object]) -> list[AgentWorkflowGraphNodeResponse]:
    return [
        AgentWorkflowGraphNodeResponse(
            action_id=str(action.action_id),
            action_type=str(action.action_type),
            status=str(action.status),
            status_reason=action.status_reason,
            error_message=action.error_message,
            scope=str(action.scope),
            blocking=bool(action.blocking),
            parent_action_id=action.parent_action_id,
            depends_on=_dependency_action_ids(action.dependency_json),
            parallel_group=_parallel_group(action.dependency_json),
        )
        for action in actions
    ]


def _workflow_edges(actions: list[object]) -> list[AgentWorkflowGraphEdgeResponse]:
    known_action_ids = {str(action.action_id) for action in actions}
    edges: list[AgentWorkflowGraphEdgeResponse] = []
    seen: set[tuple[str, str, str]] = set()
    for action in actions:
        to_action_id = str(action.action_id)
        if isinstance(action.parent_action_id, str) and action.parent_action_id in known_action_ids:
            _append_workflow_edge(edges, seen, action.parent_action_id, to_action_id, "parent")
        for dependency_action_id in _dependency_action_ids(action.dependency_json):
            if dependency_action_id in known_action_ids:
                _append_workflow_edge(edges, seen, dependency_action_id, to_action_id, "depends_on")
    return edges


def _append_workflow_edge(
    edges: list[AgentWorkflowGraphEdgeResponse],
    seen: set[tuple[str, str, str]],
    from_action_id: str,
    to_action_id: str,
    relation: str,
) -> None:
    key = (from_action_id, to_action_id, relation)
    if key in seen:
        return
    seen.add(key)
    edges.append(
        AgentWorkflowGraphEdgeResponse(
            from_action_id=from_action_id,
            to_action_id=to_action_id,
            relation=relation,
        )
    )


def _dependency_action_ids(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    raw_depends_on = value.get("depends_on")
    if not isinstance(raw_depends_on, list):
        return []
    return [item.strip() for item in raw_depends_on if isinstance(item, str) and item.strip()]


def _parallel_group(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    parallel_group = value.get("parallel_group")
    if isinstance(parallel_group, str) and parallel_group.strip():
        return parallel_group.strip()
    return None
