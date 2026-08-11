"""Pure business rules used by the CRM agent."""
from __future__ import annotations

from typing import Dict, List, Optional, Union

from app.services.agent import action_workflow, agent_copy
from app.utils.name_normalizer import normalize_corp_name


def customer_not_found_response(customer_name: str) -> str:
    return f"我识别到客户「{customer_name}」，但没有找到你可访问的客户。可以换成客户全称试试。"


def context_items(value: object) -> List[Dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _ids_match(left: object, right: object) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def extract_customer_candidates(data: object) -> List[Dict[str, object]]:
    if not isinstance(data, dict):
        return []
    items = data.get("items") or []
    candidates = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        candidates.append({
            "id": item.get("id"),
            "account_name": item.get("account_name"),
            "owner_info": item.get("owner_info"),
            "collaborator_infos": item.get("collaborator_infos") or [],
            "match": item.get("match") if isinstance(item.get("match"), dict) else {},
        })
    return candidates


def creation_duplicate_keywords(name: Optional[str]) -> List[str]:
    if not name:
        return []
    keywords = []
    for keyword in [name.strip(), normalize_corp_name(name)]:
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return keywords


def build_creation_duplicate_response(duplicate_candidates: Dict[str, object]) -> str:
    customers = duplicate_candidates.get("customers") or []
    leads = duplicate_candidates.get("leads") or []
    hidden_customer_count = duplicate_candidates.get("hidden_customer_count") or 0
    hidden_lead_count = duplicate_candidates.get("hidden_lead_count") or 0
    parts = []
    if customers:
        names = "、".join(
            f"「{customer.get('account_name')}」"
            for customer in customers[:3]
            if customer.get("account_name")
        )
        if names:
            parts.append(f"客户 {names}")
    if leads:
        names = "、".join(
            f"「{lead.get('lead_name')}」"
            for lead in leads[:3]
            if lead.get("lead_name")
        )
        if names:
            parts.append(f"线索 {names}")
    if hidden_customer_count:
        parts.append("团队内客户")
    if hidden_lead_count:
        parts.append("团队内线索")
    matched = "、".join(parts) if parts else "记录"
    return f"已存在：{matched}。"


def drop_empty_values(payload: Dict[str, object]) -> Dict[str, object]:
    return {key: value for key, value in payload.items() if value not in (None, "")}


def customer_requires_procurement_method(customer: Dict[str, object]) -> bool:
    return "default_procurement_method_id" in customer and not customer.get("default_procurement_method_id")


def customer_default_procurement_method_id(customer: Dict[str, object]) -> Optional[int]:
    value = customer.get("default_procurement_method_id")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def opportunity_interaction_fields(missing_fields: List[str]) -> List[str]:
    fields = list(dict.fromkeys(missing_fields))
    if "license_type" in fields and "subscription_years" not in fields:
        fields.insert(fields.index("license_type") + 1, "subscription_years")
    if "procurement_method_id" not in fields:
        fields.append("procurement_method_id")
    return fields


def opportunity_missing_display_fields(missing_fields: List[str]) -> List[str]:
    return opportunity_interaction_fields(missing_fields)


def opportunity_field_defaults(customer: Dict[str, object]) -> Dict[str, object]:
    default_procurement_method_id = customer_default_procurement_method_id(customer)
    if default_procurement_method_id is None:
        return {}
    return {"procurement_method_id": default_procurement_method_id}


def append_suggestions_to_response(response: str, suggestions: List[object]) -> str:
    actionable = [
        suggestion
        for suggestion in suggestions
        if getattr(suggestion, "action", None) != "NO_ACTION" and getattr(suggestion, "confidence", 0.0) >= 0.7
    ]
    if not actionable:
        return response
    suggestion_lines = [
        f"{index}. {suggestion.title}"
        for index, suggestion in enumerate(actionable[:3], start=1)
    ]
    return response + "\n\n基于客户上下文，我建议下一步可以：" + "；".join(suggestion_lines) + "。"


def opportunity_next_task_from_suggestions(
    suggestions: List[object],
    parsed: Dict[str, object],
    customer: Dict[str, object],
) -> Optional[Dict[str, object]]:
    if not customer.get("id"):
        return None
    suggestion = next(
        (
            item
            for item in suggestions
            if getattr(item, "action", None) == "CREATE_OPPORTUNITY"
            and getattr(item, "confidence", 0.0) >= 0.7
        ),
        None,
    )
    if suggestion is None:
        return None

    opportunity = dict(parsed.get("opportunity") or {})
    opportunity.pop("opportunity_name", None)
    opportunity["customer_id"] = customer.get("id")
    missing_fields = missing_opportunity_fields(
        opportunity,
        require_procurement_method=customer_requires_procurement_method(customer),
    )
    title = getattr(suggestion, "title", None) or "创建商机"
    needs_procurement_review = not opportunity.get("procurement_method_id")
    if missing_fields or needs_procurement_review:
        display_fields = format_opportunity_missing_fields(opportunity_missing_display_fields(missing_fields))
        content = (
            agent_copy.opportunity_suggestion_needs_fields(title, display_fields.split("、"))
            if missing_fields
            else agent_copy.opportunity_suggestion_needs_procurement(title)
        )
        next_task = {
            "action": "collect_opportunity_fields",
            "customer": customer,
            "payload": {
                "customer_id": customer.get("id"),
                "opportunity": opportunity,
                "missing_fields": missing_fields,
                "interaction_fields": opportunity_interaction_fields(missing_fields),
                "field_defaults": opportunity_field_defaults(customer),
            },
            "content": content,
        }
        return action_workflow.attach_workflow(
            next_task,
            action_workflow.optional_suggestion_contract(action=next_task["action"]),
        )
    next_task = {
        "action": "create_opportunity",
        "customer": customer,
        "payload": {
            "customer_id": customer.get("id"),
            "opportunity": opportunity,
        },
        "content": f"这条还像「{title}」，{format_opportunity_summary(opportunity)}。要创建吗？",
    }
    return action_workflow.attach_workflow(
        next_task,
        action_workflow.optional_suggestion_contract(action=next_task["action"]),
    )


def stage_move_action_from_suggestions(
    suggestions: List[object],
    customer: Dict[str, object],
    business_context: Dict[str, object],
) -> Optional[Dict[str, object]]:
    if not customer.get("id"):
        return None
    stage_suggestion = next(
        (
            suggestion
            for suggestion in suggestions
            if getattr(suggestion, "action", None) == "MOVE_OPPORTUNITY_STAGE"
            and getattr(suggestion, "requires_confirmation", True)
            and getattr(suggestion, "confidence", 0.0) >= 0.8
            and not getattr(suggestion, "missing_fields", None)
        ),
        None,
    )
    if not stage_suggestion:
        return None
    execution_payload = getattr(stage_suggestion, "execution_payload", None) or {}
    opportunity_id = getattr(stage_suggestion, "related_object_id", None)
    stage_template_id = execution_payload.get("stage_template_id")
    if not opportunity_id or not stage_template_id:
        return None

    opportunity = find_opportunity_in_context(business_context, opportunity_id)
    stage_target = resolve_stage_move_plan(business_context, opportunity_id, int(stage_template_id))
    if not stage_target:
        if context_items(business_context.get("active_opportunity_stage_context")):
            return None
        stage_target = {
            "stage_template_id": int(stage_template_id),
            "target_stage_name": execution_payload.get("target_stage_name"),
            "stage_move_steps": [{
                "stage_template_id": int(stage_template_id),
                "stage_name": execution_payload.get("target_stage_name"),
            }],
        }
    opportunity_name = opportunity.get("opportunity_name") or opportunity.get("name") or f"商机 {opportunity_id}"
    content = build_stage_move_confirmation_content(opportunity_name, stage_target)
    return {
        "action": "move_opportunity_stage",
        "customer": customer,
        "content": content,
        "payload": {
            "customer_id": customer.get("id"),
            "opportunity_id": opportunity_id,
            "stage_template_id": int(stage_target["stage_template_id"]),
            "opportunity_name": opportunity_name,
            "target_stage_name": stage_target.get("target_stage_name"),
            "stage_move_steps": stage_target.get("stage_move_steps"),
            "suggestion_title": getattr(stage_suggestion, "title", None),
            "suggestion_reason": getattr(stage_suggestion, "reason", None),
        },
    }


def stage_move_selection_action_from_suggestions(
    suggestions: List[object],
    customer: Dict[str, object],
    business_context: Dict[str, object],
) -> Optional[Dict[str, object]]:
    if not customer.get("id"):
        return None
    stage_suggestion = next(
        (
            suggestion
            for suggestion in suggestions
            if getattr(suggestion, "action", None) == "MOVE_OPPORTUNITY_STAGE"
            and getattr(suggestion, "requires_confirmation", True)
            and getattr(suggestion, "confidence", 0.0) >= 0.75
            and not getattr(suggestion, "related_object_id", None)
        ),
        None,
    )
    if not stage_suggestion:
        return None
    execution_payload = getattr(stage_suggestion, "execution_payload", None) or {}
    stage_template_id = execution_payload.get("stage_template_id")
    if not stage_template_id:
        return None
    candidates = stage_move_candidates(business_context, int(stage_template_id))
    if len(candidates) < 2:
        return None
    target_stage_name = candidates[0].get("target_stage_name")
    content = (
        "我识别到这次跟进可能需要推进商机阶段"
        f"{f'到「{target_stage_name}」' if target_stage_name else ''}，"
        "但该客户有多个可推进商机。请选择要推进哪一个。"
    )
    return {
        "action": "select_opportunity_for_stage_move",
        "customer": customer,
        "content": content,
        "opportunities": candidates,
        "payload": {
            "customer_id": customer.get("id"),
            "stage_template_id": int(stage_template_id),
            "target_stage_name": target_stage_name,
            "suggestion_title": getattr(stage_suggestion, "title", None),
            "suggestion_reason": getattr(stage_suggestion, "reason", None),
        },
    }


def stage_move_action_from_candidate(
    *,
    stage_suggestion: object,
    customer: Dict[str, object],
    candidate: Dict[str, object],
) -> Optional[Dict[str, object]]:
    opportunity_id = candidate.get("id")
    stage_template_id = candidate.get("target_stage_template_id")
    if opportunity_id is None or stage_template_id is None:
        return None
    opportunity_name = candidate.get("opportunity_name") or candidate.get("name") or f"商机 {opportunity_id}"
    target_stage_name = candidate.get("target_stage_name")
    stage_target = {
        "stage_template_id": int(stage_template_id),
        "target_stage_name": target_stage_name,
        "stage_move_steps": candidate.get("stage_move_steps") or [],
    }
    return {
        "action": "move_opportunity_stage",
        "customer": customer,
        "content": build_stage_move_confirmation_content(opportunity_name, stage_target),
        "payload": {
            "customer_id": customer.get("id"),
            "opportunity_id": opportunity_id,
            "stage_template_id": int(stage_template_id),
            "opportunity_name": opportunity_name,
            "target_stage_name": target_stage_name,
            "stage_move_steps": candidate.get("stage_move_steps") or [],
            "suggestion_title": getattr(stage_suggestion, "title", None),
            "suggestion_reason": getattr(stage_suggestion, "reason", None),
            "resolution_confidence": candidate.get("confidence"),
            "resolution_evidence": candidate.get("evidence") or [],
        },
    }


def stage_move_candidates(
    business_context: Dict[str, object],
    stage_template_id: int,
) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    for item in context_items(business_context.get("active_opportunity_stage_context")):
        opportunity = item.get("opportunity") if isinstance(item.get("opportunity"), dict) else {}
        if not _is_active_approved_opportunity(opportunity):
            continue
        stages = [stage for stage in item.get("procurement_stages") or [] if isinstance(stage, dict)]
        current_stage = next((stage for stage in stages if stage.get("is_current")), None)
        target_stage = _stage_by_template_id(stages, stage_template_id)
        stage_plan = _forward_stage_move_plan(stages, current_stage, target_stage)
        if not target_stage or not stage_plan:
            continue
        if _is_backward_stage_move(current_stage, target_stage) or target_stage.get("is_current"):
            continue
        opportunity_id = opportunity.get("id")
        if opportunity_id is None:
            continue
        candidates.append({
            "id": opportunity_id,
            "opportunity_name": opportunity.get("opportunity_name") or opportunity.get("name") or f"商机 {opportunity_id}",
            "current_stage_name": current_stage.get("stage_name") if current_stage else None,
            "target_stage_template_id": int(stage_template_id),
            "target_stage_name": target_stage.get("stage_name"),
            "stage_move_steps": stage_plan,
        })
    return candidates


def resolve_stage_move_plan(
    business_context: Dict[str, object],
    opportunity_id: Union[str, int],
    target_stage_template_id: int,
) -> Optional[Dict[str, object]]:
    for item in context_items(business_context.get("active_opportunity_stage_context")):
        opportunity = item.get("opportunity") if isinstance(item.get("opportunity"), dict) else {}
        if not _ids_match(opportunity.get("id"), opportunity_id):
            continue
        stages = [stage for stage in item.get("procurement_stages") or [] if isinstance(stage, dict)]
        current_stage = next((stage for stage in stages if stage.get("is_current")), None)
        target_stage = _stage_by_template_id(stages, target_stage_template_id)
        if not target_stage:
            return None
        if _is_backward_stage_move(current_stage, target_stage) or target_stage.get("is_current"):
            return None
        stage_plan = _forward_stage_move_plan(stages, current_stage, target_stage)
        if not stage_plan:
            return None
        return {
            "stage_template_id": int(target_stage_template_id),
            "target_stage_name": target_stage.get("stage_name"),
            "stage_move_steps": stage_plan,
        }
    return None


def build_stage_move_confirmation_content(
    opportunity_name: object,
    stage_target: Dict[str, object],
) -> str:
    target_stage_name = stage_target.get("target_stage_name")
    return (
        f"我还识别到商机「{opportunity_name}」可能需要推进阶段"
        f"{f'到「{target_stage_name}」' if target_stage_name else ''}。"
        "请确认是否推进？"
    )


def _is_active_approved_opportunity(opportunity: Dict[str, object]) -> bool:
    return str(opportunity.get("status")) == "0" and str(opportunity.get("approval_phase") or "").lower() == "approved"


def _stage_by_template_id(stages: List[Dict[str, object]], stage_template_id: int) -> Optional[Dict[str, object]]:
    return next(
        (
            stage
            for stage in stages
            if stage.get("id") is not None and int(stage["id"]) == int(stage_template_id)
        ),
        None,
    )


def _forward_stage_move_plan(
    stages: List[Dict[str, object]],
    current_stage: object,
    target_stage: Dict[str, object],
) -> List[Dict[str, object]]:
    target_order = _stage_sort_order(target_stage)
    if target_stage.get("id") is None or target_order is None:
        return []
    if not isinstance(current_stage, dict):
        start_order = None
    else:
        start_order = _stage_sort_order(current_stage)
        if start_order is None or target_order <= start_order:
            return []
    candidates = [
        stage
        for stage in stages
        if stage.get("id") is not None
        and _stage_sort_order(stage) is not None
        and int(_stage_sort_order(stage) or 0) <= target_order
        and (start_order is None or int(_stage_sort_order(stage) or 0) > start_order)
    ]
    return [
        {
            "stage_template_id": int(stage["id"]),
            "stage_name": stage.get("stage_name"),
        }
        for stage in sorted(candidates, key=lambda stage: int(_stage_sort_order(stage) or 0))
    ]


def _next_stage_after_current(
    stages: List[Dict[str, object]],
    current_stage: object,
) -> Optional[Dict[str, object]]:
    if not stages:
        return None
    if not isinstance(current_stage, dict):
        default_stage = next((stage for stage in stages if stage.get("is_default_start")), None)
        if default_stage:
            return default_stage
        return _first_sorted_stage(stages)
    current_order = _stage_sort_order(current_stage)
    if current_order is None:
        return None
    forward_stages = [
        stage
        for stage in stages
        if not stage.get("is_current")
        and _stage_sort_order(stage) is not None
        and int(_stage_sort_order(stage)) > current_order
    ]
    if not forward_stages:
        return None
    return min(forward_stages, key=lambda stage: int(_stage_sort_order(stage) or 0))


def _first_sorted_stage(stages: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    sortable = [stage for stage in stages if _stage_sort_order(stage) is not None]
    if not sortable:
        return None
    return min(sortable, key=lambda stage: int(_stage_sort_order(stage) or 0))


def _stage_sort_order(stage: Dict[str, object]) -> Optional[int]:
    if stage.get("sort_order") is None:
        return None
    try:
        return int(stage["sort_order"])
    except (TypeError, ValueError):
        return None


def _is_backward_stage_move(current_stage: object, target_stage: Dict[str, object]) -> bool:
    if not isinstance(current_stage, dict):
        return False
    if target_stage.get("sort_order") is None or current_stage.get("sort_order") is None:
        return False
    try:
        return int(target_stage["sort_order"]) < int(current_stage["sort_order"])
    except (TypeError, ValueError):
        return True


def find_opportunity_in_context(business_context: Dict[str, object], opportunity_id: Union[str, int]) -> Dict[str, object]:
    for opportunity in context_items(business_context.get("opportunities")):
        if _ids_match(opportunity.get("id"), opportunity_id):
            return opportunity
    for item in context_items(business_context.get("active_opportunity_stage_context")):
        opportunity = item.get("opportunity") or {}
        if _ids_match(opportunity.get("id"), opportunity_id):
            return opportunity
    return {"id": opportunity_id}


def missing_contact_fields(contact: Dict[str, object]) -> List[str]:
    required_fields = ["name", "mobile", "position", "gender"]
    return [field for field in required_fields if not contact.get(field)]


def missing_lead_fields(lead: Dict[str, object]) -> List[str]:
    required_fields = ["lead_name", "city", "contact_name", "contact_phone"]
    return [field for field in required_fields if not lead.get(field)]


def missing_customer_fields(customer: Dict[str, object]) -> List[str]:
    missing = [field for field in ["account_name", "city"] if not customer.get(field)]
    has_contact = any(customer.get(field) for field in ["contact_name", "contact_phone", "contact_position", "contact_gender"])
    if has_contact:
        missing.extend(field for field in ["contact_name", "contact_phone", "contact_position", "contact_gender"] if not customer.get(field))
    return list(dict.fromkeys(missing))


def format_customer_missing_fields(fields: List[str]) -> str:
    labels = {
        "account_name": "客户名称",
        "city": "所在城市",
        "contact_name": "主联系人姓名",
        "contact_phone": "主联系人手机号",
        "contact_position": "主联系人职务",
        "contact_gender": "主联系人性别（男/女/未知）",
    }
    return "、".join(labels.get(field, field) for field in fields)


def format_lead_missing_fields(fields: List[str]) -> str:
    labels = {
        "lead_name": "线索名称",
        "city": "所在城市",
        "contact_name": "联系人姓名",
        "contact_phone": "联系人手机号",
        "source": "线索来源",
        "company_scale": "公司规模",
    }
    return "、".join(labels.get(field, field) for field in fields)


def format_contact_missing_fields(fields: List[str]) -> str:
    labels = {
        "name": "联系人姓名",
        "mobile": "手机号",
        "position": "职务",
        "gender": "性别（男/女/未知）",
    }
    return "、".join(labels.get(field, field) for field in fields)


def missing_invoice_title_fields(invoice_title: Dict[str, object]) -> List[str]:
    required_fields = ["title_type", "title", "taxpayer_id"]
    return [field for field in required_fields if not invoice_title.get(field)]


def format_invoice_title_missing_fields(fields: List[str]) -> str:
    labels = {
        "title_type": "抬头类型（单位/个人）",
        "title": "开票抬头",
        "taxpayer_id": "纳税人识别号",
    }
    return "、".join(labels.get(field, field) for field in fields)


def missing_deployment_info_fields(deployment_info: Dict[str, object]) -> List[str]:
    required_fields = ["deployment_name", "server_address"]
    return [field for field in required_fields if not deployment_info.get(field)]


def format_deployment_info_missing_fields(fields: List[str]) -> str:
    labels = {
        "deployment_name": "部署名称",
        "server_address": "服务器地址（需以 http:// 或 https:// 开头）",
    }
    return "、".join(labels.get(field, field) for field in fields)


def missing_customer_member_fields(member: Dict[str, object]) -> List[str]:
    if member.get("user_id") or member.get("user_name"):
        return []
    return ["user_name"]


def format_customer_member_missing_fields(fields: List[str]) -> str:
    labels = {
        "user_name": "成员姓名",
        "user_id": "成员用户 ID",
    }
    return "、".join(labels.get(field, field) for field in fields)


def resolve_customer_member(member: Dict[str, object], business_context: Dict[str, object]) -> tuple[Dict[str, object], Optional[str]]:
    normalized = {
        "user_id": member.get("user_id"),
        "member_role": member.get("member_role") or "PRESALES",
        "access_level": member.get("access_level") or "VIEW",
        "remark": member.get("remark"),
    }
    if normalized["user_id"]:
        return drop_empty_values({
            **normalized,
            "user_name": member.get("user_name"),
        }), None

    user_name = str(member.get("user_name") or "").strip()
    if not user_name:
        return member, None

    candidates_value = business_context.get("member_candidates")
    if isinstance(candidates_value, dict) and candidates_value.get("error"):
        return member, f"我识别到要添加客户成员「{user_name}」，但读取成员候选人失败。请确认你有客户成员管理权限。"

    candidates = context_items(candidates_value)
    matches = [
        item
        for item in candidates
        if str(item.get("name") or "") == user_name
        or (user_name and user_name in str(item.get("name") or ""))
    ]
    available_matches = [item for item in matches if not item.get("already_member")]
    if len(available_matches) == 1:
        candidate = available_matches[0]
        return drop_empty_values({
            **normalized,
            "user_id": candidate.get("id"),
            "user_name": candidate.get("name"),
        }), None
    if len(matches) == 1 and matches[0].get("already_member"):
        return member, f"「{matches[0].get('name')}」已经是这个客户的负责人或成员，不需要重复添加。"
    if len(available_matches) > 1:
        names = "；".join(f"{index}. {item.get('name')}" for index, item in enumerate(available_matches, start=1))
        return member, f"我找到了多个叫「{user_name}」的候选成员，请补充更明确的成员信息：{names}"
    return member, f"我没在客户成员候选人里找到「{user_name}」。请确认成员姓名，或先把这个人加入团队。"


def missing_payment_fields(actual_amount: object, payment_date: object) -> List[str]:
    fields = []
    if not actual_amount:
        fields.append("actual_amount")
    if not payment_date:
        fields.append("payment_date")
    return fields


def missing_opportunity_fields(
    opportunity: Dict[str, object],
    *,
    require_procurement_method: bool = False,
) -> List[str]:
    fields = []
    required_fields = [
        "total_amount",
        "user_count",
        "license_type",
        "purchase_type",
        "expected_closing_date",
    ]
    for field in required_fields:
        if not opportunity.get(field):
            fields.append(field)
    if require_procurement_method and not opportunity.get("procurement_method_id"):
        fields.append("procurement_method_id")
    if opportunity.get("license_type") == "SUBSCRIPTION" and not opportunity.get("subscription_years"):
        fields.append("subscription_years")
    return fields


def format_payment_missing_fields(fields: List[str]) -> str:
    labels = {
        "actual_amount": "实际回款金额",
        "payment_date": "实际回款日期",
    }
    return "、".join(labels.get(field, field) for field in fields)


def format_opportunity_missing_fields(fields: List[str]) -> str:
    labels = {
        "total_amount": "预计成交金额",
        "user_count": "采购用户数",
        "license_type": "授权模式",
        "subscription_years": "订阅年限",
        "purchase_type": "采购类型（新购/续购/增购）",
        "procurement_method_id": "采购方式",
        "expected_closing_date": "预计成交日期",
    }
    return "、".join(labels.get(field, field) for field in fields)


def format_opportunity_summary(opportunity: Dict[str, object]) -> str:
    parts = []
    if opportunity.get("total_amount"):
        parts.append(f"预计金额 {opportunity.get('total_amount')}")
    if opportunity.get("user_count"):
        parts.append(f"{opportunity.get('user_count')} 人")
    if opportunity.get("license_type") == "SUBSCRIPTION":
        years = opportunity.get("subscription_years") or 1
        parts.append(f"订阅 {years} 年")
    elif opportunity.get("license_type") == "PERPETUAL":
        parts.append("买断")
    return "，".join(parts) if parts else "商机名称将由系统自动生成"


def is_open_payment_plan(plan: Dict[str, object]) -> bool:
    status = str(plan.get("status") or "").upper()
    remaining_amount = plan.get("remaining_amount")
    try:
        has_remaining = remaining_amount is None or float(remaining_amount) > 0
    except (TypeError, ValueError):
        has_remaining = True
    return status != "COMPLETED" and has_remaining


def resolve_commission_member_id(customer: Dict[str, object]) -> Optional[str]:
    collaborators = customer.get("collaborator_infos") or []
    if collaborators:
        first = collaborators[0] or {}
        member_id = first.get("id") or first.get("user_id") or first.get("userId")
        if member_id:
            return str(member_id)
    owner = customer.get("owner_info") or {}
    owner_id = owner.get("id") or owner.get("user_id") or owner.get("userId")
    return str(owner_id) if owner_id else None


def payment_record_payload(plan: Dict[str, object], payment: Dict[str, object], commission_member_id: str) -> Dict[str, object]:
    return {
        "payment_plan_id": plan.get("id"),
        "actual_amount": payment.get("actual_amount"),
        "payment_date": payment.get("payment_date_iso"),
        "actual_payer_name": payment.get("actual_payer_name"),
        "commission_member_id": commission_member_id,
        "notes": payment.get("notes"),
    }


def payment_plan_payload(contract: Dict[str, object], payment: Dict[str, object], commission_member_id: Optional[str]) -> Dict[str, object]:
    return {
        "contract_id": contract.get("id"),
        "stage_name": "AI登记回款计划",
        "planned_amount": payment.get("actual_amount"),
        "due_date": payment.get("payment_date_iso"),
        "notes": payment.get("notes") or "由 CRM AI Agent 根据回款登记场景创建",
        "pending_payment_record": {
            "actual_amount": payment.get("actual_amount"),
            "payment_date": payment.get("payment_date_iso"),
            "actual_payer_name": payment.get("actual_payer_name"),
            "commission_member_id": commission_member_id,
            "notes": payment.get("notes"),
        },
    }
