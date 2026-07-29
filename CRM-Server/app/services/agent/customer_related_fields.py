"""Agent customer related record field collection."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.schemas.agent import AgentTaskUpdate
from app.services.agent import business_rules
from app.services.agent.schemas import AgentHITLPolicy, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParserError
from app.services.agent.field_common import _drop_empty_values, _parse_task_field_supplement

def _is_contact_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_contact_fields"

def _is_invoice_title_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_invoice_title_fields"

def _is_deployment_info_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_deployment_info_fields"

def _is_customer_member_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_customer_member_fields"

def _merge_contact_fields(existing_contact: dict, semantic_result: AgentSemanticParseResult) -> dict:
    return {**existing_contact, **_drop_empty_values(semantic_result.contact)}

def _merge_invoice_title_fields(existing_invoice_title: dict, semantic_result: AgentSemanticParseResult) -> dict:
    merged = {**existing_invoice_title, **_drop_empty_values(semantic_result.invoice_title)}
    merged.pop("set_default", None)
    return merged

def _merge_deployment_info_fields(existing_deployment_info: dict, semantic_result: AgentSemanticParseResult) -> dict:
    return {**existing_deployment_info, **_drop_empty_values(semantic_result.deployment_info)}

def _merge_customer_member_fields(existing_member: dict, semantic_result: AgentSemanticParseResult) -> dict:
    return {**existing_member, **_drop_empty_values(semantic_result.customer_member)}

async def _apply_contact_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的联系人信息，请换一种说法补充。原因：{str(exc)}"
    contact = _merge_contact_fields(payload.get("contact") or {}, semantic_result)
    missing_fields = business_rules.missing_contact_fields(contact)
    payload["contact"] = contact
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{business_rules.format_contact_missing_fields(missing_fields)}。"
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
    missing_fields = business_rules.missing_invoice_title_fields(invoice_title)
    set_default = bool(payload.get("set_default")) or bool((semantic_result.invoice_title or {}).get("set_default"))
    payload["invoice_title"] = invoice_title
    payload["missing_fields"] = missing_fields
    payload["set_default"] = set_default

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{business_rules.format_invoice_title_missing_fields(missing_fields)}。"
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
    missing_fields = business_rules.missing_deployment_info_fields(deployment_info)
    payload["deployment_info"] = deployment_info
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{business_rules.format_deployment_info_missing_fields(missing_fields)}。"
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

async def _apply_customer_member_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的成员信息，请换一种说法补充。原因：{str(exc)}"
    member = _merge_customer_member_fields(payload.get("customer_member") or {}, semantic_result)
    missing_fields = business_rules.missing_customer_member_fields(member)
    if missing_fields:
        payload["customer_member"] = member
        payload["missing_fields"] = missing_fields
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{business_rules.format_customer_member_missing_fields(missing_fields)}。"
        )

    resolved_member, member_error = business_rules.resolve_customer_member(
        member,
        {"member_candidates": payload.get("member_candidates")},
    )
    if member_error:
        payload["customer_member"] = member
        payload["missing_fields"] = ["user_name"]
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, member_error

    next_payload = {"customer_id": payload.get("customer_id") or customer.get("id"), "member": resolved_member}
    new_state = {
        "action": "create_customer_member",
        "payload": next_payload,
        "customer": customer,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_customer_member"],
            confirmation_summary=f"为「{customer.get('account_name')}」添加客户成员「{resolved_member.get('user_name') or resolved_member.get('user_id')}」",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_customer_member",
            input_json=next_payload,
            state_json=new_state,
        ),
    )
    return True, f"成员信息已补齐。请确认是否为「{customer.get('account_name')}」添加客户成员「{resolved_member.get('user_name') or resolved_member.get('user_id')}」？"
