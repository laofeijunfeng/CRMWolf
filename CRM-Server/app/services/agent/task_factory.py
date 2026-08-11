"""Factories for persisted Agent waiting tasks."""
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
from app.models.lead import Lead
from app.schemas.agent import (
    AgentCreateSessionRequest,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentTaskCreate,
    AgentTaskUpdate,
)
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.quality import AgentFollowUpQualityEvaluatorError, agent_follow_up_quality_evaluator
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent import action_workflow
from app.services.agent import task_display
from app.services.agent import workflow_action_ledger
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

from app.services.agent.task_actions import _tool_name_for_action


WAITING_TASK_EVENT_TYPES = frozenset({
    "confirmation_required",
    "customer_selection_required",
    "contact_fields_required",
    "invoice_title_fields_required",
    "deployment_info_fields_required",
    "customer_member_fields_required",
    "payment_fields_required",
    "lead_fields_required",
    "customer_fields_required",
    "opportunity_fields_required",
    "follow_up_quality_required",
    "business_selection_required",
})


def _new_task_key() -> str:
    return f"task_{uuid.uuid4().hex}"


def _task_target_id(db: Session, *, team_id: int, target_type: str | None, target_id: object) -> int | None:
    """Return the internal integer id stored on crm_agent_tasks.

    Agent tool payloads use public ids such as ``cus_...`` and ``lead_...``.
    The task table keeps an integer target_id for historical audit/indexing, so
    task creation/update must normalize at that boundary only.
    """
    if target_id is None:
        return None
    if isinstance(target_id, int):
        return target_id
    if isinstance(target_id, str):
        value = target_id.strip()
        if not value:
            return None
        if value.isdigit():
            return int(value)
        if target_type == "customer":
            customer = (
                db.query(Customer.id)
                .filter(Customer.team_id == team_id, Customer.public_id == value)
                .first()
            )
            return int(customer[0]) if customer else None
        if target_type == "lead":
            lead = (
                db.query(Lead.id)
                .filter(Lead.team_id == team_id, Lead.public_id == value)
                .first()
            )
            return int(lead[0]) if lead else None
    return None


def _is_waiting_task_event(event: dict[str, object]) -> bool:
    return event.get("event") in WAITING_TASK_EVENT_TYPES


def _create_waiting_task_from_event(db: Session, event: dict, team_id: int, user_id: int, session):
    action = event.get("action")
    payload = event.get("payload") or {}
    customer = event.get("customer")
    customers = event.get("customers") or []
    opportunities = event.get("opportunities") or []
    contracts = event.get("contracts") or []
    payment_plans = event.get("payment_plans") or []
    hitl_review = event.get("hitl_review") if isinstance(event.get("hitl_review"), dict) else {}
    workflow = action_workflow.ensure_event_workflow(event)
    intent = None
    if action in {"create_customer_activity", "select_customer_for_activity", "collect_follow_up_quality_fields"}:
        intent = "CUSTOMER_ACTIVITY"
    elif action in {"create_lead", "collect_lead_fields", "create_lead_follow_up", "collect_lead_follow_up_quality_fields"}:
        intent = "CREATE_LEAD"
    elif action in {"create_customer", "collect_customer_fields"}:
        intent = "CREATE_CUSTOMER"
    elif action in {"create_opportunity", "select_customer_for_opportunity", "collect_opportunity_fields"}:
        intent = "CREATE_OPPORTUNITY"
    elif action in {"move_opportunity_stage", "select_opportunity_for_stage_move"}:
        intent = "CUSTOMER_ACTIVITY"
    elif action == "transition_follow_up_task":
        intent = "FOLLOW_UP_TASK_TRANSITION"
    elif action in {"create_contact", "select_customer_for_contact", "collect_contact_fields"}:
        intent = "CREATE_CONTACT"
    elif action in {"create_invoice_title", "select_customer_for_invoice_title", "collect_invoice_title_fields"}:
        intent = "CREATE_INVOICE_TITLE"
    elif action in {"create_deployment_info", "select_customer_for_deployment_info", "collect_deployment_info_fields"}:
        intent = "CREATE_DEPLOYMENT_INFO"
    elif action in {"create_customer_member", "select_customer_for_customer_member", "collect_customer_member_fields"}:
        intent = "CREATE_CUSTOMER_MEMBER"
    elif action in {
        "create_payment_plan",
        "create_payment_record",
        "collect_payment_fields",
        "select_customer_for_payment_record",
        "select_contract_for_payment_plan",
        "select_payment_plan_for_record",
    }:
        intent = "PAYMENT_RECORD"
    confirmation_summary = _confirmation_summary_for_action(
        action,
        content=event.get("content") or event.get("message"),
    )
    hitl_policy = AgentHITLPolicy(
        required_for_tools=[_tool_name_for_action(action)] if _tool_name_for_action(action) else [],
        confirmation_summary=confirmation_summary,
    )
    target_type = "lead" if intent == "CREATE_LEAD" else "customer"
    target_id = _task_target_id(
        db,
        team_id=team_id,
        target_type=target_type,
        target_id=payload.get("lead_id") if target_type == "lead" else payload.get("customer_id"),
    )
    task = agent_task_crud.create(
        db,
        AgentTaskCreate(
            task_key=_new_task_key(),
            team_id=team_id,
            user_id=user_id,
            session_id=session.id,
            intent=intent,
            status=AgentTaskStatus.WAITING_USER,
            target_type=target_type,
            target_id=target_id,
            summary=confirmation_summary,
            input_json=payload,
            state_json={
                "action": action,
                "payload": payload,
                "customer": customer,
                "customers": customers,
                "opportunities": opportunities,
                "contracts": contracts,
                "payment_plans": payment_plans,
                "workflow": workflow,
                "hitl_review": hitl_review,
                "hitl": hitl_policy.model_dump(exclude_none=True),
            },
        ),
    )
    workflow_action_ledger.create_or_update_waiting_action(
        db,
        workflow=workflow,
        team_id=team_id,
        user_id=user_id,
        session_id=session.id,
        task_id=task.id,
        source_type=workflow_action_ledger.SOURCE_AGENT_PLANNING,
        payload=payload,
        target_type=target_type,
        target_id=target_id,
    )
    event["task_id"] = task.id
    event["task_key"] = task.task_key
    return task


def _confirmation_summary_for_action(action: object, *, content: object) -> str:
    if isinstance(content, str) and content.strip() and "_" not in content and "等待确认执行：" not in content:
        return content.strip()
    action_label = task_display.readable_action_label(action)
    if action_label:
        return action_label
    return "等待确认业务操作"
