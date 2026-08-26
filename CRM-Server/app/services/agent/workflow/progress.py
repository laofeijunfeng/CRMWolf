"""Authoritative, channel-neutral progress projections for durable Workflows."""

from __future__ import annotations

from app.services.agent.workflow.contracts import WorkflowProgress, WorkflowProgressStep


def _step(
    key: str,
    title: str,
    status: str,
    description: str | None = None,
) -> WorkflowProgressStep:
    return WorkflowProgressStep.model_validate(
        {
            "key": key,
            "title": title,
            "status": status,
            "description": description,
        }
    )


def understanding_progress(*, outcome: str = "RUNNING") -> WorkflowProgress:
    return WorkflowProgress(
        steps=[_step("understand_request", "理解业务操作", outcome)]
    )


def planning_progress(
    *,
    has_supplements: bool = False,
    outcome: str = "RUNNING",
) -> WorkflowProgress:
    steps = [_step("understand_request", "理解业务操作", "COMPLETED")]
    if has_supplements:
        steps.append(_step("collect_required_input", "接收补充信息", "COMPLETED"))
    steps.append(_step("prepare_plan", "生成执行计划", outcome))
    return WorkflowProgress(steps=steps)


def input_failed_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[_step("understand_request", "理解业务操作", "FAILED")]
    )


def planning_failed_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("prepare_plan", "生成执行计划", "FAILED"),
        ]
    )


def awaiting_required_input_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("collect_required_input", "等待补充必要信息", "WAITING"),
        ]
    )


def required_input_failed_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("collect_required_input", "处理补充信息", "FAILED"),
        ]
    )


def required_input_cancelled_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("collect_required_input", "补充必要信息", "CANCELLED"),
        ]
    )


def awaiting_confirmation_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("prepare_plan", "生成执行计划", "COMPLETED"),
            _step("await_confirmation", "等待用户确认", "WAITING"),
        ]
    )


def confirmation_failed_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("prepare_plan", "生成执行计划", "COMPLETED"),
            _step("await_confirmation", "处理确认结果", "FAILED"),
        ]
    )


def confirmation_cancelled_progress() -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            _step("understand_request", "理解业务操作", "COMPLETED"),
            _step("prepare_plan", "生成执行计划", "COMPLETED"),
            _step("await_confirmation", "用户已取消", "CANCELLED"),
        ]
    )


def execution_progress(
    *,
    confirmation_required: bool,
    has_supplements: bool,
    outcome: str,
) -> WorkflowProgress:
    steps = [_step("understand_request", "理解业务操作", "COMPLETED")]
    if has_supplements:
        steps.append(_step("collect_required_input", "接收补充信息", "COMPLETED"))
    steps.append(_step("prepare_plan", "生成执行计划", "COMPLETED"))
    if confirmation_required:
        steps.append(_step("await_confirmation", "完成用户确认", "COMPLETED"))
    steps.append(_step("execute_action", "执行 CRM 操作", outcome))
    if outcome == "COMPLETED":
        steps.append(_step("prepare_result", "整理执行结果", "COMPLETED"))
    return WorkflowProgress(steps=steps)
