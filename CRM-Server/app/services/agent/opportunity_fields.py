"""Agent opportunity field collection."""
from __future__ import annotations

from copy import deepcopy
from typing import Optional

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.schemas.agent import AgentTaskUpdate
from app.services.agent.graph import CRMAgentGraphService
from app.services.agent.schemas import AgentHITLPolicy, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParserError
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.field_common import _drop_empty_values, _extract_generated_form_int, _parse_task_field_supplement
from app.services.agent.interactions import (
    _customer_requires_procurement_method,
    _opportunity_field_defaults,
    _opportunity_interaction_fields,
    _opportunity_missing_display_fields,
)

def _is_opportunity_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_opportunity_fields"

def _merge_opportunity_fields(existing_opportunity: dict, semantic_result: AgentSemanticParseResult) -> dict:
    opportunity = semantic_result.opportunity
    resolved_date = agent_temporal_resolver.resolve_date(opportunity.expected_closing_date)
    merged = {
        **existing_opportunity,
        **_drop_empty_values({
            "procurement_method_id": opportunity.procurement_method_id,
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

async def _apply_opportunity_fields(db: Session, task, content: str):
    state = deepcopy(task.state_json or {})
    customer = state.get("customer") or {}
    payload = deepcopy(state.get("payload") or {})
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的商机信息，请换一种说法补充。原因：{str(exc)}"
    opportunity = _merge_opportunity_fields(payload.get("opportunity") or {}, semantic_result)
    procurement_method_id = _extract_generated_form_int(content, "procurement_method_id")
    if procurement_method_id is not None:
        opportunity["procurement_method_id"] = procurement_method_id
    opportunity["customer_id"] = payload.get("customer_id") or customer.get("id") or opportunity.get("customer_id")
    interaction_fields = payload.get("interaction_fields")
    require_procurement_method = (
        _customer_requires_procurement_method(customer)
        or "procurement_method_id" in [str(field) for field in payload.get("missing_fields") or []]
    )
    missing_fields = CRMAgentGraphService.missing_opportunity_fields(
        opportunity,
        require_procurement_method=require_procurement_method,
    )
    payload["opportunity"] = opportunity
    payload["missing_fields"] = missing_fields
    payload["interaction_fields"] = _opportunity_interaction_fields(missing_fields, customer)
    payload["field_defaults"] = _opportunity_field_defaults(customer)
    state = {**state, "payload": payload}

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{CRMAgentGraphService.format_opportunity_missing_fields(_opportunity_missing_display_fields(missing_fields, customer))}。"
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
