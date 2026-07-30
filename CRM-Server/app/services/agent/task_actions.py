"""Agent task action to tool payload mapping."""
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


def _normalize_gender(value: Any) -> str:
    text = str(value or "").strip()
    return {"男": "1", "女": "2", "未知": "0"}.get(text, text or "0")

def _customer_create_api_payload(customer: dict) -> dict:
    payload = {
        key: customer.get(key)
        for key in ("account_name", "source", "city", "industry", "company_scale")
        if customer.get(key) not in (None, "")
    }
    payload.setdefault("source", "其他")
    has_contact = any(customer.get(field) for field in ["contact_name", "contact_phone", "contact_position", "contact_gender", "contact_email"])
    if has_contact:
        payload["primary_contact"] = {
            "name": customer.get("contact_name"),
            "mobile": customer.get("contact_phone"),
            "position": customer.get("contact_position"),
            "gender": _normalize_gender(customer.get("contact_gender")),
            "email": customer.get("contact_email"),
        }
    return payload

def _tool_name_for_action(action: Optional[str]) -> Optional[str]:
    return {
        "create_customer_activity": "create_customer_activity",
        "create_lead": "create_lead",
        "create_customer": "create_customer",
        "create_lead_follow_up": "create_lead_follow_up",
        "create_contact": "create_contact",
        "create_invoice_title": "create_invoice_title",
        "create_deployment_info": "create_deployment_info",
        "create_customer_member": "create_customer_member",
        "create_opportunity": "create_opportunity",
        "move_opportunity_stage": "move_opportunity_stage",
        "create_payment_plan": "create_payment_plan",
        "create_payment_record": "create_payment_record",
    }.get(action or "")

def _tool_payload_for_action(action: Optional[str], payload: dict, customer: dict, task_key: str) -> Optional[dict]:
    if action == "create_customer_activity":
        return {
            "customer_id": payload["customer_id"],
            "customer_name": customer.get("account_name"),
            "activity_kind": payload.get("activity_kind") or "OTHER_FOLLOW_UP",
            "source_content": payload.get("source_content") or payload.get("content") or "",
            "title": payload.get("title"),
            "next_action": payload.get("next_action"),
            "next_follow_time": payload.get("next_follow_time_iso"),
            "idempotency_suffix": task_key,
        }
    if action == "create_lead":
        lead = dict(payload["lead"])
        lead.setdefault("source", "其他")
        return {"lead": lead, "idempotency_suffix": task_key}
    if action == "create_customer":
        return {
            "customer": _customer_create_api_payload(dict(payload["customer"])),
            "idempotency_suffix": task_key,
        }
    if action == "create_lead_follow_up":
        return {
            "lead_id": payload["lead_id"],
            "content": payload["content"],
            "method": payload.get("method") or "其他",
            "next_action": payload.get("next_action"),
            "next_follow_time": payload.get("next_follow_time"),
            "idempotency_suffix": task_key,
        }
    if action == "create_contact":
        return {"customer_id": payload["customer_id"], "contact": payload["contact"]}
    if action == "create_invoice_title":
        return {
            "customer_id": payload["customer_id"],
            "invoice_title": payload["invoice_title"],
            "set_default": bool(payload.get("set_default")),
        }
    if action == "create_deployment_info":
        deployment_info = dict(payload["deployment_info"])
        deployment_info["customer_id"] = payload.get("customer_id") or deployment_info.get("customer_id")
        return {"deployment_info": deployment_info}
    if action == "create_customer_member":
        member = dict(payload["member"])
        member.pop("user_name", None)
        return {"customer_id": payload["customer_id"], "member": member}
    if action == "create_opportunity":
        opportunity = dict(payload["opportunity"])
        opportunity.pop("opportunity_name", None)
        opportunity["customer_id"] = payload.get("customer_id") or opportunity.get("customer_id")
        return {"opportunity": opportunity, "idempotency_suffix": task_key}
    if action == "move_opportunity_stage":
        return {
            "opportunity_id": payload["opportunity_id"],
            "stage_template_id": payload["stage_template_id"],
            "idempotency_suffix": task_key,
        }
    if action == "create_payment_plan":
        return {
            "contract_id": payload["contract_id"],
            "stage_name": payload["stage_name"],
            "planned_amount": payload["planned_amount"],
            "due_date": payload["due_date"],
            "notes": payload.get("notes"),
            "idempotency_suffix": task_key,
        }
    if action == "create_payment_record":
        return {
            "payment_plan_id": payload["payment_plan_id"],
            "actual_amount": payload["actual_amount"],
            "payment_date": payload["payment_date"],
            "actual_payer_name": payload.get("actual_payer_name"),
            "commission_member_id": payload["commission_member_id"],
            "proof_attachment": payload.get("proof_attachment"),
            "notes": payload.get("notes"),
            "idempotency_suffix": task_key,
        }
    return None
