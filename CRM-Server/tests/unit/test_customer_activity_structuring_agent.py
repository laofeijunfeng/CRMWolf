from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.customer_activity_ai.schemas import FollowUpStructuringResult
from app.services.customer_activity_ai.structuring_agent import ActivityStructuringAgent


class FakeRuntime:
    def __init__(self) -> None:
        self.user_prompt = ""

    async def ainvoke_structured(self, **kwargs: Any):
        self.user_prompt = kwargs["user_prompt"]
        return FollowUpStructuringResult.model_validate({
            "title": "电话跟进",
            "summary": "客户反馈项目还在立项评估阶段。",
            "next_action": "下周三找王总确认进展",
            "content_json": {
                "content": (
                    "活动类型：微信跟进（WECHAT_FOLLOW_UP）。发生时间：2026-07-30T19:53:46。"
                    "今天和睿狐科技的王总沟通了项目进展。客户反馈目前还在立项评估阶段，"
                    "当前先持续跟进，计划下周三再找王总确认进展。已有下一步未填写。"
                ),
                "customer_feedback": "客户反馈还在立项评估阶段",
                "current_progress": "立项评估阶段",
                "risks": [],
                "next_action": "下周三找王总确认进展",
                "next_follow_time_text": "下周三",
            },
        })


@pytest.mark.asyncio
async def test_follow_up_structuring_strips_prompt_metadata_from_content(monkeypatch):
    from app.services.customer_activity_ai import structuring_agent as module

    monkeypatch.setattr(module.ai_config_crud, "get_config", lambda db, team_id: SimpleNamespace(
        api_host="https://example.com",
        model_name="test-model",
        temperature=0.1,
    ))
    monkeypatch.setattr(module.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "test-key")

    source_content = "今天和睿狐科技的王总沟通了下项目进展，客户反馈还在立项评估阶段，先持续跟进，下周三再找王总确认进展"
    runtime = FakeRuntime()
    agent = ActivityStructuringAgent(runtime=runtime)

    result = await agent.structure(None, team_id=1, context={
        "current_activity": {
            "activity_category": "FOLLOW_UP",
            "activity_label": "电话跟进",
            "activity_kind": "PHONE_FOLLOW_UP",
            "source_content": source_content,
            "next_action": "",
            "occurred_at": "2026-07-30T10:00:00",
        },
    })

    assert result["content_json"]["content"] == "今天和睿狐科技的王总沟通了项目进展。客户反馈目前还在立项评估阶段，当前先持续跟进，计划下周三再找王总确认进展"
    assert result["content_json"]["current_progress"] == "立项评估阶段"
    assert result["next_action"] == "下周三找王总确认进展"
    assert "<metadata>" in runtime.user_prompt
    assert "<raw_activity>" in runtime.user_prompt
