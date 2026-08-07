"""LLM-backed semantic suggestion for follow-up task reconciliation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.crud.ai_config import ai_config_crud
from app.crud.sales_commitment import follow_up_task_llm_matcher_run_crud
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTaskLLMMatcherRunStatus
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.follow_up_task_reconciliation_evaluation_service import (
    AUTO_TRANSITION_DECISIONS,
    DEFAULT_AUTO_CONFIDENCE_THRESHOLD,
    FOLLOW_UP_TASK_RECONCILIATION_DECISIONS,
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationEvaluationCase,
    FollowUpTaskReconciliationEvaluationResult,
    follow_up_task_reconciliation_evaluation_service,
)
from app.services.task_reconciliation_service import (
    TaskReconciliationCandidate,
    TaskReconciliationCandidateSet,
    task_reconciliation_service,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.orm import Session


ReconciliationDecisionLiteral = Literal[
    "COMPLETE",
    "DELAY",
    "CANCEL",
    "KEEP_OPEN",
    "UNRELATED",
    "ASK_CONFIRMATION",
]


class TaskReconciliationSemanticOutput(BaseModel):
    """Structured output contract returned by the LLM semantic matcher."""

    model_config = ConfigDict(extra="forbid")

    decision: ReconciliationDecisionLiteral
    confidence: float = Field(ge=0, le=1)
    task_public_id: str | None = None
    candidate_public_ids: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    proposed_due_at: str | None = None
    forbid_auto_reasons: list[str] = Field(default_factory=list)
    evidence_terms: list[str] = Field(default_factory=list)
    referenced_source_public_ids: list[str] = Field(default_factory=list)
    state_mutation_requested: bool = False

    @field_validator("task_public_id", mode="before")
    @classmethod
    def trim_optional_public_id(cls, value: object) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("candidate_public_ids", "forbid_auto_reasons", "evidence_terms", "referenced_source_public_ids")
    @classmethod
    def trim_string_list(cls, values: list[object]) -> list[str]:
        return [str(value).strip() for value in values if str(value).strip()]

    @model_validator(mode="after")
    def enforce_reconciliation_contract(self) -> TaskReconciliationSemanticOutput:
        if self.task_public_id and not self.task_public_id.startswith("fut_"):
            raise ValueError("task_public_id must be a follow-up task public_id")
        invalid_candidate_ids = [
            candidate_public_id
            for candidate_public_id in self.candidate_public_ids
            if not candidate_public_id.startswith("fut_")
        ]
        if invalid_candidate_ids:
            raise ValueError("candidate_public_ids must contain only follow-up task public_ids")
        if self.decision in AUTO_TRANSITION_DECISIONS and not self.task_public_id:
            raise ValueError("auto transition decision requires task_public_id")
        if self.decision == "DELAY" and not self.proposed_due_at:
            raise ValueError("DELAY requires proposed_due_at")
        if self.decision == "ASK_CONFIRMATION":
            self.needs_confirmation = True
        return self


class AIConfigLike(Protocol):
    api_host: str
    model_name: str
    temperature: float | None


class AIConfigCrudProtocol(Protocol):
    def get_config(self, db: Session, team_id: int) -> AIConfigLike | None: ...

    def get_decrypted_api_key(self, db: Session, team_id: int) -> str | None: ...


class TaskReconciliationCandidateServiceProtocol(Protocol):
    def list_candidates_for_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        include_cross_owner: bool = False,
    ) -> TaskReconciliationCandidateSet: ...


class FollowUpTaskReconciliationEvaluationServiceProtocol(Protocol):
    def evaluate_case(
        self,
        case: FollowUpTaskReconciliationEvaluationCase,
    ) -> FollowUpTaskReconciliationEvaluationResult: ...


@dataclass(frozen=True)
class TaskReconciliationSemanticMatchResult:
    """Auditable semantic reconciliation suggestion with safety metadata."""

    decision: FollowUpTaskReconciliationDecision
    candidate_set: TaskReconciliationCandidateSet
    source: str
    evaluation_failures: tuple[str, ...] = ()
    referenced_source_public_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": {
                "decision": self.decision.decision,
                "task_public_id": self.decision.task_public_id,
                "candidate_public_ids": list(self.decision.candidate_public_ids),
                "confidence": self.decision.confidence,
                "needs_confirmation": self.decision.needs_confirmation,
                "proposed_due_at": self.decision.proposed_due_at,
                "forbid_auto_reasons": list(self.decision.forbid_auto_reasons),
                "evidence_terms": list(self.decision.evidence_terms),
                "state_mutation_requested": self.decision.state_mutation_requested,
            },
            "candidate_set": self.candidate_set.to_dict(),
            "source": self.source,
            "evaluation_failures": list(self.evaluation_failures),
            "referenced_source_public_ids": list(self.referenced_source_public_ids),
        }


class TaskReconciliationSemanticMatcher:
    """Produces read-only LLM reconciliation suggestions for follow-up tasks."""

    def __init__(
        self,
        *,
        runtime: AgentLangChainRuntime | None = None,
        config_crud: AIConfigCrudProtocol = ai_config_crud,
        candidate_service: TaskReconciliationCandidateServiceProtocol = task_reconciliation_service,
        evaluation_service: FollowUpTaskReconciliationEvaluationServiceProtocol = (
            follow_up_task_reconciliation_evaluation_service
        ),
        matcher_run_crud: Any = follow_up_task_llm_matcher_run_crud,
        auto_confidence_threshold: float = DEFAULT_AUTO_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.runtime = runtime or AgentLangChainRuntime()
        self.config_crud = config_crud
        self.candidate_service = candidate_service
        self.evaluation_service = evaluation_service
        self.matcher_run_crud = matcher_run_crud
        self.auto_confidence_threshold = auto_confidence_threshold

    async def match_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        include_cross_owner: bool = False,
    ) -> TaskReconciliationSemanticMatchResult:
        activity = (
            db.query(CustomerActivity)
            .filter(CustomerActivity.team_id == team_id, CustomerActivity.id == activity_id)
            .first()
        )
        if activity is None:
            raise ValueError("客户活动不存在")

        candidate_set = self.candidate_service.list_candidates_for_activity(
            db,
            team_id=team_id,
            activity_id=activity_id,
            include_cross_owner=include_cross_owner,
        )
        return await self.match_candidates(
            db,
            team_id=team_id,
            activity_context=self._activity_context(activity),
            candidate_set=candidate_set,
        )

    async def match_candidates(
        self,
        db: Session,
        *,
        team_id: int,
        activity_context: Mapping[str, Any],
        candidate_set: TaskReconciliationCandidateSet,
    ) -> TaskReconciliationSemanticMatchResult:
        started_at = business_now()
        started_monotonic = perf_counter()
        activity_owner_id = str(activity_context.get("owner_id") or "")
        source_activity_id = self._optional_int(activity_context.get("activity_id"))
        source_public_id = self._optional_str(activity_context.get("public_id"))
        reconciliation_run_public_id = candidate_set.run_public_id

        if not candidate_set.items:
            result = self._safe_result(
                candidate_set,
                activity_owner_id=activity_owner_id,
                reason="NO_OPEN_CANDIDATES",
                decision="UNRELATED",
                confidence=1.0,
            )
            self._record_match_result(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                result=result,
                status=FollowUpTaskLLMMatcherRunStatus.SKIPPED,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            return result

        config = self.config_crud.get_config(db, team_id)
        if not config:
            result = self._safe_result(
                candidate_set,
                activity_owner_id=activity_owner_id,
                reason="AI_CONFIG_MISSING",
            )
            self._record_match_result(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                result=result,
                status=FollowUpTaskLLMMatcherRunStatus.SKIPPED,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            return result
        api_key = self.config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            result = self._safe_result(
                candidate_set,
                activity_owner_id=activity_owner_id,
                reason="AI_API_KEY_MISSING",
            )
            self._record_match_result(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                result=result,
                status=FollowUpTaskLLMMatcherRunStatus.SKIPPED,
                model_name=config.model_name,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            return result

        try:
            output = await self.runtime.ainvoke_structured(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                temperature=min(float(config.temperature or 0.1), 0.2),
                system_prompt=self._system_prompt(),
                user_prompt=self._user_prompt(activity_context, candidate_set),
                response_model=TaskReconciliationSemanticOutput,
                structured_output_strategy="tool",
                error_prefix="跟进任务 reconciliation structured output",
            )
        except (AgentLangChainStructuredOutputError, RuntimeError, ValueError) as exc:
            self._record_schema_error(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                candidate_public_ids=[candidate.public_id for candidate in candidate_set.items],
                error=exc,
                model_name=config.model_name,
                structured_output_strategy="tool",
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            return self._safe_result(
                candidate_set,
                activity_owner_id=activity_owner_id,
                reason="STRUCTURED_OUTPUT_FAILED",
                evidence_terms=(str(exc)[:160],),
            )
        if output is None:
            result = self._safe_result(
                candidate_set,
                activity_owner_id=activity_owner_id,
                reason="LLM_UNAVAILABLE",
            )
            self._record_match_result(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                result=result,
                status=FollowUpTaskLLMMatcherRunStatus.FAILED,
                model_name=config.model_name,
                structured_output_strategy="tool",
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            return result

        result = self._normalize_output(
            output,
            candidate_set,
            activity_context=activity_context,
            activity_owner_id=activity_owner_id,
        )
        self._record_match_result(
            db,
            team_id=team_id,
            owner_id=activity_owner_id,
            source_activity_id=source_activity_id,
            source_public_id=source_public_id,
            reconciliation_run_public_id=reconciliation_run_public_id,
            result=result,
            model_name=config.model_name,
            structured_output_strategy="tool",
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
        return result

    def _normalize_output(
        self,
        output: TaskReconciliationSemanticOutput,
        candidate_set: TaskReconciliationCandidateSet,
        *,
        activity_context: Mapping[str, Any],
        activity_owner_id: str,
    ) -> TaskReconciliationSemanticMatchResult:
        candidates_by_id = {candidate.public_id: candidate for candidate in candidate_set.items}
        selected = candidates_by_id.get(output.task_public_id or "")
        candidate_public_ids = tuple(candidate.public_id for candidate in candidate_set.items)
        decision = output.decision
        task_public_id = output.task_public_id if output.task_public_id in candidates_by_id else None
        needs_confirmation = output.needs_confirmation
        forbid_auto_reasons = list(dict.fromkeys(output.forbid_auto_reasons))
        evidence_terms = tuple(dict.fromkeys(output.evidence_terms))

        if output.task_public_id and task_public_id is None:
            decision = "KEEP_OPEN"
            forbid_auto_reasons.append("UNKNOWN_TASK_CANDIDATE")
        elif decision in AUTO_TRANSITION_DECISIONS:
            if selected and not selected.auto_transition_eligible:
                decision = "ASK_CONFIRMATION"
                needs_confirmation = True
                forbid_auto_reasons.append(selected.confirmation_required_reason or "CROSS_OWNER")
            if output.confidence < self.auto_confidence_threshold:
                decision = "ASK_CONFIRMATION"
                needs_confirmation = True
                forbid_auto_reasons.append("LOW_CONFIDENCE")
            if not evidence_terms:
                decision = "ASK_CONFIRMATION"
                needs_confirmation = True
                forbid_auto_reasons.append("MISSING_EVIDENCE")
            elif not self._evidence_terms_are_grounded(
                evidence_terms,
                activity_context=activity_context,
                candidate_set=candidate_set,
            ):
                decision = "ASK_CONFIRMATION"
                needs_confirmation = True
                forbid_auto_reasons.append("UNGROUNDED_EVIDENCE")

        if output.state_mutation_requested:
            forbid_auto_reasons.append("STATE_MUTATION_FORBIDDEN")
            if decision in AUTO_TRANSITION_DECISIONS:
                decision = "ASK_CONFIRMATION"
                needs_confirmation = True

        if decision == "ASK_CONFIRMATION":
            needs_confirmation = True
        if decision == "UNRELATED":
            task_public_id = None

        normalized = FollowUpTaskReconciliationDecision(
            decision=decision,
            confidence=output.confidence,
            task_public_id=task_public_id,
            candidate_public_ids=candidate_public_ids,
            needs_confirmation=needs_confirmation,
            proposed_due_at=output.proposed_due_at,
            forbid_auto_reasons=tuple(dict.fromkeys(forbid_auto_reasons)),
            evidence_terms=evidence_terms,
            state_mutation_requested=False,
        )
        evaluation = self.evaluation_service.evaluate_case(
            self._evaluation_case(normalized, candidate_set, activity_owner_id=activity_owner_id)
        )
        if evaluation.passed:
            return TaskReconciliationSemanticMatchResult(
                decision=normalized,
                candidate_set=candidate_set,
                source="langchain_structured_output",
                referenced_source_public_ids=tuple(output.referenced_source_public_ids),
            )

        fallback = self._safe_result(
            candidate_set,
            activity_owner_id=activity_owner_id,
            reason="CONTRACT_EVALUATION_FAILED",
            task_public_id=normalized.task_public_id,
            evidence_terms=tuple(evaluation.failures),
            force_confirmation=bool(normalized.task_public_id),
        )
        return TaskReconciliationSemanticMatchResult(
            decision=fallback.decision,
            candidate_set=candidate_set,
            source="guardrail_fallback",
            evaluation_failures=tuple(evaluation.failures),
            referenced_source_public_ids=tuple(output.referenced_source_public_ids),
        )

    def _safe_result(
        self,
        candidate_set: TaskReconciliationCandidateSet,
        *,
        activity_owner_id: str,
        reason: str,
        decision: str = "KEEP_OPEN",
        confidence: float = 0.0,
        task_public_id: str | None = None,
        evidence_terms: tuple[str, ...] = (),
        force_confirmation: bool = False,
    ) -> TaskReconciliationSemanticMatchResult:
        if decision not in FOLLOW_UP_TASK_RECONCILIATION_DECISIONS:
            decision = "KEEP_OPEN"
        if force_confirmation:
            decision = "ASK_CONFIRMATION"
        candidate_public_ids = tuple(candidate.public_id for candidate in candidate_set.items)
        normalized = FollowUpTaskReconciliationDecision(
            decision=decision,
            confidence=confidence,
            task_public_id=task_public_id,
            candidate_public_ids=candidate_public_ids,
            needs_confirmation=decision == "ASK_CONFIRMATION",
            forbid_auto_reasons=(reason,),
            evidence_terms=evidence_terms,
            state_mutation_requested=False,
        )
        evaluation = self.evaluation_service.evaluate_case(
            self._evaluation_case(normalized, candidate_set, activity_owner_id=activity_owner_id)
        )
        return TaskReconciliationSemanticMatchResult(
            decision=normalized,
            candidate_set=candidate_set,
            source="safe_fallback",
            evaluation_failures=tuple(evaluation.failures),
        )

    def _evaluation_case(
        self,
        decision: FollowUpTaskReconciliationDecision,
        candidate_set: TaskReconciliationCandidateSet,
        *,
        activity_owner_id: str,
    ) -> FollowUpTaskReconciliationEvaluationCase:
        return FollowUpTaskReconciliationEvaluationCase(
            name="semantic_match_guardrail",
            activity_owner_id=activity_owner_id,
            task_owner_by_public_id={candidate.public_id: candidate.owner_id for candidate in candidate_set.items},
            result=decision,
            allowed_decisions=set(FOLLOW_UP_TASK_RECONCILIATION_DECISIONS),
            auto_confidence_threshold=self.auto_confidence_threshold,
        )

    def _system_prompt(self) -> str:
        return """你是 CRM 系统中的销售承诺 reconciliation Agent.

任务: 判断一条新的客户跟进记录, 是否和候选的开放跟进任务存在完成、延期、取消、继续保持或无关关系.

硬性边界:
- 你只输出结构化 JSON, 不输出 Markdown 或解释文字.
- 只能引用候选任务中的 public_id, 禁止输出数据库主键 id.
- 你不能要求或执行任何状态写入; state_mutation_requested 必须为 false.
- 跨 owner、证据不足、低置信、语义不确定时必须使用 ASK_CONFIRMATION 或 KEEP_OPEN。
- COMPLETE 表示新活动已经明确完成候选任务要确认的事项。
- DELAY 表示新活动明确把同一事项推迟到新的时间, 必须给 proposed_due_at.
- CANCEL 表示新活动明确说明该事项不再处理。
- KEEP_OPEN 表示相关但没有完成、延期或取消证据。
- UNRELATED 表示新活动和候选任务都无关。
- evidence_terms 必须列出来自新活动和候选任务的短证据词。"""

    def _user_prompt(
        self,
        activity_context: Mapping[str, Any],
        candidate_set: TaskReconciliationCandidateSet,
    ) -> str:
        payload = {
            "current_date": business_now().date().isoformat(),
            "current_activity": self._activity_prompt_context(activity_context),
            "candidate_tasks": [self._candidate_prompt_context(candidate) for candidate in candidate_set.items],
            "usage_policy": candidate_set.usage_policy,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _activity_prompt_context(self, activity_context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in activity_context.items()
            if key not in {"owner_id", "creator_id", "customer_id", "activity_id", "id"}
        }

    def _candidate_prompt_context(self, candidate: TaskReconciliationCandidate) -> dict[str, Any]:
        return {
            "public_id": candidate.public_id,
            "title": candidate.title,
            "description": candidate.description,
            "due_at": candidate.due_at,
            "due_at_text": candidate.due_at_text,
            "due_at_granularity": candidate.due_at_granularity,
            "due_at_timezone": candidate.due_at_timezone,
            "source_type": candidate.source_type,
            "source_public_id": candidate.source_public_id,
            "confidence": candidate.confidence,
            "candidate_reasons": list(candidate.candidate_reasons),
            "owner_relation": "same_owner"
            if candidate.auto_transition_eligible
            else "cross_owner_confirmation_only",
            "auto_transition_eligible": candidate.auto_transition_eligible,
            "confirmation_required_reason": candidate.confirmation_required_reason,
        }

    def _evidence_terms_are_grounded(
        self,
        evidence_terms: tuple[str, ...],
        *,
        activity_context: Mapping[str, Any],
        candidate_set: TaskReconciliationCandidateSet,
    ) -> bool:
        searchable_text = "\n".join(
            str(value)
            for value in [
                activity_context.get("source_content"),
                activity_context.get("content_json"),
                activity_context.get("summary"),
                activity_context.get("next_action"),
                *[
                    part
                    for candidate in candidate_set.items
                    for part in (
                        candidate.title,
                        candidate.description,
                        candidate.due_at_text,
                    )
                ],
            ]
            if value
        ).lower()
        return all(term.lower() in searchable_text for term in evidence_terms)

    def _activity_context(self, activity: CustomerActivity) -> dict[str, Any]:
        return {
            "activity_id": activity.id,
            "customer_id": activity.customer_id,
            "owner_id": activity.owner_id,
            "creator_id": activity.creator_id,
            "activity_kind": activity.activity_kind,
            "title": activity.title,
            "source_content": activity.source_content,
            "content_json": activity.content_json,
            "summary": activity.summary,
            "next_action": activity.next_action,
            "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
            "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
        }

    def _record_match_result(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        source_activity_id: int | None,
        source_public_id: str | None,
        reconciliation_run_public_id: str | None,
        result: TaskReconciliationSemanticMatchResult,
        status: str | None = None,
        model_name: str | None = None,
        structured_output_strategy: str | None = None,
        started_at: Any = None,
        started_monotonic: float | None = None,
    ) -> None:
        self.matcher_run_crud.record_match_result(
            db,
            team_id=team_id,
            owner_id=owner_id or None,
            source_activity_id=source_activity_id,
            source_public_id=source_public_id,
            reconciliation_run_public_id=reconciliation_run_public_id,
            result=result,
            status=status,
            model_name=model_name,
            structured_output_strategy=structured_output_strategy,
            duration_ms=self._duration_ms(started_monotonic),
            started_at=started_at,
        )

    def _record_schema_error(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        source_activity_id: int | None,
        source_public_id: str | None,
        reconciliation_run_public_id: str | None,
        candidate_public_ids: list[str],
        error: Exception,
        model_name: str | None,
        structured_output_strategy: str,
        started_at: Any,
        started_monotonic: float,
    ) -> None:
        self.matcher_run_crud.record_schema_error(
            db,
            team_id=team_id,
            owner_id=owner_id or None,
            source_activity_id=source_activity_id,
            source_public_id=source_public_id,
            reconciliation_run_public_id=reconciliation_run_public_id,
            candidate_public_ids=candidate_public_ids,
            error=error,
            model_name=model_name,
            structured_output_strategy=structured_output_strategy,
            duration_ms=self._duration_ms(started_monotonic),
            started_at=started_at,
        )

    def _duration_ms(self, started_monotonic: float | None) -> int | None:
        if started_monotonic is None:
            return None
        return int((perf_counter() - started_monotonic) * 1000)

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


task_reconciliation_semantic_matcher = TaskReconciliationSemanticMatcher()
