"""CRM AI Agent API."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user, get_current_user_team, security
from app.crud.agent import agent_message_crud, agent_session_crud
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentCreateSessionRequest,
    AgentMessageResponse,
    AgentRuntimeCheckpointStateResponse,
    AgentRuntimeHistoryItemResponse,
    AgentRuntimeHistoryResponse,
    AgentSessionResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.agent import application as agent_application_module
from app.services.agent import confirmation_intent, field_common, follow_up_fields, selection, session_state, task_execution
from app.services.agent import interactions as agent_interactions
from app.services.agent.application import agent_application_service
from app.services.agent.graph import crm_agent_graph_service
from app.services.agent.input import AgentTurnInput
from app.services.agent.interactions import (
    _interaction_for_event as _service_interaction_for_event,
    _procurement_method_options,
    _with_interaction as _service_with_interaction,
)
from app.services.agent.quality import agent_follow_up_quality_evaluator
from app.services.agent.semantic import agent_semantic_parser
from app.services.agent.session_state import (
    _build_session_create,
    _get_owned_session,
)
from app.services.agent.root_runtime import agent_root_runtime
from app.services.agent.tools import CRMAgentToolService
from app.utils.sse_encoder import SSEJsonEncoder


router = APIRouter(prefix="/v1/agent", tags=["CRM AI Agent"])


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
