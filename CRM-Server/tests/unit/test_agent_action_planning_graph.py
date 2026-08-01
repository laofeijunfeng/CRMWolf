"""Action-planning domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.action_planning_graph import (
    ActionPlanningGraphService,
    build_action_planning_graph_config,
    build_action_planning_thread_id,
)
from app.services.agent.schemas import AgentFollowUpQualityResult, AgentMemorySnapshot, AgentSuggestionResult
from tests.unit.test_agent_graph import opportunity_semantic_result, semantic_result


def action_input(**overrides):
    semantic = overrides.pop("semantic_result", semantic_result())
    payload = {
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "今天和越秀金融沟通了项目进展",
        "intent": semantic.intent,
        "parsed": {
            "customer_name": "越秀金融",
            "follow_up_content": "客户反馈项目还在立项评估阶段",
            "original_content": "客户反馈项目还在立项评估阶段",
            "method": "未指定",
            "next_action": "下周三确认进展",
            "next_follow_time_text": "下周三",
            "next_follow_time_iso": "2026-07-29T09:00:00",
        },
        "customer_candidates": [{"id": 101, "account_name": "越秀金融"}],
        "selected_customer": {"id": 101, "account_name": "越秀金融"},
        "business_context": {},
        "semantic": semantic.model_dump(exclude_none=True),
        "semantic_metadata": {"parse_source": "test"},
        "events": [],
        "memory": AgentMemorySnapshot(),
        "semantic_result": semantic,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_action_planning_graph_builds_follow_up_confirmation_event():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(action_input())

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert build_action_planning_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_action_planning:1:2:3"
    )
    assert result["response_route"] == "business_action"
    assert result["business_action_route"] == "customer_activity"
    assert result["response"] == "我识别到客户「越秀金融」的客户活动。请确认是否创建这条客户活动？"
    assert confirmation_events[0]["action"] == "create_customer_activity"
    assert confirmation_events[0]["payload"]["customer_id"] == 101


@pytest.mark.asyncio
async def test_action_planning_graph_routes_customer_activity_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())

    result = await service.run(action_input(
        customer_candidates=[
            {"id": 101, "account_name": "越秀金融"},
            {"id": 102, "account_name": "越秀金融科技"},
        ],
    ))

    choice_events = [event for event in result["events"] if event["event"] == "customer_selection_required"]
    assert result["business_action_route"] == "customer_activity"
    assert choice_events[0]["action"] == "select_customer_for_activity"
    assert choice_events[0]["customers"][1]["id"] == 102


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_lead_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = semantic_result(
        intent="CREATE_LEAD",
        customer={"name_text": None, "confidence": 0.0, "resolution_source": "NONE"},
        lead={"lead_name": "广州睿狐科技"},
        missing_fields=["city", "contact_name", "contact_phone"],
    )

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_LEAD",
        parsed={"lead": {"lead_name": "广州睿狐科技"}},
    ))

    field_events = [event for event in result["events"] if event["event"] == "lead_fields_required"]
    assert result["business_action_route"] == "create_lead"
    assert field_events[0]["action"] == "collect_lead_fields"
    assert field_events[0]["payload"]["missing_fields"] == ["city", "contact_name", "contact_phone"]


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_customer_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = semantic_result(
        intent="CREATE_CUSTOMER",
        customer={"name_text": None, "confidence": 0.0, "resolution_source": "NONE"},
        customer_create={"account_name": "广州睿狐科技"},
        missing_fields=["city"],
    )

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_CUSTOMER",
        parsed={"customer_create": {"account_name": "广州睿狐科技"}},
    ))

    field_events = [event for event in result["events"] if event["event"] == "customer_fields_required"]
    assert result["business_action_route"] == "create_customer"
    assert field_events[0]["action"] == "collect_customer_fields"
    assert field_events[0]["payload"]["missing_fields"] == ["city"]


@pytest.mark.asyncio
async def test_action_planning_graph_resets_events_between_turns_on_same_thread():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())

    first = await service.run(action_input(content="第一轮跟进"))
    second = await service.run(action_input(content="第二轮跟进"))

    assert [event["event"] for event in first["events"]].count("confirmation_required") == 1
    assert [event["event"] for event in second["events"]].count("confirmation_required") == 1
    assert [event["event"] for event in second["events"]].count("final") == 1
    assert len(second["events"]) == len(first["events"])


@pytest.mark.asyncio
async def test_action_planning_graph_routes_low_quality_follow_up_to_form_interrupt_event():
    service = ActionPlanningGraphService()
    quality = AgentFollowUpQualityResult.model_validate({
        "score": 45,
        "passed": False,
        "reason": "缺少明确下一步动作",
        "missing_aspects": ["下一步动作"],
        "supplement_question": "请补充下一步由谁在什么时间做什么。",
        "suggested_revision": None,
        "principle_scores": {},
    })

    result = await service.run(action_input(
        follow_up_quality=quality.model_dump(exclude_none=True),
        follow_up_quality_result=quality,
    ))

    quality_events = [event for event in result["events"] if event["event"] == "follow_up_quality_required"]
    assert result["response"] == "请补充下一步由谁在什么时间做什么。"
    assert result["response_route"] == "follow_up_quality"
    assert "business_action_route" not in result or result["business_action_route"] is None
    assert quality_events[0]["action"] == "collect_follow_up_quality_fields"
    assert quality_events[0]["payload"]["quality"]["score"] == 45
    assert not [event for event in result["events"] if event["event"] == "confirmation_required"]


@pytest.mark.asyncio
async def test_action_planning_graph_attaches_stage_move_as_deferred_next_task():
    service = ActionPlanningGraphService()
    suggestion_result = AgentSuggestionResult.model_validate({
        "summary": "客户表达了签约意向。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进到签约",
            "reason": "张总说今天可以开始签合同了。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "opportunity",
            "related_object_id": 301,
            "execution_payload": {
                "stage_template_id": 9,
                "target_stage_name": "签约",
            },
            "risk_notes": [],
            "confidence": 0.91,
        }],
        "need_user_choice": False,
        "clarification_question": None,
    })

    result = await service.run(action_input(
        business_context={
            "opportunities": {
                "items": [{"id": 301, "opportunity_name": "CRM 项目"}],
            },
        },
        suggestion=suggestion_result.model_dump(exclude_none=True),
        suggestion_result=suggestion_result,
    ))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    next_task = confirmation_events[0]["payload"]["_next_task"]
    assert confirmation_events[0]["action"] == "create_customer_activity"
    assert next_task["action"] == "move_opportunity_stage"
    assert next_task["payload"]["opportunity_id"] == 301
    assert next_task["payload"]["target_stage_name"] == "签约"


@pytest.mark.asyncio
async def test_action_planning_graph_routes_direct_stage_move_to_confirmation():
    service = ActionPlanningGraphService()
    suggestion_result = AgentSuggestionResult.model_validate({
        "summary": "客户表达可以签合同。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进到签约",
            "reason": "张总说今天可以开始签合同。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "opportunity",
            "related_object_id": 301,
            "execution_payload": {
                "stage_template_id": 9,
                "target_stage_name": "签约",
            },
            "risk_notes": [],
            "confidence": 0.91,
        }],
        "need_user_choice": False,
        "clarification_question": None,
    })

    semantic = semantic_result(intent="CUSTOMER_QUERY")
    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CUSTOMER_QUERY",
        parsed={"customer_name": "越秀金融"},
        business_context={
            "opportunities": {
                "items": [{"id": 301, "opportunity_name": "CRM 项目"}],
            },
        },
        suggestion=suggestion_result.model_dump(exclude_none=True),
        suggestion_result=suggestion_result,
    ))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    assert result["action"]["action"] == "move_opportunity_stage"
    assert confirmation_events[0]["action"] == "move_opportunity_stage"
    assert confirmation_events[0]["payload"]["opportunity_id"] == 301


@pytest.mark.asyncio
async def test_action_planning_graph_plans_multi_step_stage_move_to_target_stage():
    service = ActionPlanningGraphService()
    suggestion_result = AgentSuggestionResult.model_validate({
        "summary": "客户表达可以签合同。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进到签约",
            "reason": "张总说今天可以开始签合同。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": [],
            "related_object_type": "opportunity",
            "related_object_id": 301,
            "execution_payload": {
                "stage_template_id": 10,
                "target_stage_name": "签约",
            },
            "risk_notes": [],
            "confidence": 0.91,
        }],
        "need_user_choice": False,
        "clarification_question": None,
    })

    semantic = semantic_result(intent="CUSTOMER_QUERY")
    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CUSTOMER_QUERY",
        parsed={"customer_name": "越秀金融"},
        business_context={
            "opportunities": {
                "items": [{"id": 301, "opportunity_name": "CRM 项目"}],
            },
            "active_opportunity_stage_context": [{
                "opportunity": {"id": 301, "opportunity_name": "CRM 项目", "status": 0, "approval_phase": "approved"},
                "procurement_stages": [
                    {"id": 8, "stage_name": "立项", "sort_order": 1, "is_current": True},
                    {"id": 9, "stage_name": "方案确认", "sort_order": 2, "is_current": False},
                    {"id": 10, "stage_name": "签约", "sort_order": 3, "is_current": False},
                ],
            }],
        },
        suggestion=suggestion_result.model_dump(exclude_none=True),
        suggestion_result=suggestion_result,
    ))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    payload = confirmation_events[0]["payload"]
    assert result["action"]["action"] == "move_opportunity_stage"
    assert payload["stage_template_id"] == 10
    assert payload["target_stage_name"] == "签约"
    assert payload["stage_move_steps"] == [
        {"stage_template_id": 9, "stage_name": "方案确认"},
        {"stage_template_id": 10, "stage_name": "签约"},
    ]
    assert "签约" in result["response"]
    assert "逐阶段推进" not in result["response"]


@pytest.mark.asyncio
async def test_action_planning_graph_attaches_stage_move_selection_as_deferred_next_task():
    service = ActionPlanningGraphService()
    suggestion_result = AgentSuggestionResult.model_validate({
        "summary": "客户表达可以签合同。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进到签约",
            "reason": "张总说今天可以开始签合同。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": ["opportunity_id"],
            "related_object_type": "opportunity",
            "related_object_id": None,
            "execution_payload": {
                "stage_template_id": 9,
                "target_stage_name": "签约",
            },
            "risk_notes": [],
            "confidence": 0.86,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    result = await service.run(action_input(
        business_context={
            "active_opportunity_stage_context": [
                {
                    "opportunity": {"id": 301, "opportunity_name": "CRM 一期", "status": 0, "approval_phase": "approved"},
                    "procurement_stages": [
                        {"id": 8, "stage_name": "商务谈判", "sort_order": 1, "is_current": True},
                        {"id": 9, "stage_name": "签约", "sort_order": 2, "is_current": False},
                    ],
                },
                {
                    "opportunity": {"id": 302, "opportunity_name": "CRM 二期", "status": 0, "approval_phase": "approved"},
                    "procurement_stages": [
                        {"id": 8, "stage_name": "商务谈判", "sort_order": 1, "is_current": True},
                        {"id": 9, "stage_name": "签约", "sort_order": 2, "is_current": False},
                    ],
                },
            ],
        },
        suggestion=suggestion_result.model_dump(exclude_none=True),
        suggestion_result=suggestion_result,
    ))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    next_task = confirmation_events[0]["payload"]["_next_task"]
    assert next_task["action"] == "select_opportunity_for_stage_move"
    assert next_task["opportunities"][0]["opportunity_name"] == "CRM 一期"
    assert next_task["payload"]["stage_template_id"] == 9


@pytest.mark.asyncio
async def test_action_planning_graph_auto_resolves_named_stage_move_candidate():
    service = ActionPlanningGraphService()
    suggestion_result = AgentSuggestionResult.model_validate({
        "summary": "客户表达可以开始 POC。",
        "suggestions": [{
            "action": "MOVE_OPPORTUNITY_STAGE",
            "title": "推进到产品试用",
            "reason": "张总说 CRM 二期今天可以开始 POC。",
            "priority": "high",
            "requires_confirmation": True,
            "missing_fields": ["opportunity_id"],
            "related_object_type": "opportunity",
            "related_object_id": None,
            "execution_payload": {
                "stage_template_id": 12,
                "target_stage_name": "产品试用",
            },
            "risk_notes": [],
            "confidence": 0.88,
        }],
        "need_user_choice": True,
        "clarification_question": None,
    })

    result = await service.run(action_input(
        content="张总说 CRM 二期今天可以开始 POC 了",
        business_context={
            "active_opportunity_stage_context": [
                {
                    "opportunity": {"id": 301, "opportunity_name": "CRM 一期", "status": 0, "approval_phase": "approved"},
                    "procurement_stages": [
                        {"id": 11, "stage_name": "方案交流", "sort_order": 1, "is_current": True},
                        {"id": 12, "stage_name": "产品试用", "sort_order": 2, "is_current": False},
                    ],
                },
                {
                    "opportunity": {"id": 302, "opportunity_name": "CRM 二期", "status": 0, "approval_phase": "approved"},
                    "procurement_stages": [
                        {"id": 11, "stage_name": "方案交流", "sort_order": 1, "is_current": True},
                        {"id": 12, "stage_name": "产品试用", "sort_order": 2, "is_current": False},
                    ],
                },
            ],
        },
        suggestion=suggestion_result.model_dump(exclude_none=True),
        suggestion_result=suggestion_result,
    ))

    confirmation_events = [event for event in result["events"] if event["event"] == "confirmation_required"]
    next_task = confirmation_events[0]["payload"]["_next_task"]
    assert next_task["action"] == "move_opportunity_stage"
    assert next_task["payload"]["opportunity_id"] == 302
    assert next_task["payload"]["target_stage_name"] == "产品试用"
    assert [event for event in result["events"] if event["event"] == "resource_resolution"]


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_opportunity_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = opportunity_semantic_result()

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_OPPORTUNITY",
        parsed={
            "customer_name": "越秀金融",
            "opportunity": {
                "total_amount": 50000,
                "user_count": 100,
                "license_type": "SUBSCRIPTION",
                "subscription_years": 1,
                "purchase_type": None,
                "expected_closing_date": None,
            },
            "missing_opportunity_fields": ["purchase_type", "expected_closing_date"],
        },
        customer_candidates=[{"id": 101, "account_name": "越秀金融"}],
    ))

    field_events = [event for event in result["events"] if event["event"] == "opportunity_fields_required"]
    assert result["business_action_route"] == "create_opportunity"
    assert field_events[0]["action"] == "collect_opportunity_fields"
    assert field_events[0]["payload"]["customer_id"] == 101
    assert field_events[0]["payload"]["missing_fields"] == ["purchase_type", "expected_closing_date"]


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_contact_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = semantic_result(
        intent="CREATE_CONTACT",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        contact={"name": "王总"},
        missing_fields=["mobile", "position", "gender"],
    )

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_CONTACT",
        parsed={
            "customer_name": "越秀金融",
            "contact": {"name": "王总"},
        },
        customer_candidates=[{"id": 101, "account_name": "越秀金融"}],
    ))

    field_events = [event for event in result["events"] if event["event"] == "contact_fields_required"]
    assert result["business_action_route"] == "create_contact"
    assert field_events[0]["action"] == "collect_contact_fields"
    assert field_events[0]["payload"]["customer_id"] == 101
    assert field_events[0]["payload"]["missing_fields"] == ["mobile", "position", "gender"]


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_invoice_title_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = semantic_result(
        intent="CREATE_INVOICE_TITLE",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        invoice_title={"title": "越秀金融科技有限公司"},
        missing_fields=["title_type", "taxpayer_id"],
    )

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_INVOICE_TITLE",
        parsed={
            "customer_name": "越秀金融",
            "invoice_title": {"title": "越秀金融科技有限公司"},
        },
        customer_candidates=[{"id": 101, "account_name": "越秀金融"}],
    ))

    field_events = [event for event in result["events"] if event["event"] == "invoice_title_fields_required"]
    assert result["business_action_route"] == "create_invoice_title"
    assert field_events[0]["action"] == "collect_invoice_title_fields"
    assert field_events[0]["payload"]["customer_id"] == 101
    assert field_events[0]["payload"]["missing_fields"] == ["title_type", "taxpayer_id"]


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_deployment_info_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = semantic_result(
        intent="CREATE_DEPLOYMENT_INFO",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        deployment_info={"deployment_name": "生产环境"},
        missing_fields=["server_address", "authorized_users"],
    )

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_DEPLOYMENT_INFO",
        parsed={
            "customer_name": "越秀金融",
            "deployment_info": {"deployment_name": "生产环境"},
        },
        customer_candidates=[{"id": 101, "account_name": "越秀金融"}],
    ))

    field_events = [
        event
        for event in result["events"]
        if event["event"] == "deployment_info_fields_required"
    ]
    assert result["business_action_route"] == "create_deployment_info"
    assert field_events[0]["action"] == "collect_deployment_info_fields"
    assert field_events[0]["payload"]["customer_id"] == 101
    assert field_events[0]["payload"]["missing_fields"] == ["server_address", "authorized_users"]


@pytest.mark.asyncio
async def test_action_planning_graph_routes_create_customer_member_through_domain_subgraph():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    semantic = semantic_result(
        intent="CREATE_CUSTOMER_MEMBER",
        customer={"name_text": "越秀金融", "confidence": 0.95},
        customer_member={},
        missing_fields=["user_name"],
    )

    result = await service.run(action_input(
        semantic_result=semantic,
        intent="CREATE_CUSTOMER_MEMBER",
        parsed={
            "customer_name": "越秀金融",
            "customer_member": {},
        },
        customer_candidates=[{"id": 101, "account_name": "越秀金融"}],
        business_context={"member_candidates": {"items": []}},
    ))

    field_events = [
        event
        for event in result["events"]
        if event["event"] == "customer_member_fields_required"
    ]
    assert result["business_action_route"] == "create_customer_member"
    assert field_events[0]["action"] == "collect_customer_member_fields"
    assert field_events[0]["payload"]["customer_id"] == 101
    assert field_events[0]["payload"]["missing_fields"] == ["user_name"]


@pytest.mark.asyncio
async def test_action_planning_graph_checkpoints_json_state_not_runtime_objects():
    service = ActionPlanningGraphService(checkpointer=InMemorySaver())
    suggestion_result = AgentSuggestionResult.model_validate({
        "summary": "无需动作。",
        "suggestions": [],
        "need_user_choice": False,
        "clarification_question": None,
    })

    await service.run(action_input(
        suggestion=suggestion_result.model_dump(exclude_none=True),
        suggestion_result=suggestion_result,
    ))
    snapshot = await service._graph.aget_state(build_action_planning_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))

    assert snapshot.values["semantic"]["intent"] == "CUSTOMER_ACTIVITY"
    assert "semantic_result" not in snapshot.values
    assert "memory" not in snapshot.values
    assert "follow_up_quality_result" not in snapshot.values
    assert "suggestion_result" not in snapshot.values
