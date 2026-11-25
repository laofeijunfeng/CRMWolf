"""Server-side intent verdict over the root model's semantic plan.

The model only nominates (speech act, business object, operation, confidence); this module decides
whether the sentence becomes an activity task, a direct-create entity task, a refusal with links, or
one clarifying question. The conversation root and the direct ``POST /tasks`` intake share it.
"""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.schemas.assistant_conversation import ConversationLink

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.services.agent.semantic_plan import AgentSemanticPlan
    from app.services.assistant.contracts import TaskKind

NOT_WRITTEN_SUFFIX = "这次没有写入。"
CAPABILITIES = "我可以记跟进，也可以新建联系人、开票抬头、部署信息、商机、客户"
CONFIDENT = 0.8
# Below CONFIDENT but at least this sure about a create: ask entity-vs-activity once instead of refusing.
INTENT_QUESTION_FLOOR = 0.5

ENTITY_TASK_KINDS: dict[str, TaskKind] = {
    "CONTACT": "contact_create",
    "INVOICE_TITLE": "invoice_title_create",
    "DEPLOYMENT_INFO": "deployment_create",
    "OPPORTUNITY": "opportunity_create",
    "CUSTOMER": "customer_create",
}
ENTITY_LABELS: dict[TaskKind, str] = {
    "contact_create": "联系人",
    "invoice_title_create": "开票抬头",
    "deployment_create": "部署信息",
    "opportunity_create": "商机",
    "customer_create": "客户",
}
_WRITE_ACTS = frozenset({"ASSERT_EVENT", "REQUEST_ACTION", "PROVIDE_SUPPLEMENT"})
_ACTIVITY_ACTS = frozenset({*_WRITE_ACTS, "CORRECT"})

_LEADS = ConversationLink(page="leads", label="线索管理")
_PAYMENTS = ConversationLink(page="payments", label="回款管理")
_CONTRACTS = ConversationLink(page="contracts", label="合同管理")
_INVOICES = ConversationLink(page="invoices", label="发票管理")
_CUSTOMERS = ConversationLink(page="customers", label="客户管理")
_FOLLOW_UP_TASKS = ConversationLink(page="follow_up_tasks", label="客户追踪")
QUERY_REFUSAL_LINKS = (_CUSTOMERS, _FOLLOW_UP_TASKS)

_UNSUPPORTED_CREATES: dict[str, tuple[str, ConversationLink]] = {
    "LEAD": ("新建线索请到线索管理", _LEADS),
    "PAYMENT_RECORD": ("登记回款请到回款管理", _PAYMENTS),
    "CONTRACT": ("新建合同请到合同管理", _CONTRACTS),
}
_EXISTING_RECORD_PAGES: dict[str, ConversationLink] = {
    "LEAD": _LEADS,
    "PAYMENT_RECORD": _PAYMENTS,
    "CONTRACT": _CONTRACTS,
    "FOLLOW_UP_TASK": _FOLLOW_UP_TASKS,
}


def not_written(message: str) -> str:
    """Every reply that wrote nothing ends with the same suffix; callers never hand-write it."""

    body = message.strip()
    if body.endswith(NOT_WRITTEN_SUFFIX):
        return body
    if body.endswith(("？", "?")):
        return f"{body}{NOT_WRITTEN_SUFFIX}"
    return f"{body.rstrip('。；;，, ')}；{NOT_WRITTEN_SUFFIX}"


UNCLEAR_MESSAGE = not_written(f"没太明白要做什么。{CAPABILITIES}，请直接说要记的沟通或要新建的资料")
QUERY_REFUSAL_MESSAGE = not_written(f"销售助手不做查询，查询请到客户管理或客户追踪页面。{CAPABILITIES}")


@dataclass(frozen=True)
class IntentVerdict:
    route: Literal["activity", "entity", "intent_question", "refuse"]
    task_kind: TaskKind = "customer_activity"
    message: str = ""
    links: tuple[ConversationLink, ...] = ()


def _refuse(message: str, *links: ConversationLink) -> IntentVerdict:
    return IntentVerdict(route="refuse", message=not_written(message), links=links)


def judge_intent(plan: AgentSemanticPlan, confidence: float) -> IntentVerdict:
    """The single rule set deciding what a root sentence may become."""

    sure = min(confidence, plan.confidence)
    obj, operation = plan.business_object, plan.operation
    entity_kind = ENTITY_TASK_KINDS.get(obj) if operation == "CREATE" else None
    if sure < CONFIDENT:
        if entity_kind is not None and plan.speech_act in _WRITE_ACTS and sure >= INTENT_QUESTION_FLOOR:
            return IntentVerdict(route="intent_question", task_kind=entity_kind)
        return _refuse(UNCLEAR_MESSAGE)
    if plan.speech_act == "ASK_FACT" and operation == "READ":
        return IntentVerdict(route="refuse", message=QUERY_REFUSAL_MESSAGE, links=QUERY_REFUSAL_LINKS)
    if obj == "CUSTOMER_MEMBER":
        return _refuse("设置客户负责人或成员请到客户详情处理", _CUSTOMERS)
    if obj == "INVOICE_TITLE" and operation == "TRANSITION":
        return _refuse("申请开票请到发票管理", _INVOICES)
    if operation in {"TRANSITION", "DELETE"}:
        return _refuse("这里不修改或删除已有记录，请到对应业务页面处理", _EXISTING_RECORD_PAGES.get(obj, _CUSTOMERS))
    if operation == "CREATE" and obj in _UNSUPPORTED_CREATES:
        message, link = _UNSUPPORTED_CREATES[obj]
        return _refuse(message, link)
    if entity_kind is not None and plan.speech_act in _WRITE_ACTS:
        return IntentVerdict(route="entity", task_kind=entity_kind)
    if obj == "CUSTOMER_ACTIVITY" and operation == "CREATE" and plan.speech_act in _ACTIVITY_ACTS:
        return IntentVerdict(route="activity")
    return _refuse(f"{CAPABILITIES}，其他操作请到对应业务页面处理")


INTENT_FIELD = "intent"


def open_verdict_task(
    db: Session, *, team_id: int, user_id: int, key: str, goal: str, verdict: IntentVerdict
) -> AssistantTask:
    """Accept the task a verdict names; an unsure create waits on one entity-vs-activity question."""

    from app.services.assistant.contracts import TaskWaiting
    from app.services.assistant.task_state import TaskUpdate, apply_task_update
    from app.services.assistant.turns import accept_create

    task = accept_create(db, team_id=team_id, user_id=user_id, key=key, goal=goal, task_kind=verdict.task_kind)
    if verdict.route != "intent_question" or task.version != 0:
        return task
    label = ENTITY_LABELS[verdict.task_kind]
    task = apply_task_update(
        db,
        task,
        TaskUpdate(
            waiting=TaskWaiting(
                type="OBJECT_SELECTION",
                field=INTENT_FIELD,
                question_id=f"q_{task.public_id}_intent",
                prompt=f"这句要存为{label}，还是记一条跟进？",
                candidates=[{"id": "entity", "label": f"存为{label}"}, {"id": "activity", "label": "记一条跟进"}],
            ),
            action_actor="SYSTEM",
            action_name="ask_entity_intent",
            action_input={"task_kind": verdict.task_kind},
        ),
    ).task
    db.commit()
    return task
