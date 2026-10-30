# ruff: noqa: RUF001
"""Stable model failure codes and the only user-facing copy for them."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timedelta
from enum import StrEnum
from typing import NamedTuple

from app.utils.time import business_now


class AssistantFailureCode(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    STRUCTURING_UNAVAILABLE = "STRUCTURING_UNAVAILABLE"
    QUALITY_GATE_UNAVAILABLE = "QUALITY_GATE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_ROOT_FAILURE_CODES = frozenset(
    {
        AssistantFailureCode.CONFIGURATION_ERROR,
        AssistantFailureCode.UPSTREAM_UNAVAILABLE,
        AssistantFailureCode.UPSTREAM_TIMEOUT,
        AssistantFailureCode.MODEL_OUTPUT_INVALID,
        AssistantFailureCode.INTERNAL_ERROR,
    }
)


ROOT_RETRYABLE_FAILURE_CODES = frozenset(
    {
        AssistantFailureCode.UPSTREAM_UNAVAILABLE,
        AssistantFailureCode.UPSTREAM_TIMEOUT,
        AssistantFailureCode.MODEL_OUTPUT_INVALID,
    }
)

ATTEMPT_DEADLINE_SECONDS = 180
_ATTEMPT_DEADLINE: ContextVar[datetime | None] = ContextVar("assistant_attempt_deadline", default=None)


class RootFailurePresentation(NamedTuple):
    title: str
    message: str


_PRESENTATIONS: dict[AssistantFailureCode, RootFailurePresentation] = {
    AssistantFailureCode.CONFIGURATION_ERROR: RootFailurePresentation(
        "模型配置不可用",
        "模型配置暂不可用，本次没有写入客户活动，请联系管理员。",
    ),
    AssistantFailureCode.UPSTREAM_UNAVAILABLE: RootFailurePresentation(
        "模型服务不可达",
        "模型服务暂时不可达，本次没有写入客户活动。",
    ),
    AssistantFailureCode.UPSTREAM_TIMEOUT: RootFailurePresentation(
        "模型服务响应超时",
        "模型服务响应超时，本次没有写入客户活动。",
    ),
    AssistantFailureCode.MODEL_OUTPUT_INVALID: RootFailurePresentation(
        "模型返回格式异常",
        "模型返回结果格式异常，本次没有写入客户活动。",
    ),
    AssistantFailureCode.STRUCTURING_UNAVAILABLE: RootFailurePresentation(
        "整理未完成",
        "跟进整理依赖暂不可用，尚未写入客户活动。原始内容已保存，本次没有产生 CRM 活动。",
    ),
    AssistantFailureCode.QUALITY_GATE_UNAVAILABLE: RootFailurePresentation(
        "评估未完成",
        "质量评估依赖暂不可用，尚未写入客户活动。原始内容已保存，本次没有产生 CRM 活动。",
    ),
    AssistantFailureCode.INTERNAL_ERROR: RootFailurePresentation(
        "处理失败",
        "处理失败，本次没有写入客户活动，请联系管理员。",
    ),
}


def is_root_failure_code(value: object) -> bool:
    return isinstance(value, str) and value in {item.value for item in _ROOT_FAILURE_CODES}


def root_failure_code(value: object) -> AssistantFailureCode:
    if isinstance(value, AssistantFailureCode) and value in _ROOT_FAILURE_CODES:
        return value
    if is_root_failure_code(value):
        return AssistantFailureCode(str(value))
    return AssistantFailureCode.INTERNAL_ERROR


def root_failure_presentation(code: AssistantFailureCode) -> RootFailurePresentation:
    return _PRESENTATIONS[code]


def root_failure_retryable(code: AssistantFailureCode) -> bool:
    return code in ROOT_RETRYABLE_FAILURE_CODES


def bind_attempt_deadline(started_at: datetime) -> Token[datetime | None]:
    """One execution attempt must reach a card before this deadline."""

    return _ATTEMPT_DEADLINE.set(started_at + timedelta(seconds=ATTEMPT_DEADLINE_SECONDS))


def reset_attempt_deadline(token: Token[datetime | None]) -> None:
    _ATTEMPT_DEADLINE.reset(token)


def attempt_budget_remaining() -> float | None:
    """Seconds left in this attempt. None means the caller is not inside a turn."""

    deadline = _ATTEMPT_DEADLINE.get()
    if deadline is None:
        return None
    return (deadline - business_now()).total_seconds()


_SAVED_SOURCE = "原始内容已保存，本次没有产生 CRM 活动。"
ORGANIZE_FAILURE_MESSAGE = f"跟进整理超时，尚未写入客户活动。{_SAVED_SOURCE}"
QUALITY_GATE_FAILURE_MESSAGE = f"质量评估超时，尚未写入客户活动。{_SAVED_SOURCE}"
QUALITY_GATE_FAILURE_TITLE = "评估未完成"
CLASSIFY_TIMEOUT_MESSAGE = f"活动类型判断超时，尚未写入客户活动。{_SAVED_SOURCE}"
MEETING_TIMEOUT_MESSAGE = f"会议整理超时，尚未写入客户活动。{_SAVED_SOURCE}"
VALIDATION_FAILURE_MESSAGE = "整理结果未通过校验，尚未写入客户活动。"
ACTIVITY_COMMIT_UNKNOWN_MESSAGE = "客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。"
REPROCESS_HINT = "使用同一条任务重新处理，不会重复写入。"
_EXPLICIT_ORGANIZE_CODES = frozenset(
    {
        AssistantFailureCode.CONFIGURATION_ERROR,
        AssistantFailureCode.UPSTREAM_UNAVAILABLE,
        AssistantFailureCode.UPSTREAM_TIMEOUT,
        AssistantFailureCode.MODEL_OUTPUT_INVALID,
        AssistantFailureCode.STRUCTURING_UNAVAILABLE,
        AssistantFailureCode.QUALITY_GATE_UNAVAILABLE,
    }
)
_OUTPUT_ERROR_NAMES = frozenset({"ValidationError", "ActionContractError", "TemporalContractError"})
_CAUSE_LIMIT = 500
_MEETING_KINDS = frozenset({"ONLINE_MEETING", "OFFLINE_MEETING"})


class AssistantStageFailure(Exception):
    """Technical stage failure already flushed onto the task.

    execute_turn must commit it as FAILED without rolling back the draft.
    """

    def __init__(
        self,
        *,
        code: AssistantFailureCode,
        stage: str,
        retryable: bool,
        user_message: str,
        task_public_id: str,
        failure_origin: str | None = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.stage = stage
        self.retryable = retryable
        self.user_message = user_message
        self.task_public_id = task_public_id
        self.failure_origin = failure_origin


def _explicit_code(exc: BaseException) -> AssistantFailureCode | None:
    code = getattr(exc, "code", None)
    if isinstance(code, AssistantFailureCode) and code in _EXPLICIT_ORGANIZE_CODES:
        return code
    if isinstance(code, str) and code in {item.value for item in _EXPLICIT_ORGANIZE_CODES}:
        return AssistantFailureCode(code)
    return None


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    cursor: BaseException | None = exc
    while cursor is not None and cursor not in seen:
        seen.append(cursor)
        cursor = cursor.__cause__
    return seen


def failure_origin_of(exc: BaseException) -> str | None:
    for item in _chain(exc):
        origin = getattr(item, "failure_origin", None)
        if origin in {"model_output", "server_contract"}:
            return str(origin)
    return None


def classify_organize_failure(exc: BaseException) -> tuple[AssistantFailureCode, bool]:
    """Map a structuring or quality exception to a stable code.

    A wrapper that only carries the default internal code must not hide a timeout
    or an output-validation error further down the cause chain.
    """

    chain = _chain(exc)
    for item in chain:
        code = _explicit_code(item)
        if code is not None:
            retryable = root_failure_retryable(code)
            if code in {
                AssistantFailureCode.STRUCTURING_UNAVAILABLE,
                AssistantFailureCode.QUALITY_GATE_UNAVAILABLE,
            }:
                retryable = getattr(item, "retryable", False) is True
            if failure_origin_of(exc) == "server_contract" and code is AssistantFailureCode.MODEL_OUTPUT_INVALID:
                retryable = False
            return code, retryable
    if any(isinstance(item, TimeoutError) for item in chain):
        return AssistantFailureCode.UPSTREAM_TIMEOUT, True
    if any(isinstance(item, (ValueError, TypeError)) or type(item).__name__ in _OUTPUT_ERROR_NAMES for item in chain):
        retryable = failure_origin_of(exc) != "server_contract"
        return AssistantFailureCode.MODEL_OUTPUT_INVALID, retryable
    for item in chain:
        code = getattr(item, "code", None)
        if isinstance(code, AssistantFailureCode):
            return code, root_failure_retryable(code)
        if is_root_failure_code(code):
            resolved = AssistantFailureCode(str(code))
            return resolved, root_failure_retryable(resolved)
    return AssistantFailureCode.INTERNAL_ERROR, False


def classify_stage_failure(exc: BaseException, stage: str) -> tuple[AssistantFailureCode, bool, str | None]:
    """Keep timeout, unreachable, invalid output, and stage dependency failures apart."""

    code, retryable = classify_organize_failure(exc)
    origin = failure_origin_of(exc)
    if code is AssistantFailureCode.INTERNAL_ERROR and stage == "structure":
        return AssistantFailureCode.STRUCTURING_UNAVAILABLE, False, origin
    if code is AssistantFailureCode.INTERNAL_ERROR and stage == "quality_gate":
        return AssistantFailureCode.QUALITY_GATE_UNAVAILABLE, False, origin
    return code, retryable, origin


def _meeting(activity_kind: str | None) -> bool:
    return activity_kind in _MEETING_KINDS


def _stage_label(stage: str, activity_kind: str | None) -> str:
    if stage == "classify":
        return "活动类型判断时"
    if stage == "quality_gate":
        return "质量评估时"
    if stage == "structure":
        return "会议整理时" if _meeting(activity_kind) else "跟进整理时"
    if stage == "write":
        return "写入客户活动时"
    return ""


def stage_user_message(
    *,
    code: AssistantFailureCode,
    stage: str,
    activity_kind: str | None = None,
) -> str:
    """One sentence for the page. Callers must not interpolate model or vendor text."""

    if stage == "classify" and code is AssistantFailureCode.UPSTREAM_TIMEOUT:
        return CLASSIFY_TIMEOUT_MESSAGE
    if stage == "quality_gate" and code is AssistantFailureCode.UPSTREAM_TIMEOUT:
        return QUALITY_GATE_FAILURE_MESSAGE
    if stage == "structure" and code is AssistantFailureCode.UPSTREAM_TIMEOUT:
        return MEETING_TIMEOUT_MESSAGE if _meeting(activity_kind) else ORGANIZE_FAILURE_MESSAGE
    if stage == "structure" and code is AssistantFailureCode.MODEL_OUTPUT_INVALID:
        return VALIDATION_FAILURE_MESSAGE
    if code is AssistantFailureCode.STRUCTURING_UNAVAILABLE:
        noun = "会议整理" if _meeting(activity_kind) else "跟进整理"
        return f"{noun}依赖暂不可用，尚未写入客户活动。{_SAVED_SOURCE}"
    if code is AssistantFailureCode.QUALITY_GATE_UNAVAILABLE:
        return _PRESENTATIONS[code].message
    if code is AssistantFailureCode.UPSTREAM_UNAVAILABLE:
        return f"{_stage_label(stage, activity_kind)}模型服务暂时不可达，本次没有写入客户活动。"
    if code is AssistantFailureCode.MODEL_OUTPUT_INVALID:
        return f"{_stage_label(stage, activity_kind)}模型返回结果格式异常，本次没有写入客户活动。"
    if code is AssistantFailureCode.CONFIGURATION_ERROR:
        return _PRESENTATIONS[code].message
    return _PRESENTATIONS[AssistantFailureCode.INTERNAL_ERROR].message


def failure_cause(exc: BaseException) -> str:
    root = exc
    while root.__cause__ is not None:
        root = root.__cause__
    cause = f"{type(root).__name__}: {root}"
    if root is not exc:
        cause = f"{type(exc).__name__}: {exc} ({cause})"
    return cause[:_CAUSE_LIMIT]
