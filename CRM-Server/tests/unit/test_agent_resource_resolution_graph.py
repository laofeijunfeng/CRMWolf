"""Reusable resource-resolution LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.resource_resolution_graph import (
    ResourceResolutionGraphService,
    build_resource_resolution_thread_id,
)
from app.services.agent.state import ResourceResolutionGraphState
from app.services.agent.types import JSONDict


@pytest.mark.asyncio
async def test_resource_resolution_graph_selects_explicitly_named_candidate():
    service = ResourceResolutionGraphService(checkpointer=InMemorySaver())

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "resource_kind": "opportunity",
        "action_name": "move_opportunity_stage",
        "content": "张总说 CRM 二期今天可以开始 POC 了",
        "target": {"target_stage_name": "产品试用", "stage_template_id": 12},
        "candidates": [
            {"id": 301, "opportunity_name": "CRM 一期", "stage_move_steps": [{"stage_template_id": 12}]},
            {"id": 302, "opportunity_name": "CRM 二期", "stage_move_steps": [{"stage_template_id": 12}]},
        ],
    })

    assert build_resource_resolution_thread_id(
        team_id=1,
        user_id=2,
        session_id=3,
        resource_kind="opportunity",
        action_name="move_opportunity_stage",
    ) == "crm_agent_resource_resolution:1:2:3:opportunity:move_opportunity_stage"
    assert result["resolution_status"] == "selected"
    assert result["selected_candidate"]["id"] == 302
    assert result["selected_candidate"]["confidence"] >= 0.82


@pytest.mark.asyncio
async def test_resource_resolution_graph_asks_user_when_candidates_are_close():
    service = ResourceResolutionGraphService(checkpointer=InMemorySaver())

    result = await service.run({
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "resource_kind": "opportunity",
        "action_name": "move_opportunity_stage",
        "content": "张总说今天可以开始 POC 了",
        "target": {"target_stage_name": "产品试用", "stage_template_id": 12},
        "candidates": [
            {"id": 301, "opportunity_name": "CRM 一期", "stage_move_steps": [{"stage_template_id": 12}]},
            {"id": 302, "opportunity_name": "CRM 二期", "stage_move_steps": [{"stage_template_id": 12}]},
        ],
    })

    assert result["resolution_status"] == "needs_user_choice"
    assert "selected_candidate" not in result


@pytest.mark.asyncio
async def test_resource_resolution_graph_accepts_model_ranker_but_keeps_candidate_guardrail():
    service = ResourceResolutionGraphService(checkpointer=InMemorySaver())

    async def ranker(state: ResourceResolutionGraphState) -> list[JSONDict]:
        return [
            {"resource_id": 999, "confidence": 0.99, "evidence": ["无效候选"], "risk_notes": []},
            {"resource_id": 302, "confidence": 0.91, "evidence": ["模型判断二期更匹配"], "risk_notes": []},
            {"resource_id": 301, "confidence": 0.4, "evidence": [], "risk_notes": []},
        ]

    result = await service.run(
        {
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "resource_kind": "opportunity",
            "action_name": "move_opportunity_stage",
            "content": "张总说今天可以开始 POC 了",
            "target": {"target_stage_name": "产品试用", "stage_template_id": 12},
            "candidates": [
                {"id": 301, "opportunity_name": "CRM 一期", "stage_move_steps": [{"stage_template_id": 12}]},
                {"id": 302, "opportunity_name": "CRM 二期", "stage_move_steps": [{"stage_template_id": 12}]},
            ],
        },
        ranker=ranker,
    )

    assert result["resolution_status"] == "selected"
    assert result["selected_candidate"]["id"] == 302
