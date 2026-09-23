"""Validation for team-level reminder rules."""

from __future__ import annotations

from typing import Any

from app.models.deal_journey import DealJourneyStatus

OBJECTS: dict[str, dict[str, Any]] = {
    "business_journey": {
        "label": "业务旅程",
        "statuses": {
            DealJourneyStatus.ACTIVE: "进行中",
            DealJourneyStatus.WON: "已赢单但未完成",
            DealJourneyStatus.LOST: "已输单",
            DealJourneyStatus.COMPLETED: "已完成",
            DealJourneyStatus.ARCHIVED: "已归档",
        },
        "recipients": {
            "primary_opportunity_owner": "主商机负责人",
            "customer_owner": "客户负责人",
            "customer_members": "客户协作成员",
        },
        "fields": {"业务旅程名称", "客户名称", "静默天数", "最近动态摘要", "最近业务动态时间"},
        "condition_fields": {
            "status": {"in"},
            "last_effective_event_at": {"older_than_days"},
            "primary_opportunity_owner": {"not_empty"},
            "customer_owner": {"not_empty"},
        },
    },
    "opportunity": {
        "label": "商机",
        "statuses": {"FOLLOWING": "跟进中"},
        "recipients": {"owner": "负责人", "customer_members": "客户协作成员"},
        "fields": {"商机名称", "当前阶段", "天数"},
        "date_fields": set(),
    },
    "customer": {
        "label": "客户",
        "statuses": {"FOLLOWING": "跟进中"},
        "recipients": {"owner": "负责人", "customer_members": "客户协作成员"},
        "fields": {"客户名称", "天数"},
        "date_fields": set(),
    },
    "lead": {
        "label": "线索",
        "statuses": {"FOLLOWING": "跟进中"},
        "recipients": {"owner": "负责人"},
        "fields": {"线索名称", "天数"},
        "date_fields": set(),
    },
    "follow_up_task": {
        "label": "跟进任务",
        "statuses": {"OPEN": "待处理"},
        "recipients": {"owner": "负责人", "customer_members": "客户协作成员"},
        "fields": {"任务标题", "天数"},
        "date_fields": {"due_at"},
    },
    "approval": {
        "label": "审批",
        "statuses": {"PENDING": "待处理"},
        "recipients": {"submitter": "提交人"},
        "fields": {"单据名称", "天数"},
        "date_fields": set(),
    },
    "payment_plan": {
        "label": "回款计划",
        "statuses": {"PENDING": "待回款", "OVERDUE": "逾期"},
        "recipients": {"contract_owner": "合同负责人", "customer_members": "客户协作成员"},
        "fields": {"回款计划", "天数"},
        "date_fields": {"due_date"},
    },
}

TRIGGERS = {"schedule", "change", "date"}
CHANNELS = {"in_app", "feishu"}
RECIPIENT_LABELS = {
    "owner": "负责人",
    "customer_members": "客户协作成员",
    "primary_opportunity_owner": "主商机负责人",
    "customer_owner": "客户负责人",
    "current_approver": "当前审批人",
    "submitter": "提交人",
    "contract_owner": "合同负责人",
    "sales_manager": "销售经理",
}
VALID_TRIGGER_TIMES = {
    f"{hour:02d}:{minute:02d}" for hour in range(9, 20) for minute in (0, 30) if not (hour == 19 and minute == 30)
}

V2_STATUSES = {
    "business_journey": {
        "ACTIVE": "进行中",
        "WON": "已赢单",
        "LOST": "已输单",
        "COMPLETED": "已完成",
        "ARCHIVED": "已归档",
    },
    "opportunity": {"FOLLOWING": "跟进中", "WON": "已赢单", "LOST": "已输单"},
    "customer": {"FOLLOWING": "跟进中", "WON": "已赢单", "LOST": "已输单", "INACTIVE": "沉寂"},
    "lead": {"NEW": "新线索", "FOLLOWING": "跟进中", "CONVERTED": "已转化", "INVALID": "无效"},
    "follow_up_task": {"OPEN": "待处理", "COMPLETED": "已完成", "CANCELLED": "已取消"},
    "approval": {"PENDING": "待处理", "APPROVED": "已通过", "REJECTED": "已拒绝", "CANCELLED": "已取消"},
    "payment_plan": {"PENDING": "待回款", "OVERDUE": "已逾期", "PARTIAL": "部分回款", "COMPLETED": "已完成"},
}

V2_DATE_FIELDS = {
    "business_journey": {
        "last_effective_event_at": "最近有效业务动态",
        "started_at": "开始时间",
        "closed_at": "结束时间",
        "created_time": "创建时间",
    },
    "opportunity": {
        "current_stage_entered_at": "当前阶段进入时间",
        "expected_closing_date": "预计成交日期",
        "created_time": "创建时间",
        "actual_closing_date": "实际成交日期",
    },
    "customer": {
        "last_activity_at": "最近客户活动",
        "created_time": "创建时间",
        "license_expiry_date": "License 到期日期",
    },
    "lead": {"created_time": "创建时间", "last_modified_time": "最后修改时间"},
    "follow_up_task": {"due_at": "到期时间", "created_time": "创建时间", "completed_at": "完成时间"},
    "approval": {"created_time": "创建时间", "updated_time": "更新时间"},
    "payment_plan": {"due_date": "到期日期", "created_time": "创建时间"},
}
V2_DEADLINE_FIELDS = {"expected_closing_date", "license_expiry_date", "due_at", "due_date"}
V2_OWNER_FIELDS = {
    "business_journey": {"primary_opportunity_owner": "主商机负责人", "customer_owner": "客户负责人"},
    "opportunity": {"owner": "负责人"},
    "customer": {"owner": "负责人"},
    "lead": {"owner": "负责人"},
    "follow_up_task": {"owner": "负责人"},
    "approval": {"submitter": "提交人"},
    "payment_plan": {"contract_owner": "合同负责人"},
}
V2_OPERATORS = {
    "in": "属于",
    "not_empty": "不为空",
    "older_than_days": "已过去至少 N 天",
    "due_in_days": "到期前 N 天起（含逾期）",  # noqa: RUF001
}


def reminder_rule_catalog() -> list[dict[str, Any]]:
    catalog = []
    for object_type, statuses in V2_STATUSES.items():
        fields = [
            {
                "value": "status",
                "label": "状态",
                "operators": [{"value": "in", "label": V2_OPERATORS["in"]}],
                "options": [{"value": value, "label": label} for value, label in statuses.items()],
            }
        ]
        for name, label in V2_DATE_FIELDS[object_type].items():
            operators = ["older_than_days"] + (["due_in_days"] if name in V2_DEADLINE_FIELDS else [])
            fields.append(
                {
                    "value": name,
                    "label": label,
                    "operators": [{"value": op, "label": V2_OPERATORS[op]} for op in operators],
                }
            )
        for name, label in V2_OWNER_FIELDS[object_type].items():
            fields.append(
                {
                    "value": name,
                    "label": label,
                    "operators": [{"value": "not_empty", "label": V2_OPERATORS["not_empty"]}],
                }
            )
        catalog.append(
            {
                "object_type": object_type,
                "label": OBJECTS[object_type]["label"],
                "recipients": [
                    {"value": name, "label": label} for name, label in OBJECTS[object_type]["recipients"].items()
                ],
                "fields": fields,
            }
        )
    return catalog


def _validate_v2(payload: dict[str, Any], object_type: str, errors: list[str]) -> None:
    if payload.get("trigger") != "schedule":
        errors.append("新版提醒只支持定时查找")
    if _text(payload.get("trigger_time")) not in VALID_TRIGGER_TIMES:
        errors.append("提醒时间仅支持 09:00-19:00，每 30 分钟一个选项")  # noqa: RUF001
    if payload.get("channels") != ["feishu"]:
        errors.append("新版提醒只支持飞书通知")
    if payload.get("notify_once_per_window", True) is not True:
        errors.append("新版提醒必须按时间窗口去重")
    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        errors.append("至少需要一个条件")
        return
    seen: set[str] = set()
    for condition in conditions:
        if not isinstance(condition, dict) or set(condition) != {"field", "operator", "value"}:
            errors.append("条件格式无效")
            continue
        field = condition["field"]
        operator = condition["operator"]
        value = condition["value"]
        if not isinstance(field, str) or not isinstance(operator, str):
            errors.append("条件字段或操作符无效")
            continue
        if field in seen:
            errors.append(f"重复条件字段: {field}")
        seen.add(field)
        if field == "status":
            valid = (
                operator == "in"
                and isinstance(value, list)
                and bool(value)
                and all(isinstance(item, str) and item in V2_STATUSES[object_type] for item in value)
            )
        elif field in V2_OWNER_FIELDS[object_type]:
            valid = operator == "not_empty" and value is True
        elif field in V2_DATE_FIELDS[object_type]:
            valid = operator in (
                {"older_than_days", "due_in_days"} if field in V2_DEADLINE_FIELDS else {"older_than_days"}
            ) and (type(value) is int and 0 <= value <= 36500)
        else:
            valid = False
        if not valid:
            errors.append(f"不支持的条件字段、操作符或取值: {field}/{operator}")


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _tokens(template: str) -> list[str]:
    tokens: list[str] = []
    cursor = 0
    while True:
        start = template.find("{", cursor)
        if start < 0:
            return tokens
        end = template.find("}", start + 1)
        if end < 0:
            return tokens
        tokens.append(template[start + 1 : end])
        cursor = end + 1


def _validate_recipients(payload: dict[str, Any], spec: dict[str, Any], errors: list[str]) -> None:
    recipients = payload.get("recipients")
    if not isinstance(recipients, list) or not recipients:
        errors.append("至少选择一个通知对象")
        return
    for recipient in recipients:
        text = str(recipient)
        explicit = text.removeprefix("user:")
        if text.startswith("user:") and explicit.isdigit():
            continue
        if not isinstance(recipient, str) or recipient not in spec["recipients"]:
            errors.append(f"该对象不能通知{RECIPIENT_LABELS.get(text, text)}")


def _validate_journey(payload: dict[str, Any], spec: dict[str, Any], errors: list[str]) -> None:
    trigger_time = _text(payload.get("trigger_time"))
    if trigger_time not in VALID_TRIGGER_TIMES:
        errors.append("业务旅程提醒时间仅支持 09:00-19:00，每 30 分钟一个选项")  # noqa: RUF001
    inactivity_days = payload.get("inactive_days")
    if not isinstance(inactivity_days, int) or isinstance(inactivity_days, bool) or inactivity_days < 1:
        errors.append("业务旅程提醒必须设置大于 0 的静默天数")
    offset_days = payload.get("offset_days", 0)
    if not isinstance(offset_days, int) or isinstance(offset_days, bool) or not -7 <= offset_days <= 0:
        errors.append("业务旅程提醒只支持当天或提前 1-7 天")
    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        errors.append("业务旅程提醒至少需要一个条件")
        return
    for condition in conditions:
        if not isinstance(condition, dict):
            errors.append("条件格式无效")
            continue
        field = _text(condition.get("field"))
        operator = _text(condition.get("operator"))
        if field == "status":
            values = condition.get("value")
            valid_statuses = spec["statuses"]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or value not in valid_statuses for value in values)
            ):
                errors.append("旅程状态条件包含未知状态")
        allowed = spec["condition_fields"].get(field)
        if allowed is None or operator not in allowed:
            errors.append(f"不支持条件字段或操作符: {field}/{operator}")
    if not _text(payload.get("message_title")).strip():
        errors.append("发送飞书消息必须填写标题")


def validate_reminder_rule(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["规则必须是对象"]
    errors: list[str] = []
    object_type = _text(payload.get("object_type"))
    spec = OBJECTS.get(object_type)
    if spec is None:
        return ["不支持的业务对象"]
    version = payload.get("version", 1)
    if type(version) is not int or version not in (1, 2):
        errors.append("不支持的规则版本")
        return errors
    trigger = _text(payload.get("trigger"))
    if trigger not in TRIGGERS:
        errors.append("不支持的触发方式")
    if version == 2:
        _validate_v2(payload, object_type, errors)
    elif object_type == "business_journey":
        _validate_journey(payload, spec, errors)
    elif version == 1:
        status = _text(payload.get("status"))
        if status not in spec["statuses"]:
            errors.append("该对象不支持此状态")
        inactive_days = payload.get("inactive_days")
        if trigger == "schedule" and (
            not isinstance(inactive_days, int) or isinstance(inactive_days, bool) or inactive_days < 1
        ):
            errors.append("定时查找必须设置大于 0 的天数")
        if trigger == "date" and payload.get("date_field") not in spec["date_fields"]:
            errors.append("该对象没有可用的日期字段")
    _validate_recipients(payload, spec, errors)
    channels = payload.get("channels")
    if not isinstance(channels, list) or not channels or any(channel not in CHANNELS for channel in channels):
        errors.append("通知渠道只支持站内和飞书卡片")
    template = _text(payload.get("message_template")).strip()
    if template == "":
        errors.append("消息不能为空")
    else:
        for token in _tokens(template):
            if token not in spec["fields"]:
                errors.append(f"消息不能引用{token}")
    title = _text(payload.get("message_title"))
    for token in _tokens(title):
        if token not in spec["fields"]:
            errors.append(f"标题不能引用{token}")
    return errors


def describe_reminder_rule(payload: dict[str, Any]) -> str:
    spec = OBJECTS[str(payload["object_type"])]
    labels = spec["recipients"]
    raw = payload["recipients"] if isinstance(payload["recipients"], list) else []
    names = ["指定成员" if str(item).startswith("user:") else labels[item] for item in raw]
    recipients = "和".join(names) if len(names) == 2 else "、".join(names)
    if payload.get("version", 1) == 2:
        field_labels = {
            field["value"]: field["label"]
            for obj in reminder_rule_catalog()
            if obj["object_type"] == payload["object_type"]
            for field in obj["fields"]
        }
        conditions = "且".join(
            field_labels[row["field"]]
            + " "
            + V2_OPERATORS[row["operator"]]
            + (
                " " + "、".join(V2_STATUSES[str(payload["object_type"])][value] for value in row["value"])
                if row["operator"] == "in"
                else " " + str(row["value"]) + " 天"
                if row["operator"] in {"older_than_days", "due_in_days"}
                else ""
            )
            for row in payload["conditions"]
        )
        return f"当{spec['label']}{conditions}时，于每日 {payload['trigger_time']} 通知{recipients}。"  # noqa: RUF001
    if payload["object_type"] == "business_journey":
        days = payload.get("inactive_days", "")
        offset = int(payload.get("offset_days") or 0)
        when = "当天" if offset == 0 else f"提前 {abs(offset)} 天"
        return f"当业务旅程连续 {days} 天没有有效业务动态时，于{when} {payload['trigger_time']} 通知{recipients}。"  # noqa: RUF001
    status = spec["statuses"][str(payload["status"])]
    if payload["object_type"] == "opportunity" and payload["trigger"] == "schedule":
        activity = "，且期间没有新的客户活动" if payload.get("require_no_new_activity") else ""  # noqa: RUF001
        return f"当{status}的商机进入当前阶段满 {payload['inactive_days']} 天{activity}，通知{recipients}。"  # noqa: RUF001
    return f"当{status}的{spec['label']}满足提醒条件，通知{recipients}。"  # noqa: RUF001
