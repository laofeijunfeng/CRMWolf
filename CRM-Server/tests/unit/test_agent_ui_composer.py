"""Behavior tests for the authoritative Agent UI composition seam."""

import pytest

from app.services.agent.orchestrator import (
    AgentExecutionError,
    ClarificationDispatchResult,
    ClarificationRequest,
    ContextPolicy,
    FailureDispatchResult,
    QueryDispatchResult,
    RootDecision,
    WorkflowContinuation,
    WorkflowDispatchResult,
)
from app.services.agent.query import CRMQueryAgentResult
from app.services.agent.semantic_plan import AgentSemanticPlan
from app.services.agent.ui.composer import AgentUIComposer
from app.services.agent.workflow import (
    WorkflowCompletedResult,
    WorkflowFailedResult,
    WorkflowInteraction,
    WorkflowInteractionField,
    WorkflowInteractionOption,
    WorkflowProgress,
    WorkflowProgressStep,
    WorkflowRef,
    WorkflowWaitingResult,
)


def _decision(route: str) -> RootDecision:
    return RootDecision(
        task_relation="NEW_TASK",
        route=route,
        risk="READ_ONLY" if route != "WORKFLOW" else "WRITE",
        context_policy=ContextPolicy(
            selected_entity="IGNORE",
            previous_query="IGNORE",
            result_set="IGNORE",
            active_workflow="NONE",
        ),
        confidence=1.0,
        reason_code=f"{route}_TEST",
        evidence=[],
        semantic_plan=AgentSemanticPlan(
            speech_act="REQUEST_ACTION" if route == "WORKFLOW" else "ASK_FACT",
            business_object="CUSTOMER_ACTIVITY" if route == "WORKFLOW" else "CUSTOMER",
            operation="CREATE" if route == "WORKFLOW" else "READ",
            confidence=1.0,
        ),
    )


def _query_dispatch(*, answer: str = "上海共有 2 个客户。") -> QueryDispatchResult:
    return QueryDispatchResult(
        decision=_decision("QUERY"),
        query_result=CRMQueryAgentResult.model_validate(
            {
                "response": {
                    "status": "ANSWERED",
                    "answer": answer,
                    "evidence_refs": ["qry_1"],
                },
                "query_results": [
                    {
                        "query_id": "qry_1",
                        "result_set_id": "rs_1",
                        "resource": "customer",
                        "status": "SUCCESS",
                        "rows": [
                            {"account_name": "上海星云科技", "city": "上海"},
                            {"account_name": "上海远景软件", "city": "上海"},
                        ],
                        "entity_refs": [
                            {
                                "ref_id": "eref_customer_1",
                                "resource": "customer",
                                "public_id": "cus_1",
                                "display_name": "上海星云科技",
                                "result_set_id": "rs_1",
                            },
                            {
                                "ref_id": "eref_customer_2",
                                "resource": "customer",
                                "public_id": "cus_2",
                                "display_name": "上海远景软件",
                                "result_set_id": "rs_1",
                            },
                        ],
                        "total": 2,
                        "applied_filters": [],
                        "applied_sorts": [],
                        "facts": [],
                        "warnings": [],
                    }
                ],
                "customer_context_results": [],
                "trace": {
                    "model": "test-model",
                    "tool_names": ["query_customers"],
                    "tool_calls": [],
                    "tool_call_count": 1,
                    "total_entity_count": 2,
                    "elapsed_ms": 1,
                    "stop_reason": "COMPLETED",
                },
            }
        ),
    )


def _progress(*, final_status: str = "COMPLETED") -> WorkflowProgress:
    return WorkflowProgress(
        steps=[
            WorkflowProgressStep(
                key="understand_request",
                title="理解业务操作",
                status="COMPLETED",
            ),
            WorkflowProgressStep(
                key="execute_action",
                title="执行 CRM 操作",
                status=final_status,
            ),
        ]
    )


def _continuation() -> WorkflowContinuation:
    return WorkflowContinuation(
        root_thread_id="crm_agent_turn:test",
        workflow_ref=WorkflowRef(workflow_id="wf_1", interrupt_id="intr_1"),
        parent_checkpoint_id="parent_cp_1",
        subgraph_checkpoint_ns="workflow:abc",
        subgraph_checkpoint_id="sub_cp_1",
    )


def _waiting_dispatch(interaction: WorkflowInteraction) -> WorkflowDispatchResult:
    continuation = _continuation()
    return WorkflowDispatchResult(
        decision=_decision("WORKFLOW"),
        workflow_result=WorkflowWaitingResult(
            workflow_ref=continuation.workflow_ref,
            assistant_text=interaction.prompt,
            interaction=interaction,
            progress=_progress(final_status="WAITING"),
        ),
        continuation=continuation,
    )


def test_query_result_is_composed_as_text_and_entity_list() -> None:
    composition = AgentUIComposer().compose(_query_dispatch())

    assert composition.content == "共找到 2 家公司。"
    assert composition.body.state == "final"
    assert composition.body.metadata.route == "QUERY"
    assert composition.body.metadata.result_set_id == "rs_1"
    assert [block.type for block in composition.body.blocks] == ["text", "entity_list"]
    text_block = composition.body.blocks[0]
    assert text_block.type == "text"
    assert text_block.text == "共找到 2 家公司。"
    entity_list = composition.body.blocks[1]
    assert entity_list.type == "entity_list"
    assert entity_list.total == 2
    assert [item.entity_ref.display_name for item in entity_list.items] == [
        "上海星云科技",
        "上海远景软件",
    ]
    assert entity_list.items[0].entity_ref.model_dump(mode="json") == {
        "ref_id": "eref_customer_1",
        "resource": "customer",
        "public_id": "cus_1",
        "display_name": "上海星云科技",
        "result_set_id": "rs_1",
    }
    assert entity_list.items[0].model_dump(mode="json") == {
        "entity_ref": entity_list.items[0].entity_ref.model_dump(mode="json")
    }
    assert composition.action_drafts == ()


def test_waiting_workflow_composes_server_owned_action_with_exact_continuation() -> None:
    dispatch = _waiting_dispatch(
        WorkflowInteraction(
            interaction_id="int_customer_1",
            interaction_type="choice",
            business_action="select_customer",
            title="选择客户",
            prompt="请选择客户。",
            options=[
                WorkflowInteractionOption(value="cus_1", label="上海星云科技"),
                WorkflowInteractionOption(value="cus_2", label="上海远景软件", disabled=True),
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
        )
    )

    composition = AgentUIComposer().compose(dispatch)

    assert [block.type for block in composition.body.blocks] == ["process", "interaction"]
    assert composition.content == "请选择客户。"
    assert composition.body.metadata.accessibility_label == "请选择客户。"
    interaction = composition.body.blocks[1]
    assert interaction.type == "interaction"
    assert interaction.interaction_type == "choice"
    assert interaction.options[1].disabled is True
    assert composition.action_drafts[0].action_type == "submit_interaction"
    assert composition.action_drafts[0].target == {
        "workflow_continuation": dispatch.continuation.model_dump(mode="json"),
        "interaction_id": "int_customer_1",
        "interaction_type": "choice",
        "business_action": "select_customer",
        "submit_label": "提交",
        "submit_on_select": False,
        "choices": [option.model_dump(mode="json") for option in interaction.options],
        "selection_mode": "single",
        "min_selections": 1,
        "max_selections": 1,
    }
    assert "workflow_id" not in composition.action_drafts[0].target
    assert "interrupt_id" not in composition.action_drafts[0].target


def test_form_interaction_signs_the_same_constraints_rendered_to_the_user() -> None:
    dispatch = _waiting_dispatch(
        WorkflowInteraction(
            interaction_id="int_amount_1",
            interaction_type="form",
            business_action="create_payment",
            title="补充金额",
            prompt="请输入金额。",
            fields=[
                WorkflowInteractionField(
                    key="amount",
                    label="金额",
                    field_type="number",
                    required=True,
                    minimum=0,
                    maximum=100000,
                )
            ],
        )
    )

    composition = AgentUIComposer().compose(dispatch)

    interaction = composition.body.blocks[1]
    assert interaction.type == "interaction"
    assert composition.action_drafts[0].target["fields"] == [
        interaction.fields[0].model_dump(mode="json")
    ]


def test_confirmation_preserves_canonical_workflow_options() -> None:
    dispatch = _waiting_dispatch(
        WorkflowInteraction(
            interaction_id="int_confirmation_1",
            interaction_type="confirmation",
            business_action="create_customer_activity",
            title="确认创建",
            prompt="请确认是否创建这条客户活动？",  # noqa: RUF001
            options=[
                WorkflowInteractionOption(value="confirm", label="确认创建"),
                WorkflowInteractionOption(value="cancel", label="取消"),
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
        )
    )

    composition = AgentUIComposer().compose(dispatch)

    interaction = composition.body.blocks[1]
    assert interaction.type == "interaction"
    assert interaction.interaction_type == "confirmation"
    assert interaction.submit_label == "提交"
    assert [option.label for option in interaction.options] == ["确认创建", "取消"]
    assert composition.action_drafts[0].target["choices"] == [
        option.model_dump(mode="json") for option in interaction.options
    ]


def test_terminal_workflow_result_includes_execution_process() -> None:
    composition = AgentUIComposer().compose(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW"),
            workflow_result=WorkflowCompletedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_1"),
                assistant_text="已创建跟进任务。",
                progress=_progress(),
            ),
        )
    )

    assert [block.type for block in composition.body.blocks] == ["process", "text"]
    assert composition.content == "已创建跟进任务。"
    assert composition.action_drafts == ()
    process = composition.body.blocks[0]
    assert process.type == "process"
    assert [item.title for item in process.items] == ["理解业务操作", "执行 CRM 操作"]


def test_completed_workflow_projects_execution_process_as_process_block() -> None:
    composition = AgentUIComposer().compose(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW"),
            workflow_result=WorkflowCompletedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_customer_follow_up"),
                assistant_text="已创建跟进任务。",
                progress=_progress(),
            ),
        )
    )

    assert [block.type for block in composition.body.blocks] == ["process", "text"]


def test_failed_workflow_result_is_error_only() -> None:
    composition = AgentUIComposer().compose(
        WorkflowDispatchResult(
            decision=_decision("WORKFLOW"),
            workflow_result=WorkflowFailedResult(
                workflow_ref=WorkflowRef(workflow_id="wf_1"),
                code="WORKFLOW_EFFECT_FAILED",
                message="创建失败，请稍后重试。",  # noqa: RUF001
                retryable=True,
                progress=_progress(final_status="FAILED"),
            ),
        )
    )

    assert [block.type for block in composition.body.blocks] == ["process", "error"]
    error = composition.body.blocks[1]
    assert error.type == "error"
    assert error.code == "INTERNAL_ERROR"
    assert error.message == "创建失败，请稍后重试。"  # noqa: RUF001
    assert error.retryable is True


def test_clarification_is_text_only() -> None:
    composition = AgentUIComposer().compose(
        ClarificationDispatchResult(
            decision=_decision("CLARIFY"),
            clarification=ClarificationRequest(
                question="你想查询客户，还是创建跟进任务？",  # noqa: RUF001
                reason_code="REQUEST_AMBIGUOUS",
            ),
        )
    )

    assert composition.body.metadata.route == "CLARIFY"
    assert [block.type for block in composition.body.blocks] == ["text"]
    assert composition.content == "你想查询客户，还是创建跟进任务？"  # noqa: RUF001


def test_root_model_timeout_uses_human_facing_message_and_title() -> None:
    composition = AgentUIComposer().compose(
        FailureDispatchResult(
            error=AgentExecutionError(
                code="ROOT_DECISION_MODEL_TIMEOUT",
                message="AI 刚才响应超时了，请再试一次。",  # noqa: RUF001
                retryable=True,
            )
        )
    )

    error = composition.body.blocks[0]
    assert error.type == "error"
    assert error.title == "这次没处理成"
    assert error.message == "AI 刚才响应超时了，请再试一次。"  # noqa: RUF001
    assert error.code == "UPSTREAM_TIMEOUT"
    assert error.retryable is True


def test_query_failure_uses_query_title_for_canonical_error_code() -> None:
    composition = AgentUIComposer().compose(
        FailureDispatchResult(
            decision=_decision("QUERY"),
            error=AgentExecutionError(
                code="QUERY_INVALID",
                message="我还没看懂你要查什么，请补充客户、时间或内容。",  # noqa: RUF001
                retryable=False,
            ),
        )
    )

    error = composition.body.blocks[0]
    assert error.type == "error"
    assert error.title == "查询没完成"
    assert error.code == "QUERY_INVALID"


def test_root_failure_is_composed_as_structured_error_block() -> None:
    composition = AgentUIComposer().compose(
        FailureDispatchResult(
            error=AgentExecutionError(
                code="CHECKPOINT_UNAVAILABLE",
                message="会话状态服务暂时不可用。请稍后重试。",
                retryable=True,
            )
        )
    )

    assert [block.type for block in composition.body.blocks] == ["error"]
    error = composition.body.blocks[0]
    assert error.type == "error"
    assert error.code == "CHECKPOINT_UNAVAILABLE"
    assert error.retryable is True


@pytest.mark.parametrize("content", ["=", "-", "before\n\n=\nafter", "金额条件：1 < 2 > 0"])  # noqa: RUF001
def test_text_projection_preserves_non_markdown_business_symbols(content: str) -> None:
    composition = AgentUIComposer().compose(
        ClarificationDispatchResult(
            decision=_decision("CLARIFY"),
            clarification=ClarificationRequest(
                question=content,
                reason_code="TEXT_PROJECTION_TEST",
            ),
        )
    )

    assert composition.content == content
    assert composition.body.metadata.accessibility_label == content


def test_choice_keeps_authoritative_metadata_only_in_signed_action_target() -> None:
    dispatch = _waiting_dispatch(
        WorkflowInteraction(
            interaction_id="int_member_choice_1",
            interaction_type="choice",
            business_action="select_customer_member",
            title="选择客户成员",
            prompt="请选择具体人员。",
            options=[
                WorkflowInteractionOption(
                    value="9",
                    label="张三",
                    metadata={
                        "customer_member_user_id": "9",
                        "customer_member_user_name": "张三",
                    },
                )
            ],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
        )
    )

    composition = AgentUIComposer().compose(dispatch)

    interaction = composition.body.blocks[1]
    assert interaction.type == "interaction"
    assert interaction.options[0].model_dump(mode="json") == {
        "value": "9",
        "label": "张三",
        "description": None,
        "disabled": False,
    }
    assert composition.action_drafts[0].target["choices"] == [
        {
            "value": "9",
            "label": "张三",
            "description": None,
            "disabled": False,
            "metadata": {
                "customer_member_user_id": "9",
                "customer_member_user_name": "张三",
            },
        }
    ]


def test_follow_up_confirmation_signs_case_public_id_for_read_time_projection() -> None:
    dispatch = _waiting_dispatch(
        WorkflowInteraction(
            interaction_id="int_follow_up_confirmation_1",
            interaction_type="choice",
            business_action="resolve_follow_up_task_confirmation_case",
            title="确认待办",
            prompt="请确认待办是否完成。",
            options=[WorkflowInteractionOption(value="已完成", label="标记完成")],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_on_select=True,
        )
    )

    composition = AgentUIComposer().compose_follow_up_task_confirmations(
        [dispatch],
        case_public_ids=["fuc_case_1"],
    )

    assert composition.action_drafts[0].target["follow_up_confirmation_case_public_id"] == "fuc_case_1"


def test_model_reference_links_are_projected_to_safe_plain_text() -> None:
    result = CRMQueryAgentResult.model_validate(
        {
            "response": {
                "status": "ANSWERED",
                "answer": (
                    "河南双汇发展股份有限公司当前处于跟进阶段。"
                    "\n\n[客户档案][customer-profile]\n\n"
                    "[customer-profile]: https://example.com/customer/1"
                ),
                "evidence_refs": ["ctx_1"],
            },
            "query_results": [],
            "customer_context_results": [],
            "trace": {
                "model": "test-model",
                "tool_names": ["get_customer_context"],
                "tool_calls": [],
                "tool_call_count": 1,
                "total_entity_count": 1,
                "elapsed_ms": 1,
                "stop_reason": "COMPLETED",
            },
        }
    )
    composition = AgentUIComposer().compose(
        QueryDispatchResult(decision=_decision("QUERY"), query_result=result)
    )

    text_block = composition.body.blocks[0]
    assert text_block.type == "text"
    assert text_block.format == "plain"
    assert "客户档案" in text_block.text
    assert "[customer-profile]" not in text_block.text


def test_customer_context_projects_the_authoritative_customer_as_clickable_entity() -> None:
    result = CRMQueryAgentResult.model_validate(
        {
            "response": {
                "status": "ANSWERED",
                "answer": "河南双汇发展股份有限公司当前客户情况已整理。",
                "evidence_refs": ["eref_customer_1"],
            },
            "query_results": [],
            "customer_context_results": [
                {
                    "customer_ref": {
                        "ref_id": "eref_customer_1",
                        "resource": "customer",
                        "public_id": "cus_1",
                        "display_name": "河南双汇发展股份有限公司",
                    },
                    "sections": {"profile": {"city": "漯河"}},
                    "citations": [],
                    "coverage": {
                        "requested": ["profile"],
                        "returned": ["profile"],
                        "unavailable": [],
                    },
                    "degraded_reasons": [],
                }
            ],
            "trace": {
                "model": "test-model",
                "tool_names": ["get_customer_context"],
                "tool_calls": [],
                "tool_call_count": 1,
                "total_entity_count": 1,
                "elapsed_ms": 1,
                "stop_reason": "COMPLETED",
            },
        }
    )

    composition = AgentUIComposer().compose(
        QueryDispatchResult(decision=_decision("QUERY"), query_result=result)
    )

    assert composition.content == "河南双汇发展股份有限公司当前客户情况已整理。"
    assert [block.type for block in composition.body.blocks] == ["text", "entity_list"]
    entity_block = composition.body.blocks[1]
    assert entity_block.items[0].entity_ref.display_name == "河南双汇发展股份有限公司"
