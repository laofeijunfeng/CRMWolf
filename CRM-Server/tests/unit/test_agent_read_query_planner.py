from app.services.agent.read_query_planner import AgentReadQueryPlanner
from app.services.agent.schemas import AgentSemanticParseResult


def semantic_result(**overrides):
    payload = {
        "intent": "CRM_READ_QUERY",
        "intent_confidence": 0.95,
        "customer": {"name_text": None, "confidence": 0.0},
        "read_query": {"type": "UNKNOWN_READ"},
        "contact": {},
        "invoice_title": {},
        "deployment_info": {},
        "business_signals": [],
        "requested_actions": [],
        "missing_fields": [],
        "need_clarification": False,
        "clarification_question": None,
        "evidence": [],
    }
    payload.update(overrides)
    return AgentSemanticParseResult.model_validate(payload)


def test_planner_routes_new_crm_read_query_to_follow_up_tasks():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(),
        content="下周我还有哪些客户要跟进？",
        parsed={},
    )

    assert plan is not None
    assert plan.query_type == "FOLLOW_UP_TASKS"
    assert plan.trace_label == "任务查询"
    assert plan.tool_name == "list_follow_up_tasks"
    assert plan.payload["status"] == "open"
    assert plan.payload["owner_scope"] == "mine"
    assert plan.payload["due_window"] == "next_week"
    assert plan.payload["retrieval_mode"] == "structured"
    assert "query_text" not in plan.payload


def test_planner_ignores_generic_llm_query_text_for_task_list():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(read_query={
            "type": "FOLLOW_UP_TASKS",
            "query_text": "我还有哪些任务",
        }),
        content="我还有哪些任务",
        parsed={},
    )

    assert plan is not None
    assert plan.payload["retrieval_mode"] == "structured"
    assert "query_text" not in plan.payload


def test_planner_ignores_generic_task_query_text_variants():
    for query_text in (
        "我需要跟进哪些客户",
        "哪些客户需要跟进",
        "我的跟进任务",
        "我有什么要做的",
        "下周我有什么工作安排",
    ):
        plan = AgentReadQueryPlanner().plan(
            semantic_result=semantic_result(read_query={
                "type": "FOLLOW_UP_TASKS",
                "query_text": query_text,
            }),
            content=query_text,
            parsed={},
        )

        assert plan is not None
        assert plan.payload["retrieval_mode"] == "structured"
        assert "query_text" not in plan.payload


def test_planner_uses_semantic_filter_for_topic_task_query():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(read_query={
            "type": "FOLLOW_UP_TASKS",
            "query_text": "预算相关未完成任务",
        }),
        content="预算相关未完成任务",
        parsed={},
    )

    assert plan is not None
    assert plan.payload["retrieval_mode"] == "semantic_filter"
    assert plan.payload["query_text"] == "预算相关"


def test_planner_does_not_use_customer_name_as_task_query_text_after_resolution():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(
            customer={"name_text": "越秀金融", "confidence": 0.95},
            read_query={"type": "FOLLOW_UP_TASKS", "query_text": "越秀金融下周有哪些任务"},
        ),
        content="越秀金融下周有哪些任务？",
        parsed={"customer_name": "越秀金融"},
        selected_customer={"id": "cus_101", "account_name": "越秀金融"},
    )

    assert plan is not None
    assert plan.payload["customer_id"] == "cus_101"
    assert plan.payload["retrieval_mode"] == "structured"
    assert "query_text" not in plan.payload


def test_planner_routes_new_crm_read_query_to_work_summary():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(read_query={"type": "WORK_SUMMARY"}),
        content="本月工作总结",
        parsed={},
    )

    assert plan is not None
    assert plan.query_type == "WORK_SUMMARY"
    assert plan.trace_label == "工作总结"
    assert plan.tool_name == "summarize_completed_work"
    assert plan.payload["window"] == "this_month"


def test_planner_defers_customer_scoped_read_until_customer_is_resolved():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(customer={"name_text": "越秀金融", "confidence": 0.95}),
        content="越秀金融下周有哪些任务？",
        parsed={"customer_name": "越秀金融"},
    )

    assert plan is not None
    assert plan.requires_customer_resolution is True
    assert plan.tool_name == ""


def test_planner_uses_selected_customer_public_id_after_resolution():
    plan = AgentReadQueryPlanner().plan(
        semantic_result=semantic_result(customer={"name_text": "越秀金融", "confidence": 0.95}),
        content="越秀金融下周有哪些任务？",
        parsed={"customer_name": "越秀金融"},
        selected_customer={"id": "cus_101", "account_name": "越秀金融"},
    )

    assert plan is not None
    assert plan.requires_customer_resolution is False
    assert plan.payload["customer_id"] == "cus_101"


def test_legacy_customer_query_is_normalized_at_schema_boundary():
    result = AgentSemanticParseResult.model_validate({
        "intent": "CUSTOMER_QUERY",
        "intent_confidence": 0.95,
        "customer": {"name_text": None, "confidence": 0.0},
    })

    assert result.intent == "CRM_READ_QUERY"
