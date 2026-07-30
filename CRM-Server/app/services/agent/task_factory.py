"""Factories for persisted Agent waiting tasks."""
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

from app.services.agent.session_state import _remember_pending_task
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


def _is_waiting_task_event(event: dict[str, Any]) -> bool:
    return event.get("event") in WAITING_TASK_EVENT_TYPES


def _create_waiting_task_from_event(db: Session, event: dict, team_id: int, user_id: int, session):
    action = event.get("action")
    payload = event.get("payload") or {}
    customer = event.get("customer")
    customers = event.get("customers") or []
    contracts = event.get("contracts") or []
    payment_plans = event.get("payment_plans") or []
    intent = None
    if action in {"create_customer_activity", "select_customer_for_activity", "collect_follow_up_quality_fields"}:
        intent = "CUSTOMER_ACTIVITY"
    elif action in {"create_lead", "collect_lead_fields", "create_lead_follow_up", "collect_lead_follow_up_quality_fields"}:
        intent = "CREATE_LEAD"
    elif action in {"create_customer", "collect_customer_fields"}:
        intent = "CREATE_CUSTOMER"
    elif action in {"create_opportunity", "select_customer_for_opportunity", "collect_opportunity_fields"}:
        intent = "CREATE_OPPORTUNITY"
    elif action == "move_opportunity_stage":
        intent = "CUSTOMER_ACTIVITY"
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
    hitl_policy = AgentHITLPolicy(
        required_for_tools=[_tool_name_for_action(action)] if _tool_name_for_action(action) else [],
        confirmation_summary=event.get("content") or event.get("message") or f"等待确认执行：{action}",
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
            target_type="lead" if intent == "CREATE_LEAD" else "customer",
            target_id=payload.get("customer_id"),
            summary=f"等待确认执行：{action}",
            input_json=payload,
            state_json={
                "action": action,
                "payload": payload,
                "customer": customer,
                "customers": customers,
                "contracts": contracts,
                "payment_plans": payment_plans,
                "hitl": hitl_policy.model_dump(exclude_none=True),
            },
        ),
    )
    event["task_id"] = task.id
    event["task_key"] = task.task_key
    _remember_pending_task(db, session, task)
    return task
