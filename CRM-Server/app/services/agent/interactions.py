"""Agent interaction payload builders."""
from __future__ import annotations

from copy import deepcopy
import json
import uuid
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
from app.services.agent import business_rules
from app.services.agent import agent_copy
from app.services.agent import choice_resolution
from app.services.agent import task_display
from app.services.agent.interaction_contract import (
    INTERACTION_TYPE_CHOICE,
    INTERACTION_TYPE_FORM,
    INTERACTION_TYPE_TEXT,
    STATUS_WAITING_CONFIRMATION,
    STATUS_WAITING_USER_INPUT,
    build_interaction,
    payload_from_event,
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


def _append_trace_event(trace_events: list[dict], event: dict) -> None:
    if event.get("event") in {"session", "message", "final", "done"}:
        return
    trace_events.append(json.loads(json.dumps(event, ensure_ascii=False, cls=SSEJsonEncoder)))

def _choice_interaction(
    prompt: str,
    choices: list[dict[str, object]],
    *,
    event: Optional[dict[str, object]] = None,
    title: Optional[str] = None,
    business_action: Optional[str] = None,
    status: str = STATUS_WAITING_USER_INPUT,
) -> dict[str, object]:
    event = event or {}
    return build_interaction(
        event_name=event.get("event"),
        interaction_type=INTERACTION_TYPE_CHOICE,
        prompt=prompt,
        choices=choices,
        status=status,
        title=title,
        business_action=business_action,
        payload=payload_from_event(event),
        task_id=event.get("task_id"),
        task_key=event.get("task_key"),
    )

def _form_field(
    key: str,
    label: str,
    field_type: str = "text",
    *,
    required: bool = True,
    options: Optional[list[dict[str, str]]] = None,
    placeholder: Optional[str] = None,
    default_value: Optional[object] = None,
) -> dict[str, object]:
    field = {
        "key": key,
        "label": label,
        "type": field_type,
        "required": required,
    }
    if options:
        field["options"] = options
    if placeholder:
        field["placeholder"] = placeholder
    if default_value is not None:
        field["default_value"] = str(default_value)
    return field

def _procurement_method_options(db: Optional[Session], team_id: Optional[int]) -> list[dict[str, str]]:
    if db is None or team_id is None:
        return []
    try:
        methods, _ = procurement_method_crud.get_multi(db, team_id=team_id, skip=0, limit=100, is_active=1)
    except SQLAlchemyError:
        db.rollback()
        return []
    return [{"label": method.name, "value": str(method.id)} for method in methods]

def _customer_requires_procurement_method(customer: dict) -> bool:
    return business_rules.customer_requires_procurement_method(customer)

def _customer_default_procurement_method_id(customer: dict) -> Optional[int]:
    return business_rules.customer_default_procurement_method_id(customer)

def _opportunity_interaction_fields(missing_fields: list[str], customer: dict) -> list[str]:
    return business_rules.opportunity_interaction_fields(missing_fields)

def _opportunity_missing_display_fields(missing_fields: list[str], customer: dict) -> list[str]:
    return business_rules.opportunity_missing_display_fields(missing_fields)

def _opportunity_field_defaults(
    customer: dict,
    *,
    db: Optional[Session] = None,
    team_id: Optional[int] = None,
    customer_id: Optional[int] = None,
) -> dict[str, object]:
    default_procurement_method_id = _customer_default_procurement_method_id(customer)
    if default_procurement_method_id is None and db is not None and customer_id:
        try:
            row = (
                db.query(Customer.default_procurement_method_id)
                .filter(Customer.id == customer_id, Customer.team_id == team_id)
                .first()
            )
            default_procurement_method_id = row[0] if row else None
        except SQLAlchemyError:
            db.rollback()
            default_procurement_method_id = None
    if default_procurement_method_id is None:
        return {}
    return {"procurement_method_id": default_procurement_method_id}

def _fields_for_missing(
    kind: str,
    missing_fields: list[str],
    *,
    db: Optional[Session] = None,
    team_id: Optional[int] = None,
    default_values: Optional[dict[str, object]] = None,
) -> list[dict[str, object]]:
    default_values = default_values or {}
    option_sets = {
        "license_type": [
            {"label": "订阅", "value": "订阅"},
            {"label": "买断", "value": "买断"},
        ],
        "purchase_type": [
            {"label": "新购", "value": "新购"},
            {"label": "续购", "value": "续购"},
            {"label": "增购", "value": "增购"},
        ],
        "gender": [
            {"label": "男", "value": "男"},
            {"label": "女", "value": "女"},
            {"label": "未知", "value": "未知"},
        ],
        "title_type": [
            {"label": "单位", "value": "单位"},
            {"label": "个人", "value": "个人"},
        ],
        "member_role": [
            {"label": "售前", "value": "售前"},
            {"label": "销售", "value": "销售"},
            {"label": "实施", "value": "实施"},
        ],
    }
    procurement_options = (
        _procurement_method_options(db, team_id)
        if "procurement_method_id" in missing_fields
        else []
    )
    if procurement_options:
        option_sets["procurement_method_id"] = procurement_options
    labels = {
        "total_amount": "预计成交金额",
        "user_count": "采购用户数",
        "license_type": "授权模式",
        "subscription_years": "订阅年限",
        "purchase_type": "采购类型",
        "procurement_method_id": "采购方式",
        "expected_closing_date": "预计成交日期",
        "name": "联系人姓名",
        "mobile": "手机号",
        "position": "职务",
        "gender": "性别",
        "title_type": "抬头类型",
        "title": "开票抬头",
        "taxpayer_id": "纳税人识别号",
        "deployment_name": "部署名称",
        "server_address": "服务器地址",
        "authorized_users": "授权人数",
        "user_name": "成员姓名",
        "actual_amount": "实际回款金额",
        "payment_date": "实际回款日期",
        "lead_name": "线索名称",
        "account_name": "客户名称",
        "source": "来源",
        "city": "所在城市",
        "contact_name": "联系人姓名",
        "contact_phone": "联系人手机号",
        "contact_position": "联系人职务",
        "contact_gender": "联系人性别",
        "company_scale": "公司规模",
    }
    numeric_fields = {"total_amount", "user_count", "subscription_years", "authorized_users", "actual_amount"}
    date_fields = {"expected_closing_date", "payment_date"}
    if kind == "lead":
        option_sets["source"] = [
            {"label": "线上注册", "value": "线上注册"},
            {"label": "市场活动", "value": "市场活动"},
            {"label": "客户推荐", "value": "客户推荐"},
            {"label": "电话营销", "value": "电话营销"},
            {"label": "网站咨询", "value": "网站咨询"},
            {"label": "展会", "value": "展会"},
            {"label": "其他", "value": "其他"},
        ]
        option_sets["company_scale"] = [
            {"label": "1-50人", "value": "1-50人"},
            {"label": "51-200人", "value": "51-200人"},
            {"label": "201-500人", "value": "201-500人"},
            {"label": "501-1000人", "value": "501-1000人"},
            {"label": "1000人以上", "value": "1000人以上"},
        ]
    if kind == "customer":
        option_sets["source"] = [
            {"label": "线上注册", "value": "线上注册"},
            {"label": "市场活动", "value": "市场活动"},
            {"label": "客户推荐", "value": "客户推荐"},
            {"label": "电话营销", "value": "电话营销"},
            {"label": "网站咨询", "value": "网站咨询"},
            {"label": "展会", "value": "展会"},
            {"label": "其他", "value": "其他"},
        ]
        option_sets["company_scale"] = [
            {"label": "1-50人", "value": "1-50人"},
            {"label": "51-200人", "value": "51-200人"},
            {"label": "201-500人", "value": "201-500人"},
            {"label": "501-1000人", "value": "501-1000人"},
            {"label": "1000人以上", "value": "1000人以上"},
        ]
        option_sets["contact_gender"] = option_sets["gender"]
    fields = []
    for key in missing_fields:
        required = not (kind == "opportunity" and key == "subscription_years" and "license_type" in missing_fields)
        if key in option_sets:
            fields.append(_form_field(key, labels.get(key, key), "select", required=required, options=option_sets[key], default_value=default_values.get(key)))
        elif key in numeric_fields:
            fields.append(_form_field(key, labels.get(key, key), "number", required=required, default_value=default_values.get(key)))
        elif key in date_fields:
            fields.append(_form_field(key, labels.get(key, key), "date", required=required, default_value=default_values.get(key)))
        else:
            fields.append(_form_field(key, labels.get(key, key), "text", required=required, default_value=default_values.get(key)))
    if kind == "customer_member" and not any(field["key"] == "member_role" for field in fields):
        fields.append(_form_field("member_role", "成员角色", "select", required=False, options=option_sets["member_role"]))
    return fields

def _interaction_for_event(
    event: dict,
    *,
    db: Optional[Session] = None,
    team_id: Optional[int] = None,
) -> Optional[dict[str, object]]:
    event_name = event.get("event")
    content = str(event.get("content") or "")
    if event.get("interaction"):
        return event["interaction"]
    if event_name == "confirmation_required":
        return _choice_interaction(_confirmation_prompt(content, event), [
            {"label": "是", "value": "是"},
            {"label": "否", "value": "否"},
        ], event=event, status=STATUS_WAITING_CONFIRMATION)
    if event_name == "customer_selection_required":
        raw_customers = event.get("customers") or []
        customers = [item for item in raw_customers if isinstance(item, dict)] if isinstance(raw_customers, list) else []
        choices = choice_resolution.project_choices(choice_resolution.CUSTOMER_SPEC, customers)
        return _choice_interaction(content or agent_copy.choose_customer(), choices, event=event)
    if event_name == "business_selection_required":
        choices = choice_resolution.project_business_choices(event)
        return _choice_interaction(content or agent_copy.choose_business_object(), choices, event=event)
    form_kinds = {
        "opportunity_fields_required": "opportunity",
        "contact_fields_required": "contact",
        "invoice_title_fields_required": "invoice_title",
        "deployment_info_fields_required": "deployment_info",
        "customer_member_fields_required": "customer_member",
        "payment_fields_required": "payment",
        "lead_fields_required": "lead",
        "customer_fields_required": "customer",
    }
    if event_name in form_kinds:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        missing_fields = payload.get("missing_fields") if isinstance(payload, dict) else None
        if not isinstance(missing_fields, list):
            missing_fields = []
        interaction_fields = payload.get("interaction_fields") if isinstance(payload, dict) else None
        if not isinstance(interaction_fields, list):
            interaction_fields = missing_fields
        default_values = payload.get("field_defaults") if isinstance(payload, dict) else None
        if not isinstance(default_values, dict):
            default_values = {}
        if form_kinds[event_name] == "opportunity":
            payload_customer_id = payload.get("customer_id")
            customer_id = payload_customer_id if isinstance(payload_customer_id, int) else None
            default_values = {
                **_opportunity_field_defaults({}, db=db, team_id=team_id, customer_id=customer_id),
                **default_values,
            }
        fields = _fields_for_missing(
                form_kinds[event_name],
                [str(field) for field in interaction_fields],
                db=db,
                team_id=team_id,
                default_values=default_values,
            )
        return build_interaction(
            event_name=event_name,
            interaction_type=INTERACTION_TYPE_FORM,
            prompt=content or agent_copy.fill_fields(str(form_kinds[event_name]), interaction_fields),
            submit_label="提交",
            fields=fields,
            status=STATUS_WAITING_USER_INPUT,
            payload=payload_from_event(event, extra={
                "missing_fields": [str(field) for field in missing_fields],
                "interaction_fields": [str(field) for field in interaction_fields],
            }),
            task_id=event.get("task_id"),
            task_key=event.get("task_key"),
        )
    if event_name == "follow_up_quality_required":
        return build_interaction(
            event_name=event_name,
            interaction_type=INTERACTION_TYPE_TEXT,
            prompt=content or agent_copy.follow_up_quality_prompt(),
            placeholder="补充跟进背景、下一步动作、时间或负责人...",
            submit_label="补充",
            status=STATUS_WAITING_USER_INPUT,
            payload=payload_from_event(event),
            task_id=event.get("task_id"),
            task_key=event.get("task_key"),
        )
    if event_name == "pending_interruption_confirmation_required":
        return _choice_interaction(content or agent_copy.pending_interruption_prompt(), [
            {"label": "切换新流程", "value": "切换新流程"},
            {"label": "继续刚才", "value": "继续刚才"},
        ], event=event, status=STATUS_WAITING_CONFIRMATION)
    if event_name == "turn_relation_clarification_required":
        candidates = event.get("candidates") if isinstance(event.get("candidates"), list) else []
        choices = []
        for index, candidate in enumerate(candidates[:2], start=1):
            if not isinstance(candidate, dict):
                continue
            summary = _turn_relation_candidate_summary(candidate, index)
            continue_label = f"继续处理：{summary}"
            choice: dict[str, object] = {
                "label": continue_label,
                "value": continue_label,
            }
            if candidate.get("id") is not None:
                choice["metadata"] = {"selected_task_id": candidate.get("id")}
            choices.append(choice)
        choices.append({
            "label": "作为新流程处理",
            "value": "作为新流程处理",
            "metadata": {"turn_relation": "START_NEW_FLOW"},
        })
        return _choice_interaction(
            _turn_relation_prompt(content, candidates),
            choices,
            event=event,
            status=STATUS_WAITING_USER_INPUT,
        )
    return None


def _turn_relation_candidate_summary(candidate: dict[object, object], index: int) -> str:
    return task_display.readable_task_summary_from_candidate(candidate, index=index)


def _confirmation_prompt(content: str, event: dict) -> str:
    action_label = task_display.readable_action_label(event.get("action"))
    if _is_internal_confirmation_content(content):
        return agent_copy.confirm_prompt(action_label)
    if content.strip():
        return content
    return agent_copy.confirm_prompt(action_label)


def _is_internal_confirmation_content(content: str) -> bool:
    value = content.strip()
    return bool(value and ("_" in value or "等待确认执行：" in value))


def _turn_relation_prompt(content: str, candidates: list[object]) -> str:
    if content.strip() and "_" not in content and "等待确认执行：" not in content:
        return content
    summaries = [
        _turn_relation_candidate_summary(candidate, index)
        for index, candidate in enumerate(candidates[:2], start=1)
        if isinstance(candidate, dict)
    ]
    return agent_copy.turn_relation_clarification(summary for summary in summaries if summary)

def _with_interaction(event: dict, *, db: Optional[Session] = None, team_id: Optional[int] = None) -> dict:
    interaction = _interaction_for_event(event, db=db, team_id=team_id)
    if interaction is None:
        return event
    return {**event, "interaction": interaction}

def _pending_task_confirmation_interaction(content: str) -> dict[str, object]:
    return _choice_interaction(content or "要继续处理下一步吗？", [
        {"label": "继续处理", "value": "是"},
    ], event={"event": "confirmation_required"}, status=STATUS_WAITING_CONFIRMATION)


def _pending_task_interaction(task, content: str, *, db: Optional[Session] = None, team_id: Optional[int] = None) -> dict[str, object]:
    state = task.state_json or {}
    action = state.get("action")
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    customer = state.get("customer")
    event_names = {
        "collect_opportunity_fields": "opportunity_fields_required",
        "collect_contact_fields": "contact_fields_required",
        "collect_invoice_title_fields": "invoice_title_fields_required",
        "collect_deployment_info_fields": "deployment_info_fields_required",
        "collect_customer_member_fields": "customer_member_fields_required",
        "collect_payment_fields": "payment_fields_required",
        "collect_lead_fields": "lead_fields_required",
        "collect_customer_fields": "customer_fields_required",
        "collect_follow_up_quality_fields": "follow_up_quality_required",
        "collect_lead_follow_up_quality_fields": "follow_up_quality_required",
        "create_opportunity": "confirmation_required",
        "move_opportunity_stage": "confirmation_required",
        "select_opportunity_for_stage_move": "business_selection_required",
        "create_customer_activity": "confirmation_required",
        "create_lead_follow_up": "confirmation_required",
        "create_payment_record": "confirmation_required",
        "create_payment_plan": "confirmation_required",
        "create_lead": "confirmation_required",
        "create_customer": "confirmation_required",
    }
    event_name = event_names.get(str(action))
    if not event_name:
        return _pending_task_confirmation_interaction(content)
    event = {
        "event": event_name,
        "action": action,
        "task_id": getattr(task, "id", None),
        "task_key": getattr(task, "task_key", None),
        "content": content,
        "payload": payload,
    }
    if customer:
        event["customer"] = customer
    for key in ("opportunities", "contracts", "payment_plans"):
        values = state.get(key)
        if isinstance(values, list):
            event[key] = values
    interaction = _interaction_for_event(event, db=db, team_id=team_id)
    return interaction or _pending_task_confirmation_interaction(content)


def _should_offer_next_pending_task(action: Optional[str]) -> bool:
    return action in {"create_customer_activity", "create_payment_plan", "create_lead", "create_customer"}
