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
    FollowUpTaskReconciliationTaskDecision,
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
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.crud.sales_commitment import FollowUpTaskLLMMatcherRunCRUD


ReconciliationDecisionLiteral = Literal[
    "COMPLETE",
    "POSTPONE",
    "CANCEL",
    "KEEP_OPEN",
    "UNRELATED",
    "ASK_CONFIRMATION",
]


class TaskReconciliationSemanticOutput(BaseModel):
    """Structured output contract returned by the LLM semantic matcher."""

    model_config = ConfigDict(extra="forbid")

    referenced_source_public_ids: list[str] = Field(default_factory=list)
    tasks: list[TaskReconciliationTaskOutput] = Field(min_length=1)

    @field_validator("referenced_source_public_ids")
    @classmethod
    def trim_string_list(cls, values: list[object]) -> list[str]:
        return [str(value).strip() for value in values if str(value).strip()]

    @model_validator(mode="after")
    def reject_duplicate_task_decisions(self) -> TaskReconciliationSemanticOutput:
        task_public_ids = [task.task_public_id for task in self.tasks]
        duplicate_ids = sorted(
            task_public_id
            for task_public_id in set(task_public_ids)
            if task_public_ids.count(task_public_id) > 1
        )
        if duplicate_ids:
            raise ValueError(f"duplicate task_public_id: {', '.join(duplicate_ids)}")
        return self


class TaskReconciliationTaskOutput(BaseModel):
    """Structured decision for one candidate task in a reconciliation batch."""

    model_config = ConfigDict(extra="forbid")

    task_public_id: str
    decision: ReconciliationDecisionLiteral
    confidence: float = Field(ge=0, le=1)
    needs_confirmation: bool = False
    proposed_due_at: str | None = None
    forbid_auto_reasons: list[str] = Field(default_factory=list)
    evidence_terms: list[str] = Field(default_factory=list)
    state_mutation_requested: bool = False

    @field_validator("task_public_id", mode="before")
    @classmethod
    def trim_task_public_id(cls, value: object) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("task_public_id is required")
        return value

    @field_validator("forbid_auto_reasons", "evidence_terms")
    @classmethod
    def trim_task_string_list(cls, values: list[object]) -> list[str]:
        return [str(value).strip() for value in values if str(value).strip()]

    @model_validator(mode="after")
    def enforce_task_contract(self) -> TaskReconciliationTaskOutput:
        if not self.task_public_id.startswith("fut_"):
            raise ValueError("task_public_id must be a follow-up task public_id")
        if self.decision == "POSTPONE" and not self.proposed_due_at:
            raise ValueError("POSTPONE requires proposed_due_at")
        if self.decision == "ASK_CONFIRMATION":
            self.needs_confirmation = True
        return self


class TaskReconciliationUnavailableError(RuntimeError):
    """Raised when historical-task reconciliation cannot produce a valid decision."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


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
                "candidate_public_ids": list(self.decision.candidate_public_ids),
                "task_decisions": self.decision.task_decisions_to_dict(),
                "empty_outcome": (
                    {
                        "reason": self.decision.empty_reason,
                        "confidence": self.decision.empty_confidence,
                        "evidence_terms": list(self.decision.empty_evidence_terms),
                    }
                    if not self.decision.task_decisions
                    else None
                ),
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
        matcher_run_crud: FollowUpTaskLLMMatcherRunCRUD = follow_up_task_llm_matcher_run_crud,
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
            result = self._empty_result(
                candidate_set,
                reason="NO_OPEN_CANDIDATES",
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
            self._record_unavailable(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                candidate_public_ids=[candidate.public_id for candidate in candidate_set.items],
                reason_code="AI_CONFIG_MISSING",
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            raise TaskReconciliationUnavailableError("AI_CONFIG_MISSING")
        api_key = self.config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            self._record_unavailable(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                candidate_public_ids=[candidate.public_id for candidate in candidate_set.items],
                reason_code="AI_API_KEY_MISSING",
                model_name=config.model_name,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            raise TaskReconciliationUnavailableError("AI_API_KEY_MISSING")

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
            raise TaskReconciliationUnavailableError("STRUCTURED_OUTPUT_FAILED") from exc
        if output is None:
            self._record_unavailable(
                db,
                team_id=team_id,
                owner_id=activity_owner_id,
                source_activity_id=source_activity_id,
                source_public_id=source_public_id,
                reconciliation_run_public_id=reconciliation_run_public_id,
                candidate_public_ids=[candidate.public_id for candidate in candidate_set.items],
                reason_code="LLM_UNAVAILABLE",
                model_name=config.model_name,
                structured_output_strategy="tool",
                started_at=started_at,
                started_monotonic=started_monotonic,
            )
            raise TaskReconciliationUnavailableError("LLM_UNAVAILABLE")

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
        """Normalize one structured decision for every candidate task."""
        candidates_by_id = {candidate.public_id: candidate for candidate in candidate_set.items}
        candidate_public_ids = tuple(candidate.public_id for candidate in candidate_set.items)
        task_outputs_by_id: dict[str, TaskReconciliationTaskOutput] = {}
        unknown_task_ids: list[str] = []
        for task_output in output.tasks:
            if task_output.task_public_id not in candidates_by_id:
                unknown_task_ids.append(task_output.task_public_id)
                continue
            task_outputs_by_id.setdefault(task_output.task_public_id, task_output)

        task_decisions: list[FollowUpTaskReconciliationTaskDecision] = []
        evaluation_failures: list[str] = []
        for candidate in candidate_set.items:
            task_output = task_outputs_by_id.get(candidate.public_id)
            if task_output is None:
                task_decisions.append(
                    FollowUpTaskReconciliationTaskDecision(
                        decision="ASK_CONFIRMATION",
                        confidence=0.0,
                        task_public_id=candidate.public_id,
                        needs_confirmation=True,
                        forbid_auto_reasons=("TASK_NOT_ADDRESSED_BY_MODEL",),
                    )
                )
                continue

            task_decision = self._normalize_task_output(
                task_output,
                candidate=candidate,
                activity_context=activity_context,
            )
            single_task_result = FollowUpTaskReconciliationDecision(
                candidate_public_ids=(candidate.public_id,),
                task_decisions=(task_decision,),
            )
            evaluation = self.evaluation_service.evaluate_case(
                self._evaluation_case(single_task_result, candidate_set, activity_owner_id=activity_owner_id)
            )
            if not evaluation.passed:
                evaluation_failures.extend(
                    f"{candidate.public_id}:{failure}" for failure in evaluation.failures
                )
                task_decision = FollowUpTaskReconciliationTaskDecision(
                    decision="ASK_CONFIRMATION",
                    confidence=task_decision.confidence,
                    task_public_id=task_decision.task_public_id,
                    needs_confirmation=True,
                    proposed_due_at=task_decision.proposed_due_at,
                    forbid_auto_reasons=tuple(
                        dict.fromkeys((*task_decision.forbid_auto_reasons, "CONTRACT_EVALUATION_FAILED"))
                    ),
                    evidence_terms=task_decision.evidence_terms,
                    state_mutation_requested=False,
                )
            task_decisions.append(task_decision)

        if unknown_task_ids:
            evaluation_failures.extend(
                f"unknown_task_candidate:{task_public_id}" for task_public_id in unknown_task_ids
            )

        task_decisions_tuple = tuple(task_decisions)
        return TaskReconciliationSemanticMatchResult(
            decision=self._batch_decision(
                task_decisions_tuple,
                candidate_public_ids=candidate_public_ids,
            ),
            candidate_set=candidate_set,
            source="langchain_structured_output",
            evaluation_failures=tuple(evaluation_failures),
            referenced_source_public_ids=tuple(output.referenced_source_public_ids),
        )

    def _normalize_task_output(
        self,
        output: TaskReconciliationTaskOutput,
        *,
        candidate: TaskReconciliationCandidate | None,
        activity_context: Mapping[str, Any],
    ) -> FollowUpTaskReconciliationTaskDecision:
        decision = output.decision
        needs_confirmation = output.needs_confirmation
        reasons = list(dict.fromkeys(output.forbid_auto_reasons))
        evidence_terms = tuple(dict.fromkeys(output.evidence_terms))

        if decision in AUTO_TRANSITION_DECISIONS:
            if candidate is None:
                decision = "KEEP_OPEN"
                reasons.append("UNKNOWN_TASK_CANDIDATE")
            elif not candidate.auto_transition_eligible:
                needs_confirmation = True
                reasons.append(candidate.confirmation_required_reason or "CROSS_OWNER")
            if output.confidence < self.auto_confidence_threshold:
                needs_confirmation = True
                reasons.append("LOW_CONFIDENCE")
            if not evidence_terms:
                needs_confirmation = True
                reasons.append("MISSING_EVIDENCE")
            elif not self._evidence_terms_are_grounded(
                evidence_terms,
                activity_context=activity_context,
                candidate=candidate,
            ):
                needs_confirmation = True
                reasons.append("UNGROUNDED_EVIDENCE")

        if decision == "KEEP_OPEN":
            needs_confirmation = True
            reasons.append("RELATED_TASK_REQUIRES_CONFIRMATION")

        if decision in {"KEEP_OPEN", "UNRELATED"} and output.confidence < self.auto_confidence_threshold:
            decision = "ASK_CONFIRMATION"
            needs_confirmation = True
            reasons.append("LOW_CONFIDENCE")

        if output.state_mutation_requested:
            reasons.append("STATE_MUTATION_FORBIDDEN")
            if decision in AUTO_TRANSITION_DECISIONS:
                needs_confirmation = True

        if decision == "ASK_CONFIRMATION":
            needs_confirmation = True

        return FollowUpTaskReconciliationTaskDecision(
            decision=decision,
            confidence=output.confidence,
            task_public_id=output.task_public_id,
            needs_confirmation=needs_confirmation,
            proposed_due_at=output.proposed_due_at,
            forbid_auto_reasons=tuple(dict.fromkeys(reasons)),
            evidence_terms=evidence_terms,
            state_mutation_requested=False,
        )

    def _empty_result(
        self,
        candidate_set: TaskReconciliationCandidateSet,
        *,
        reason: str,
        confidence: float = 0.0,
        evidence_terms: tuple[str, ...] = (),
    ) -> TaskReconciliationSemanticMatchResult:
        normalized = FollowUpTaskReconciliationDecision(
            candidate_public_ids=(),
            task_decisions=(),
            empty_reason=reason,
            empty_confidence=confidence,
            empty_evidence_terms=evidence_terms,
        )
        return TaskReconciliationSemanticMatchResult(
            decision=normalized,
            candidate_set=candidate_set,
            source="deterministic_empty",
        )

    @staticmethod
    def _batch_decision(
        task_decisions: tuple[FollowUpTaskReconciliationTaskDecision, ...],
        *,
        candidate_public_ids: tuple[str, ...],
    ) -> FollowUpTaskReconciliationDecision:
        return FollowUpTaskReconciliationDecision(
            candidate_public_ids=candidate_public_ids,
            task_decisions=task_decisions,
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
        return "\n".join(
            (
                "你是 CRM 系统中的历史跟进待办对账 Agent。",
                "",
                "任务: 对每一条历史 OPEN 待办，判断本次客户跟进是否已经履行了该待办要求销售执行的动作。",
                "",
                "核心领域语义:",
                "- 判断对象是历史待办要求销售执行的动作是否已履行，不是客户项目、立项、采购或 POC 是否最终结束。",
                "- 项目或客户事项是否最终结束不是 COMPLETE 的判断对象。",
                "- 例如历史待办是‘继续跟进立项流程’，本次已联系客户并取得立项进展，",
                "  即表示这一次跟进行为已履行，应判为 COMPLETE；项目仍在立项中不构成 KEEP_OPEN。",
                "- activity_execution_evidence 只描述本次已经发生的沟通和动作，",
                "  是判断历史待办是否履行的事实证据。",
                "- new_future_plan 表示本次跟进后新产生的未来待办。",
                "  即使它与历史待办文字相同或相近，也代表新一轮跟进。",
                "  不能据此把已履行的历史待办判为 KEEP_OPEN，也不能把新待办当作本轮候选任务。",
                "- 如果历史待办要求联系、询问、确认、跟进或了解进展，",
                "  只要 activity_execution_evidence 明确表明已实施该动作并取得反馈，就视为该历史动作已履行。",
                "- 只有 activity_execution_evidence 没有表明历史待办动作已执行时，",
                "  才可判为 KEEP_OPEN 或 ASK_CONFIRMATION。",
                "",
                "输出边界:",
                "- 你只输出结构化 JSON，不输出 Markdown 或解释文字。",
                "- 只能引用 historical_candidate_tasks 中的 public_id，禁止输出数据库主键 id。",
                "- 你不能要求或执行任何状态写入；state_mutation_requested 必须为 false。",
                "- 顶层只允许返回 referenced_source_public_ids 和 tasks，",
                "  不允许返回单任务 decision/task_public_id 等旧字段。",
                "- 你必须对每一个 historical_candidate_tasks 返回一个 tasks 项，不能只返回最相关的一项。",
                "- 跨 owner、证据不足、置信度低于 0.85 或语义不确定时，",
                "  必须标记 needs_confirmation=true；无法判断建议动作时使用 ASK_CONFIRMATION。",
                "- COMPLETE：activity_execution_evidence 已明确证明历史待办要求的销售动作已经执行。",
                "- POSTPONE：历史待办动作尚未执行，且本次记录明确将该历史动作延期到新时间；",
                "  必须给 proposed_due_at。不要把已执行动作后产生的 new_future_plan 判为 POSTPONE。",
                "- CANCEL：本次记录明确说明历史待办动作不再处理。",
                "- KEEP_OPEN：与历史待办相关，但没有历史动作已执行、延期或取消的证据；",
                "  必须 needs_confirmation=true。",
                "- UNRELATED：本次已发生动作与历史待办无关。",
                "- evidence_terms 必须同时包含 activity_execution_evidence 中的执行证据词",
                "  和历史候选任务中的目标动作词。",
                "- tasks 中每项只能引用一个历史候选任务 public_id。",
            )
        )

    def _user_prompt(
        self,
        activity_context: Mapping[str, Any],
        candidate_set: TaskReconciliationCandidateSet,
    ) -> str:
        payload = {
            "current_date": business_now().date().isoformat(),
            "activity_execution_evidence": self._activity_execution_prompt_context(activity_context),
            "new_future_plan": self._future_plan_prompt_context(activity_context),
            "historical_candidate_tasks": [
                self._candidate_prompt_context(candidate) for candidate in candidate_set.items
            ],
            "usage_policy": candidate_set.usage_policy,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _activity_execution_prompt_context(
        self,
        activity_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        excluded_keys = {
            "owner_id",
            "creator_id",
            "customer_id",
            "activity_id",
            "id",
            "next_action",
            "next_action_source",
            "next_follow_time",
            "next_follow_time_source",
        }
        return {key: value for key, value in activity_context.items() if key not in excluded_keys}

    def _future_plan_prompt_context(self, activity_context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "next_action": activity_context.get("next_action"),
            "next_follow_time": activity_context.get("next_follow_time"),
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
        candidate: TaskReconciliationCandidate | None,
    ) -> bool:
        if candidate is None:
            return False

        execution_text = "\n".join(
            str(value)
            for value in (
                activity_context.get("title"),
                activity_context.get("source_content"),
                activity_context.get("content_json"),
                activity_context.get("summary"),
            )
            if value
        ).lower()
        candidate_text = "\n".join(
            str(value)
            for value in (
                candidate.title,
                candidate.description,
                candidate.due_at_text,
            )
            if value
        ).lower()
        normalized_terms = tuple(term.lower() for term in evidence_terms)
        all_terms_are_grounded = all(
            term in execution_text or term in candidate_text for term in normalized_terms
        )
        has_execution_evidence = any(term in execution_text for term in normalized_terms)
        has_candidate_evidence = any(term in candidate_text for term in normalized_terms)
        return all_terms_are_grounded and has_execution_evidence and has_candidate_evidence

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
        started_at: datetime | None = None,
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
        started_at: datetime,
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

    def _record_unavailable(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        source_activity_id: int | None,
        source_public_id: str | None,
        reconciliation_run_public_id: str | None,
        candidate_public_ids: list[str],
        reason_code: str,
        model_name: str | None = None,
        structured_output_strategy: str | None = None,
        started_at: datetime,
        started_monotonic: float,
    ) -> None:
        self.matcher_run_crud.record_unavailable(
            db,
            team_id=team_id,
            owner_id=owner_id or None,
            source_activity_id=source_activity_id,
            source_public_id=source_public_id,
            reconciliation_run_public_id=reconciliation_run_public_id,
            candidate_public_ids=candidate_public_ids,
            reason_code=reason_code,
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
