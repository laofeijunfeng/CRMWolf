"""Read-only observability for follow-up task transition safety."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.sales_commitment import (
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskEvent,
    FollowUpTaskLLMMatcherRun,
    FollowUpTaskReconciliationEvaluationRun,
    FollowUpTaskReconciliationRun,
    FollowUpTaskTransitionPolicyDecisionLog,
)

TRANSITION_EXECUTED_REASON = "RECONCILIATION_TRANSITION_PLAN_EXECUTED"
TRANSITION_ROLLBACK_REASON = "RECONCILIATION_TRANSITION_ROLLBACK"
EXECUTION_KIND_AUTOMATIC = "automatic"
EXECUTION_KIND_MANUAL_CONFIRMATION = "manual_confirmation"
UNKNOWN_BUCKET = "UNKNOWN"


@dataclass(frozen=True)
class FollowUpTaskTransitionObservabilitySummary:
    """Aggregated transition safety signals for one team and time window."""

    team_id: int
    start_at: datetime
    end_at: datetime
    owner_id: str | None
    transition_events: dict[str, Any]
    confirmation_cases: dict[str, Any]
    prompt_deliveries: dict[str, Any]
    policy_decisions: dict[str, Any]
    reconciliation_runs: dict[str, Any]
    llm_matcher_runs: dict[str, Any]
    evaluation_runs: dict[str, Any]
    metric_gaps: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "window": {
                "start_at": self.start_at.isoformat(),
                "end_at": self.end_at.isoformat(),
            },
            "owner_id": self.owner_id,
            "transition_events": self.transition_events,
            "confirmation_cases": self.confirmation_cases,
            "prompt_deliveries": self.prompt_deliveries,
            "policy_decisions": self.policy_decisions,
            "reconciliation_runs": self.reconciliation_runs,
            "llm_matcher_runs": self.llm_matcher_runs,
            "evaluation_runs": self.evaluation_runs,
            "metric_gaps": list(self.metric_gaps),
            "usage_policy": {
                "state_source": "mysql.sales_commitment_tables",
                "mutation": "forbidden",
                "id_boundary": "summary contains aggregate counts and public event references only",
            },
        }


class FollowUpTaskTransitionObservabilityService:
    """Builds operational summaries from persisted task/confirmation audit facts."""

    def summarize(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None = None,
    ) -> FollowUpTaskTransitionObservabilitySummary:
        events = self._transition_events(db, team_id=team_id, start_at=start_at, end_at=end_at, owner_id=owner_id)
        created_cases = self._created_confirmation_cases(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
        )
        resolved_cases = self._resolved_confirmation_cases(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
        )
        prompt_deliveries = self._prompt_deliveries(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
        )
        policy_decisions = self._policy_decisions(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
        )
        reconciliation_runs = self._reconciliation_runs(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
        )
        llm_matcher_runs = self._llm_matcher_runs(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
        )
        evaluation_runs = self._evaluation_runs(
            db,
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
        )
        return FollowUpTaskTransitionObservabilitySummary(
            team_id=team_id,
            start_at=start_at,
            end_at=end_at,
            owner_id=owner_id,
            transition_events=self._event_summary(events),
            confirmation_cases=self._confirmation_case_summary(created_cases, resolved_cases),
            prompt_deliveries=self._prompt_delivery_summary(prompt_deliveries),
            policy_decisions=self._policy_decision_summary(policy_decisions),
            reconciliation_runs=self._reconciliation_run_summary(reconciliation_runs),
            llm_matcher_runs=self._llm_matcher_run_summary(llm_matcher_runs),
            evaluation_runs=self._evaluation_run_summary(evaluation_runs),
            metric_gaps=self._metric_gaps(),
        )

    def _transition_events(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskEvent]:
        query = (
            db.query(FollowUpTaskEvent)
            .join(FollowUpTask, FollowUpTaskEvent.task_id == FollowUpTask.id)
            .filter(
                FollowUpTaskEvent.team_id == team_id,
                FollowUpTaskEvent.created_time >= start_at,
                FollowUpTaskEvent.created_time < end_at,
            )
        )
        if owner_id is not None:
            query = query.filter(FollowUpTask.owner_id == owner_id)
        return query.order_by(FollowUpTaskEvent.created_time.asc(), FollowUpTaskEvent.public_id.asc()).all()

    def _created_confirmation_cases(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskConfirmationCase]:
        query = db.query(FollowUpTaskConfirmationCase).filter(
            FollowUpTaskConfirmationCase.team_id == team_id,
            FollowUpTaskConfirmationCase.created_time >= start_at,
            FollowUpTaskConfirmationCase.created_time < end_at,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTaskConfirmationCase.owner_id == owner_id)
        return query.order_by(
            FollowUpTaskConfirmationCase.created_time.asc(),
            FollowUpTaskConfirmationCase.public_id.asc(),
        ).all()

    def _resolved_confirmation_cases(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskConfirmationCase]:
        query = db.query(FollowUpTaskConfirmationCase).filter(
            FollowUpTaskConfirmationCase.team_id == team_id,
            FollowUpTaskConfirmationCase.resolved_at.is_not(None),
            FollowUpTaskConfirmationCase.resolved_at >= start_at,
            FollowUpTaskConfirmationCase.resolved_at < end_at,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTaskConfirmationCase.owner_id == owner_id)
        return query.order_by(
            FollowUpTaskConfirmationCase.resolved_at.asc(),
            FollowUpTaskConfirmationCase.public_id.asc(),
        ).all()

    def _prompt_deliveries(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskConfirmationPromptDelivery]:
        query = db.query(FollowUpTaskConfirmationPromptDelivery).filter(
            FollowUpTaskConfirmationPromptDelivery.team_id == team_id,
            FollowUpTaskConfirmationPromptDelivery.prompted_at >= start_at,
            FollowUpTaskConfirmationPromptDelivery.prompted_at < end_at,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTaskConfirmationPromptDelivery.owner_id == owner_id)
        return query.order_by(
            FollowUpTaskConfirmationPromptDelivery.prompted_at.asc(),
            FollowUpTaskConfirmationPromptDelivery.public_id.asc(),
        ).all()

    def _policy_decisions(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskTransitionPolicyDecisionLog]:
        query = db.query(FollowUpTaskTransitionPolicyDecisionLog).filter(
            FollowUpTaskTransitionPolicyDecisionLog.team_id == team_id,
            FollowUpTaskTransitionPolicyDecisionLog.created_time >= start_at,
            FollowUpTaskTransitionPolicyDecisionLog.created_time < end_at,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTaskTransitionPolicyDecisionLog.owner_id == owner_id)
        return query.order_by(
            FollowUpTaskTransitionPolicyDecisionLog.created_time.asc(),
            FollowUpTaskTransitionPolicyDecisionLog.public_id.asc(),
        ).all()

    def _reconciliation_runs(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskReconciliationRun]:
        query = db.query(FollowUpTaskReconciliationRun).filter(
            FollowUpTaskReconciliationRun.team_id == team_id,
            FollowUpTaskReconciliationRun.created_time >= start_at,
            FollowUpTaskReconciliationRun.created_time < end_at,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTaskReconciliationRun.owner_id == owner_id)
        return query.order_by(
            FollowUpTaskReconciliationRun.created_time.asc(),
            FollowUpTaskReconciliationRun.public_id.asc(),
        ).all()

    def _llm_matcher_runs(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
        owner_id: str | None,
    ) -> list[FollowUpTaskLLMMatcherRun]:
        query = db.query(FollowUpTaskLLMMatcherRun).filter(
            FollowUpTaskLLMMatcherRun.team_id == team_id,
            FollowUpTaskLLMMatcherRun.created_time >= start_at,
            FollowUpTaskLLMMatcherRun.created_time < end_at,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTaskLLMMatcherRun.owner_id == owner_id)
        return query.order_by(
            FollowUpTaskLLMMatcherRun.created_time.asc(),
            FollowUpTaskLLMMatcherRun.public_id.asc(),
        ).all()

    def _evaluation_runs(
        self,
        db: Session,
        *,
        team_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[FollowUpTaskReconciliationEvaluationRun]:
        query = db.query(FollowUpTaskReconciliationEvaluationRun).filter(
            or_(
                FollowUpTaskReconciliationEvaluationRun.team_id == team_id,
                FollowUpTaskReconciliationEvaluationRun.team_id.is_(None),
            ),
            FollowUpTaskReconciliationEvaluationRun.created_time >= start_at,
            FollowUpTaskReconciliationEvaluationRun.created_time < end_at,
        )
        return query.order_by(
            FollowUpTaskReconciliationEvaluationRun.created_time.asc(),
            FollowUpTaskReconciliationEvaluationRun.public_id.asc(),
        ).all()

    def _event_summary(self, events: list[FollowUpTaskEvent]) -> dict[str, Any]:
        transition_events = [event for event in events if self._payload(event).get("reason") == TRANSITION_EXECUTED_REASON]
        automatic_events = [
            event
            for event in transition_events
            if self._payload(event).get("execution_kind") == EXECUTION_KIND_AUTOMATIC
        ]
        manual_confirmation_events = [
            event
            for event in transition_events
            if self._payload(event).get("execution_kind") == EXECUTION_KIND_MANUAL_CONFIRMATION
        ]
        rollback_events = [event for event in events if self._payload(event).get("reason") == TRANSITION_ROLLBACK_REASON]
        return {
            "total_events": len(events),
            "transition_events": len(transition_events),
            "automatic_transition_events": len(automatic_events),
            "manual_confirmation_transition_events": len(manual_confirmation_events),
            "rollback_events": len(rollback_events),
            "transition_ratio": self._ratio_parts(len(automatic_events), len(manual_confirmation_events)),
            "automatic_by_action": self._count_by_payload_value(automatic_events, "action"),
            "manual_confirmation_by_action": self._count_by_payload_value(manual_confirmation_events, "action"),
            "rollback_by_action": self._count_by_payload_value(rollback_events, "rolled_back_action"),
            "by_event_type": self._count_by_attr(events, "event_type"),
            "by_decision": self._count_by_payload_value(transition_events, "decision"),
            "by_plan_source": self._count_by_payload_value(transition_events, "plan_source"),
            "confidence": self._confidence_summary(transition_events),
            "rollback_event_public_ids": tuple(event.public_id for event in rollback_events),
        }

    def _confirmation_case_summary(
        self,
        created_cases: list[FollowUpTaskConfirmationCase],
        resolved_cases: list[FollowUpTaskConfirmationCase],
    ) -> dict[str, Any]:
        return {
            "created_cases": len(created_cases),
            "resolved_cases": len(resolved_cases),
            "created_by_status": self._count_by_attr(created_cases, "status"),
            "created_by_suggested_action": self._count_by_attr(created_cases, "suggested_action"),
            "resolved_by_action": self._count_by_attr(resolved_cases, "resolved_action"),
            "application_by_status": self._count_by_attr(resolved_cases, "application_status"),
            "application_skip_reasons": self._count_by_attr(resolved_cases, "application_skip_reason"),
            "unresolved_reply_total": sum(int(case.unresolved_reply_count or 0) for case in created_cases),
        }

    def _prompt_delivery_summary(
        self,
        deliveries: list[FollowUpTaskConfirmationPromptDelivery],
    ) -> dict[str, Any]:
        return {
            "total_deliveries": len(deliveries),
            "by_channel": self._count_by_attr(deliveries, "channel"),
            "by_provider": self._count_by_attr(deliveries, "provider"),
            "by_status": self._count_by_attr(deliveries, "status"),
        }

    def _policy_decision_summary(
        self,
        decisions: list[FollowUpTaskTransitionPolicyDecisionLog],
    ) -> dict[str, Any]:
        allowed_count = sum(1 for decision in decisions if decision.allowed)
        blocked_count = len(decisions) - allowed_count
        return {
            "total_decisions": len(decisions),
            "allowed_decisions": allowed_count,
            "blocked_decisions": blocked_count,
            "allow_ratio": self._allow_ratio_parts(allowed_count, blocked_count),
            "by_reason": self._count_by_attr(decisions, "reason"),
            "by_action": self._count_by_attr(decisions, "action"),
            "by_enabled": self._count_bool_attr(decisions, "enabled"),
            "by_owner_allowlist_configured": self._count_bool_attr(decisions, "owner_allowlist_configured"),
            "config_error_total": sum(len(self._json_list(decision.config_errors_json)) for decision in decisions),
        }

    def _reconciliation_run_summary(
        self,
        runs: list[FollowUpTaskReconciliationRun],
    ) -> dict[str, Any]:
        return {
            "total_runs": len(runs),
            "by_status": self._count_by_attr(runs, "status"),
            "by_skip_reason": self._count_by_attr(runs, "skip_reason"),
            "by_include_cross_owner": self._count_bool_attr(runs, "include_cross_owner"),
            "candidate_count_total": sum(int(run.candidate_count or 0) for run in runs),
            "duration_ms": self._number_attr_summary(runs, "duration_ms"),
        }

    def _llm_matcher_run_summary(
        self,
        runs: list[FollowUpTaskLLMMatcherRun],
    ) -> dict[str, Any]:
        return {
            "total_runs": len(runs),
            "by_status": self._count_by_attr(runs, "status"),
            "by_source": self._count_by_attr(runs, "source"),
            "by_decision": self._count_by_attr(runs, "decision"),
            "by_needs_confirmation": self._count_bool_attr(runs, "needs_confirmation"),
            "by_schema_error_type": self._count_by_attr(runs, "schema_error_type"),
            "by_model": self._count_by_attr(runs, "model_name"),
            "schema_error_total": sum(1 for run in runs if run.schema_error_type),
            "evaluation_failure_total": sum(len(self._json_list(run.evaluation_failures_json)) for run in runs),
            "confidence": self._number_attr_summary(runs, "confidence"),
            "duration_ms": self._number_attr_summary(runs, "duration_ms"),
        }

    def _evaluation_run_summary(
        self,
        runs: list[FollowUpTaskReconciliationEvaluationRun],
    ) -> dict[str, Any]:
        latest_run = max(runs, key=lambda run: run.created_time) if runs else None
        return {
            "total_runs": len(runs),
            "by_status": self._count_by_attr(runs, "status"),
            "by_ok": self._count_bool_attr(runs, "ok"),
            "quality_gate_failures": sum(1 for run in runs if not run.ok),
            "case_count_total": sum(int(run.total_cases or 0) for run in runs),
            "failed_case_count_total": sum(int(run.failed_cases or 0) for run in runs),
            "false_close_count_total": sum(int(run.false_close_count or 0) for run in runs),
            "false_delay_count_total": sum(int(run.false_delay_count or 0) for run in runs),
            "missed_confirmation_count_total": sum(int(run.missed_confirmation_count or 0) for run in runs),
            "over_confirmation_count_total": sum(int(run.over_confirmation_count or 0) for run in runs),
            "latest_run": self._latest_evaluation_run(latest_run),
        }

    def _metric_gaps(self) -> tuple[dict[str, str], ...]:
        return ()

    def _latest_evaluation_run(
        self,
        run: FollowUpTaskReconciliationEvaluationRun | None,
    ) -> dict[str, Any] | None:
        if run is None:
            return None
        return {
            "id": run.public_id,
            "public_id": run.public_id,
            "suite_name": run.suite_name,
            "status": run.status,
            "ok": run.ok,
            "total_cases": run.total_cases,
            "passed_cases": run.passed_cases,
            "failed_cases": run.failed_cases,
            "false_close_rate": run.false_close_rate,
            "false_delay_rate": run.false_delay_rate,
            "missed_confirmation_rate": run.missed_confirmation_rate,
            "over_confirmation_rate": run.over_confirmation_rate,
            "fixture_hash": run.fixture_hash,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }

    def _payload(self, event: FollowUpTaskEvent) -> dict[str, Any]:
        payload = event.payload_json
        if isinstance(payload, dict):
            return payload
        return {}

    def _count_by_attr(self, rows: list[Any], attr: str) -> dict[str, int]:
        return self._counter_dict(getattr(row, attr, None) for row in rows)

    def _count_by_payload_value(self, events: list[FollowUpTaskEvent], key: str) -> dict[str, int]:
        return self._counter_dict(self._payload(event).get(key) for event in events)

    def _counter_dict(self, values: Any) -> dict[str, int]:
        counter = Counter(str(value or UNKNOWN_BUCKET) for value in values)
        return dict(sorted(counter.items()))

    def _count_bool_attr(self, rows: list[Any], attr: str) -> dict[str, int]:
        return self._counter_dict(str(bool(getattr(row, attr, False))).lower() for row in rows)

    def _json_list(self, value: object) -> list[Any]:
        if isinstance(value, list):
            return value
        return []

    def _confidence_summary(self, events: list[FollowUpTaskEvent]) -> dict[str, float | int | None]:
        values = [self._payload(event).get("confidence") for event in events]
        confidence_values = [float(value) for value in values if isinstance(value, int | float)]
        if not confidence_values:
            return {"count": 0, "avg": None, "min": None, "max": None}
        return {
            "count": len(confidence_values),
            "avg": round(sum(confidence_values) / len(confidence_values), 4),
            "min": min(confidence_values),
            "max": max(confidence_values),
        }

    def _number_attr_summary(self, rows: list[Any], attr: str) -> dict[str, float | int | None]:
        values = [getattr(row, attr, None) for row in rows]
        number_values = [float(value) for value in values if isinstance(value, int | float)]
        if not number_values:
            return {"count": 0, "avg": None, "min": None, "max": None}
        return {
            "count": len(number_values),
            "avg": round(sum(number_values) / len(number_values), 4),
            "min": min(number_values),
            "max": max(number_values),
        }

    def _ratio_parts(self, automatic_count: int, manual_count: int) -> dict[str, float | int]:
        total = automatic_count + manual_count
        if total == 0:
            return {
                "automatic": 0,
                "manual_confirmation": 0,
                "automatic_percent": 0.0,
                "manual_confirmation_percent": 0.0,
            }
        return {
            "automatic": automatic_count,
            "manual_confirmation": manual_count,
            "automatic_percent": round(automatic_count / total, 4),
            "manual_confirmation_percent": round(manual_count / total, 4),
        }

    def _allow_ratio_parts(self, allowed_count: int, blocked_count: int) -> dict[str, float | int]:
        total = allowed_count + blocked_count
        if total == 0:
            return {
                "allowed": 0,
                "blocked": 0,
                "allowed_percent": 0.0,
                "blocked_percent": 0.0,
            }
        return {
            "allowed": allowed_count,
            "blocked": blocked_count,
            "allowed_percent": round(allowed_count / total, 4),
            "blocked_percent": round(blocked_count / total, 4),
        }


follow_up_task_transition_observability_service = FollowUpTaskTransitionObservabilityService()
