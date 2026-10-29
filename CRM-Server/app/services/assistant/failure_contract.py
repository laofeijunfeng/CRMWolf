# ruff: noqa: RUF001
"""Stable Root model failure codes and the only user-facing copy for them."""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class AssistantFailureCode(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ROOT_RETRYABLE_FAILURE_CODES = frozenset(
    {
        AssistantFailureCode.UPSTREAM_UNAVAILABLE,
        AssistantFailureCode.UPSTREAM_TIMEOUT,
        AssistantFailureCode.MODEL_OUTPUT_INVALID,
    }
)


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
    AssistantFailureCode.INTERNAL_ERROR: RootFailurePresentation(
        "处理失败",
        "处理失败，本次没有写入客户活动，请联系管理员。",
    ),
}


def is_root_failure_code(value: object) -> bool:
    return isinstance(value, str) and value in AssistantFailureCode.__members__.values()


def root_failure_code(value: object) -> AssistantFailureCode:
    if isinstance(value, AssistantFailureCode):
        return value
    if is_root_failure_code(value):
        return AssistantFailureCode(str(value))
    return AssistantFailureCode.INTERNAL_ERROR


def root_failure_presentation(code: AssistantFailureCode) -> RootFailurePresentation:
    return _PRESENTATIONS[code]


def root_failure_retryable(code: AssistantFailureCode) -> bool:
    return code in ROOT_RETRYABLE_FAILURE_CODES


ORGANIZE_FAILURE_MESSAGE = "内容已保存，但整理未完成，尚未写入客户活动"
_EXPLICIT_ORGANIZE_CODES = frozenset(
    {
        AssistantFailureCode.CONFIGURATION_ERROR,
        AssistantFailureCode.UPSTREAM_UNAVAILABLE,
        AssistantFailureCode.UPSTREAM_TIMEOUT,
        AssistantFailureCode.MODEL_OUTPUT_INVALID,
    }
)
_OUTPUT_ERROR_NAMES = frozenset({"ValidationError", "ActionContractError", "TemporalContractError"})
_CAUSE_LIMIT = 500


class AssistantStageFailure(Exception):
    """Technical organize or quality failure already flushed onto the task.

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
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.stage = stage
        self.retryable = retryable
        self.user_message = user_message
        self.task_public_id = task_public_id


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


def classify_organize_failure(exc: BaseException) -> tuple[AssistantFailureCode, bool]:
    """Map a structuring or quality exception to a stable code.

    A wrapper that only carries the default internal code must not hide a timeout
    or an output-validation error further down the cause chain.
    """

    chain = _chain(exc)
    for item in chain:
        code = _explicit_code(item)
        if code is not None:
            return code, root_failure_retryable(code)
    if any(isinstance(item, TimeoutError) for item in chain):
        return AssistantFailureCode.UPSTREAM_TIMEOUT, True
    if any(isinstance(item, (ValueError, TypeError)) or type(item).__name__ in _OUTPUT_ERROR_NAMES for item in chain):
        return AssistantFailureCode.MODEL_OUTPUT_INVALID, True
    for item in chain:
        code = getattr(item, "code", None)
        if isinstance(code, AssistantFailureCode):
            return code, root_failure_retryable(code)
        if is_root_failure_code(code):
            resolved = AssistantFailureCode(str(code))
            return resolved, root_failure_retryable(resolved)
    return AssistantFailureCode.INTERNAL_ERROR, False


def failure_cause(exc: BaseException) -> str:
    root = exc
    while root.__cause__ is not None:
        root = root.__cause__
    cause = f"{type(root).__name__}: {root}"
    if root is not exc:
        cause = f"{type(exc).__name__}: {exc} ({cause})"
    return cause[:_CAUSE_LIMIT]
