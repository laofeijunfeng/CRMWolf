"""Agent session state and pending task memory helpers."""
from __future__ import annotations

from copy import deepcopy
import json
import uuid
from typing import Optional

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
from app.services.agent import action_workflow
from app.services.agent import business_rules
from app.services.agent import session_projection
from app.services.agent import task_display
from app.services.agent import workflow_action_ledger
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.quality import AgentFollowUpQualityEvaluatorError, agent_follow_up_quality_evaluator
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent.schemas import (
    AgentHITLPolicy,
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentSemanticParseResult,
    AgentTurnRelationDecision,
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

def _remember_current_customer(
    db: Session,
    session,
    customer: Optional[dict],
    *,
    commit: bool = True,
) -> None:
    context = session_projection.with_current_customer(session_projection.session_context(session), customer)
    if context == session_projection.session_context(session):
        return
    agent_session_crud.update(
        db,
        session,
        AgentSessionUpdate(context_json=context),
        commit=commit,
    )

def _suspend_pending_task(
    db: Session,
    session,
    task,
    reason: str,
    *,
    suspension_kind: str | None = None,
    commit: bool = True,
) -> None:
    if not task:
        return
    state = dict(task.state_json or {})
    state["suspended_reason"] = reason
    if suspension_kind:
        state["suspension_kind"] = suspension_kind
        if suspension_kind == "dismissed":
            state["dismissed"] = True
            state["dismissed_reason"] = reason
            workflow = action_workflow.workflow_from_task_state(state)
            if action_workflow.is_optional_skip_workflow(workflow):
                state["workflow"] = action_workflow.mark_skipped(
                    workflow,
                    reason=reason,
                    source="langgraph_resume",
                )
                workflow_action_ledger.mark_action_skipped(
                    db,
                    workflow=workflow,
                    team_id=task.team_id,
                    user_id=task.user_id,
                    task_id=task.id,
                    reason=reason,
                    source_type=workflow_action_ledger.SOURCE_PENDING_RESUME,
                    decision={
                        "suspension_kind": suspension_kind,
                        "decision": "skip_current_action",
                    },
                    commit=commit,
                )
    elif state.get("suspension_kind") is None:
        state["suspension_kind"] = "paused"
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.SUSPENDED, state_json=state),
        commit=commit,
    )

def _get_latest_suspended_task(db: Session, session, team_id: int, user_id: int):
    for task in agent_task_crud.list_by_session(db, session.id, team_id=team_id, user_id=user_id):
        if task.status == AgentTaskStatus.SUSPENDED and _is_resumable_task(task):
            return task
    return None

def _resume_suspended_task(db: Session, session, task):
    state = dict(task.state_json or {})
    state.pop("suspended_reason", None)
    task = agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.WAITING_USER, state_json=state),
    )
    return task

def _is_resumable_task(task) -> bool:
    state = task.state_json or {}
    if state.get("dismissed") is True or state.get("suspension_kind") == "dismissed":
        return False
    action = (task.state_json or {}).get("action")
    return action in {
        "collect_opportunity_fields",
        "create_opportunity",
    }

def _task_input_payload(task_input: dict[str, object]) -> dict[str, object]:
    nested_payload = task_input.get("payload")
    if isinstance(nested_payload, dict):
        return nested_payload
    return task_input

def _pending_task_display_summary(
    task,
    *,
    state: dict[str, object],
    task_input: dict[str, object],
    payload: dict[str, object],
    customer: dict[str, object],
    missing_fields: list[str],
) -> str:
    action = state.get("action") or task_input.get("action")
    return task_display.pending_task_display_summary(
        action=action,
        summary=task.summary,
        intent=task.intent,
        state=state,
        task_input=task_input,
        payload=payload,
        customer=customer,
        missing_fields=missing_fields,
    )

def _pending_task_snapshot(task) -> dict[str, object]:
    state = task.state_json or {}
    task_input = task.input_json or {}
    payload = _task_input_payload(task_input) if isinstance(task_input, dict) else {}
    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    if not customer and isinstance(state.get("customer"), dict):
        customer = state["customer"]
    missing_fields = []
    if isinstance(state.get("missing_fields"), list):
        missing_fields = state["missing_fields"]
    elif isinstance(task_input, dict) and isinstance(task_input.get("missing_fields"), list):
        missing_fields = task_input["missing_fields"]
    elif isinstance(payload.get("missing_fields"), list):
        missing_fields = payload["missing_fields"]
    return {
        "id": task.id,
        "intent": task.intent,
        "target_type": task.target_type,
        "target_id": task.target_id,
        "summary": task.summary,
        "display_summary": _pending_task_display_summary(
            task,
            state=state,
            task_input=task_input,
            payload=payload,
            customer=customer,
            missing_fields=missing_fields,
        ),
        "action": state.get("action") or (task_input.get("action") if isinstance(task_input, dict) else None),
        "customer_name": customer.get("account_name") or customer.get("name") or state.get("customer_name"),
        "missing_fields": missing_fields,
        "status": getattr(task.status, "value", task.status),
        "created_time": getattr(task, "created_time", None),
        "updated_time": getattr(task, "updated_time", None),
        "state": state,
        "input": task_input,
    }

def _memory_snapshot_for_session(session, task=None) -> AgentMemorySnapshot:
    return AgentMemorySnapshot(
        pending_task=_pending_task_snapshot(task) if task else None,
        session_context=session_projection.session_context(session),
    )

def _suspended_task_snapshots(db: Session, session, team_id: int, user_id: int) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    for task in agent_task_crud.list_by_session(db, session.id, team_id=team_id, user_id=user_id):
        if task.id in seen_ids:
            continue
        if task.status == AgentTaskStatus.SUSPENDED and _is_suspended_business_draft(task):
            snapshots.append(_pending_task_snapshot(task))
            seen_ids.add(task.id)
        if len(snapshots) >= 5:
            break
    return snapshots[:5]


def _is_suspended_business_draft(task) -> bool:
    action = (task.state_json or {}).get("action")
    return action in {
        "collect_opportunity_fields",
        "create_opportunity",
    }

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

async def _assess_turn_relation(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    session,
    task=None,
    user_message: str,
) -> AgentTurnRelationDecision:
    suspended_tasks = _suspended_task_snapshots(db, session, team_id, user_id)
    try:
        return await agent_semantic_parser.assess_turn_relation(
            db,
            team_id=team_id,
            user_message=user_message,
            active_task=_pending_task_snapshot(task) if task else None,
            suspended_tasks=suspended_tasks,
            memory=_memory_snapshot_for_session(session, task),
            current_date=agent_temporal_resolver.now().date(),
        )
    except Exception:
        return AgentTurnRelationDecision(
            relation="START_NEW_FLOW",
            confidence=0.0,
            reason="本轮关系判断不可用，保守进入新流程，不自动恢复挂起草稿。",
        )

def _is_confirmation(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {"是", "确认", "可以", "执行", "好的", "好", "yes", "y", "ok"}

def _is_rejection(content: str) -> bool:
    normalized = content.strip().lower()
    return normalized in {"否", "不", "不用", "不要", "取消", "先不处理", "暂不处理", "no", "n"}
