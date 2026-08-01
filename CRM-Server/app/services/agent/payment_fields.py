"""Agent payment field collection."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.schemas.agent import AgentTaskUpdate
from app.services.agent import business_rules
from app.services.agent.schemas import AgentHITLPolicy, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParserError
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.field_common import _drop_empty_values, _parse_task_field_supplement

def _is_payment_fields_task(task) -> bool:
    state = task.state_json or {}
    return state.get("action") == "collect_payment_fields"

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

async def _apply_payment_fields(db: Session, task, content: str):
    state = task.state_json or {}
    customer = state.get("customer") or {}
    payload = state.get("payload") or {}
    try:
        semantic_result = await _parse_task_field_supplement(db, task, content)
    except AgentSemanticParserError as exc:
        return False, f"我没有可靠识别到补充的回款信息，请换一种说法补充。原因：{str(exc)}"

    payment = _merge_payment_fields(payload.get("payment") or {}, semantic_result)
    missing_fields = business_rules.missing_payment_fields(
        payment.get("actual_amount"),
        payment.get("payment_date_iso"),
    )
    payload["payment"] = payment
    payload["missing_fields"] = missing_fields

    if missing_fields:
        agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
        return False, (
            "还需要补充："
            f"{business_rules.format_payment_missing_fields(missing_fields)}。"
        )

    commission_member_id = payload.get("commission_member_id")
    payment_plans = state.get("payment_plans") or payload.get("payment_plans") or []
    contracts = state.get("contracts") or payload.get("contracts") or []

    if len(payment_plans) == 1:
        next_payload = business_rules.payment_record_payload(payment_plans[0], payment, commission_member_id)
        new_state = {
            "action": "create_payment_record",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_record"],
                confirmation_summary=f"为「{customer.get('account_name')}」登记回款 {payment.get('actual_amount')}",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary="等待确认登记回款", input_json=next_payload, state_json=new_state))
        return True, f"回款信息已补齐。请确认是否为「{customer.get('account_name')}」登记回款 {payment.get('actual_amount')}？"

    if len(contracts) == 1:
        next_payload = business_rules.payment_plan_payload(contracts[0], payment, commission_member_id)
        new_state = {
            "action": "create_payment_plan",
            "payload": next_payload,
            "customer": customer,
            "hitl": AgentHITLPolicy(
                required_for_tools=["create_payment_plan"],
                confirmation_summary=f"基于合同「{contracts[0].get('contract_name')}」创建回款计划",
            ).model_dump(exclude_none=True),
        }
        agent_task_crud.update(db, task, AgentTaskUpdate(summary="等待确认创建回款计划", input_json=next_payload, state_json=new_state))
        return True, f"回款信息已补齐。请确认是否基于合同「{contracts[0].get('contract_name')}」创建回款计划？"

    agent_task_crud.update(db, task, AgentTaskUpdate(input_json=payload, state_json=state))
    return False, "回款信息已补齐，但仍需要先确认合同或回款计划。"
