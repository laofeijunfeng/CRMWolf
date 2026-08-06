from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.agent.langchain_runtime import AgentLangChainStructuredOutputError
from app.services.task_reconciliation_semantic_matcher import (
    TaskReconciliationSemanticMatcher,
    TaskReconciliationSemanticOutput,
)
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet


class FakeConfigCrud:
    def __init__(self, *, has_config: bool = True, has_key: bool = True) -> None:
        self.has_config = has_config
        self.has_key = has_key

    def get_config(self, db, team_id: int):
        if not self.has_config:
            return None
        return SimpleNamespace(
            api_host="https://api.example.test",
            model_name="test-model",
            temperature=0.1,
        )

    def get_decrypted_api_key(self, db, team_id: int):
        return "test-key" if self.has_key else None


class FakeRuntime:
    def __init__(self, payload=None, exc: Exception | None = None) -> None:
        self.payload = payload
        self.exc = exc
        self.calls = []

    async def ainvoke_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        if self.payload is None:
            return None
        return kwargs["response_model"].model_validate(self.payload)


class FakeMatcherRunCrud:
    def __init__(self) -> None:
        self.match_results = []
        self.schema_errors = []

    def record_match_result(self, *args, **kwargs):
        self.match_results.append(kwargs)

    def record_schema_error(self, *args, **kwargs):
        self.schema_errors.append(kwargs)


def _matcher(
    runtime: FakeRuntime,
    *,
    config_crud: FakeConfigCrud | None = None,
    matcher_run_crud: FakeMatcherRunCrud | None = None,
) -> TaskReconciliationSemanticMatcher:
    return TaskReconciliationSemanticMatcher(
        runtime=runtime,
        config_crud=config_crud or FakeConfigCrud(),
        matcher_run_crud=matcher_run_crud or FakeMatcherRunCrud(),
    )


def _candidate(
    public_id: str = "fut_11111111111111111111111111111111",
    *,
    owner_id: str = "2",
    auto_transition_eligible: bool = True,
    confirmation_required_reason: str | None = None,
) -> TaskReconciliationCandidate:
    return TaskReconciliationCandidate(
        public_id=public_id,
        owner_id=owner_id,
        title="确认客户预算是否通过",
        description="客户说本周确认预算。",
        due_at="2026-08-05T10:00:00",
        due_at_text="本周三",
        due_at_granularity="DATETIME",
        due_at_timezone="Asia/Shanghai",
        source_type="CUSTOMER_ACTIVITY",
        source_public_id=None,
        confidence=0.91,
        candidate_reasons=("same_customer", "open_task", "due_window"),
        auto_transition_eligible=auto_transition_eligible,
        confirmation_required_reason=confirmation_required_reason,
    )


def _candidate_set(*items: TaskReconciliationCandidate) -> TaskReconciliationCandidateSet:
    return TaskReconciliationCandidateSet(
        items=list(items),
        total=len(items),
        filters={"activity_owner_id": "2"},
        usage_policy={
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        },
    )


def _activity_context() -> dict[str, object]:
    return {
        "owner_id": "2",
        "source_content": "今天已电话和王总确认, 客户预算已经通过。",
        "summary": "客户预算已通过。",
        "next_action": None,
        "occurred_at": "2026-08-06T10:00:00",
    }


@pytest.mark.asyncio
async def test_semantic_matcher_returns_same_owner_completion_suggestion():
    task = _candidate()
    runtime = FakeRuntime(
        {
            "decision": "COMPLETE",
            "task_public_id": task.public_id,
            "candidate_public_ids": [task.public_id],
            "confidence": 0.94,
            "needs_confirmation": False,
            "forbid_auto_reasons": [],
            "evidence_terms": ["预算已经通过", "确认客户预算"],
            "state_mutation_requested": False,
        }
    )
    run_log = FakeMatcherRunCrud()
    matcher = _matcher(runtime, matcher_run_crud=run_log)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.source == "langchain_structured_output"
    assert result.decision.decision == "COMPLETE"
    assert result.decision.task_public_id == task.public_id
    assert result.decision.state_mutation_requested is False
    assert runtime.calls[0]["structured_output_strategy"] == "tool"
    assert '"owner_id"' not in runtime.calls[0]["user_prompt"]
    assert '"owner_relation": "same_owner"' in runtime.calls[0]["user_prompt"]
    assert run_log.match_results[0]["result"].decision.decision == "COMPLETE"


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_state_mutation_request_to_confirmation():
    task = _candidate()
    runtime = FakeRuntime(
        {
            "decision": "COMPLETE",
            "task_public_id": task.public_id,
            "candidate_public_ids": [task.public_id],
            "confidence": 0.94,
            "needs_confirmation": False,
            "forbid_auto_reasons": [],
            "evidence_terms": ["预算已经通过", "确认客户预算"],
            "state_mutation_requested": True,
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.decision.decision == "ASK_CONFIRMATION"
    assert result.decision.needs_confirmation is True
    assert result.decision.state_mutation_requested is False
    assert "STATE_MUTATION_FORBIDDEN" in result.decision.forbid_auto_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "proposed_due_at"),
    [
        ("COMPLETE", None),
        ("DELAY", "2026-08-14T10:00:00"),
        ("CANCEL", None),
    ],
)
async def test_semantic_matcher_downgrades_cross_owner_auto_transition_to_confirmation(decision, proposed_due_at):
    task = _candidate(
        owner_id="3",
        auto_transition_eligible=False,
        confirmation_required_reason="CROSS_OWNER",
    )
    runtime = FakeRuntime(
        {
            "decision": decision,
            "task_public_id": task.public_id,
            "candidate_public_ids": [task.public_id],
            "confidence": 0.96,
            "needs_confirmation": False,
            "proposed_due_at": proposed_due_at,
            "forbid_auto_reasons": [],
            "evidence_terms": ["预算已经通过"],
            "state_mutation_requested": False,
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.decision.decision == "ASK_CONFIRMATION"
    assert result.decision.needs_confirmation is True
    assert result.decision.task_public_id == task.public_id
    assert "CROSS_OWNER" in result.decision.forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_missing_or_ungrounded_evidence():
    task = _candidate()
    runtime = FakeRuntime(
        {
            "decision": "COMPLETE",
            "task_public_id": task.public_id,
            "candidate_public_ids": [task.public_id],
            "confidence": 0.94,
            "needs_confirmation": False,
            "forbid_auto_reasons": [],
            "evidence_terms": ["不存在的证据词"],
            "state_mutation_requested": False,
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.decision.decision == "ASK_CONFIRMATION"
    assert result.decision.needs_confirmation is True
    assert "UNGROUNDED_EVIDENCE" in result.decision.forbid_auto_reasons

    runtime.payload["evidence_terms"] = []
    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.decision.decision == "ASK_CONFIRMATION"
    assert "MISSING_EVIDENCE" in result.decision.forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_unknown_candidate_public_id():
    task = _candidate()
    runtime = FakeRuntime(
        {
            "decision": "COMPLETE",
            "task_public_id": "fut_99999999999999999999999999999999",
            "candidate_public_ids": ["fut_99999999999999999999999999999999"],
            "confidence": 0.94,
            "needs_confirmation": False,
            "forbid_auto_reasons": [],
            "evidence_terms": ["预算已经通过", "确认客户预算"],
            "state_mutation_requested": False,
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.decision.decision == "KEEP_OPEN"
    assert result.decision.task_public_id is None
    assert "UNKNOWN_TASK_CANDIDATE" in result.decision.forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_low_confidence_auto_transition():
    task = _candidate()
    runtime = FakeRuntime(
        {
            "decision": "DELAY",
            "task_public_id": task.public_id,
            "candidate_public_ids": [task.public_id],
            "confidence": 0.62,
            "needs_confirmation": False,
            "proposed_due_at": "2026-08-14T10:00:00",
            "forbid_auto_reasons": [],
            "evidence_terms": ["下周五再说"],
            "state_mutation_requested": False,
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.decision.decision == "ASK_CONFIRMATION"
    assert result.decision.needs_confirmation is True
    assert result.decision.proposed_due_at == "2026-08-14T10:00:00"
    assert "LOW_CONFIDENCE" in result.decision.forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_uses_safe_fallback_when_structured_output_fails():
    task = _candidate()
    runtime = FakeRuntime(
        exc=AgentLangChainStructuredOutputError("invalid structured output"),
    )
    run_log = FakeMatcherRunCrud()
    matcher = _matcher(runtime, matcher_run_crud=run_log)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert result.source == "safe_fallback"
    assert result.decision.decision == "KEEP_OPEN"
    assert result.decision.state_mutation_requested is False
    assert result.decision.candidate_public_ids == (task.public_id,)
    assert result.decision.forbid_auto_reasons == ("STRUCTURED_OUTPUT_FAILED",)
    assert run_log.schema_errors[0]["candidate_public_ids"] == [task.public_id]
    assert run_log.schema_errors[0]["error"].args == ("invalid structured output",)


def test_semantic_output_schema_rejects_internal_task_ids_and_incomplete_delay():
    with pytest.raises(ValidationError):
        TaskReconciliationSemanticOutput.model_validate(
            {
                "decision": "COMPLETE",
                "task_public_id": "123",
                "candidate_public_ids": ["123"],
                "confidence": 0.95,
                "evidence_terms": ["预算通过"],
            }
        )

    with pytest.raises(ValidationError):
        TaskReconciliationSemanticOutput.model_validate(
            {
                "decision": "DELAY",
                "task_public_id": "fut_11111111111111111111111111111111",
                "candidate_public_ids": ["fut_11111111111111111111111111111111"],
                "confidence": 0.95,
                "evidence_terms": ["下周再说"],
            }
        )
