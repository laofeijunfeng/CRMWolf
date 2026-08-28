"""CRM AI Agent API."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, security
from app.crud.agent import agent_session_crud, agent_workflow_action_crud
from app.crud.permission import permission_crud
from app.crud.sales_commitment import follow_up_task_confirmation_case_crud
from app.models.user import User
from app.schemas.agent import (
    AgentAsyncOperationResponse,
    AgentCreateSessionRequest,
    AgentSessionResponse,
    AgentSSEEventEnvelope,
    AgentWorkflowActionResponse,
    AgentWorkflowActionSummaryResponse,
    AgentWorkflowDetailResponse,
    AgentWorkflowGraphEdgeResponse,
    AgentWorkflowGraphNodeResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.agent import action_workflow
from app.services.agent.application import agent_application_service
from app.services.agent.async_operation_service import (
    TERMINAL_OPERATION_STATUSES,
    AgentAsyncOperationProjection,
    agent_async_operation_service,
)
from app.services.agent.durable_work import agent_durable_work_recovery_service
from app.services.agent.follow_up_confirmation_projection import (
    follow_up_confirmation_agent_ui_projection,
)
from app.services.agent.sessions import build_session_create, require_owned_session
from app.services.agent.turns import AgentTurnRepository
from app.services.agent.ui.actions import AgentUIActionRepository
from app.services.agent.ui.read_projection import project_interaction_action_states
from app.services.agent.ui.schemas import AgentChatRequest, AgentUIEnvelope
from app.services.customer_activity_post_commit_operation_projector import (
    customer_activity_post_commit_operation_projector,
)
from app.services.customer_intelligence_operation_projector import (
    customer_intelligence_operation_projector,
)
from app.utils.sse_encoder import SSEJsonEncoder

router = APIRouter(prefix="/v1/agent", tags=["CRM AI Agent"])
logger = logging.getLogger(__name__)
agent_turn_repository = AgentTurnRepository()
agent_ui_action_repository = AgentUIActionRepository()


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


def _encode_sse(event: AgentSSEEventEnvelope) -> str:
    payload = event.model_dump(mode="json", exclude_none=True)
    return f"data: {json.dumps(payload, ensure_ascii=False, cls=SSEJsonEncoder)}\n\n"


def _authorization_header(credentials: HTTPAuthorizationCredentials) -> str:
    return f"{credentials.scheme} {credentials.credentials}"



@router.post("/sessions", response_model=AgentSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_session(
    request: AgentCreateSessionRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    session = agent_session_crud.create(
        db,
        build_session_create(request, team_id=team_id, user_id=current_user.id),
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
        require_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
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


@router.get("/sessions/{session_id}/operations", response_model=list[AgentAsyncOperationResponse])
async def list_agent_async_operations(
    session_id: int,
    limit: int = Query(50, ge=1, le=100, description="异步操作数量"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    require_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    try:
        recovered = agent_durable_work_recovery_service.recover_session(
            db,
            team_id=team_id,
            user_id=current_user.id,
            session_id=session_id,
        )
        if recovered:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "读取 Agent 异步操作时恢复持久任务失败: session_id=%s",
            session_id,
        )

    operations = agent_async_operation_service.list_session_projections(
        db,
        team_id=team_id,
        user_id=current_user.id,
        session_id=session_id,
        limit=limit,
    )
    repaired = _read_repair_customer_intelligence_operations(db, operations)
    if _read_repair_customer_activity_post_commit_operations(db, operations):
        repaired = True
    if repaired:
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
    repaired = _read_repair_customer_intelligence_operations(db, [operation])
    if _read_repair_customer_activity_post_commit_operations(db, [operation]):
        repaired = True
    if repaired:
        operation = agent_async_operation_service.get_projection(
            db,
            team_id=team_id,
            user_id=current_user.id,
            public_id=operation_public_id,
        )
        if operation is None:
            raise HTTPException(status_code=404, detail="Agent async operation not found")
    return operation


@router.get(
    "/sessions/{session_id}/messages",
    response_model=PaginatedResponse[AgentUIEnvelope],
)
async def list_agent_messages(
    session_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=200, description="每页数量"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    require_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
    permission_codes = frozenset(
        permission.code
        for permission in permission_crud.get_user_permissions(
            db,
            user_id=current_user.id,
            team_id=team_id,
        )
        if isinstance(getattr(permission, "code", None), str) and permission.code
    )
    try:
        await follow_up_confirmation_agent_ui_projection.project_pending(
            db,
            team_id=team_id,
            user_id=current_user.id,
            session_id=session_id,
            authorization=f"Bearer {credentials.credentials}",
            permission_codes=permission_codes,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "读取 Agent 历史时投影跟进任务确认失败: session_id=%s",
            session_id,
        )
    skip = (page - 1) * page_size
    records, total = agent_turn_repository.list_visible_by_session(
        db,
        session_id=session_id,
        team_id=team_id,
        user_id=current_user.id,
        skip=skip,
        limit=page_size,
    )
    items = [record.ui for record in records]
    action_ids = {
        block.submit_action_id
        for item in items
        for block in item.blocks
        if getattr(block, "type", None) == "interaction"
        and getattr(block, "submit_action_id", None) is not None
    }
    if action_ids:
        actions = agent_ui_action_repository.list_owned_for_messages(
            db,
            team_id=team_id,
            user_id=current_user.id,
            session_id=session_id,
            message_ids=[item.message_id for item in items],
        )
        follow_up_actions = [
            action
            for action in actions
            if action.target.get("business_action") == "resolve_follow_up_task_confirmation_case"
            or isinstance(action.target.get("follow_up_confirmation_case_public_id"), str)
        ]
        explicit_case_actions = [
            action
            for action in follow_up_actions
            if isinstance(action.target.get("follow_up_confirmation_case_public_id"), str)
            and action.target.get("follow_up_confirmation_case_public_id")
        ]
        unbound_follow_up_actions = [
            action for action in follow_up_actions if action not in explicit_case_actions
        ]
        follow_up_case_statuses_by_action: dict[str, str] = {
            action.public_id: "READ_ONLY" for action in unbound_follow_up_actions
        }

        if explicit_case_actions:
            explicit_case_ids = [
                action.target["follow_up_confirmation_case_public_id"]
                for action in explicit_case_actions
            ]
            try:
                follow_up_case_statuses = follow_up_task_confirmation_case_crud.list_statuses_by_public_ids(
                    db,
                    team_id=team_id,
                    public_ids=explicit_case_ids,
                )
            except Exception:
                db.rollback()
                logger.exception(
                    "读取 Agent 跟进确认 Case 状态失败，显式绑定卡片降级为只读: session_id=%s",
                    session_id,
                )
                follow_up_case_statuses_by_action.update(
                    {action.public_id: "LOOKUP_FAILED" for action in explicit_case_actions}
                )
            else:
                for action in explicit_case_actions:
                    case_public_id = action.target["follow_up_confirmation_case_public_id"]
                    follow_up_case_statuses_by_action[action.public_id] = follow_up_case_statuses.get(
                        case_public_id,
                        "MISSING",
                    )

        items = project_interaction_action_states(
            items,
            actions,
            follow_up_confirmation_case_statuses_by_action=follow_up_case_statuses_by_action,
        )
    return PaginatedResponse[AgentUIEnvelope](
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
    require_owned_session(db, team_id=team_id, user_id=current_user.id, session_id=session_id)
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


@router.post("/chat/stream")
async def stream_agent_chat(
    request: AgentChatRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    user_id = current_user.id
    async def generate_sse():
        async for event in agent_application_service.stream_chat_events(
            request_input=request.input,
            client_request_id=request.client_request_id,
            team_id=team_id,
            user_id=user_id,
            authorization=_authorization_header(credentials),
            session_id=request.session_id,
            session_key=request.session_key,
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
        action_summary=AgentWorkflowActionSummaryResponse(
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
    for workflow_status in ("BLOCKED", "FAILED", "WAITING_USER"):
        matching = [
            action
            for action in actions
            if getattr(action, "status", None) == workflow_status
        ]
        if matching:
            action_ids = ", ".join(str(getattr(action, "action_id", "")) for action in matching[:3])
            return f"{workflow_status}: {action_ids}"
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
