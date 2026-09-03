"""Safety and fallback behavior for LLM-assisted resource disambiguation."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.agent.workflow.contracts import WorkflowRuntimeContext
from app.services.agent.workflow.planning import CRMWorkflowPlanner


class StaticRanker:
    def __init__(self, rankings: object = None, *, error: Exception | None = None) -> None:
        self.rankings = rankings if rankings is not None else []
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def rank_resource_candidates(self, db: object, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.rankings


CANDIDATES = [
    {"id": 1, "name": "星云企业版采购", "current_stage": "需求确认"},
    {"id": 2, "name": "星云数据平台采购", "current_stage": "方案评估"},
]


async def select(rankings: object, *, error: Exception | None = None) -> dict[str, object] | None:
    ranker = StaticRanker(rankings, error=error)
    planner = CRMWorkflowPlanner(resource_ranker=ranker)
    selected = await planner._select_semantic_resource(
        runtime=WorkflowRuntimeContext(db=object()),
        user_message="推进企业版那个商机",
        resource_kind="opportunity",
        action_name="MOVE_OPPORTUNITY_STAGE",
        target={"customer_name": "上海星云科技有限公司"},
        candidates=CANDIDATES,
        team_id=1,
        current_date=date(2026, 9, 3),
    )
    return selected


@pytest.mark.asyncio
async def test_high_confidence_clear_winner_is_selected() -> None:
    selected = await select(
        [
            {"resource_id": 1, "confidence": 0.97},
            {"resource_id": 2, "confidence": 0.52},
        ]
    )

    assert selected == CANDIDATES[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rankings",
    [
        [{"resource_id": 1, "confidence": 0.89}],
        [
            {"resource_id": 1, "confidence": 0.94},
            {"resource_id": 2, "confidence": 0.88},
        ],
        [{"resource_id": 99, "confidence": 0.99}],
        [{"resource_id": 1, "confidence": float("nan")}],
        "not-a-list",
    ],
)
async def test_uncertain_or_invalid_output_falls_back_without_selection(rankings: object) -> None:
    assert await select(rankings) is None


@pytest.mark.asyncio
async def test_ranker_failure_falls_back_to_existing_signed_choice() -> None:
    assert await select([], error=RuntimeError("provider unavailable")) is None


@pytest.mark.asyncio
async def test_single_candidate_does_not_call_ranker() -> None:
    ranker = StaticRanker([{"resource_id": 1, "confidence": 1.0}])
    planner = CRMWorkflowPlanner(resource_ranker=ranker)

    selected = await planner._select_semantic_resource(
        runtime=WorkflowRuntimeContext(db=object()),
        user_message="推进这个商机",
        resource_kind="opportunity",
        action_name="MOVE_OPPORTUNITY_STAGE",
        target={},
        candidates=[CANDIDATES[0]],
        team_id=1,
        current_date=date(2026, 9, 3),
    )

    assert selected is None
    assert ranker.calls == []
