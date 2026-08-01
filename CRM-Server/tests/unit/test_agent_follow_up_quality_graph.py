"""Follow-up quality domain LangGraph tests."""

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from app.services.agent.follow_up_quality_graph import (
    FollowUpQualityGraphService,
    build_follow_up_quality_graph_config,
    build_follow_up_quality_thread_id,
)
from app.services.agent.schemas import AgentFollowUpQualityResult
from tests.unit.test_agent_graph import FakeMemoryService, semantic_result


class FakeFollowUpQualityEvaluator:
    def __init__(self, score=80, passed=True):
        self.calls = []
        self.score = score
        self.passed = passed

    async def evaluate_with_metadata(self, db, *, team_id, user_message, semantic_result, memory=None, current_date=None):
        self.calls.append({
            "db": db,
            "team_id": team_id,
            "user_message": user_message,
            "semantic_result": semantic_result,
            "memory": memory,
            "current_date": current_date,
        })
        score = self.score
        passed = self.passed

        class Envelope:
            result = AgentFollowUpQualityResult.model_validate({
                "score": score,
                "passed": passed,
                "reason": "质量达标" if passed else "缺少明确下一步动作",
                "missing_aspects": [] if passed else ["下一步动作"],
                "supplement_question": None if passed else "请补充下一步由谁在什么时间做什么。",
                "suggested_revision": None,
                "principle_scores": {},
            })
            quality_source = "test_follow_up_quality_graph"
            model = "test-model"
            fallback_reason = None
            fallback_error = None

        return Envelope()


@pytest.mark.asyncio
async def test_follow_up_quality_graph_evaluates_and_checkpoints_json_state():
    evaluator = FakeFollowUpQualityEvaluator(score=72, passed=True)
    service = FollowUpQualityGraphService(
        follow_up_quality_evaluator=evaluator,
        checkpointer=InMemorySaver(),
    )
    memory = FakeMemoryService().load_snapshot(
        object(),
        team_id=1,
        user_id=2,
        session_id=3,
        session_context={},
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "今天和越秀金融沟通了项目进展",
        "current_date": "2026-07-31",
        "semantic_result": semantic_result(),
        "memory": memory,
        "has_single_customer": True,
        "has_memory_customer": False,
        "events": [],
    })
    snapshot = await service._graph.aget_state(build_follow_up_quality_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
    ))

    assert build_follow_up_quality_thread_id(team_id=1, user_id=2, session_id=3) == (
        "crm_agent_follow_up_quality:1:2:3"
    )
    assert evaluator.calls[0]["team_id"] == 1
    assert evaluator.calls[0]["current_date"].isoformat() == "2026-07-31"
    assert result["follow_up_quality_result"].score == 72
    assert snapshot.values["follow_up_quality"]["score"] == 72
    assert snapshot.values["follow_up_quality_metadata"]["quality_source"] == "test_follow_up_quality_graph"
    assert "follow_up_quality_result" not in snapshot.values
    assert "memory" not in snapshot.values
    assert "semantic_result" not in snapshot.values


@pytest.mark.asyncio
async def test_follow_up_quality_graph_skips_without_single_customer():
    evaluator = FakeFollowUpQualityEvaluator(score=45, passed=False)
    service = FollowUpQualityGraphService(
        follow_up_quality_evaluator=evaluator,
        checkpointer=InMemorySaver(),
    )

    result = await service.run({
        "db": object(),
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "content": "今天沟通了项目进展",
        "current_date": "2026-07-31",
        "semantic_result": semantic_result(),
        "has_single_customer": False,
        "has_memory_customer": False,
        "events": [],
    })

    assert evaluator.calls == []
    assert result["quality_evaluation_requested"] is False
    assert result["quality_skip_reason"] == "missing_single_customer"
    assert result["follow_up_quality"] == {}
