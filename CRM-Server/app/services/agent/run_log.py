"""Reconstruct a six-step Agent turn timeline from a Root dispatch result."""

# ruff: noqa: RUF001
from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.services.agent.orchestrator.contracts import (
    ClarificationDispatchResult,
    FailureDispatchResult,
    QueryDispatchResult,
    RootDispatchResult,
    WorkflowDispatchResult,
)
from app.services.agent.workflow.contracts import (
    WorkflowCompletedResult,
    WorkflowQualityGate,
    WorkflowWaitingResult,
)

TurnOutcome: TypeAlias = Literal[
    "answered",
    "blocked_unwritten",
    "waiting_confirmation",
    "waiting_input",
    "written",
    "failed",
    "clarified",
]
StepKind: TypeAlias = Literal["model", "code", "interaction", "api", "background"]
StepTone: TypeAlias = Literal["done", "blocked", "skipped"]


class TurnTimelineStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: StepKind
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=2_000)
    tone: StepTone

    @field_validator("title", "detail", mode="before")
    @classmethod
    def clip_step_text(cls, value: object, info: ValidationInfo) -> object:
        limit = 200 if info.field_name == "title" else 2_000
        return _clip_required(value, limit)


class TurnTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    outcome: TurnOutcome
    summary: str = Field(min_length=1, max_length=500)
    quality_score: int | None = Field(default=None, ge=0, le=100)
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    steps: list[TurnTimelineStep] = Field(min_length=6, max_length=6)

    @field_validator("summary", mode="before")
    @classmethod
    def clip_summary(cls, value: object) -> object:
        return _clip_required(value, 500)

    @field_validator("customer_name", "model", mode="before")
    @classmethod
    def clip_optional_text(cls, value: object, info: ValidationInfo) -> object:
        limit = 255 if info.field_name == "customer_name" else 256
        return _clip_optional(value, limit)


def _clip_required(value: object, limit: int) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip() or "（无内容）"
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)]}…"[:limit]


def _clip_optional(value: object, limit: int) -> object:
    if value is None or not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)]}…"[:limit]


_OBJECT_LABELS = {
    "CUSTOMER_ACTIVITY": "客户活动",
    "CUSTOMER": "客户",
    "OPPORTUNITY": "商机",
    "FOLLOW_UP_TASK": "跟进任务",
    "CONTACT": "联系人",
}

_OPERATION_LABELS = {
    "CREATE": "新增",
    "READ": "查询",
    "TRANSITION": "推进",
    "UPDATE": "更新",
}


def build_turn_timeline(
    dispatch: RootDispatchResult,
    *,
    user_text: str,
    model: str | None = None,
) -> TurnTimeline:
    del user_text
    if isinstance(dispatch, QueryDispatchResult):
        return _query_timeline(dispatch, model=model)
    if isinstance(dispatch, WorkflowDispatchResult):
        return _workflow_timeline(dispatch, model=model)
    if isinstance(dispatch, ClarificationDispatchResult):
        return _clarification_timeline(dispatch, model=model)
    return _failure_timeline(dispatch, model=model)


def _query_timeline(dispatch: QueryDispatchResult, *, model: str | None) -> TurnTimeline:
    trace_model = dispatch.query_result.trace.model
    tool_names = list(dispatch.query_result.trace.tool_names)
    if not tool_names:
        tool_names = [call.tool_name for call in dispatch.query_result.trace.tool_calls]
    tool_label = "、".join(tool_names) if tool_names else "只读查询"
    return TurnTimeline(
        outcome="answered",
        summary="已回答查询，没有写入。",
        model=model or trace_model,
        steps=[
            _model_step(dispatch, fallback="查询"),
            TurnTimelineStep(
                kind="code",
                title="未绑定写入客户",
                detail="只读查询不创建或改写客户活动。",
                tone="skipped",
            ),
            TurnTimelineStep(
                kind="code",
                title="未做质量门禁",
                detail="查询路径不评分、不拦写入。",
                tone="skipped",
            ),
            TurnTimelineStep(
                kind="interaction",
                title="没有等待用户确认",
                detail="查询结果直接返回。",
                tone="skipped",
            ),
            TurnTimelineStep(kind="api", title="已执行只读查询", detail=tool_label, tone="done"),
            TurnTimelineStep(
                kind="background",
                title="没有整理 / 评分任务",
                detail="查询路径不创建后台任务。",
                tone="skipped",
            ),
        ],
    )


def _workflow_timeline(dispatch: WorkflowDispatchResult, *, model: str | None) -> TurnTimeline:
    result = dispatch.workflow_result
    quality = getattr(result, "quality_gate", None)
    customer = getattr(result, "resolved_customer", None)
    customer_name = customer.customer_name if customer is not None else None
    quality_score = quality.score if isinstance(quality, WorkflowQualityGate) else None
    resolved_model = model
    if isinstance(quality, WorkflowQualityGate) and quality.model:
        resolved_model = quality.model
    if isinstance(result, WorkflowWaitingResult):
        return _waiting_workflow_timeline(
            dispatch,
            result=result,
            quality=quality if isinstance(quality, WorkflowQualityGate) else None,
            customer_name=customer_name,
            quality_score=quality_score,
            model=resolved_model,
        )
    if isinstance(result, WorkflowCompletedResult):
        has_background = bool(result.durable_work)
        return TurnTimeline(
            outcome="written",
            summary="已写入，并登记后台任务。" if has_background else "已写入。",
            quality_score=quality_score,
            customer_name=customer_name,
            model=resolved_model,
            steps=[
                _model_step(dispatch, fallback="记跟进"),
                _customer_step(customer_name),
                _quality_passed_step(quality),
                TurnTimelineStep(
                    kind="interaction",
                    title="没有等待用户确认",
                    detail="本轮已完成写入。",
                    tone="skipped",
                ),
                TurnTimelineStep(
                    kind="api",
                    title="已调用写入接口",
                    detail="create_customer_activity 已执行。",
                    tone="done",
                ),
                TurnTimelineStep(
                    kind="background",
                    title="已登记后台任务" if has_background else "没有整理 / 评分任务",
                    detail="写入后的整理、评分或商机建议已入队。" if has_background else "本轮没有后台任务。",
                    tone="done" if has_background else "skipped",
                ),
            ],
        )
    return TurnTimeline(
        outcome="failed",
        summary=getattr(result, "message", None) or "工作流执行失败。",
        quality_score=quality_score,
        customer_name=customer_name,
        model=resolved_model,
        steps=_failed_steps(dispatch, detail=getattr(result, "message", None) or "工作流执行失败。"),
    )


def _waiting_workflow_timeline(
    dispatch: WorkflowDispatchResult,
    *,
    result: WorkflowWaitingResult,
    quality: WorkflowQualityGate | None,
    customer_name: str | None,
    quality_score: int | None,
    model: str | None,
) -> TurnTimeline:
    action = result.interaction.business_action
    if action == "supplement_follow_up_quality" or (quality is not None and not quality.passed):
        score = quality.score if quality is not None else 0
        reason = quality.reason if quality is not None else result.interaction.prompt
        return TurnTimeline(
            outcome="blocked_unwritten",
            summary=f"结论：质量 {score} 分，拦住写入。没有创建跟进，也没有后台任务。",
            quality_score=score,
            customer_name=customer_name,
            model=model,
            steps=[
                _model_step(dispatch, fallback="记跟进"),
                _customer_step(customer_name),
                TurnTimelineStep(
                    kind="code",
                    title=f"质量 {score} 分，拦住",
                    detail=f"阈值 60。{reason}。不写库，不生成商机建议。",
                    tone="blocked",
                ),
                TurnTimelineStep(
                    kind="interaction",
                    title="只问了一个补充问题",
                    detail=result.interaction.prompt,
                    tone="blocked",
                ),
                TurnTimelineStep(
                    kind="api",
                    title="没有调创建",
                    detail="create_customer_activity 未调用",
                    tone="skipped",
                ),
                TurnTimelineStep(
                    kind="background",
                    title="没有整理 / 评分任务",
                    detail="Agent 路径不创建 AIJob",
                    tone="skipped",
                ),
            ],
        )
    if result.interaction.interaction_type == "confirmation":
        return TurnTimeline(
            outcome="waiting_confirmation",
            summary="等待用户确认后才会写入。",
            quality_score=quality_score,
            customer_name=customer_name,
            model=model,
            steps=[
                _model_step(dispatch, fallback="记跟进"),
                _customer_step(customer_name),
                _quality_passed_step(quality),
                TurnTimelineStep(
                    kind="interaction",
                    title="等待确认",
                    detail=result.interaction.prompt,
                    tone="blocked",
                ),
                TurnTimelineStep(
                    kind="api",
                    title="尚未调用写入接口",
                    detail="确认前不执行写入。",
                    tone="skipped",
                ),
                TurnTimelineStep(
                    kind="background",
                    title="没有整理 / 评分任务",
                    detail="确认前不创建后台任务。",
                    tone="skipped",
                ),
            ],
        )
    return TurnTimeline(
        outcome="waiting_input",
        summary="等待用户补充后再继续。",
        quality_score=quality_score,
        customer_name=customer_name,
        model=model,
        steps=[
            _model_step(dispatch, fallback="记跟进"),
            _customer_step(customer_name),
            _quality_passed_step(quality),
            TurnTimelineStep(
                kind="interaction",
                title=result.interaction.title,
                detail=result.interaction.prompt,
                tone="blocked",
            ),
            TurnTimelineStep(
                kind="api",
                title="尚未调用写入接口",
                detail="补充完成前不执行写入。",
                tone="skipped",
            ),
            TurnTimelineStep(
                kind="background",
                title="没有整理 / 评分任务",
                detail="补充完成前不创建后台任务。",
                tone="skipped",
            ),
        ],
    )


def _clarification_timeline(dispatch: ClarificationDispatchResult, *, model: str | None) -> TurnTimeline:
    return TurnTimeline(
        outcome="clarified",
        summary="本轮需要澄清，没有写入。",
        model=model,
        steps=[
            _model_step(dispatch, fallback="澄清"),
            TurnTimelineStep(
                kind="code",
                title="未绑定写入客户",
                detail="澄清路径不创建客户活动。",
                tone="skipped",
            ),
            TurnTimelineStep(
                kind="code",
                title="未做质量门禁",
                detail="澄清路径不评分。",
                tone="skipped",
            ),
            TurnTimelineStep(
                kind="interaction",
                title="需要澄清",
                detail=dispatch.clarification.question,
                tone="blocked",
            ),
            TurnTimelineStep(
                kind="api",
                title="没有调创建",
                detail="澄清完成前不执行写入。",
                tone="skipped",
            ),
            TurnTimelineStep(
                kind="background",
                title="没有整理 / 评分任务",
                detail="澄清路径不创建后台任务。",
                tone="skipped",
            ),
        ],
    )


def _failure_timeline(dispatch: FailureDispatchResult, *, model: str | None) -> TurnTimeline:
    return TurnTimeline(
        outcome="failed",
        summary=dispatch.error.message or "执行失败。",
        model=model,
        steps=_failed_steps(dispatch, detail=dispatch.error.message or "执行失败。"),
    )


def _failed_steps(dispatch: RootDispatchResult, *, detail: str) -> list[TurnTimelineStep]:
    return [
        _model_step(dispatch, fallback="处理请求"),
        TurnTimelineStep(
            kind="code",
            title="未完成客户绑定",
            detail="本轮在写入前失败。",
            tone="skipped",
        ),
        TurnTimelineStep(
            kind="code",
            title="未完成质量门禁",
            detail="本轮在写入前失败。",
            tone="skipped",
        ),
        TurnTimelineStep(kind="interaction", title="没有完成交互", detail=detail, tone="blocked"),
        TurnTimelineStep(
            kind="api",
            title="没有调创建",
            detail="失败路径不执行写入。",
            tone="skipped",
        ),
        TurnTimelineStep(
            kind="background",
            title="没有整理 / 评分任务",
            detail="失败路径不创建后台任务。",
            tone="skipped",
        ),
    ]


def _model_step(dispatch: RootDispatchResult, *, fallback: str) -> TurnTimelineStep:
    decision = getattr(dispatch, "decision", None)
    plan = getattr(decision, "semantic_plan", None)
    object_label = _OBJECT_LABELS.get(getattr(plan, "business_object", ""), fallback)
    operation_label = _OPERATION_LABELS.get(getattr(plan, "operation", ""), "")
    route = getattr(decision, "route", None)
    if route == "QUERY":
        title = "判成「查询」"
    elif route == "CLARIFY":
        title = "判成「澄清」"
    elif object_label:
        title = f"判成「{fallback if fallback != object_label else '记跟进'}」"
        if fallback == "记跟进" or getattr(plan, "business_object", None) == "CUSTOMER_ACTIVITY":
            title = "判成「记跟进」"
        elif operation_label:
            title = f"判成「{object_label}{operation_label}」"
    else:
        title = f"判成「{fallback}」"
    detail_parts = []
    if route is not None:
        detail_parts.append(f"route = {route}")
    if getattr(plan, "speech_act", None):
        detail_parts.append(f"speech_act = {plan.speech_act}")
    if object_label and operation_label:
        detail_parts.append(f"{object_label}{operation_label}")
    return TurnTimelineStep(
        kind="model",
        title=title,
        detail=" · ".join(detail_parts) if detail_parts else title,
        tone="done",
    )


def _customer_step(customer_name: str | None) -> TurnTimelineStep:
    if customer_name:
        return TurnTimelineStep(
            kind="code",
            title=f"匹配到客户「{customer_name}」",
            detail="checkpoint 已有客户绑定，本轮未重新搜索",
            tone="done",
        )
    return TurnTimelineStep(
        kind="code",
        title="未记录客户绑定",
        detail="本轮结果未带出已解析客户。",
        tone="skipped",
    )


def _quality_passed_step(quality: WorkflowQualityGate | None) -> TurnTimelineStep:
    if quality is None:
        return TurnTimelineStep(
            kind="code",
            title="未做质量门禁",
            detail="本轮没有跟进质量评分。",
            tone="skipped",
        )
    return TurnTimelineStep(
        kind="code",
        title=f"质量 {quality.score} 分，通过",
        detail=quality.reason,
        tone="done",
    )
