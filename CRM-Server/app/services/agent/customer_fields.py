"""Agent customer field collection."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.schemas.agent import AgentTaskUpdate
from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.schemas import AgentHITLPolicy, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParserError
from app.services.agent.field_common import _drop_empty_values, _parse_task_field_supplement
from app.services.agent.follow_up_fields import _merge_customer_follow_up_fields

def _is_customer_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_customer_fields"

def _merge_customer_fields(existing_customer: dict, semantic_result: AgentSemanticParseResult) -> dict:
    customer = semantic_result.customer_create
    return {
        **existing_customer,
        **_drop_empty_values({
            "account_name": customer.account_name,
            "source": customer.source,
            "city": customer.city,
            "industry": customer.industry,
            "company_scale": customer.company_scale,
            "contact_name": customer.contact_name,
            "contact_phone": customer.contact_phone,
            "contact_position": customer.contact_position,
            "contact_gender": customer.contact_gender,
            "contact_email": customer.contact_email,
        }),
    }

async def _apply_customer_fields(db: Session, task, content: str):
    state = task.state_json or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的客户信息，请换一种说法补充。原因：{str(exc)}"

    customer = _merge_customer_fields(payload.get("customer") or {}, semantic_result)
    customer.setdefault("source", "其他")
    customer_follow_up = _merge_customer_follow_up_fields(payload.get("customer_follow_up") or {}, semantic_result)
    missing_fields = CRMAgentGraphService.missing_customer_fields(customer)
    payload["customer"] = customer
    payload["customer_follow_up"] = customer_follow_up
    payload["missing_fields"] = missing_fields
    state = {**state, "payload": payload}

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_customer_missing_fields(missing_fields)}。"
        )

    next_payload = {"customer": customer, "customer_follow_up": customer_follow_up}
    new_state = {
        "action": "create_customer",
        "payload": next_payload,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_customer"],
            confirmation_summary=f"创建客户「{customer.get('account_name')}」",
        ).model_dump(exclude_none=True),
    }
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认执行：create_customer",
            input_json=next_payload,
            state_json=new_state,
        ),
    )
    return True, f"客户信息已补齐。请确认是否创建客户「{customer.get('account_name')}」？"
