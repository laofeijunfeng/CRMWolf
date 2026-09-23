# ruff: noqa: TC002

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256

from sqlalchemy.orm import Session

from app.models.approval import Approval
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyEventType
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.models.reminder_rule import ReminderRule
from app.models.reminder_rule_run import ReminderRuleRun
from app.models.sales_commitment import FollowUpTask
from app.models.team import UserTeam
from app.models.user import User, UserStatus
from app.services.reminder_rule_dsl import V2_DATE_FIELDS, V2_OWNER_FIELDS, validate_reminder_rule

V2_MODELS = {
    "business_journey": CustomerDealJourney,
    "opportunity": Opportunity,
    "customer": Customer,
    "lead": Lead,
    "follow_up_task": FollowUpTask,
    "approval": Approval,
    "payment_plan": PaymentPlan,
}
V2_NUMERIC_STATUSES = {
    "opportunity": {"FOLLOWING": 0, "WON": 1, "LOST": 2},
    "customer": {"FOLLOWING": 0, "WON": 1, "LOST": 2, "INACTIVE": 3},
    "lead": {"NEW": 0, "FOLLOWING": 1, "CONVERTED": 2, "INVALID": 3},
}

Deliver = Callable[..., Awaitable[dict[str, int]] | dict[str, int]]
STATUS_VALUES = {"FOLLOWING": 0, "OPEN": "OPEN", "PENDING": "PENDING", "OVERDUE": "OVERDUE"}


@dataclass(frozen=True)
class ReminderExecutionResult:
    sent_count: int


def _customer_member_ids(db: Session, team_id: int, customer_id: str) -> list[int]:
    if not customer_id.isdigit():
        return []
    rows = (
        db.query(CustomerMember.user_id)
        .filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == int(customer_id),
            CustomerMember.is_active.is_(True),
        )
        .all()
    )
    return [int(row.user_id) for row in rows if str(row.user_id).isdigit()]


def _recipient_ids(db: Session, team_id: int, recipients: Iterable[str], values: dict[str, str]) -> list[int]:
    ids: list[int] = []
    for recipient in recipients:
        text = str(recipient)
        if text == "customer_members":
            ids.extend(_customer_member_ids(db, team_id, values.get("customer_id", "")))
            continue
        explicit = text.removeprefix("user:")
        if text.startswith("user:") and explicit.isdigit():
            ids.append(int(explicit))
            continue
        raw = values.get(text, "")
        if raw.isdigit():
            ids.append(int(raw))
    return sorted(set(ids))


def _render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


async def _deliver(
    deliver: Deliver,
    team_id: int,
    user_ids: list[int],
    title: str,
    content: str,
) -> dict[str, int]:
    try:
        receipt = deliver(team_id, user_ids, title, content)
    except TypeError:
        receipt = deliver(team_id, user_ids, content)
    if inspect.isawaitable(receipt):
        receipt = await receipt
    return receipt


def _already_sent(db: Session, rule_id: int, object_id: int, window_key: str) -> bool:
    return (
        db.query(ReminderRuleRun)
        .filter(
            ReminderRuleRun.rule_id == rule_id,
            ReminderRuleRun.object_id == object_id,
            ReminderRuleRun.window_key == window_key,
        )
        .first()
        is not None
    )


async def _record(
    db: Session,
    rule: ReminderRule,
    object_id: int,
    window_key: str,
    user_ids: list[int],
    message: str,
    receipt: dict[str, int],
    now: datetime,
) -> None:
    db.add(
        ReminderRuleRun(
            team_id=rule.team_id,
            rule_id=rule.id,
            object_type=rule.object_type,
            object_id=object_id,
            window_key=window_key,
            recipient_ids=",".join(str(user_id) for user_id in user_ids),
            message=message,
            sent_count=int(receipt.get("sent", 0)),
            skipped_count=int(receipt.get("skipped", 0)),
            created_time=now,
        )
    )


def _latest_activity_at(db: Session, team_id: int, customer_id: int) -> datetime | None:
    activity = (
        db.query(CustomerActivity)
        .filter(CustomerActivity.team_id == team_id, CustomerActivity.customer_id == customer_id)
        .order_by(CustomerActivity.occurred_at.desc())
        .first()
    )
    return None if activity is None else activity.occurred_at


EFFECTIVE_JOURNEY_EVENTS = {
    DealJourneyEventType.OPPORTUNITY_CREATED,
    DealJourneyEventType.OPPORTUNITY_APPROVED,
    DealJourneyEventType.OPPORTUNITY_STAGE_CHANGED,
    DealJourneyEventType.OPPORTUNITY_WON,
    DealJourneyEventType.OPPORTUNITY_LOST,
    DealJourneyEventType.CONTRACT_CREATED,
    DealJourneyEventType.CONTRACT_SIGNED,
    DealJourneyEventType.PAYMENT_PLAN_CREATED,
    DealJourneyEventType.PAYMENT_RECEIVED,
    DealJourneyEventType.PAYMENT_CONFIRMED,
    DealJourneyEventType.INVOICE_APPLIED,
    DealJourneyEventType.INVOICE_ISSUED,
    DealJourneyEventType.ACTIVITY_ADDED,
    DealJourneyEventType.FOLLOW_UP_ADDED,
}


def _condition(payload: dict, field: str) -> dict | None:
    for condition in payload.get("conditions", []):
        if isinstance(condition, dict) and condition.get("field") == field:
            return condition
    return None


async def _execute_journey_rule(db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver) -> int:
    status_condition = _condition(payload, "status") or {}
    statuses = status_condition.get("value")
    inactivity_days = payload.get("inactive_days")
    offset_days = payload.get("offset_days", 0)
    trigger_time = str(payload.get("trigger_time") or "")
    if not isinstance(statuses, list) or not isinstance(inactivity_days, int) or not isinstance(offset_days, int):
        return 0
    try:
        trigger_hour, trigger_minute = (int(part) for part in trigger_time.split(":", 1))
        daily_time = time(trigger_hour, trigger_minute)
    except (TypeError, ValueError):
        return 0
    journeys = (
        db.query(CustomerDealJourney)
        .filter(
            CustomerDealJourney.team_id == rule.team_id,
            CustomerDealJourney.status.in_(statuses),
        )
        .all()
    )
    sent = 0
    for journey in journeys:
        latest = (
            db.query(CustomerDealJourneyEvent)
            .filter(
                CustomerDealJourneyEvent.deal_journey_id == journey.id,
                CustomerDealJourneyEvent.event_type.in_(EFFECTIVE_JOURNEY_EVENTS),
            )
            .order_by(CustomerDealJourneyEvent.event_time.desc())
            .first()
        )
        if latest is None:
            continue
        trigger_date = latest.event_time.date() + timedelta(days=inactivity_days + offset_days)
        due_at = datetime.combine(trigger_date, daily_time)
        if now < due_at:
            continue
        window = f"effective_event:{latest.event_time.isoformat()}"
        if _already_sent(db, int(rule.id), int(journey.id), window):
            continue
        customer = db.query(Customer).filter(Customer.id == journey.customer_id).first()
        opportunity = (
            db.query(Opportunity).filter(Opportunity.id == journey.primary_opportunity_id).first()
            if journey.primary_opportunity_id is not None
            else None
        )
        silence_days = (now - latest.event_time).days
        values = {
            "customer_id": str(journey.customer_id),
            "customer_owner": str(customer.owner_id or "") if customer is not None else "",
            "primary_opportunity_owner": str(opportunity.owner_id) if opportunity is not None else "",
            "客户名称": str(customer.account_name) if customer is not None else "",
            "业务旅程名称": str(journey.name),
            "静默天数": str(silence_days),
            "最近动态摘要": str(latest.summary or latest.event_type),
            "最近业务动态时间": latest.event_time.strftime("%Y-%m-%d %H:%M"),
        }
        primary_owner_condition = _condition(payload, "primary_opportunity_owner")
        if primary_owner_condition is not None and not values["primary_opportunity_owner"]:
            continue
        customer_owner_condition = _condition(payload, "customer_owner")
        if customer_owner_condition is not None and not values["customer_owner"]:
            continue
        users = _recipient_ids(db, int(rule.team_id), payload["recipients"], values)
        if not users:
            continue
        title = _render(str(payload.get("message_title") or rule.name), values)
        content = _render(str(payload["message_template"]), values)
        receipt = await _deliver(deliver, int(rule.team_id), users, title, content)
        await _record(db, rule, int(journey.id), window, users, content, receipt, now)
        sent += 1
    return sent


def _v2_values(
    db: Session, rule: ReminderRule, obj: object, needed: set[str], now: datetime
) -> tuple[dict[str, object], dict[str, str]] | None:
    kind = str(rule.object_type)
    team = int(rule.team_id)
    values: dict[str, object] = {"status": obj.status}
    if kind in V2_NUMERIC_STATUSES:
        status = values["status"]
        values["status"] = getattr(status, "value", status)
    recipient_values: dict[str, str] = {}
    if kind == "business_journey":
        journey = obj
        customer = db.query(Customer).filter(Customer.id == journey.customer_id, Customer.team_id == team).first()
        opportunity = (
            db.query(Opportunity)
            .filter(
                Opportunity.id == journey.primary_opportunity_id,
                Opportunity.team_id == team,
            )
            .first()
            if journey.primary_opportunity_id is not None
            else None
        )
        if customer is None or (journey.primary_opportunity_id is not None and opportunity is None):
            return None
        recipient_values = {
            "customer_id": str(journey.customer_id) if customer is not None else "",
            "customer_owner": str(customer.owner_id or "") if customer is not None else "",
            "primary_opportunity_owner": str(opportunity.owner_id or "") if opportunity is not None else "",
            "客户名称": str(customer.account_name) if customer is not None else "",
            "业务旅程名称": str(journey.name),
        }
        if "last_effective_event_at" in needed or any(
            token in str(rule.rule.get("message_title") or "") + str(rule.rule.get("message_template") or "")
            for token in ("最近动态摘要", "最近业务动态时间", "静默天数")
        ):
            latest = (
                db.query(CustomerDealJourneyEvent)
                .filter(
                    CustomerDealJourneyEvent.team_id == team,
                    CustomerDealJourneyEvent.deal_journey_id == journey.id,
                    CustomerDealJourneyEvent.event_type.in_(EFFECTIVE_JOURNEY_EVENTS),
                )
                .order_by(CustomerDealJourneyEvent.event_time.desc())
                .first()
            )
            values["last_effective_event_at"] = latest.event_time if latest is not None else None
            if latest is not None:
                recipient_values["最近动态摘要"] = str(latest.summary or latest.event_type)
                recipient_values["最近业务动态时间"] = latest.event_time.strftime("%Y-%m-%d %H:%M")
                recipient_values["静默天数"] = str((now.date() - latest.event_time.date()).days)
    elif kind == "payment_plan":
        contract = db.query(Contract).filter(Contract.id == obj.contract_id, Contract.team_id == team).first()
        if (
            contract is None
            or db.query(Customer.id)
            .filter(
                Customer.id == contract.customer_id,
                Customer.team_id == team,
            )
            .first()
            is None
        ):
            return None
        recipient_values = {
            "contract_owner": str(contract.owner_id or "") if contract is not None else "",
            "customer_id": str(contract.customer_id) if contract is not None else "",
            "回款计划": str(obj.stage_name),
        }
    else:
        owner_field = "submitter_id" if kind == "approval" else "owner_id"
        owner_key = "submitter" if kind == "approval" else "owner"
        recipient_values[owner_key] = str(getattr(obj, owner_field, "") or "")
        if kind in {"opportunity", "follow_up_task"}:
            if db.query(Customer.id).filter(Customer.id == obj.customer_id, Customer.team_id == team).first() is None:
                return None
            recipient_values["customer_id"] = str(obj.customer_id)
        if kind == "customer":
            recipient_values["customer_id"] = str(obj.id)
        label_field = {
            "opportunity": ("商机名称", "opportunity_name"),
            "customer": ("客户名称", "account_name"),
            "lead": ("线索名称", "lead_name"),
            "follow_up_task": ("任务标题", "title"),
            "approval": ("单据名称", "business_type"),
        }[kind]
        recipient_values[label_field[0]] = str(getattr(obj, label_field[1]) or "")
        if kind == "opportunity":
            recipient_values["当前阶段"] = str(obj.current_stage_name or "")
        if kind == "customer" and "last_activity_at" in needed:
            values["last_activity_at"] = _latest_activity_at(db, team, int(obj.id))
    for field in needed & V2_DATE_FIELDS[kind].keys():
        if field not in values:
            values[field] = getattr(obj, field)
    for field in V2_OWNER_FIELDS[kind]:
        values[field] = recipient_values.get(field, "")
    return values, recipient_values


async def _execute_v2_rule(db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver) -> int:
    if rule.trigger != "schedule" or rule.object_type != payload.get("object_type") or validate_reminder_rule(payload):
        return 0
    hour, minute = (int(part) for part in payload["trigger_time"].split(":"))
    scheduled_at = datetime.combine(now.date(), time(hour, minute))
    if now < scheduled_at or rule.created_time > scheduled_at:
        return 0
    kind = str(rule.object_type)
    conditions = payload["conditions"]
    needed = {condition["field"] for condition in conditions}
    sent = 0
    for obj in db.query(V2_MODELS[kind]).filter(V2_MODELS[kind].team_id == rule.team_id).all():
        resolved = _v2_values(db, rule, obj, needed, now)
        if resolved is None:
            continue
        values, message_values = resolved
        anchors = []
        eligible = True
        for condition in conditions:
            field, operator, expected = condition["field"], condition["operator"], condition["value"]
            actual = values.get(field)
            if field == "status":
                mapping = V2_NUMERIC_STATUSES.get(kind)
                eligible = any(mapping[value] == actual for value in expected) if mapping else actual in expected
            elif field in V2_OWNER_FIELDS[kind]:
                eligible = bool(str(actual or "").strip())
            else:
                if not isinstance(actual, (date, datetime)):
                    eligible = False
                else:
                    anchor_date = actual.date() if isinstance(actual, datetime) else actual
                    eligible = (
                        (now.date() - anchor_date).days >= expected
                        if operator == "older_than_days"
                        else (anchor_date - now.date()).days <= expected
                    )
                    anchors.append((field, actual.isoformat()))
                    if field == "last_effective_event_at":
                        message_values["静默天数"] = str((now.date() - anchor_date).days)
                    message_values["天数"] = str((now.date() - anchor_date).days)
            if not eligible:
                break
        if not eligible:
            continue
        # Hash all field names and full precision timestamps to bound the indexed window key.
        anchor_key = "|".join(f"{field}:{value}" for field, value in sorted(anchors)) if anchors else "object"
        ledger = db.query(ReminderRuleRun).filter(
            ReminderRuleRun.rule_id == rule.id,
            ReminderRuleRun.object_id == obj.id,
            ReminderRuleRun.window_key == window,
        ).first()
        users = _recipient_ids(db, int(rule.team_id), payload["recipients"], message_values)
        users = sorted(
            user_id
            for (user_id,) in db.query(User.id)
            .join(
                UserTeam,
                UserTeam.user_id == User.id,
            )
            .filter(
                User.id.in_(users),
                User.status == UserStatus.ACTIVE,
                UserTeam.team_id == rule.team_id,
            )
            .all()
        )
        delivered_ids = {int(value) for value in ledger.recipient_ids.split(",") if value} if ledger else set()
        pending = [user_id for user_id in users if user_id not in delivered_ids]
        if not pending:
            continue
        title = _render(str(payload.get("message_title") or rule.name), message_values)
        content = _render(str(payload["message_template"]), message_values)
        successful = False
        for user_id in pending:
            receipt = await _deliver(deliver, int(rule.team_id), [user_id], title, content)
            if receipt.get("sent", 0) <= 0:
                continue
            successful = True
            delivered_ids.add(user_id)
            if ledger is None:
                ledger = ReminderRuleRun(
                    team_id=rule.team_id, rule_id=rule.id, object_type=rule.object_type,
                    object_id=obj.id, window_key=window, message=content,
                    sent_count=0, skipped_count=0, created_time=now,
                )
                db.add(ledger)
            ledger.recipient_ids = ",".join(str(value) for value in sorted(delivered_ids))
            ledger.sent_count = int(ledger.sent_count) + int(receipt["sent"])
            ledger.skipped_count = int(ledger.skipped_count) + int(receipt.get("skipped", 0))
        if successful:
            sent += 1
    return sent


async def _execute_opportunity_rule(
    db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver
) -> int:
    sent = 0
    inactive_days = int(payload["inactive_days"])
    opportunities = (
        db.query(Opportunity)
        .filter(
            Opportunity.team_id == rule.team_id,
            Opportunity.status == STATUS_VALUES[str(payload["status"])],
            Opportunity.current_stage_entered_at.is_not(None),
        )
        .all()
    )
    for opportunity in opportunities:
        entered_at = opportunity.current_stage_entered_at
        elapsed = (now - entered_at).days
        if elapsed < inactive_days:
            continue
        if payload.get("require_no_new_activity"):
            latest = _latest_activity_at(db, int(rule.team_id), int(opportunity.customer_id))
            if latest is not None and latest >= entered_at:
                continue
        window = f"stage:{entered_at.isoformat()}"
        if _already_sent(db, int(rule.id), int(opportunity.id), window):
            continue
        users = _recipient_ids(
            db,
            int(rule.team_id),
            payload["recipients"],
            {"owner": str(opportunity.owner_id), "customer_id": str(opportunity.customer_id)},
        )
        message = _render(
            str(payload["message_template"]),
            {
                "商机名称": str(opportunity.opportunity_name),
                "当前阶段": str(opportunity.current_stage_name or ""),
                "天数": str(elapsed),
            },
        )
        title = _render(str(payload.get("message_title") or rule.name), {"天数": str(elapsed)})
        await _record(
            db,
            rule,
            int(opportunity.id),
            window,
            users,
            message,
            await _deliver(deliver, int(rule.team_id), users, title, message),
            now,
        )
        sent += 1
    return sent


async def _execute_follow_up_rule(
    db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver
) -> int:
    sent = 0
    tasks = (
        db.query(FollowUpTask)
        .filter(FollowUpTask.team_id == rule.team_id, FollowUpTask.status == payload["status"])
        .all()
    )
    for task in tasks:
        if task.due_at > now:
            continue
        window = f"due:{task.due_at.isoformat()}"
        if _already_sent(db, int(rule.id), int(task.id), window):
            continue
        users = _recipient_ids(
            db,
            int(rule.team_id),
            payload["recipients"],
            {"owner": str(task.owner_id), "customer_id": str(task.customer_id)},
        )
        message = _render(str(payload["message_template"]), {"任务标题": str(task.title), "天数": "0"})
        title = str(payload.get("message_title") or rule.name)
        await _record(
            db,
            rule,
            int(task.id),
            window,
            users,
            message,
            await _deliver(deliver, int(rule.team_id), users, title, message),
            now,
        )
        sent += 1
    return sent


async def _execute_customer_rule(
    db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver
) -> int:
    sent = 0
    cutoff = now - timedelta(days=int(payload["inactive_days"]))
    customers = (
        db.query(Customer)
        .filter(Customer.team_id == rule.team_id, Customer.status == STATUS_VALUES[str(payload["status"])])
        .all()
    )
    for customer in customers:
        latest = _latest_activity_at(db, int(rule.team_id), int(customer.id))
        if latest is None or latest > cutoff:
            continue
        window = f"activity:{latest.isoformat()}"
        if _already_sent(db, int(rule.id), int(customer.id), window):
            continue
        users = _recipient_ids(
            db,
            int(rule.team_id),
            payload["recipients"],
            {"owner": str(customer.owner_id or ""), "customer_id": str(customer.id)},
        )
        message = _render(
            str(payload["message_template"]), {"客户名称": str(customer.account_name), "天数": str((now - latest).days)}
        )
        title = str(payload.get("message_title") or rule.name)
        await _record(
            db,
            rule,
            int(customer.id),
            window,
            users,
            message,
            await _deliver(deliver, int(rule.team_id), users, title, message),
            now,
        )
        sent += 1
    return sent


async def _execute_lead_rule(db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver) -> int:
    sent = 0
    cutoff = now - timedelta(days=int(payload["inactive_days"]))
    leads = (
        db.query(Lead).filter(Lead.team_id == rule.team_id, Lead.status == STATUS_VALUES[str(payload["status"])]).all()
    )
    for lead in leads:
        if lead.owner_id is None or lead.last_modified_time > cutoff:
            continue
        window = f"assigned:{lead.last_modified_time.isoformat()}"
        if _already_sent(db, int(rule.id), int(lead.id), window):
            continue
        users = _recipient_ids(db, int(rule.team_id), payload["recipients"], {"owner": str(lead.owner_id)})
        message = _render(
            str(payload["message_template"]),
            {"线索名称": str(lead.lead_name), "天数": str((now - lead.last_modified_time).days)},
        )
        title = str(payload.get("message_title") or rule.name)
        await _record(
            db,
            rule,
            int(lead.id),
            window,
            users,
            message,
            await _deliver(deliver, int(rule.team_id), users, title, message),
            now,
        )
        sent += 1
    return sent


async def _execute_approval_rule(
    db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver
) -> int:
    sent = 0
    cutoff = now - timedelta(days=int(payload["inactive_days"]))
    approvals = db.query(Approval).filter(Approval.team_id == rule.team_id, Approval.status == payload["status"]).all()
    for approval in approvals:
        if approval.created_time > cutoff:
            continue
        window = f"submitted:{approval.created_time.isoformat()}"
        if _already_sent(db, int(rule.id), int(approval.id), window):
            continue
        users = _recipient_ids(db, int(rule.team_id), payload["recipients"], {"submitter": str(approval.submitter_id)})
        message = _render(
            str(payload["message_template"]),
            {"单据名称": str(approval.business_type), "天数": str((now - approval.created_time).days)},
        )
        title = str(payload.get("message_title") or rule.name)
        await _record(
            db,
            rule,
            int(approval.id),
            window,
            users,
            message,
            await _deliver(deliver, int(rule.team_id), users, title, message),
            now,
        )
        sent += 1
    return sent


async def _execute_payment_rule(db: Session, rule: ReminderRule, payload: dict, now: datetime, deliver: Deliver) -> int:
    sent = 0
    plans = (
        db.query(PaymentPlan)
        .join(Contract, Contract.id == PaymentPlan.contract_id)
        .filter(
            PaymentPlan.team_id == rule.team_id,
            PaymentPlan.status == payload["status"],
            PaymentPlan.due_date <= now.date(),
        )
        .all()
    )
    for plan in plans:
        window = f"due:{plan.due_date.isoformat()}"
        if _already_sent(db, int(rule.id), int(plan.id), window):
            continue
        owner = str(plan.contract.owner_id) if plan.contract is not None else ""
        users = _recipient_ids(
            db,
            int(rule.team_id),
            payload["recipients"],
            {
                "contract_owner": owner,
                "customer_id": str(plan.contract.customer_id) if plan.contract is not None else "",
            },
        )
        message = _render(
            str(payload["message_template"]),
            {"回款计划": str(plan.stage_name), "天数": str((now.date() - plan.due_date).days)},
        )
        title = str(payload.get("message_title") or rule.name)
        await _record(
            db,
            rule,
            int(plan.id),
            window,
            users,
            message,
            await _deliver(deliver, int(rule.team_id), users, title, message),
            now,
        )
        sent += 1
    return sent


LEGACY_RULE_HANDLERS = {
    ("business_journey", "schedule"): _execute_journey_rule,
    ("opportunity", "schedule"): _execute_opportunity_rule,
    ("follow_up_task", "date"): _execute_follow_up_rule,
    ("customer", "schedule"): _execute_customer_rule,
    ("lead", "schedule"): _execute_lead_rule,
    ("approval", "schedule"): _execute_approval_rule,
    ("payment_plan", "date"): _execute_payment_rule,
}


async def execute_due_reminder_rules(db: Session, *, now: datetime, deliver: Deliver) -> ReminderExecutionResult:
    sent_count = 0
    rules = db.query(ReminderRule).filter(ReminderRule.enabled.is_(True)).all()
    handlers = LEGACY_RULE_HANDLERS
    for rule in rules:
        if not isinstance(rule.rule, dict):
            continue
        payload = dict(rule.rule)
        if type(payload.get("version", 1)) is not int or payload.get("version", 1) not in (1, 2):
            continue
        if payload.get("version", 1) == 2:
            sent_count += await _execute_v2_rule(db, rule, payload, now, deliver)
            continue
        handler = handlers.get((str(payload.get("object_type")), str(rule.trigger)))
        if handler is None:
            continue
        sent_count += await handler(db, rule, payload, now, deliver)
    db.commit()
    return ReminderExecutionResult(sent_count=sent_count)
