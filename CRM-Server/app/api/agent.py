"""CRM AI Agent API."""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user, get_current_user_team, security
from app.crud.agent import agent_message_crud, agent_session_crud, agent_task_crud
from app.models.agent import AgentMessageRole, AgentTaskStatus
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentCreateSessionRequest,
    AgentMessageCreate,
    AgentMessageResponse,
    AgentSessionCreate,
    AgentSessionResponse,
    AgentTaskCreate,
    AgentTaskUpdate,
)
from app.schemas.common import PaginatedResponse
from app.services.agent import crm_agent_graph_service
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext
from app.utils.sse_encoder import SSEJsonEncoder


router = APIRouter(prefix="/v1/agent", tags=["CRM AI Agent"])


def _new_session_key() -> str:
    return f"agent_{uuid.uuid4().hex}"


def _build_session_create(
    request: AgentCreateSessionRequest,
    team_id: int,
    user_id: int,
) -> AgentSessionCreate:
    return AgentSessionCreate(
        session_key=_new_session_key(),
        team_id=team_id,
        user_id=user_id,
        title=request.title,
        context_json=request.context_json,
    )


def _get_owned_session(
    db: Session,
    team_id: int,
    user_id: int,
    session_id: Optional[int] = None,
    session_key: Optional[str] = None,
):
    if session_id is not None:
        session = agent_session_crud.get_by_id(db, session_id, team_id=team_id, user_id=user_id)
    elif session_key:
        session = agent_session_crud.get_by_key(db, session_key, team_id=team_id, user_id=user_id)
    else:
        session = None

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent会话不存在")
    return session


def _encode_sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, cls=SSEJsonEncoder)}\n\n"


def _authorization_header(credentials: HTTPAuthorizationCredentials) -> str:
    return f"{credentials.scheme} {credentials.credentials}"


def _new_task_key() -> str:
    return f"task_{uuid.uuid4().hex}"


def _is_confirmation(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {"是", "确认", "可以", "执行", "好的", "好", "yes", "y", "ok"}


def _create_waiting_task_from_event(db: Session, event: dict, team_id: int, user_id: int, session_id: int):
    action = event.get("action")
    payload = event.get("payload") or {}
    task = agent_task_crud.create(
        db,
        AgentTaskCreate(
            task_key=_new_task_key(),
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            intent="CUSTOMER_FOLLOW_UP" if action == "create_customer_follow_up" else None,
            status=AgentTaskStatus.WAITING_USER,
            target_type="customer",
            target_id=payload.get("customer_id"),
            summary=f"等待确认执行：{action}",
            input_json=payload,
            state_json={"action": action, "payload": payload, "customer": event.get("customer")},
        ),
    )
    event["task_id"] = task.id
    event["task_key"] = task.task_key
    return task


async def _execute_waiting_task(
    db: Session,
    task,
    team_id: int,
    user_id: int,
    session_id: int,
    authorization: str,
):
    state = task.state_json or {}
    action = state.get("action")
    payload = state.get("payload") or {}
    customer = state.get("customer") or {}
    context = AgentToolContext(
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task.id,
        authorization=authorization,
    )
    tool_service = CRMAgentToolService()

    agent_task_crud.update(db, task, AgentTaskUpdate(status=AgentTaskStatus.RUNNING))
    if action == "create_customer_follow_up":
        result = await tool_service.create_customer_follow_up(
            context,
            customer_id=payload["customer_id"],
            customer_name=customer.get("account_name"),
            content=payload["content"],
            next_action=payload.get("next_action"),
            next_follow_time=payload.get("next_follow_time_text"),
            idempotency_suffix=task.task_key,
        )
    else:
        result = None

    if result and result.success:
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(status=AgentTaskStatus.COMPLETED, result_json=result.data),
        )
        return result, "跟进记录已创建。"

    error_message = result.error_message if result else f"暂不支持的执行动作：{action}"
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.FAILED, error_message=error_message),
    )
    return result, f"执行失败：{error_message}"


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


@router.post("/chat/stream")
async def stream_agent_chat(
    request: AgentChatRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    user_id = current_user.id

    async def generate_sse():
        db = SessionLocal()
        try:
            if request.session_id or request.session_key:
                session = _get_owned_session(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=request.session_id,
                    session_key=request.session_key,
                )
            else:
                session = agent_session_crud.create(
                    db,
                    AgentSessionCreate(
                        session_key=_new_session_key(),
                        team_id=team_id,
                        user_id=user_id,
                        title=request.content[:50],
                    ),
                )

            yield _encode_sse({
                "event": "session",
                "session_id": session.id,
                "session_key": session.session_key,
            })

            user_message = agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    event_type="user_message",
                    content=request.content,
                ),
            )
            yield _encode_sse({
                "event": "message",
                "role": AgentMessageRole.USER,
                "message_id": user_message.id,
                "content": user_message.content,
            })

            assistant_content = None
            authorization = _authorization_header(credentials)
            if _is_confirmation(request.content):
                task = agent_task_crud.get_latest_waiting(
                    db,
                    session_id=session.id,
                    team_id=team_id,
                    user_id=user_id,
                )
                if task:
                    result, assistant_content = await _execute_waiting_task(
                        db,
                        task,
                        team_id=team_id,
                        user_id=user_id,
                        session_id=session.id,
                        authorization=authorization,
                    )
                    if result:
                        yield _encode_sse(result.to_event())
                    yield _encode_sse({
                        "event": "task_completed" if result and result.success else "task_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                    })
                    yield _encode_sse({"event": "final", "content": assistant_content})
                else:
                    assistant_content = "当前没有等待确认的操作。"
                    yield _encode_sse({"event": "final", "content": assistant_content})
            else:
                async for event in crm_agent_graph_service.stream_events({
                    "db": db,
                    "team_id": team_id,
                    "user_id": user_id,
                    "session_id": session.id,
                    "content": request.content,
                    "authorization": authorization,
                }):
                    if event.get("event") == "confirmation_required":
                        _create_waiting_task_from_event(db, event, team_id, user_id, session.id)
                    if event.get("event") == "final":
                        assistant_content = event.get("content")
                    yield _encode_sse(event)

            if not assistant_content:
                assistant_content = "Agent 已完成处理。"

            assistant_message = agent_message_crud.create(
                db,
                AgentMessageCreate(
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    role=AgentMessageRole.ASSISTANT,
                    event_type="assistant_message",
                    content=assistant_content,
                    payload_json={"source": "langgraph"},
                ),
            )
            yield _encode_sse({
                "event": "message",
                "role": AgentMessageRole.ASSISTANT,
                "message_id": assistant_message.id,
                "content": assistant_content,
            })
            yield _encode_sse({"event": "done", "session_id": session.id})
        except HTTPException as exc:
            yield _encode_sse({"event": "error", "message": exc.detail, "status_code": exc.status_code})
        except Exception as exc:
            yield _encode_sse({"event": "error", "message": f"Agent服务异常：{str(exc)}"})
        finally:
            db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
