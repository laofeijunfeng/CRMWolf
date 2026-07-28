"""Agent pending task selection handlers."""
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

from app.services.agent.interactions import (
    _customer_requires_procurement_method,
    _opportunity_field_defaults,
    _opportunity_interaction_fields,
    _opportunity_missing_display_fields,
)
from app.services.agent.task_actions import _tool_name_for_action


def _is_customer_selection_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") in {
        "select_customer_for_follow_up",
        "select_customer_for_opportunity",
        "select_customer_for_contact",
        "select_customer_for_invoice_title",
        "select_customer_for_deployment_info",
        "select_customer_for_customer_member",
        "select_customer_for_payment_record",
    }

def _is_business_selection_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") in {"select_contract_for_payment_plan", "select_payment_plan_for_record"}

def _select_customer_candidate(content: str, customers: list[dict]) -> Optional[dict]:
    normalized = content.strip()
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(customers):
            return customers[index - 1]

    for customer in customers:
        account_name = str(customer.get("account_name") or "")
        if account_name and (normalized == account_name or normalized in account_name or account_name in normalized):
            return customer
    return None

async def _load_member_candidates_for_customer(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    authorization: str,
    customer_id: int,
):
    context = AgentToolContext(
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        authorization=authorization,
        allowed_tool_names=["get_customer_context"],
        allowed_customer_ids=[customer_id],
    )
    try:
        return await CRMAgentToolService().api_client.request(
            "GET",
            f"/v1/customers/{customer_id}/member-candidates",
            context.authorization,
        )
    except CRMAPIClientError as exc:
        return {"error": exc.message, "status_code": exc.status_code}

async def _contact_task_next_state(
    action: str,
    state: dict,
    customer: dict,
    *,
    db: Optional[Session] = None,
    team_id: Optional[int] = None,
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
    authorization: Optional[str] = None,
):
    payload = state.get("payload") or {}
    if action == "select_customer_for_opportunity":
        opportunity = payload.get("opportunity") or {}
        opportunity["customer_id"] = customer.get("id")
        payload["customer_id"] = customer.get("id")
        payload["opportunity"] = opportunity
        missing_fields = CRMAgentGraphService.missing_opportunity_fields(
            opportunity,
            require_procurement_method=_customer_requires_procurement_method(customer),
        )
        needs_procurement_review = not opportunity.get("procurement_method_id")
        if missing_fields or needs_procurement_review:
            payload["missing_fields"] = missing_fields
            payload["interaction_fields"] = _opportunity_interaction_fields(missing_fields, customer)
            payload["field_defaults"] = _opportunity_field_defaults(customer)
            content = (
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{CRMAgentGraphService.format_opportunity_missing_fields(_opportunity_missing_display_fields(missing_fields, customer))}。"
                if missing_fields
                else f"已选择客户「{customer.get('account_name')}」，请确认采购方式。"
            )
            return (
                "collect_opportunity_fields",
                payload,
                content,
            )
        return (
            "create_opportunity",
            {
                "customer_id": customer.get("id"),
                "opportunity": opportunity,
            },
            f"已选择客户「{customer.get('account_name')}」。请确认是否创建商机？",
        )

    if action == "select_customer_for_invoice_title":
        invoice_title = payload.get("invoice_title") or {}
        payload["customer_id"] = customer.get("id")
        missing_fields = CRMAgentGraphService.missing_invoice_title_fields(invoice_title)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_invoice_title_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{CRMAgentGraphService.format_invoice_title_missing_fields(missing_fields)}。",
            )
        return (
            "create_invoice_title",
            {
                "customer_id": customer.get("id"),
                "invoice_title": invoice_title,
                "set_default": bool(payload.get("set_default")),
            },
            f"已选择客户「{customer.get('account_name')}」。请确认是否创建发票抬头「{invoice_title.get('title')}」？",
        )

    if action == "select_customer_for_deployment_info":
        deployment_info = payload.get("deployment_info") or {}
        deployment_info["customer_id"] = customer.get("id")
        payload["customer_id"] = customer.get("id")
        payload["deployment_info"] = deployment_info
        missing_fields = CRMAgentGraphService.missing_deployment_info_fields(deployment_info)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_deployment_info_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{CRMAgentGraphService.format_deployment_info_missing_fields(missing_fields)}。",
            )
        return (
            "create_deployment_info",
            {
                "customer_id": customer.get("id"),
                "deployment_info": deployment_info,
            },
            f"已选择客户「{customer.get('account_name')}」。请确认是否创建部署信息「{deployment_info.get('deployment_name')}」？",
        )

    if action == "select_customer_for_customer_member":
        customer_member = payload.get("customer_member") or {}
        payload["customer_id"] = customer.get("id")
        if (
            db is not None
            and team_id is not None
            and user_id is not None
            and session_id is not None
            and authorization
            and customer.get("id")
            and not payload.get("member_candidates")
        ):
            payload["member_candidates"] = await _load_member_candidates_for_customer(
                db,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                authorization=authorization,
                customer_id=customer["id"],
            )
        missing_fields = CRMAgentGraphService.missing_customer_member_fields(customer_member)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_customer_member_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{CRMAgentGraphService.format_customer_member_missing_fields(missing_fields)}。",
            )
        return (
            "collect_customer_member_fields",
            payload,
            f"已选择客户「{customer.get('account_name')}」。请再确认一下成员姓名，我来匹配候选人。",
        )

    contact = payload.get("contact") or {}
    if action == "select_customer_for_contact":
        payload["customer_id"] = customer.get("id")
        missing_fields = CRMAgentGraphService.missing_contact_fields(contact)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_contact_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{CRMAgentGraphService.format_contact_missing_fields(missing_fields)}。",
            )
        return (
            "create_contact",
            {"customer_id": customer.get("id"), "contact": contact},
            f"已选择客户「{customer.get('account_name')}」。请确认是否创建联系人「{contact.get('name')}」？",
        )

    payload["customer_id"] = customer.get("id")
    return (
        "create_customer_follow_up",
        payload,
        f"已选择客户「{customer.get('account_name')}」。请确认是否创建这条跟进记录？",
    )

async def _apply_customer_selection(
    db: Session,
    task,
    content: str,
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    authorization: str,
):
    state = task.state_json or {}
    action = state.get("action")
    customers = state.get("customers") or []
    customer = _select_customer_candidate(content, customers)
    if not customer:
        candidate_names = "；".join(
            f"{index}. {item.get('account_name')}"
            for index, item in enumerate(customers, start=1)
        )
        return None, f"没有匹配到你选择的客户，请回复序号或完整客户名称：{candidate_names}"

    if action == "select_customer_for_payment_record":
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(
                status=AgentTaskStatus.COMPLETED,
                target_id=customer.get("id"),
                summary="已选择回款客户，等待重新发送回款信息",
                state_json={**state, "customer": customer},
            ),
        )
        return customer, (
            f"已选择客户「{customer.get('account_name')}」。"
            "请重新发送这条回款信息，我会基于该客户重新读取合同和回款计划后继续处理。"
        )

    next_action, payload, message = await _contact_task_next_state(
        action,
        state,
        customer,
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        authorization=authorization,
    )
    new_state = {
        "action": next_action,
        "payload": payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=[_tool_name_for_action(next_action)] if _tool_name_for_action(next_action) else [],
            confirmation_summary=message,
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            target_id=customer.get("id"),
            summary=f"等待确认执行：{next_action}",
            input_json=payload,
            state_json=new_state,
        ),
    )
    return customer, message

def _select_business_item(content: str, items: list[dict], name_fields: list[str]) -> Optional[dict]:
    normalized = content.strip()
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(items):
            return items[index - 1]
    for item in items:
        for field in name_fields:
            value = str(item.get(field) or "")
            if value and (normalized == value or normalized in value or value in normalized):
                return item
    return None

def _apply_business_selection(db: Session, task, content: str):
    state = task.state_json or {}
    action = state.get("action")
    payload = state.get("payload") or {}
    customer = state.get("customer") or {}
    payment = payload.get("payment") or {}
    commission_member_id = payload.get("commission_member_id")

    if action == "select_payment_plan_for_record":
        payment_plans = state.get("payment_plans") or []
        plan = _select_business_item(content, payment_plans, ["stage_name", "contract_name"])
        if not plan:
            names = "；".join(f"{index}. {item.get('contract_name')} / {item.get('stage_name')}" for index, item in enumerate(payment_plans, start=1))
            return None, f"没有匹配到你选择的回款计划，请回复序号或阶段名称：{names}"
        next_payload = CRMAgentGraphService._payment_record_payload(plan, payment, commission_member_id)
        new_state = {
            "action": "create_payment_record",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_record"],
                confirmation_summary=f"登记回款到「{plan.get('stage_name')}」",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary="等待确认执行：create_payment_record", input_json=next_payload, state_json=new_state))
        return plan, f"已选择回款计划「{plan.get('stage_name')}」。请确认是否登记这笔回款？"

    if action == "select_contract_for_payment_plan":
        contracts = state.get("contracts") or []
        contract = _select_business_item(content, contracts, ["contract_name", "contract_number"])
        if not contract:
            names = "；".join(f"{index}. {item.get('contract_name')}" for index, item in enumerate(contracts, start=1))
            return None, f"没有匹配到你选择的合同，请回复序号或合同名称：{names}"
        next_payload = CRMAgentGraphService._payment_plan_payload(contract, payment, commission_member_id)
        new_state = {
            "action": "create_payment_plan",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_plan"],
                confirmation_summary=f"基于合同「{contract.get('contract_name')}」创建回款计划",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary="等待确认执行：create_payment_plan", input_json=next_payload, state_json=new_state))
        return contract, f"已选择合同「{contract.get('contract_name')}」。请确认是否先创建回款计划？"

    return None, f"暂不支持的选择动作：{action}"
