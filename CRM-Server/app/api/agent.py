"""CRM AI Agent API."""
import json
import uuid
from typing import Any, Optional

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
    AgentSessionUpdate,
    AgentTaskCreate,
    AgentTaskUpdate,
)
from app.schemas.common import PaginatedResponse
from app.services.agent import crm_agent_graph_service
from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent.schemas import (
    AgentHITLPolicy,
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentSemanticParseResult,
)
from app.services.agent.semantic import AgentSemanticParserError, agent_semantic_parser
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.tool_registry import AgentToolRegistry
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


def _append_trace_event(trace_events: list[dict], event: dict) -> None:
    if event.get("event") in {"session", "message", "final", "done"}:
        return
    trace_events.append(json.loads(json.dumps(event, ensure_ascii=False, cls=SSEJsonEncoder)))


def _authorization_header(credentials: HTTPAuthorizationCredentials) -> str:
    return f"{credentials.scheme} {credentials.credentials}"


def _new_task_key() -> str:
    return f"task_{uuid.uuid4().hex}"


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


def _is_customer_selection_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") in {
        "select_customer_for_follow_up",
        "select_customer_for_opportunity",
        "select_customer_for_contact",
        "select_customer_for_invoice_title",
        "select_customer_for_deployment_info",
        "select_customer_for_payment_record",
    }


def _is_contact_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_contact_fields"


def _is_opportunity_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_opportunity_fields"


def _is_invoice_title_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_invoice_title_fields"


def _is_deployment_info_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_deployment_info_fields"


def _is_payment_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_payment_fields"


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


def _contact_task_next_state(action: str, state: dict, customer: dict):
    payload = state.get("payload") or {}
    if action == "select_customer_for_opportunity":
        opportunity = payload.get("opportunity") or {}
        opportunity["customer_id"] = customer.get("id")
        payload["customer_id"] = customer.get("id")
        payload["opportunity"] = opportunity
        missing_fields = CRMAgentGraphService.missing_opportunity_fields(opportunity)
        if missing_fields:
            payload["missing_fields"] = missing_fields
            return (
                "collect_opportunity_fields",
                payload,
                f"已选择客户「{customer.get('account_name')}」，还需要补充："
                f"{CRMAgentGraphService.format_opportunity_missing_fields(missing_fields)}。",
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


def _create_waiting_task_from_event(db: Session, event: dict, team_id: int, user_id: int, session):
    action = event.get("action")
    payload = event.get("payload") or {}
    customer = event.get("customer")
    customers = event.get("customers") or []
    contracts = event.get("contracts") or []
    payment_plans = event.get("payment_plans") or []
    intent = None
    if action in {"create_customer_follow_up", "select_customer_for_follow_up"}:
        intent = "CUSTOMER_FOLLOW_UP"
    elif action in {"create_opportunity", "select_customer_for_opportunity", "collect_opportunity_fields"}:
        intent = "CREATE_OPPORTUNITY"
    elif action == "move_opportunity_stage":
        intent = "CUSTOMER_FOLLOW_UP"
    elif action in {"create_contact", "select_customer_for_contact", "collect_contact_fields"}:
        intent = "CREATE_CONTACT"
    elif action in {"create_invoice_title", "select_customer_for_invoice_title", "collect_invoice_title_fields"}:
        intent = "CREATE_INVOICE_TITLE"
    elif action in {"create_deployment_info", "select_customer_for_deployment_info", "collect_deployment_info_fields"}:
        intent = "CREATE_DEPLOYMENT_INFO"
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
            target_type="customer",
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


def _apply_customer_selection(db: Session, task, content: str):
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

    next_action, payload, message = _contact_task_next_state(action, state, customer)
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


async def _parse_task_field_supplement(db: Session, task, content: str) -> AgentSemanticParseResult:
    memory = AgentMemorySnapshot(
        pending_task={
            "id": task.id,
            "intent": task.intent,
            "target_type": task.target_type,
            "target_id": task.target_id,
            "summary": task.summary,
            "state": task.state_json,
        },
    )
    return await agent_semantic_parser.parse(
        db,
        team_id=task.team_id,
        user_message=content,
        memory=memory,
    )


def _merge_contact_fields(existing_contact: dict, semantic_result: AgentSemanticParseResult) -> dict:
    return {**existing_contact, **_drop_empty_values(semantic_result.contact)}


def _merge_invoice_title_fields(existing_invoice_title: dict, semantic_result: AgentSemanticParseResult) -> dict:
    merged = {**existing_invoice_title, **_drop_empty_values(semantic_result.invoice_title)}
    merged.pop("set_default", None)
    return merged


def _merge_deployment_info_fields(existing_deployment_info: dict, semantic_result: AgentSemanticParseResult) -> dict:
    return {**existing_deployment_info, **_drop_empty_values(semantic_result.deployment_info)}


def _merge_payment_fields(existing_payment: dict, semantic_result: AgentSemanticParseResult) -> dict:
    payment = semantic_result.payment
    resolved_date = agent_temporal_resolver.resolve_date(payment.payment_date)
    merged = {
        **existing_payment,
        **_drop_empty_values({
            "actual_amount": payment.actual_amount,
            "actual_payer_name": payment.actual_payer_name,
            "payment_date_text": payment.payment_date_text,
            "payment_date_iso": resolved_date,
            "notes": payment.notes,
        }),
    }
    return merged


def _merge_opportunity_fields(existing_opportunity: dict, semantic_result: AgentSemanticParseResult) -> dict:
    opportunity = semantic_result.opportunity
    resolved_date = agent_temporal_resolver.resolve_date(opportunity.expected_closing_date)
    merged = {
        **existing_opportunity,
        **_drop_empty_values({
            "total_amount": opportunity.total_amount,
            "user_count": opportunity.user_count,
            "license_type": opportunity.license_type,
            "subscription_years": opportunity.subscription_years,
            "purchase_type": opportunity.purchase_type,
            "decision_maker_count": opportunity.decision_maker_count,
            "expected_closing_date_text": opportunity.expected_closing_date_text,
            "expected_closing_date": resolved_date,
        }),
    }
    merged.pop("opportunity_name", None)
    return merged


def _drop_empty_values(payload: dict) -> dict:
    return {key: value for key, value in (payload or {}).items() if value not in (None, "")}


async def _apply_opportunity_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的商机信息，请换一种说法补充。原因：{str(exc)}"
    opportunity = _merge_opportunity_fields(payload.get("opportunity") or {}, semantic_result)
    opportunity["customer_id"] = payload.get("customer_id") or customer.get("id") or opportunity.get("customer_id")
    missing_fields = CRMAgentGraphService.missing_opportunity_fields(opportunity)
    payload["opportunity"] = opportunity
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_opportunity_missing_fields(missing_fields)}。"
        )

    payload = {
        "customer_id": opportunity.get("customer_id"),
        "opportunity": opportunity,
    }
    new_state = {
        "action": "create_opportunity",
        "payload": payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_opportunity"],
            confirmation_summary=f"为「{customer.get('account_name')}」创建商机",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_opportunity",
            input_json=payload,
            state_json=new_state,
        ),
    )
    return True, f"商机信息已补齐。请确认是否为「{customer.get('account_name')}」创建商机？"


async def _apply_contact_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的联系人信息，请换一种说法补充。原因：{str(exc)}"
    contact = _merge_contact_fields(payload.get("contact") or {}, semantic_result)
    missing_fields = CRMAgentGraphService.missing_contact_fields(contact)
    payload["contact"] = contact
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_contact_missing_fields(missing_fields)}。"
        )

    payload = {"customer_id": payload.get("customer_id"), "contact": contact}
    new_state = {
        "action": "create_contact",
        "payload": payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_contact"],
            confirmation_summary=f"为「{customer.get('account_name')}」创建联系人「{contact.get('name')}」",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_contact",
            input_json=payload,
            state_json=new_state,
        ),
    )
    return True, f"联系人信息已补齐。请确认是否为「{customer.get('account_name')}」创建联系人「{contact.get('name')}」？"


async def _apply_invoice_title_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的发票抬头信息，请换一种说法补充。原因：{str(exc)}"
    invoice_title = _merge_invoice_title_fields(payload.get("invoice_title") or {}, semantic_result)
    missing_fields = CRMAgentGraphService.missing_invoice_title_fields(invoice_title)
    set_default = bool(payload.get("set_default")) or bool((semantic_result.invoice_title or {}).get("set_default"))
    payload["invoice_title"] = invoice_title
    payload["missing_fields"] = missing_fields
    payload["set_default"] = set_default

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_invoice_title_missing_fields(missing_fields)}。"
        )

    payload = {
        "customer_id": payload.get("customer_id"),
        "invoice_title": invoice_title,
        "set_default": set_default,
    }
    new_state = {
        "action": "create_invoice_title",
        "payload": payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_invoice_title"],
            confirmation_summary=f"为「{customer.get('account_name')}」创建发票抬头「{invoice_title.get('title')}」",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_invoice_title",
            input_json=payload,
            state_json=new_state,
        ),
    )
    return True, f"发票抬头信息已补齐。请确认是否为「{customer.get('account_name')}」创建发票抬头「{invoice_title.get('title')}」？"


async def _apply_deployment_info_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的部署信息，请换一种说法补充。原因：{str(exc)}"
    deployment_info = _merge_deployment_info_fields(payload.get("deployment_info") or {}, semantic_result)
    deployment_info["customer_id"] = payload.get("customer_id") or deployment_info.get("customer_id")
    missing_fields = CRMAgentGraphService.missing_deployment_info_fields(deployment_info)
    payload["deployment_info"] = deployment_info
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_deployment_info_missing_fields(missing_fields)}。"
        )

    payload = {
        "customer_id": deployment_info.get("customer_id"),
        "deployment_info": deployment_info,
    }
    new_state = {
        "action": "create_deployment_info",
        "payload": payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_deployment_info"],
            confirmation_summary=f"为「{customer.get('account_name')}」创建部署信息「{deployment_info.get('deployment_name')}」",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_deployment_info",
            input_json=payload,
            state_json=new_state,
        ),
    )
    return True, f"部署信息已补齐。请确认是否为「{customer.get('account_name')}」创建部署信息「{deployment_info.get('deployment_name')}」？"


async def _apply_payment_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的回款信息，请换一种说法补充。原因：{str(exc)}"

    payment = _merge_payment_fields(payload.get("payment") or {}, semantic_result)
    missing_fields = CRMAgentGraphService.missing_payment_fields(
        payment.get("actual_amount"),
        payment.get("payment_date_iso"),
    )
    payload["payment"] = payment
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_payment_missing_fields(missing_fields)}。"
        )

    commission_member_id = payload.get("commission_member_id")
    payment_plans = state.get("payment_plans") or payload.get("payment_plans") or []
    contracts = state.get("contracts") or payload.get("contracts") or []

    if len(payment_plans) == 1:
        next_payload = CRMAgentGraphService._payment_record_payload(payment_plans[0], payment, commission_member_id)
        new_state = {
            "action": "create_payment_record",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_record"],
                confirmation_summary=f"为「{customer.get('account_name')}」登记回款 {payment.get('actual_amount')}",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary="等待确认执行：create_payment_record", input_json=next_payload, state_json=new_state))
        return True, f"回款信息已补齐。请确认是否为「{customer.get('account_name')}」登记回款 {payment.get('actual_amount')}？"

    if len(contracts) == 1:
        next_payload = CRMAgentGraphService._payment_plan_payload(contracts[0], payment, commission_member_id)
        new_state = {
            "action": "create_payment_plan",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_plan"],
                confirmation_summary=f"基于合同「{contracts[0].get('contract_name')}」创建回款计划",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary="等待确认执行：create_payment_plan", input_json=next_payload, state_json=new_state))
        return True, f"回款信息已补齐。请确认是否基于合同「{contracts[0].get('contract_name')}」创建回款计划？"

    agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
    return False, "回款信息已补齐，但仍需要先确认合同或回款计划。"


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


async def _execute_waiting_task(
    db: Session,
    task,
    session,
    team_id: int,
    user_id: int,
    authorization: str,
):
    state = task.state_json or {}
    action = state.get("action")
    payload = state.get("payload") or {}
    customer = state.get("customer") or {}
    tool_name = _tool_name_for_action(action)
    tool_payload = _tool_payload_for_action(action, payload, customer, task.task_key)
    context = AgentToolContext(
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=session.id,
        task_id=task.id,
        authorization=authorization,
        hitl_decision="approve",
        confirmed_by_user=True,
        allowed_tool_names=[tool_name] if tool_name else [],
        allowed_customer_ids=[customer["id"]] if customer.get("id") else [],
    )
    registry = AgentToolRegistry(CRMAgentToolService())
    runtime = AgentToolRuntime(registry)

    agent_task_crud.update(db, task, AgentTaskUpdate(status=AgentTaskStatus.RUNNING))
    result = None
    if tool_name and tool_payload:
        result = await runtime.execute(
            tool_name,
            context,
            tool_payload,
            policy=AgentToolExecutionPolicy(
                hitl_decision="approve",
                allowed_tool_names=[tool_name],
                allowed_customer_ids=[customer["id"]] if customer.get("id") else [],
            ),
        )

    if result and result.success:
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(status=AgentTaskStatus.COMPLETED, result_json=result.data),
        )
        if action == "create_payment_plan":
            created_items = result.data.get("items") if isinstance(result.data, dict) else result.data
            created_plan = created_items[0] if isinstance(created_items, list) and created_items else result.data
            pending_record = payload.get("pending_payment_record") or {}
            if isinstance(created_plan, dict) and created_plan.get("id") and pending_record:
                next_payload = {
                    "payment_plan_id": created_plan.get("id"),
                    **pending_record,
                }
                next_task = agent_task_crud.create(
                    db,
                    AgentTaskCreate(
                        task_key=_new_task_key(),
                        team_id=team_id,
                        user_id=user_id,
                        session_id=session.id,
                        intent="PAYMENT_RECORD",
                        status=AgentTaskStatus.WAITING_USER,
                        target_type="customer",
                        target_id=customer.get("id"),
                        summary="等待确认执行：create_payment_record",
                        input_json=next_payload,
                        state_json={
                            "action": "create_payment_record",
                            "payload": next_payload,
                            "customer": customer,
                            "hitl": AgentHITLPolicy(
                                required_for_tools=["create_payment_record"],
                                confirmation_summary="登记本次回款",
                            ).model_dump(exclude_none=True),
                        },
                    ),
                )
                _remember_pending_task(db, session, next_task)
                return result, "回款计划已创建。请确认是否登记本次回款？"
            return result, "回款计划已创建。"
        if action == "create_payment_record":
            return result, "回款已登记，并已按系统现有流程提交审批。"
        if action == "create_contact":
            return result, "联系人已创建。"
        if action == "create_invoice_title":
            return result, "发票抬头已创建。"
        if action == "create_deployment_info":
            return result, "部署信息已创建。"
        if action == "create_opportunity":
            return result, "商机已创建，并已按系统现有流程提交审批。"
        if action == "move_opportunity_stage":
            stage_name = None
            if isinstance(result.data, dict):
                current_stage = result.data.get("current_stage_snapshot") or {}
                stage_name = current_stage.get("stage_name")
            return result, f"商机阶段已推进{f'到「{stage_name}」' if stage_name else ''}。"
        if action == "create_customer_follow_up" and isinstance(payload.get("_next_task"), dict):
            next_action = payload["_next_task"]
            next_payload = next_action.get("payload") or {}
            next_task = agent_task_crud.create(
                db,
                AgentTaskCreate(
                    task_key=_new_task_key(),
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    intent="CUSTOMER_FOLLOW_UP",
                    status=AgentTaskStatus.WAITING_USER,
                    target_type="customer",
                    target_id=next_payload.get("customer_id") or customer.get("id"),
                    summary=f"等待确认执行：{next_action.get('action')}",
                    input_json=next_payload,
                    state_json={
                        "action": next_action.get("action"),
                        "payload": next_payload,
                        "customer": next_action.get("customer") or customer,
                        "hitl": AgentHITLPolicy(
                            required_for_tools=[_tool_name_for_action(next_action.get("action"))]
                            if _tool_name_for_action(next_action.get("action"))
                            else [],
                            confirmation_summary=next_action.get("content") or "等待确认执行下一步动作",
                        ).model_dump(exclude_none=True),
                    },
                ),
            )
            _remember_pending_task(db, session, next_task)
            return result, "跟进记录已创建。" + (next_action.get("content") or "请确认是否执行下一步动作？")
        return result, "跟进记录已创建。"

    error_message = result.error_message if result else f"暂不支持的执行动作：{action}"
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.FAILED, error_message=error_message),
    )
    return result, f"执行失败：{error_message}"


def _tool_name_for_action(action: Optional[str]) -> Optional[str]:
    return {
        "create_customer_follow_up": "create_customer_follow_up",
        "create_contact": "create_contact",
        "create_invoice_title": "create_invoice_title",
        "create_deployment_info": "create_deployment_info",
        "create_opportunity": "create_opportunity",
        "move_opportunity_stage": "move_opportunity_stage",
        "create_payment_plan": "create_payment_plan",
        "create_payment_record": "create_payment_record",
    }.get(action or "")


def _tool_payload_for_action(action: Optional[str], payload: dict, customer: dict, task_key: str) -> Optional[dict]:
    if action == "create_customer_follow_up":
        return {
            "customer_id": payload["customer_id"],
            "customer_name": customer.get("account_name"),
            "content": payload["content"],
            "method": payload.get("method") or "AI录入",
            "next_action": payload.get("next_action"),
            "next_follow_time": payload.get("next_follow_time_iso"),
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
            trace_events: list[dict] = []

            def emit(event: dict) -> str:
                _append_trace_event(trace_events, event)
                return _encode_sse(event)

            authorization = _authorization_header(credentials)
            task = _get_current_waiting_task(db, session, team_id, user_id)
            switch_notice = None
            pending_interruption_handled = False
            if task and not _is_confirmation(request.content):
                interruption_decision = await _assess_pending_interruption(
                    db,
                    team_id=team_id,
                    session=session,
                    task=task,
                    user_message=request.content,
                )
                yield emit({
                    "event": "pending_interruption_assessed",
                    "decision": interruption_decision.decision,
                    "confidence": interruption_decision.confidence,
                    "detected_customer_name": interruption_decision.detected_customer_name,
                    "detected_intent": interruption_decision.detected_intent,
                    "reason": interruption_decision.reason,
                })
                if _is_high_confidence_new_flow(interruption_decision):
                    customer_name = interruption_decision.detected_customer_name or "新的客户"
                    switch_notice = f"这条看起来是在说「{customer_name}」，和刚才的待处理任务不是同一个流程。我先切过来处理。"
                    suspended_task_id = task.id
                    _suspend_pending_task(db, session, task, interruption_decision.reason or "用户开启了新的业务流程")
                    task = None
                    yield emit({
                        "event": "pending_task_interrupted",
                        "content": switch_notice,
                        "suspended_task_id": suspended_task_id,
                    })
                elif _is_ambiguous_pending_interruption(interruption_decision):
                    assistant_content = interruption_decision.question or "这句像是新流程，也可能是在补刚才的任务。你要我切到新流程，还是继续刚才的任务？"
                    pending_interruption_handled = True
                    yield emit({
                        "event": "pending_interruption_confirmation_required",
                        "task_id": task.id,
                        "content": assistant_content,
                        "decision": interruption_decision.model_dump(),
                    })
                    yield emit({"event": "final", "content": assistant_content})

            if pending_interruption_handled:
                pass
            elif task and _is_contact_fields_task(task):
                ready, assistant_content = await _apply_contact_fields(db, task, request.content)
                _remember_pending_task(db, session, task)
                yield emit({
                    "event": "contact_fields_completed" if ready else "contact_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and _is_opportunity_fields_task(task):
                ready, assistant_content = await _apply_opportunity_fields(db, task, request.content)
                _remember_pending_task(db, session, task)
                yield emit({
                    "event": "opportunity_fields_completed" if ready else "opportunity_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and _is_invoice_title_fields_task(task):
                ready, assistant_content = await _apply_invoice_title_fields(db, task, request.content)
                _remember_pending_task(db, session, task)
                yield emit({
                    "event": "invoice_title_fields_completed" if ready else "invoice_title_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and _is_deployment_info_fields_task(task):
                ready, assistant_content = await _apply_deployment_info_fields(db, task, request.content)
                _remember_pending_task(db, session, task)
                yield emit({
                    "event": "deployment_info_fields_completed" if ready else "deployment_info_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and _is_payment_fields_task(task):
                ready, assistant_content = await _apply_payment_fields(db, task, request.content)
                _remember_pending_task(db, session, task)
                yield emit({
                    "event": "payment_fields_completed" if ready else "payment_fields_required",
                    "task_id": task.id,
                    "content": assistant_content,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and _is_business_selection_task(task):
                selected, assistant_content = _apply_business_selection(db, task, request.content)
                _remember_pending_task(db, session, task)
                yield emit({
                    "event": "business_selected" if selected else "business_selection_failed",
                    "task_id": task.id,
                    "content": assistant_content,
                    "selected": selected,
                })
                yield emit({"event": "final", "content": assistant_content})
            elif task and _is_customer_selection_task(task):
                customer, assistant_content = _apply_customer_selection(db, task, request.content)
                if customer:
                    _remember_current_customer(db, session, customer)
                    if task.status == AgentTaskStatus.WAITING_USER:
                        _remember_pending_task(db, session, task)
                    else:
                        _clear_pending_task(db, session, task.id)
                    yield emit({
                        "event": "customer_selected",
                        "task_id": task.id,
                        "customer": customer,
                        "content": assistant_content,
                    })
                else:
                    yield emit({
                        "event": "customer_selection_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                    })
                yield emit({"event": "final", "content": assistant_content})
            elif _is_confirmation(request.content):
                if task:
                    result, assistant_content = await _execute_waiting_task(
                        db,
                        task,
                        session=session,
                        team_id=team_id,
                        user_id=user_id,
                        authorization=authorization,
                    )
                    if result:
                        yield emit(result.to_event())
                    if result and result.success:
                        _clear_pending_task(db, session, task.id)
                    yield emit({
                        "event": "task_completed" if result and result.success else "task_failed",
                        "task_id": task.id,
                        "content": assistant_content,
                    })
                    yield emit({"event": "final", "content": assistant_content})
                else:
                    assistant_content = "当前没有等待确认的操作。"
                    yield emit({"event": "final", "content": assistant_content})
            else:
                async for event in crm_agent_graph_service.stream_events({
                    "db": db,
                    "team_id": team_id,
                    "user_id": user_id,
                    "session_id": session.id,
                    "session_context": session.context_json or {},
                    "content": request.content,
                    "authorization": authorization,
                }):
                    if event.get("event") in {
                        "confirmation_required",
                        "customer_selection_required",
                        "contact_fields_required",
                        "invoice_title_fields_required",
                        "deployment_info_fields_required",
                        "payment_fields_required",
                        "opportunity_fields_required",
                        "business_selection_required",
                    }:
                        _create_waiting_task_from_event(db, event, team_id, user_id, session)
                    if event.get("event") == "business_context_loaded":
                        _remember_current_customer(db, session, event.get("customer"))
                    if event.get("event") == "final":
                        assistant_content = event.get("content")
                        if switch_notice and assistant_content:
                            event = {**event, "content": f"{switch_notice}\n\n{assistant_content}"}
                            assistant_content = event["content"]
                    yield emit(event)

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
                    payload_json={"source": "langgraph", "trace_events": trace_events},
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
