"""Turn timeline contract for Agent run-log reconstruction."""

# ruff: noqa: RUF001
from __future__ import annotations

from app.services.agent.durable_work_contracts import CustomerActivityDurableWorkReceipt
from app.services.agent.orchestrator import (
    AgentExecutionError,
    ContextPolicy,
    FailureDispatchResult,
    QueryDispatchResult,
    RootDecision,
    WorkflowContinuation,
    WorkflowDispatchResult,
)
from app.services.agent.query import CRMQueryAgentResult
from app.services.agent.run_log import build_turn_timeline
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.services.agent.workflow import (
    WorkflowCompletedResult,
    WorkflowInteraction,
    WorkflowInteractionOption,
    WorkflowQualityGate,
    WorkflowRef,
    WorkflowResolvedCustomer,
    WorkflowWaitingResult,
)
from app.services.agent.workflow.progress import (
    awaiting_required_input_progress,
    execution_progress,
)


def _continuation(workflow_ref: WorkflowRef) -> WorkflowContinuation:
    return WorkflowContinuation(
        workflow_ref=workflow_ref,
        root_thread_id="crm_agent_turn:test",
        parent_checkpoint_id="parent_cp",
        subgraph_checkpoint_ns="workflow:customer_follow_up",
        subgraph_checkpoint_id="child_cp",
    )


def _decision(route: str) -> RootDecision:
    return RootDecision(
        task_relation="NEW_TASK",
        route=route,
        risk="WRITE" if route == "WORKFLOW" else "READ_ONLY",
        context_policy=ContextPolicy(
            selected_entity="USE" if route == "WORKFLOW" else "IGNORE",
            previous_query="IGNORE",
            result_set="IGNORE",
            active_workflow="NONE",
        ),
        confidence=1.0,
        reason_code=f"{route}_TEST",
        semantic_plan=AgentSemanticPlan(
            speech_act="ASSERT_EVENT" if route == "WORKFLOW" else "ASK_FACT",
            business_object="CUSTOMER_ACTIVITY" if route == "WORKFLOW" else "CUSTOMER",
            operation="CREATE" if route == "WORKFLOW" else "READ",
            confidence=1.0,
        ),
        evidence=[],
    )


def test_quality_blocked_waiting_turn_is_blocked_unwritten() -> None:
    workflow_ref = WorkflowRef(workflow_id="wf_customer_follow_up", interrupt_id="intr_quality")
    dispatch = WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowWaitingResult(
            workflow_ref=workflow_ref,
            assistant_text="下一步由谁、在什么时间做什么？",
            interaction=WorkflowInteraction(
                interaction_id="int_follow_up_quality",
                interaction_type="text_input",
                business_action="supplement_follow_up_quality",
                title="补充跟进信息",
                prompt="下一步由谁、在什么时间做什么？",
                allow_blank=False,
            ),
            progress=awaiting_required_input_progress(),
            quality_gate=WorkflowQualityGate(
                score=52,
                passed=False,
                reason="缺动作闭环",
                quality_source="langchain_structured_output",
                model="test-model",
            ),
            resolved_customer=WorkflowResolvedCustomer(
                customer_id="cus_shuanghui",
                customer_name="双汇",
            ),
        ),
        continuation=_continuation(workflow_ref),
    )

    timeline = build_turn_timeline(
        dispatch,
        user_text="刚和双汇技术经理聊了 POC 部署。",
        model="test-model",
    )

    assert timeline.outcome == "blocked_unwritten"
    assert timeline.quality_score == 52
    assert timeline.customer_name == "双汇"
    assert [step.kind for step in timeline.steps] == [
        "model",
        "code",
        "code",
        "interaction",
        "api",
        "background",
    ]
    assert timeline.steps[2].title.startswith("质量 52")
    assert timeline.steps[4].tone == "skipped"
    assert timeline.steps[5].tone == "skipped"
    assert "拦住" in timeline.summary


def test_query_answered_turn_marks_api_done_and_skips_write() -> None:
    dispatch = QueryDispatchResult(
        decision=_decision("QUERY"),
        query_result=CRMQueryAgentResult.model_validate(
            {
                "response": {
                    "status": "ANSWERED",
                    "answer": "你在上海有 1 个客户。",
                    "evidence_refs": ["qry_shanghai_customers"],
                },
                "query_results": [],
                "customer_context_results": [],
                "trace": {
                    "model": "test-model",
                    "tool_names": ["query_customers"],
                    "tool_calls": [
                        {
                            "tool_name": "query_customers",
                            "status": "SUCCESS",
                            "elapsed_ms": 12,
                            "entity_count": 1,
                        }
                    ],
                    "tool_call_count": 1,
                    "total_entity_count": 1,
                    "elapsed_ms": 12,
                    "stop_reason": "COMPLETED",
                },
            }
        ),
    )

    timeline = build_turn_timeline(dispatch, user_text="上海还有哪些客户？", model="test-model")

    assert timeline.outcome == "answered"
    assert timeline.steps[0].kind == "model"
    assert timeline.steps[-2].kind == "api"
    assert timeline.steps[-2].tone == "done"
    assert "query_customers" in timeline.steps[-2].detail
    assert timeline.steps[-1].kind == "background"
    assert timeline.steps[-1].tone == "skipped"


def test_confirmation_waiting_turn_is_waiting_confirmation() -> None:
    workflow_ref = WorkflowRef(workflow_id="wf_customer_follow_up", interrupt_id="intr_confirm")
    dispatch = WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowWaitingResult(
            workflow_ref=workflow_ref,
            assistant_text="请确认是否创建这条客户活动？",
            interaction=WorkflowInteraction(
                interaction_id="int_confirm_create",
                interaction_type="confirmation",
                business_action="create_customer_activity",
                title="确认创建",
                prompt="请确认是否创建这条客户活动？",
                options=[
                    WorkflowInteractionOption(value="confirm", label="确认创建"),
                    WorkflowInteractionOption(value="cancel", label="取消"),
                ],
                selection_mode="single",
                min_selections=1,
                max_selections=1,
            ),
            progress=awaiting_required_input_progress(),
        ),
        continuation=_continuation(workflow_ref),
    )

    timeline = build_turn_timeline(dispatch, user_text="记一条跟进")

    assert timeline.outcome == "waiting_confirmation"
    interaction = next(step for step in timeline.steps if step.kind == "interaction")
    assert interaction.tone == "blocked"
    assert "确认" in interaction.title


def test_completed_write_turn_marks_api_and_background_done() -> None:
    dispatch = WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowCompletedResult(
            workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up"),
            assistant_text="已创建跟进。",
            progress=execution_progress(
                confirmation_required=False,
                has_supplements=False,
                outcome="COMPLETED",
            ),
            durable_work=[
                CustomerActivityDurableWorkReceipt(
                    activity_id=241,
                    post_commit_job_public_id="pcj_1",
                    customer_intelligence_request_id="cir_1",
                )
            ],
        ),
    )

    timeline = build_turn_timeline(dispatch, user_text="记一条跟进")

    assert timeline.outcome == "written"
    assert timeline.steps[-2].kind == "api"
    assert timeline.steps[-2].tone == "done"
    assert timeline.steps[-1].kind == "background"
    assert timeline.steps[-1].tone == "done"


def test_failure_turn_is_failed() -> None:
    dispatch = FailureDispatchResult(
        decision=_decision("WORKFLOW"),
        error=AgentExecutionError(code="WORKFLOW_FAILED", message="执行失败", retryable=False),
    )

    timeline = build_turn_timeline(dispatch, user_text="记一条跟进")

    assert timeline.outcome == "failed"
    assert "失败" in timeline.summary
