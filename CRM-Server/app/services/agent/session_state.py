"""Agent session state and pending task memory helpers."""
from __future__ import annotations

from copy import deepcopy
import json
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.agent import agent_session_crud, agent_task_crud
from app.crud.procurement import procurement_method_crud
from app.models.agent import AgentTaskStatus
from app.models.customer import Customer
from app.schemas.agent import (
    AgentCreateSessionRequest,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentTaskCreate,
    AgentTaskUpdate,
)
from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.quality import AgentFollowUpQualityEvaluatorError, agent_follow_up_quality_evaluator
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent.schemas import (
    AgentHITLPolicy,
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentSemanticParseResult,
)
from app.services.agent.semantic import AgentSemanticParserError, agent_semantic_parser
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.tool_registry import AgentToolRegistry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext
from app.utils.sse_encoder import SSEJsonEncoder


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

def _remember_current_customer(db: Session, session, customer: Optional[dict]) -> None:
    if not customer or not customer.get("id") or not customer.get("account_name"):
        return
    context = dict(session.context_json or {})
    context["current_customer"] = {
        "id": customer.get("id"),
        "account_name": customer.get("account_name"),
        "owner_info": customer.get("owner_info"),
        "collaborator_infos": customer.get("collaborator_infos") or [],
    }
    agent_session_crud.update(db, session, AgentSessionUpdate(context_json=context))

def _remember_pending_task(db: Session, session, task) -> None:
    if not task or task.status != AgentTaskStatus.WAITING_USER:
        return
    context = dict(session.context_json or {})
    context["current_pending_task"] = {
        "id": task.id,
        "action": (task.state_json or {}).get("action"),
        "intent": task.intent,
        "target_id": task.target_id,
        "summary": task.summary,
    }
    agent_session_crud.update(db, session, AgentSessionUpdate(context_json=context))

def _clear_pending_task(db: Session, session, task_id: Optional[int] = None) -> None:
    context = dict(session.context_json or {})
    pending = context.get("current_pending_task")
    if task_id is not None and isinstance(pending, dict) and pending.get("id") != task_id:
        return
    if "current_pending_task" not in context:
        return
    context.pop("current_pending_task", None)
    agent_session_crud.update(db, session, AgentSessionUpdate(context_json=context))

def _suspend_pending_task(db: Session, session, task, reason: str) -> None:
    if not task:
        return
    state = dict(task.state_json or {})
    state["suspended_reason"] = reason
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.SUSPENDED, state_json=state),
    )
    context = dict(session.context_json or {})
    suspended = context.get("suspended_pending_tasks")
    if not isinstance(suspended, list):
        suspended = []
    suspended.insert(0, {
        "id": task.id,
        "action": state.get("action"),
        "intent": task.intent,
        "target_id": task.target_id,
        "summary": task.summary,
        "reason": reason,
    })
    context["suspended_pending_tasks"] = suspended[:5]
    if isinstance(context.get("current_pending_task"), dict) and context["current_pending_task"].get("id") == task.id:
        context.pop("current_pending_task", None)
    agent_session_crud.update(db, session, AgentSessionUpdate(context_json=context))

def _get_current_waiting_task(db: Session, session, team_id: int, user_id: int):
    pending = (session.context_json or {}).get("current_pending_task")
    if isinstance(pending, dict) and pending.get("id"):
        task = agent_task_crud.get_by_id(db, pending["id"], team_id=team_id, user_id=user_id)
        if task and task.status == AgentTaskStatus.WAITING_USER:
            return task
    return agent_task_crud.get_latest_waiting(
        db,
        session_id=session.id,
        team_id=team_id,
        user_id=user_id,
    )

def _pending_task_snapshot(task) -> dict[str, Any]:
    return {
        "id": task.id,
        "intent": task.intent,
        "target_type": task.target_type,
        "target_id": task.target_id,
        "summary": task.summary,
        "state": task.state_json or {},
        "input": task.input_json or {},
    }

def _memory_snapshot_for_session(session, task=None) -> AgentMemorySnapshot:
    return AgentMemorySnapshot(
        pending_task=_pending_task_snapshot(task) if task else None,
        session_context=session.context_json or {},
    )

def _is_high_confidence_new_flow(decision: AgentPendingInterruptionDecision) -> bool:
    if decision.decision != "START_NEW_FLOW":
        return False
    if decision.confidence < 0.85:
        return False
    if decision.is_field_supplement:
        return False
    return bool(decision.detected_customer_name or decision.detected_intent)

def _is_ambiguous_pending_interruption(decision: AgentPendingInterruptionDecision) -> bool:
    if decision.decision == "ASK_USER":
        return True
    return decision.decision == "START_NEW_FLOW" and decision.confidence >= 0.55

async def _assess_pending_interruption(db: Session, *, team_id: int, session, task, user_message: str):
    try:
        return await agent_semantic_parser.assess_pending_interruption(
            db,
            team_id=team_id,
            user_message=user_message,
            pending_task=_pending_task_snapshot(task),
            memory=_memory_snapshot_for_session(session, task),
        )
    except Exception:
        return AgentPendingInterruptionDecision(
            decision="CONTINUE_PENDING",
            confidence=0.0,
            reason="挂起任务判断不可用，保守继续当前任务。",
            is_field_supplement=True,
        )

def _is_confirmation(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {"是", "确认", "可以", "执行", "好的", "好", "yes", "y", "ok"}

def _is_rejection(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {"否", "不", "不用", "不要", "取消", "先不处理", "no", "n"}
