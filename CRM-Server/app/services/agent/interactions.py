"""Agent interaction payload builders."""
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


def _append_trace_event(trace_events: list[dict], event: dict) -> None:
    if event.get("event") in {"session", "message", "final", "done"}:
        return
    trace_events.append(json.loads(json.dumps(event, ensure_ascii=False, cls=SSEJsonEncoder)))

def _choice_interaction(prompt: str, choices: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "type": "choice",
        "prompt": prompt,
        "choices": choices,
        "allow_free_text": True,
        "allow_cancel": True,
    }

def _form_field(
    key: str,
    label: str,
    field_type: str = "text",
    *,
    required: bool = True,
    options: Optional[list[dict[str, str]]] = None,
    placeholder: Optional[str] = None,
    default_value: Optional[Any] = None,
) -> dict[str, Any]:
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
    return "default_procurement_method_id" in customer and not customer.get("default_procurement_method_id")

def _customer_default_procurement_method_id(customer: dict) -> Optional[int]:
    value = customer.get("default_procurement_method_id")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None

def _opportunity_interaction_fields(missing_fields: list[str], customer: dict) -> list[str]:
    fields = list(dict.fromkeys(missing_fields))
    if "license_type" in fields and "subscription_years" not in fields:
        fields.insert(fields.index("license_type") + 1, "subscription_years")
    if "procurement_method_id" not in fields:
        fields.append("procurement_method_id")
    return fields

def _opportunity_missing_display_fields(missing_fields: list[str], customer: dict) -> list[str]:
    return _opportunity_interaction_fields(missing_fields, customer)

def _opportunity_field_defaults(
    customer: dict,
    *,
    db: Optional[Session] = None,
    team_id: Optional[int] = None,
    customer_id: Optional[int] = None,
) -> dict[str, Any]:
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
    default_values: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
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
) -> Optional[dict[str, Any]]:
    event_name = event.get("event")
    content = str(event.get("content") or "")
    if event.get("interaction"):
        return event["interaction"]
    if event_name == "confirmation_required":
        return _choice_interaction(content or "请确认是否执行？", [
            {"label": "是", "value": "是"},
            {"label": "否", "value": "否"},
        ])
    if event_name == "customer_selection_required":
        customers = event.get("customers") or []
        choices = [
            {"label": str(customer.get("account_name") or f"客户 {index}"), "value": str(index)}
            for index, customer in enumerate(customers, start=1)
        ]
        return _choice_interaction(content or "请选择客户", choices)
    if event_name == "business_selection_required":
        choices = []
        for key in ("contracts", "payment_plans"):
            for index, item in enumerate(event.get(key) or [], start=1):
                name = item.get("contract_name") or item.get("plan_name") or item.get("name") or f"业务对象 {index}"
                choices.append({"label": str(name), "value": str(index)})
        return _choice_interaction(content or "请选择业务对象", choices)
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
        return {
            "type": "form",
            "prompt": content or "请补充信息",
            "submit_label": "提交",
            "fields": _fields_for_missing(
                form_kinds[event_name],
                [str(field) for field in interaction_fields],
                db=db,
                team_id=team_id,
                default_values=default_values,
            ),
            "allow_free_text": True,
            "allow_cancel": True,
        }
    if event_name == "follow_up_quality_required":
        return {
            "type": "text",
            "prompt": content or "请补充跟进记录",
            "placeholder": "补充跟进背景、下一步动作、时间或负责人...",
            "submit_label": "补充",
            "allow_free_text": True,
            "allow_cancel": True,
        }
    if event_name == "pending_interruption_confirmation_required":
        return _choice_interaction(content or "要切换到新流程吗？", [
            {"label": "切换新流程", "value": "切换新流程"},
            {"label": "继续刚才", "value": "继续刚才"},
        ])
    return None

def _with_interaction(event: dict, *, db: Optional[Session] = None, team_id: Optional[int] = None) -> dict:
    interaction = _interaction_for_event(event, db=db, team_id=team_id)
    if interaction is None:
        return event
    return {**event, "interaction": interaction}

def _pending_task_confirmation_interaction(content: str) -> dict[str, Any]:
    return _choice_interaction(content or "要继续处理下一步吗？", [
        {"label": "继续处理", "value": "是"},
    ])

def _should_offer_next_pending_task(action: Optional[str]) -> bool:
    return action in {"create_customer_follow_up", "create_payment_plan", "create_lead", "create_customer"}
