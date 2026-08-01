"""User-facing display projection for agent business drafts."""
from __future__ import annotations

from app.services.agent import business_rules


ACTION_DISPLAY_LABELS: dict[str, str] = {
    "collect_opportunity_fields": "补商机信息",
    "create_opportunity": "确认创建商机",
    "move_opportunity_stage": "确认推进商机阶段",
    "select_opportunity_for_stage_move": "选择要推进的商机",
    "create_customer_activity": "确认记录跟进",
    "create_lead_follow_up": "确认记录线索跟进",
    "create_payment_plan": "确认创建回款计划",
    "create_payment_record": "确认登记回款",
    "create_contact": "确认新增联系人",
    "create_invoice_title": "确认新增发票抬头",
    "create_deployment_info": "确认新增部署信息",
    "create_customer_member": "确认新增客户成员",
    "create_customer": "确认创建客户",
    "create_lead": "确认创建线索",
}

ACTION_EXECUTION_LABELS: dict[str, str] = {
    "collect_opportunity_fields": "补商机信息",
    "create_opportunity": "创建商机",
    "move_opportunity_stage": "推进商机阶段",
    "select_opportunity_for_stage_move": "选择商机",
    "create_customer_activity": "记录跟进",
    "create_lead_follow_up": "记录线索跟进",
    "create_payment_plan": "创建回款计划",
    "create_payment_record": "登记回款",
    "create_contact": "新增联系人",
    "create_invoice_title": "新增发票抬头",
    "create_deployment_info": "新增部署信息",
    "create_customer_member": "新增客户成员",
    "create_customer": "创建客户",
    "create_lead": "创建线索",
}


def readable_action_label(action: object) -> str | None:
    if not isinstance(action, str):
        return None
    return ACTION_DISPLAY_LABELS.get(action.strip())


def readable_execution_label(action: object) -> str | None:
    if not isinstance(action, str):
        return None
    return ACTION_EXECUTION_LABELS.get(action.strip())


def display_text_matches(user_text: object, option_text: object) -> bool:
    if not isinstance(user_text, str) or not isinstance(option_text, str):
        return False
    user_value = _searchable_text(user_text)
    option_value = _searchable_text(option_text)
    if not user_value or not option_value:
        return False
    if user_value == option_value:
        return True
    if option_value in user_value or user_value in option_value:
        return True
    stripped_user = _strip_choice_prefix(user_value)
    stripped_option = _strip_choice_prefix(option_value)
    if not stripped_user or not stripped_option:
        return False
    return stripped_user == stripped_option or stripped_option in stripped_user or stripped_user in stripped_option


def readable_task_summary_from_candidate(candidate: dict[object, object], *, index: int) -> str:
    for key in ("display_summary", "summary", "intent"):
        value = candidate.get(key)
        if not isinstance(value, str):
            continue
        readable = _readable_existing_summary(value)
        if readable:
            return readable
        action_label = _action_label_from_legacy_summary(value)
        if action_label:
            customer_name = candidate.get("customer_name")
            if isinstance(customer_name, str) and customer_name.strip():
                return _join_parts([action_label, customer_name.strip()])
            return action_label

    action_label = readable_action_label(candidate.get("action"))
    if action_label:
        customer_name = candidate.get("customer_name")
        if isinstance(customer_name, str) and customer_name.strip():
            return _join_parts([action_label, customer_name.strip()])
        return action_label
    return f"草稿 {index}"


def pending_task_display_summary(
    *,
    action: object,
    summary: object,
    intent: object,
    state: dict[str, object],
    task_input: dict[str, object],
    payload: dict[str, object],
    customer: dict[str, object],
    missing_fields: list[object],
) -> str:
    action_key = action if isinstance(action, str) else None
    label = ACTION_DISPLAY_LABELS.get(action_key or "")
    customer_name = _customer_name(customer, state, payload)
    customer_part = customer_name or "未选客户"

    if action_key == "collect_opportunity_fields":
        display_fields = business_rules.format_opportunity_missing_fields(
            business_rules.opportunity_missing_display_fields([str(field) for field in missing_fields])
        )
        if display_fields:
            return f"补商机信息｜{customer_part}｜缺：{display_fields}"
        return f"确认采购方式｜{customer_part}"

    if action_key == "create_opportunity":
        opportunity = payload.get("opportunity") if isinstance(payload.get("opportunity"), dict) else {}
        opportunity_summary = business_rules.format_opportunity_summary(opportunity)
        return f"确认创建商机｜{customer_part}｜{opportunity_summary}"

    if label:
        excerpt = _content_excerpt(state, task_input, payload)
        return _join_parts([label, customer_name, excerpt])

    readable_summary = _readable_existing_summary(summary)
    if readable_summary:
        return readable_summary
    if isinstance(intent, str) and intent.strip() and "_" not in intent:
        return intent.strip()
    return "业务草稿"


def _customer_name(
    customer: dict[str, object],
    state: dict[str, object],
    payload: dict[str, object],
) -> str | None:
    for source in (customer, payload, state):
        for key in ("account_name", "customer_name", "name"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _content_excerpt(
    state: dict[str, object],
    task_input: dict[str, object],
    payload: dict[str, object],
) -> str | None:
    for source in (payload, task_input, state):
        for key in ("content", "source_content", "follow_up_content", "remark", "notes"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip())
    return None


def _shorten(value: str, limit: int = 24) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _searchable_text(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _strip_choice_prefix(value: str) -> str:
    for prefix in ("继续处理", "继续", "处理", "作为新流程处理", "新流程处理", "新流程"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _join_parts(parts: list[str | None]) -> str:
    return "｜".join(part for part in parts if part)


def _readable_existing_summary(summary: object) -> str | None:
    if not isinstance(summary, str):
        return None
    value = summary.strip()
    if not value:
        return None
    if "_" in value:
        return None
    if value.startswith("等待确认执行："):
        return None
    return value


def _action_label_from_legacy_summary(summary: str) -> str | None:
    prefix = "等待确认执行："
    if not summary.startswith(prefix):
        return None
    return readable_action_label(summary[len(prefix):])
