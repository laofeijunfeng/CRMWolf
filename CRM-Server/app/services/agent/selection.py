"""Agent pending task selection handlers."""
from __future__ import annotations

from copy import deepcopy
import json
import uuid
from collections.abc import Mapping
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
from app.services.agent import business_rules, choice_resolution, task_display
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.quality import AgentFollowUpQualityEvaluatorError, agent_follow_up_quality_evaluator
from app.services.agent.resource_resolution_graph import resource_resolution_graph_service
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent.schemas import (
    AgentHITLPolicy,
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentSemanticParseResult,
)
from app.services.agent.semantic import AgentSemanticParserError, agent_semantic_parser
from app.services.agent.state import ResourceResolutionGraphState
from app.services.agent.task_factory import _task_target_id
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.tool_registry import AgentToolRegistry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value
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
        "select_customer_for_activity",
        "select_customer_for_opportunity",
        "select_customer_for_contact",
        "select_customer_for_invoice_title",
        "select_customer_for_deployment_info",
        "select_customer_for_customer_member",
        "select_customer_for_payment_record",
    }

def _is_business_selection_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") in {
        "select_contract_for_payment_plan",
        "select_payment_plan_for_record",
        "select_opportunity_for_stage_move",
    }


async def _resolve_candidate(
    db: Session,
    content: str,
    *,
    action_name: str,
    target: Mapping[str, object],
    metadata: Mapping[str, object],
    spec: choice_resolution.ChoiceResourceSpec,
    candidates: list[dict],
    team_id: int,
    user_id: int,
    session_id: int,
) -> Optional[dict]:
    protocol_result = choice_resolution.resolve_choice(
        content,
        metadata=metadata,
        spec=spec,
        candidates=candidates,
    )
    if protocol_result.selected is not None:
        return dict(protocol_result.selected)

    candidate_documents = [_candidate_document(spec, candidate, index) for index, candidate in enumerate(candidates, start=1)]

    async def ranker(state: ResourceResolutionGraphState) -> list[JSONDict]:
        try:
            return await agent_semantic_parser.rank_resource_candidates(
                db,
                team_id=team_id,
                user_message=str(state.get("content") or ""),
                resource_kind=spec.resource_type,
                action_name=action_name,
                target=coerce_json_dict(state.get("target")),
                candidates=candidate_documents,
            )
        except AgentSemanticParserError:
            return []

    resolution = await resource_resolution_graph_service.run(
        {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "resource_kind": spec.resource_type,
            "action_name": action_name,
            "content": content,
            "target": coerce_json_dict(target),
            "candidates": candidate_documents,
        },
        ranker=ranker,
    )
    if resolution.get("resolution_status") != "selected":
        return None
    selected = coerce_json_dict(resolution.get("selected_candidate"))
    selected_id = selected.get("id")
    for candidate in candidates:
        if _same_identifier(candidate.get(spec.id_field), selected_id):
            return dict(candidate)
    return None


def _candidate_document(
    spec: choice_resolution.ChoiceResourceSpec,
    candidate: Mapping[str, object],
    index: int,
) -> JSONDict:
    document = dict(candidate)
    document["display_label"] = choice_resolution.choice_label(spec, candidate, index=index)
    document["choice_index"] = index
    return {str(key): value for key, value in document.items()}


def _same_identifier(left: object, right: object) -> bool:
    left_value = coerce_json_value(left)
    right_value = coerce_json_value(right)
    return isinstance(left_value, (str, int)) and isinstance(right_value, (str, int)) and str(left_value) == str(right_value)


async def _select_customer_candidate(
    db: Session,
    content: str,
    customers: list[dict],
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    metadata: Optional[dict[str, object]] = None,
) -> Optional[dict]:
    result = await _resolve_candidate(
        db,
        content,
        action_name="select_customer",
        target={},
        metadata=metadata or {},
        spec=choice_resolution.CUSTOMER_SPEC,
        candidates=customers,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
    )
    return result

async def _load_member_candidates_for_customer(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    authorization: str,
    customer_id: str,
):
    context = AgentToolContext(
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        authorization=authorization,
        allowed_tool_names=["get_customer_context"],
        allowed_customer_ids=[str(customer_id)],
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
        missing_fields = business_rules.missing_opportunity_fields(
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
                f"{business_rules.format_opportunity_missing_fields(_opportunity_missing_display_fields(missing_fields, customer))}。"
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
        missing_fields = business_rules.missing_invoice_title_fields(invoice_title)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_invoice_title_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{business_rules.format_invoice_title_missing_fields(missing_fields)}。",
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
        missing_fields = business_rules.missing_deployment_info_fields(deployment_info)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_deployment_info_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{business_rules.format_deployment_info_missing_fields(missing_fields)}。",
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
        missing_fields = business_rules.missing_customer_member_fields(customer_member)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_customer_member_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{business_rules.format_customer_member_missing_fields(missing_fields)}。",
            )
        return (
            "collect_customer_member_fields",
            payload,
            f"已选择客户「{customer.get('account_name')}」。请再确认一下成员姓名，我来匹配候选人。",
        )

    contact = payload.get("contact") or {}
    if action == "select_customer_for_contact":
        payload["customer_id"] = customer.get("id")
        missing_fields = business_rules.missing_contact_fields(contact)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_contact_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{business_rules.format_contact_missing_fields(missing_fields)}。",
            )
        return (
            "create_contact",
            {"customer_id": customer.get("id"), "contact": contact},
            f"已选择客户「{customer.get('account_name')}」。请确认是否创建联系人「{contact.get('name')}」？",
        )

    payload["customer_id"] = customer.get("id")
    return (
        "create_customer_activity",
        payload,
        f"已选择客户「{customer.get('account_name')}」。请确认是否创建这条客户活动？",
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
    metadata: Optional[dict[str, object]] = None,
):
    state = task.state_json or {}
    action = state.get("action")
    customers = state.get("customers") or []
    customer = await _select_customer_candidate(
        db,
        content,
        customers,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )
    if not customer:
        candidate_names = "；".join(
            f"{index}. {item.get('account_name')}"
            for index, item in enumerate(customers, start=1)
        )
        return None, f"没有匹配到你选择的客户，请告诉我要选择哪一个：{candidate_names}"

    if action == "select_customer_for_payment_record":
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(
                status=AgentTaskStatus.COMPLETED,
                target_id=_task_target_id(
                    db,
                    team_id=team_id,
                    target_type="customer",
                    target_id=customer.get("id"),
                ),
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
            target_id=_task_target_id(
                db,
                team_id=team_id,
                target_type="customer",
                target_id=customer.get("id"),
            ),
            summary=message if "_" not in message else task_display.readable_action_label(next_action) or "等待确认业务操作",
            input_json=payload,
            state_json=new_state,
        ),
    )
    return customer, message

async def _select_business_item(
    db: Session,
    content: str,
    items: list[dict],
    spec: choice_resolution.ChoiceResourceSpec,
    *,
    action_name: str,
    target: Mapping[str, object],
    team_id: int,
    user_id: int,
    session_id: int,
    metadata: Optional[dict[str, object]] = None,
) -> Optional[dict]:
    result = await _resolve_candidate(
        db,
        content,
        action_name=action_name,
        target=target,
        metadata=metadata or {},
        spec=spec,
        candidates=items,
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
    )
    return result

async def _apply_business_selection(
    db: Session,
    task,
    content: str,
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    metadata: Optional[dict[str, object]] = None,
):
    state = task.state_json or {}
    action = state.get("action")
    payload = state.get("payload") or {}
    customer = state.get("customer") or {}
    payment = payload.get("payment") or {}
    commission_member_id = payload.get("commission_member_id")

    if action == "select_opportunity_for_stage_move":
        opportunities = state.get("opportunities") or []
        opportunity = await _select_business_item(
            db,
            content,
            opportunities,
            choice_resolution.OPPORTUNITY_SPEC,
            action_name="move_opportunity_stage",
            target={
                "customer": customer,
                "payload": payload,
            },
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )
        if not opportunity:
            names = "；".join(
                f"{index}. {item.get('opportunity_name') or item.get('name')}"
                for index, item in enumerate(opportunities, start=1)
            )
            return None, f"没有匹配到你选择的商机，请告诉我要选择哪一个：{names}"
        opportunity_id = opportunity.get("id")
        stage_template_id = opportunity.get("target_stage_template_id") or payload.get("stage_template_id")
        target_stage_name = opportunity.get("target_stage_name") or payload.get("target_stage_name")
        next_payload = {
            "customer_id": payload.get("customer_id") or customer.get("id"),
            "opportunity_id": int(opportunity_id),
            "stage_template_id": int(stage_template_id),
            "opportunity_name": opportunity.get("opportunity_name") or opportunity.get("name"),
            "target_stage_name": target_stage_name,
            "stage_move_steps": opportunity.get("stage_move_steps") or payload.get("stage_move_steps"),
            "suggestion_title": payload.get("suggestion_title"),
            "suggestion_reason": payload.get("suggestion_reason"),
        }
        message = (
            f"已选择商机「{next_payload.get('opportunity_name')}」。"
            f"请确认是否推进到「{target_stage_name}」？"
            if target_stage_name
            else f"已选择商机「{next_payload.get('opportunity_name')}」。请确认是否推进阶段？"
        )
        new_state = {
            "action": "move_opportunity_stage",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["move_opportunity_stage"],
                confirmation_summary=message,
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(summary=message, input_json=next_payload, state_json=new_state),
        )
        return opportunity, message

    if action == "select_payment_plan_for_record":
        payment_plans = state.get("payment_plans") or []
        plan = await _select_business_item(
            db,
            content,
            payment_plans,
            choice_resolution.PAYMENT_PLAN_SPEC,
            action_name="create_payment_record",
            target={
                "customer": customer,
                "payment": payment,
                "commission_member_id": commission_member_id,
            },
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )
        if not plan:
            names = "；".join(f"{index}. {item.get('contract_name')} / {item.get('stage_name')}" for index, item in enumerate(payment_plans, start=1))
            return None, f"没有匹配到你选择的回款计划，请告诉我要选择哪一个：{names}"
        next_payload = business_rules.payment_record_payload(plan, payment, commission_member_id)
        new_state = {
            "action": "create_payment_record",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_record"],
                confirmation_summary=f"登记回款到「{plan.get('stage_name')}」",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary=f"登记回款到「{plan.get('stage_name')}」", input_json=next_payload, state_json=new_state))
        return plan, f"已选择回款计划「{plan.get('stage_name')}」。请确认是否登记这笔回款？"

    if action == "select_contract_for_payment_plan":
        contracts = state.get("contracts") or []
        contract = await _select_business_item(
            db,
            content,
            contracts,
            choice_resolution.CONTRACT_SPEC,
            action_name="create_payment_plan",
            target={
                "customer": customer,
                "payment": payment,
                "commission_member_id": commission_member_id,
            },
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
        )
        if not contract:
            names = "；".join(f"{index}. {item.get('contract_name')}" for index, item in enumerate(contracts, start=1))
            return None, f"没有匹配到你选择的合同，请告诉我要选择哪一个：{names}"
        next_payload = business_rules.payment_plan_payload(contract, payment, commission_member_id)
        new_state = {
            "action": "create_payment_plan",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_plan"],
                confirmation_summary=f"基于合同「{contract.get('contract_name')}」创建回款计划",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary=f"基于合同「{contract.get('contract_name')}」创建回款计划", input_json=next_payload, state_json=new_state))
        return contract, f"已选择合同「{contract.get('contract_name')}」。请确认是否先创建回款计划？"

    return None, f"暂不支持的选择动作：{action}"
