"""Shared semantic contract between Root routing and business Workflows."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

SpeechAct: TypeAlias = Literal[
    "ASSERT_EVENT",
    "ASK_FACT",
    "REQUEST_ACTION",
    "CONFIRM_ACTION",
    "PROVIDE_SUPPLEMENT",
    "CANCEL",
    "UNKNOWN",
]
BusinessObject: TypeAlias = Literal[
    "CUSTOMER_ACTIVITY",
    "FOLLOW_UP_TASK",
    "CUSTOMER",
    "OPPORTUNITY",
    "PAYMENT_RECORD",
    "CONTRACT",
    "LEAD",
    "CONTACT",
    "INVOICE_TITLE",
    "DEPLOYMENT_INFO",
    "CUSTOMER_MEMBER",
    "UNKNOWN",
]
Operation: TypeAlias = Literal[
    "CREATE",
    "READ",
    "TRANSITION",
    "DELETE",
    "NONE",
    "UNKNOWN",
]
QueryPlanScope: TypeAlias = Literal[
    "global_work",
    "customer_scoped",
    "customer_list",
    "unknown",
]
QueryPlanResource: TypeAlias = Literal[
    "follow_up_tasks",
    "completed_work",
    "customer_context",
    "customer_activities",
    "customer_contacts",
    "deployment_info",
    "customers",
]
QueryPlanGoal: TypeAlias = Literal["list", "search", "get_detail", "get_status", "summarize"]
QueryPlanTemporalKind: TypeAlias = Literal[
    "today",
    "tomorrow",
    "this_week",
    "next_week",
    "last_week",
    "this_month",
    "overdue",
    "custom",
    "unspecified",
]


class AgentQueryTemporalPlan(BaseModel):
    """Query slots Root may provide when it owns the complete semantic intake."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: QueryPlanTemporalKind = "unspecified"
    start_at: str | None = Field(default=None, max_length=64)
    end_at: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=128)


class AgentQueryPlan(BaseModel):
    """Closed query capability details carried by the Root semantic plan."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scope: QueryPlanScope
    resource: QueryPlanResource | None = None
    query_goal: QueryPlanGoal = "list"
    customer_text: str | None = Field(default=None, max_length=255)
    task_text: str | None = Field(default=None, max_length=1000)
    temporal: AgentQueryTemporalPlan = Field(default_factory=AgentQueryTemporalPlan)


class AgentSemanticPlan(BaseModel):
    """LLM-produced meaning shared by routing and the selected capability.

    This is not a tool authorization.  The Root uses it to select a capability,
    while the Workflow or Query boundary still validates the concrete command,
    customer binding, permissions, and side effects.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    speech_act: SpeechAct = "UNKNOWN"
    business_object: BusinessObject = "UNKNOWN"
    operation: Operation = "UNKNOWN"
    user_goal: str | None = Field(default=None, max_length=2_000)
    customer_reference: str | None = Field(default=None, max_length=255)
    activity_content: str | None = Field(default=None, max_length=20_000)
    query_target: str | None = Field(default=None, max_length=2_000)
    # Query details are optional because older model outputs and write plans do
    # not need them.  When present, they let Query execute from the same Root
    # semantic intake instead of making a second provider call.
    query_plan: AgentQueryPlan | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list, max_length=20)


WRITE_SPEECH_ACTS = frozenset({
    "ASSERT_EVENT",
    "REQUEST_ACTION",
    "CONFIRM_ACTION",
    "PROVIDE_SUPPLEMENT",
})

_WORKFLOW_INTENT_BY_CAPABILITY: dict[tuple[str, str], str] = {
    ("CUSTOMER_ACTIVITY", "CREATE"): "CUSTOMER_ACTIVITY",
    ("CUSTOMER", "CREATE"): "CREATE_CUSTOMER",
    # Customer profile maintenance remains a standalone write capability.
    # These commands must not be folded into the customer-activity workflow.
    ("CONTACT", "CREATE"): "CREATE_CONTACT",
    ("INVOICE_TITLE", "CREATE"): "CREATE_INVOICE_TITLE",
    ("DEPLOYMENT_INFO", "CREATE"): "CREATE_DEPLOYMENT_INFO",
    ("CUSTOMER_MEMBER", "CREATE"): "CREATE_CUSTOMER_MEMBER",
    ("OPPORTUNITY", "CREATE"): "CREATE_OPPORTUNITY",
    ("OPPORTUNITY", "TRANSITION"): "MOVE_OPPORTUNITY_STAGE",
    ("FOLLOW_UP_TASK", "TRANSITION"): "FOLLOW_UP_TASK_TRANSITION",
}


def semantic_plan_is_read(plan: object) -> bool:
    """Return whether the structured plan explicitly requests a read."""

    return getattr(plan, "speech_act", None) == "ASK_FACT" and getattr(plan, "operation", None) == "READ"


def semantic_plan_is_write(plan: object) -> bool:
    """Return whether the structured plan represents a mutating user act."""

    return (
        getattr(plan, "speech_act", None) in WRITE_SPEECH_ACTS
        and getattr(plan, "operation", None) in {"CREATE", "TRANSITION", "DELETE"}
    )


def workflow_intent_from_semantic_plan(plan: object) -> str | None:
    """Project a supported Root write capability into its Workflow intent."""

    if not semantic_plan_is_write(plan):
        return None
    return _WORKFLOW_INTENT_BY_CAPABILITY.get(
        (getattr(plan, "business_object", None), getattr(plan, "operation", None))
    )


def semantic_plan_supports_workflow_write(plan: object) -> bool:
    """Return whether a mutating plan is supported by the current Workflow."""

    return workflow_intent_from_semantic_plan(plan) is not None


_INTENT_TO_BUSINESS_OBJECT: dict[str, BusinessObject] = {
    "CUSTOMER_ACTIVITY": "CUSTOMER_ACTIVITY",
    "FOLLOW_UP_TASK_TRANSITION": "FOLLOW_UP_TASK",
    "CREATE_CUSTOMER": "CUSTOMER",
    "CREATE_OPPORTUNITY": "OPPORTUNITY",
    "MOVE_OPPORTUNITY_STAGE": "OPPORTUNITY",
    "PAYMENT_RECORD": "PAYMENT_RECORD",
    "CREATE_LEAD": "LEAD",
    "CREATE_CONTACT": "CONTACT",
    "CREATE_INVOICE_TITLE": "INVOICE_TITLE",
    "CREATE_DEPLOYMENT_INFO": "DEPLOYMENT_INFO",
    "CREATE_CUSTOMER_MEMBER": "CUSTOMER_MEMBER",
    "CRM_READ_QUERY": "UNKNOWN",
}


def query_intent_from_semantic_plan(plan: object) -> object | None:
    """Project complete Root query slots to the Query contract when available.

    This is a structural projection only.  The Query boundary still validates
    the resulting intent and owns customer identity binding and CRM access.
    Returning ``None`` for incomplete plans preserves the specialized Query
    resolver as a bounded fallback, never as a second top-level router.
    """

    query_plan = getattr(plan, "query_plan", None)
    if query_plan is None or getattr(plan, "confidence", 0.0) < 0.80:
        return None
    try:
        from app.services.agent.query.semantic_intent import (
            CRMQuerySemanticIntent,
            QueryTemporalIntent,
        )

        temporal = getattr(query_plan, "temporal", None)
        return CRMQuerySemanticIntent(
            scope=query_plan.scope,
            resource=query_plan.resource,
            query_goal=query_plan.query_goal,
            task_text=query_plan.task_text,
            customer_text=query_plan.customer_text,
            temporal=QueryTemporalIntent(
                kind=temporal.kind,
                start_at=temporal.start_at,
                end_at=temporal.end_at,
                timezone=temporal.timezone,
            ),
            confidence=plan.confidence,
        )
    except Exception:
        # A malformed optional enrichment must not invalidate Root routing; the
        # Query resolver can still attempt its own closed-contract parse.
        return None


def semantic_plan_from_result(result: object) -> AgentSemanticPlan:
    """Project the domain parser's structured result into the Root contract.

    This is a capability vocabulary mapping, not natural-language routing: the
    parser has already understood the utterance. Keeping this projection in a
    shared module lets Root and Workflow consume the same semantic meaning
    without introducing lexical rules or a second business classifier.
    """

    intent = getattr(result, "intent", "UNKNOWN")
    if not isinstance(intent, str):
        intent = "UNKNOWN"
    confidence = getattr(result, "intent_confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    confidence_value = max(0.0, min(1.0, float(confidence)))

    if intent == "CRM_READ_QUERY":
        speech_act: SpeechAct = "ASK_FACT"
        operation: Operation = "READ"
    elif intent == "CUSTOMER_ACTIVITY":
        speech_act = "ASSERT_EVENT"
        operation = "CREATE"
    elif intent == "UNKNOWN":
        speech_act = "UNKNOWN"
        operation = "UNKNOWN"
    elif intent == "FOLLOW_UP_TASK_TRANSITION" or intent == "MOVE_OPPORTUNITY_STAGE":
        speech_act = "REQUEST_ACTION"
        operation = "TRANSITION"
    else:
        speech_act = "REQUEST_ACTION"
        operation = "CREATE"

    customer = getattr(result, "customer", None)
    customer_reference = getattr(customer, "name_text", None)
    if not isinstance(customer_reference, str) or not customer_reference.strip():
        customer_reference = None

    follow_up = getattr(result, "follow_up", None)
    activity_content = getattr(follow_up, "content", None)
    if not isinstance(activity_content, str) or not activity_content.strip():
        activity_content = None

    user_goal = None
    if intent == "CUSTOMER_ACTIVITY":
        user_goal = "记录客户活动"
    elif intent == "CRM_READ_QUERY":
        user_goal = "查询 CRM 信息"
    elif intent != "UNKNOWN":
        user_goal = intent

    evidence = getattr(result, "evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    evidence = [item for item in evidence if isinstance(item, str)][:20]

    return AgentSemanticPlan(
        speech_act=speech_act,
        business_object=_INTENT_TO_BUSINESS_OBJECT.get(intent, "UNKNOWN"),
        operation=operation,
        user_goal=user_goal,
        customer_reference=customer_reference,
        activity_content=activity_content,
        confidence=confidence_value,
        evidence=evidence,
    )
