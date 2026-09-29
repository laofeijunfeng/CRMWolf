"""Canonical follow-up and meeting quality gate before activity confirmation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import Field

from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport, team_model_credentials
from app.services.customer_activity_ai.rules import get_activity_evaluation_rubric
from app.services.customer_activity_ai.schemas import ActivityEvaluationResult, FollowUpContent, MeetingContent, PrincipleScore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ruff: noqa: RUF001

GAP_QUESTIONS = {
    "content": "这次沟通里客户明确反馈了什么？请用一两句话补充事实。",
    "next_action": "下一步是谁在什么时间做什么？",
}


class AssistantActivityScore(ActivityEvaluationResult):
    """Require the actual model score rather than accepting the domain default of zero."""

    score: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    principle_scores: dict[str, PrincipleScore] = Field(..., min_length=1)


@dataclass(frozen=True)
class QualityGateOutcome:
    passed: bool
    score: int
    reason: str
    gap_field: str | None
    question: str | None
    detail: dict[str, Any] | None = None


class QualityGate:
    """Score a typed activity against its own canonical rubric; failures are technical."""

    def __init__(self, evaluator: object | None = None) -> None:
        self.evaluator = evaluator or AssistantModelTransport()

    async def evaluate(
        self,
        db: Session,
        *,
        team_id: int,
        user_text: str,
        content: str,
        next_action: str,
        kind: str = "FOLLOW_UP",
        content_json: dict[str, Any] | None = None,
    ) -> QualityGateOutcome:
        if kind not in {"FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"}:
            raise AssistantLLMError("未知活动类型")
        meeting = kind != "FOLLOW_UP"
        rubric = get_activity_evaluation_rubric("meeting" if meeting else "follow_up")
        if content_json is None:
            payload = (
                MeetingContent(key_minutes=[content] if content else [], next_step_summary=next_action)
                if meeting else FollowUpContent(content=content, next_action=next_action)
            )
        else:
            try:
                payload = (MeetingContent if meeting else FollowUpContent).model_validate(content_json)
            except ValueError as exc:
                raise AssistantLLMError("活动正文结构无效") from exc
        host, key, name = team_model_credentials(db, team_id)
        try:
            result = await self.evaluator.ainvoke_structured(
                api_host=host,
                api_key=key,
                model=name,
                temperature=0.0,
                system_prompt=(
                    f"你是 CRM 客户活动质检员。按{rubric.title}评分。\n"
                    f"{rubric.principles}\n重点：{rubric.emphasis}\n"
                    "只根据用户原文与最终稿事实评分，不得编造。score 为 0-100 整数；"
                    "principle_scores 各维度给分与理由；低分只提一个最重要的补充问题。"
                ),
                user_prompt=json.dumps(
                    {
                        "activity_kind": kind,
                        "source_content": user_text,
                        "content_json": payload.model_dump(mode="json"),
                        "next_action": next_action,
                    },
                    ensure_ascii=False,
                ),
                response_model=AssistantActivityScore,
                error_prefix="客户活动评分",
            )
            if result is None:
                raise AssistantLLMError("客户活动评分：结构化输出不可用")
            result = AssistantActivityScore.model_validate(result)
        except AssistantLLMError:
            raise
        except (RuntimeError, TimeoutError, ValueError, TypeError) as exc:
            raise AssistantLLMError("客户活动评分：结构化输出无效") from exc
        detail = {
            **result.model_dump(mode="json"),
            "model_name": name,
            "structured_output": "json_object",
        }
        if result.is_valid:
            return QualityGateOutcome(True, result.score, result.reason, None, None, detail)
        gap_field = "next_action" if not next_action.strip() else "content"
        return QualityGateOutcome(
            False,
            result.score,
            result.reason,
            gap_field,
            result.supplement_question or GAP_QUESTIONS[gap_field],
            detail,
        )


class StubQualityGate:
    """Deterministic gate for tests and smoke runs."""

    def __init__(self, outcome: QualityGateOutcome) -> None:
        self.outcome = outcome

    async def evaluate(
        self,
        db: Session,
        *,
        team_id: int,
        user_text: str,
        content: str,
        next_action: str,
        kind: str = "FOLLOW_UP",
        content_json: dict[str, Any] | None = None,
    ) -> QualityGateOutcome:
        return self.outcome
