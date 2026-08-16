"""Agent lead field collection."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.agent import AgentTaskUpdate
from app.services.agent import business_rules
from app.services.agent.field_common import _drop_empty_values, _parse_task_field_supplement
from app.services.agent.follow_up_fields import _merge_lead_follow_up_fields
from app.services.agent.schemas import AgentHITLPolicy, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParserError
from app.services.agent.task_projection import update_agent_task


def _is_lead_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_lead_fields"

def _merge_lead_fields(existing_lead: dict, semantic_result: AgentSemanticParseResult) -> dict:
    return {
        **existing_lead,
        **_drop_empty_values({
            "lead_name": semantic_result.lead.lead_name,
            "source": semantic_result.lead.source,
            "city": semantic_result.lead.city,
            "contact_name": semantic_result.lead.contact_name,
            "contact_phone": semantic_result.lead.contact_phone,
            "company_scale": semantic_result.lead.company_scale,
        }),
    }

async def _apply_lead_fields(db: Session, task, content: str):
    state = task.state_json or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的线索信息，请换一种说法补充。原因：{str(exc)}"

    lead = _merge_lead_fields(payload.get("lead") or {}, semantic_result)
    lead.setdefault("source", "其他")
    lead_follow_up = _merge_lead_follow_up_fields(payload.get("lead_follow_up") or {}, semantic_result)
    missing_fields = business_rules.missing_lead_fields(lead)
    payload["lead"] = lead
    payload["lead_follow_up"] = lead_follow_up
    payload["missing_fields"] = missing_fields
    state = {**state, "payload": payload}

    if missing_fields:
        update_agent_task(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{business_rules.format_lead_missing_fields(missing_fields)}。"
        )

    next_payload = {"lead": lead, "lead_follow_up": lead_follow_up}
    new_state = {
        "action": "create_lead",
        "payload": next_payload,
        "hitl": AgentHITLPolicy(
            required_for_tools=["create_lead"],
            confirmation_summary=f"创建线索「{lead.get('lead_name')}」",
        ).model_dump(exclude_none=True),
    }
    update_agent_task(
        db,
        task,
        AgentTaskUpdate(
            summary="等待确认创建线索",
            input_json=next_payload,
            state_json=new_state,
        ),
    )
    return True, f"线索信息已补齐。请确认是否创建线索「{lead.get('lead_name')}」？"
