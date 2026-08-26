from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.agent.langchain_runtime import AgentLangChainStructuredOutputError
from app.services.task_reconciliation_semantic_matcher import (
    TaskReconciliationUnavailableError,
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
        self.unavailable_results = []

    def record_match_result(self, *args, **kwargs):
        self.match_results.append(kwargs)

    def record_schema_error(self, *args, **kwargs):
        self.schema_errors.append(kwargs)

    def record_unavailable(self, *args, **kwargs):
        self.unavailable_results.append(kwargs)


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


def _single_task_output(
    task_public_id: str,
    *,
    decision: str,
    confidence: float,
    needs_confirmation: bool = False,
    proposed_due_at: str | None = None,
    forbid_auto_reasons: list[str] | None = None,
    evidence_terms: list[str] | None = None,
    state_mutation_requested: bool = False,
) -> dict[str, object]:
    return {
        "tasks": [
            {
                "task_public_id": task_public_id,
                "decision": decision,
                "confidence": confidence,
                "needs_confirmation": needs_confirmation,
                "proposed_due_at": proposed_due_at,
                "forbid_auto_reasons": forbid_auto_reasons or [],
                "evidence_terms": evidence_terms or [],
                "state_mutation_requested": state_mutation_requested,
            }
        ]
    }


def _only_task_decision(result):
    assert len(result.decision.task_decisions) == 1
    return result.decision.task_decisions[0]


@pytest.mark.asyncio
async def test_semantic_matcher_returns_same_owner_completion_suggestion():
    task = _candidate()
    runtime = FakeRuntime(
        _single_task_output(
            task.public_id,
            decision="COMPLETE",
            confidence=0.94,
            evidence_terms=["预算已经通过", "确认客户预算"],
        )
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
    assert _only_task_decision(result).decision == "COMPLETE"
    assert _only_task_decision(result).task_public_id == task.public_id
    assert _only_task_decision(result).state_mutation_requested is False
    assert runtime.calls[0]["structured_output_strategy"] == "tool"
    assert '"owner_id"' not in runtime.calls[0]["user_prompt"]
    assert '"owner_relation": "same_owner"' in runtime.calls[0]["user_prompt"]
    assert run_log.match_results[0]["result"].decision.task_decisions[0].decision == "COMPLETE"


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_state_mutation_request_to_confirmation():
    task = _candidate()
    runtime = FakeRuntime(
        _single_task_output(
            task.public_id,
            decision="COMPLETE",
            confidence=0.94,
            evidence_terms=["预算已经通过", "确认客户预算"],
            state_mutation_requested=True,
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == "COMPLETE"
    assert _only_task_decision(result).needs_confirmation is True
    assert _only_task_decision(result).state_mutation_requested is False
    assert "STATE_MUTATION_FORBIDDEN" in _only_task_decision(result).forbid_auto_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "proposed_due_at"),
    [
        ("COMPLETE", None),
        ("POSTPONE", "2026-08-14T10:00:00"),
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
        _single_task_output(
            task.public_id,
            decision=decision,
            confidence=0.96,
            proposed_due_at=proposed_due_at,
            evidence_terms=["预算已经通过"],
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == decision
    assert _only_task_decision(result).needs_confirmation is True
    assert _only_task_decision(result).task_public_id == task.public_id
    assert "CROSS_OWNER" in _only_task_decision(result).forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_missing_or_ungrounded_evidence():
    task = _candidate()
    runtime = FakeRuntime(
        _single_task_output(
            task.public_id,
            decision="COMPLETE",
            confidence=0.94,
            evidence_terms=["不存在的证据词"],
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == "COMPLETE"
    assert _only_task_decision(result).needs_confirmation is True
    assert "UNGROUNDED_EVIDENCE" in _only_task_decision(result).forbid_auto_reasons

    runtime.payload["tasks"][0]["evidence_terms"] = []
    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == "COMPLETE"
    assert "MISSING_EVIDENCE" in _only_task_decision(result).forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_unknown_candidate_public_id():
    task = _candidate()
    runtime = FakeRuntime(
        _single_task_output(
            "fut_99999999999999999999999999999999",
            decision="COMPLETE",
            confidence=0.94,
            evidence_terms=["预算已经通过", "确认客户预算"],
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == "ASK_CONFIRMATION"
    assert _only_task_decision(result).task_public_id == task.public_id
    assert _only_task_decision(result).forbid_auto_reasons == ("TASK_NOT_ADDRESSED_BY_MODEL",)
    assert result.evaluation_failures == ("unknown_task_candidate:fut_99999999999999999999999999999999",)


@pytest.mark.asyncio
async def test_semantic_matcher_downgrades_low_confidence_auto_transition():
    task = _candidate()
    runtime = FakeRuntime(
        _single_task_output(
            task.public_id,
            decision="POSTPONE",
            confidence=0.62,
            proposed_due_at="2026-08-14T10:00:00",
            evidence_terms=["下周五再说"],
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == "POSTPONE"
    assert _only_task_decision(result).needs_confirmation is True
    assert _only_task_decision(result).proposed_due_at == "2026-08-14T10:00:00"
    assert "LOW_CONFIDENCE" in _only_task_decision(result).forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_reports_unavailable_instead_of_confirming_tasks_on_model_failure():
    task = _candidate()
    runtime = FakeRuntime(
        exc=AgentLangChainStructuredOutputError("invalid structured output"),
    )
    run_log = FakeMatcherRunCrud()
    matcher = _matcher(runtime, matcher_run_crud=run_log)

    with pytest.raises(TaskReconciliationUnavailableError, match="STRUCTURED_OUTPUT_FAILED"):
        await matcher.match_candidates(
            object(),
            team_id=1,
            activity_context=_activity_context(),
            candidate_set=_candidate_set(task),
        )

    assert run_log.schema_errors[0]["candidate_public_ids"] == [task.public_id]
    assert run_log.schema_errors[0]["error"].args == ("invalid structured output",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_crud", "reason"),
    [
        (FakeConfigCrud(has_config=False), "AI_CONFIG_MISSING"),
        (FakeConfigCrud(has_key=False), "AI_API_KEY_MISSING"),
    ],
)
async def test_semantic_matcher_reports_unavailable_when_ai_configuration_is_missing(config_crud, reason):
    task = _candidate()
    run_log = FakeMatcherRunCrud()
    matcher = _matcher(FakeRuntime(), config_crud=config_crud, matcher_run_crud=run_log)

    with pytest.raises(TaskReconciliationUnavailableError, match=reason):
        await matcher.match_candidates(
            object(),
            team_id=1,
            activity_context=_activity_context(),
            candidate_set=_candidate_set(task),
        )

    assert run_log.unavailable_results[0]["reason_code"] == reason
    assert run_log.unavailable_results[0]["candidate_public_ids"] == [task.public_id]


def test_semantic_output_schema_rejects_internal_task_ids_and_incomplete_postpone():
    with pytest.raises(ValidationError):
        TaskReconciliationSemanticOutput.model_validate(
            {
                "tasks": [
                    {
                        "decision": "COMPLETE",
                        "task_public_id": "123",
                        "confidence": 0.95,
                        "evidence_terms": ["预算通过"],
                    }
                ]
            }
        )


def test_semantic_output_schema_rejects_duplicate_task_decisions():
    task_public_id = "fut_11111111111111111111111111111111"

    with pytest.raises(ValidationError, match="duplicate task_public_id"):
        TaskReconciliationSemanticOutput.model_validate(
            {
                "tasks": [
                    {
                        "decision": "COMPLETE",
                        "task_public_id": task_public_id,
                        "confidence": 0.95,
                        "evidence_terms": ["预算通过"],
                    },
                    {
                        "decision": "KEEP_OPEN",
                        "task_public_id": task_public_id,
                        "confidence": 0.8,
                        "evidence_terms": ["仍在推进"],
                    },
                ]
            }
        )

    with pytest.raises(ValidationError):
        TaskReconciliationSemanticOutput.model_validate(
            {
                "tasks": [
                    {
                        "decision": "POSTPONE",
                        "task_public_id": "fut_11111111111111111111111111111111",
                        "confidence": 0.95,
                        "evidence_terms": ["下周再说"],
                    }
                ]
            }
        )


def test_semantic_output_schema_rejects_legacy_scalar_response():
    with pytest.raises(ValidationError):
        TaskReconciliationSemanticOutput.model_validate(
            {
                "decision": "KEEP_OPEN",
                "task_public_id": "fut_11111111111111111111111111111111",
                "confidence": 0.72,
                "evidence_terms": ["继续跟进"],
            }
        )


@pytest.mark.asyncio
async def test_semantic_matcher_returns_independent_decisions_for_every_candidate():
    completed = _candidate("fut_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    uncertain = _candidate("fut_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    runtime = FakeRuntime(
        payload={
            "tasks": [
                {
                    "task_public_id": completed.public_id,
                    "decision": "COMPLETE",
                    "confidence": 0.96,
                    "evidence_terms": ["预算已经通过", "确认客户预算"],
                },
                {
                    "task_public_id": uncertain.public_id,
                    "decision": "COMPLETE",
                    "confidence": 0.61,
                    "evidence_terms": ["POC 部署"],
                },
            ],
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(completed, uncertain),
    )

    assert [item.task_public_id for item in result.decision.task_decisions] == [
        completed.public_id,
        uncertain.public_id,
    ]
    assert result.decision.task_decisions[0].decision == "COMPLETE"
    assert result.decision.task_decisions[0].needs_confirmation is False
    assert result.decision.task_decisions[1].decision == "COMPLETE"
    assert result.decision.task_decisions[1].needs_confirmation is True
    assert "LOW_CONFIDENCE" in result.decision.task_decisions[1].forbid_auto_reasons
    assert set(result.to_dict()["decision"]) == {"candidate_public_ids", "task_decisions", "empty_outcome"}


@pytest.mark.asyncio
async def test_semantic_matcher_keeps_high_confidence_unrelated_task_as_noop():
    task = _candidate()
    runtime = FakeRuntime(
        payload={
            "tasks": [
                {
                    "task_public_id": task.public_id,
                    "decision": "UNRELATED",
                    "confidence": 0.97,
                    "evidence_terms": ["不同事项"],
                }
            ],
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(task),
    )

    decision = result.decision.task_decisions[0]
    assert decision.decision == "UNRELATED"
    assert decision.needs_confirmation is False
    assert result.evaluation_failures == ()


@pytest.mark.asyncio
async def test_semantic_matcher_marks_high_confidence_keep_open_as_confirmation_required():
    task = _candidate()
    runtime = FakeRuntime(
        payload={
            "tasks": [
                {
                    "task_public_id": task.public_id,
                    "decision": "KEEP_OPEN",
                    "confidence": 0.99,
                    "evidence_terms": ["跟进客户 POC 环境部署情况", "部署相关内容已反馈"],
                }
            ],
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context={**_activity_context(), "source_content": "今天已反馈部署内容, 周四继续跟进。"},
        candidate_set=_candidate_set(task),
    )

    decision = result.decision.task_decisions[0]
    assert decision.decision == "KEEP_OPEN"
    assert decision.needs_confirmation is True
    assert "RELATED_TASK_REQUIRES_CONFIRMATION" in decision.forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_requests_confirmation_for_low_confidence_keep_open_decision():
    task = _candidate()
    runtime = FakeRuntime(
        payload={
            "tasks": [
                {
                    "task_public_id": task.public_id,
                    "decision": "KEEP_OPEN",
                    "confidence": 0.72,
                    "forbid_auto_reasons": ["完成证据不足"],
                    "evidence_terms": ["继续跟进"],
                }
            ],
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context={**_activity_context(), "source_content": "今天已反馈部署内容, 周四继续跟进。"},
        candidate_set=_candidate_set(task),
    )

    decision = result.decision.task_decisions[0]
    assert decision.decision == "ASK_CONFIRMATION"
    assert decision.needs_confirmation is True
    assert "LOW_CONFIDENCE" in decision.forbid_auto_reasons


@pytest.mark.asyncio
async def test_semantic_matcher_requests_confirmation_when_model_omits_a_candidate():
    completed = _candidate("fut_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    omitted = _candidate("fut_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    runtime = FakeRuntime(
        payload={
            "tasks": [
                {
                    "task_public_id": completed.public_id,
                    "decision": "COMPLETE",
                    "confidence": 0.96,
                    "evidence_terms": ["预算已经通过", "确认客户预算"],
                }
            ],
        }
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context=_activity_context(),
        candidate_set=_candidate_set(completed, omitted),
    )

    omitted_decision = result.decision.task_decisions[1]
    assert omitted_decision.task_public_id == omitted.public_id
    assert omitted_decision.decision == "ASK_CONFIRMATION"
    assert omitted_decision.needs_confirmation is True
    assert omitted_decision.forbid_auto_reasons == ("TASK_NOT_ADDRESSED_BY_MODEL",)

@pytest.mark.asyncio
async def test_semantic_matcher_contract_completes_historical_follow_up_action_even_when_project_continues():
    task = TaskReconciliationCandidate(
        public_id="fut_cccccccccccccccccccccccccccccccc",
        owner_id="2",
        title="继续跟进立项流程",
        description="下周继续联系客户了解立项流程进展。",
        due_at="2026-08-20T09:00:00",
        due_at_text="上周三",
        due_at_granularity="DATETIME",
        due_at_timezone="Asia/Shanghai",
        source_type="CUSTOMER_ACTIVITY",
        source_public_id="act_previous_follow_up",
        confidence=0.95,
        candidate_reasons=("same_customer", "open_task", "same_owner", "historical_open_task"),
        auto_transition_eligible=True,
        confirmation_required_reason=None,
    )
    runtime = FakeRuntime(
        _single_task_output(
            task.public_id,
            decision="COMPLETE",
            confidence=0.96,
            evidence_terms=["微信联系", "立项流程"],
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context={
            "owner_id": "2",
            "source_content": "今天已微信联系客户，客户反馈项目正在走立项流程。",
            "summary": "已联系客户并取得立项流程进展。",
            "next_action": "下周三继续跟进立项流程",
            "next_follow_time": "2026-09-02T09:00:00",
            "occurred_at": "2026-08-25T10:00:00",
        },
        candidate_set=_candidate_set(task),
    )

    assert _only_task_decision(result).decision == "COMPLETE"
    system_prompt = runtime.calls[0]["system_prompt"]
    assert "判断对象是历史待办要求销售执行的动作是否已履行" in system_prompt
    assert "项目或客户事项是否最终结束不是 COMPLETE 的判断对象" in system_prompt
    assert "new_future_plan 表示本次跟进后新产生的未来待办" in system_prompt
    assert "不能据此把已履行的历史待办判为 KEEP_OPEN" in system_prompt
    user_prompt = runtime.calls[0]["user_prompt"]
    assert '"activity_execution_evidence"' in user_prompt
    assert '"new_future_plan"' in user_prompt
    assert '"historical_candidate_tasks"' in user_prompt
    execution_payload = user_prompt.split('"activity_execution_evidence": ', 1)[1].split(
        '"new_future_plan": ', 1
    )[0]
    assert '"next_action"' not in execution_payload

@pytest.mark.asyncio
async def test_semantic_matcher_does_not_use_new_future_plan_as_completion_evidence():
    task = TaskReconciliationCandidate(
        public_id="fut_dddddddddddddddddddddddddddddddd",
        owner_id="2",
        title="继续跟进立项流程",
        description="联系客户了解立项流程进展。",
        due_at="2026-08-20T09:00:00",
        due_at_text="上周四",
        due_at_granularity="DATETIME",
        due_at_timezone="Asia/Shanghai",
        source_type="CUSTOMER_ACTIVITY",
        source_public_id="act_previous_follow_up",
        confidence=0.95,
        candidate_reasons=("same_customer", "open_task", "same_owner", "historical_open_task"),
        auto_transition_eligible=True,
        confirmation_required_reason=None,
    )
    runtime = FakeRuntime(
        _single_task_output(
            task.public_id,
            decision="COMPLETE",
            confidence=0.96,
            evidence_terms=["继续跟进立项流程"],
        )
    )
    matcher = _matcher(runtime)

    result = await matcher.match_candidates(
        object(),
        team_id=1,
        activity_context={
            "owner_id": "2",
            "source_content": "客户项目仍在评估，本次尚未联系客户。",
            "summary": "本次没有执行客户跟进。",
            "next_action": "下周三继续跟进立项流程",
            "next_follow_time": "2026-09-02T09:00:00",
            "occurred_at": "2026-08-25T10:00:00",
        },
        candidate_set=_candidate_set(task),
    )

    decision = _only_task_decision(result)
    assert decision.decision == "COMPLETE"
    assert decision.needs_confirmation is True
    assert "UNGROUNDED_EVIDENCE" in decision.forbid_auto_reasons
