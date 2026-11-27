from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pydantic import ValidationError

from app.services.customer_activity_ai.schemas import (
    FollowUpStructuringResult,
    MeetingStructuringResult,
)
from app.services.customer_activity_ai.structuring_agent import (
    ActivityStructuringAgent,
    ActivityStructuringError,
)


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


def test_structuring_schemas_require_summary_and_content_json():
    with pytest.raises(ValidationError):
        FollowUpStructuringResult.model_validate({"title": "微信跟进", "summary": "只有摘要"})
    with pytest.raises(ValidationError):
        FollowUpStructuringResult.model_validate({"title": "微信跟进", "summary": "只有摘要", "content_json": {}})
    with pytest.raises(ValidationError):
        MeetingStructuringResult.model_validate({"title": "线上会议", "summary": "只有摘要"})


@pytest.mark.asyncio
async def test_follow_up_structuring_rejects_empty_content(monkeypatch):
    from app.services.customer_activity_ai import structuring_agent as module

    monkeypatch.setattr(module.ai_config_crud, "get_config", lambda db, team_id: SimpleNamespace(
        api_host="https://example.com",
        model_name="test-model",
        temperature=0.1,
    ))
    monkeypatch.setattr(module.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "test-key")

    class EmptyContentRuntime:
        async def ainvoke_structured(self, **kwargs: Any):
            return FollowUpStructuringResult.model_validate({
                "title": "微信跟进",
                "summary": "只有摘要",
                "content_json": {"content": "   "},
            })

    agent = ActivityStructuringAgent(runtime=EmptyContentRuntime())
    with pytest.raises(ActivityStructuringError, match="content_json.content"):
        await agent.structure(None, team_id=1, context={
            "current_activity": {
                "activity_category": "FOLLOW_UP",
                "activity_label": "微信跟进",
                "activity_kind": "WECHAT_FOLLOW_UP",
                "source_content": "客户反馈预算 50 万，下周二评审方案。",
                "next_action": "",
                "occurred_at": "2026-11-27T10:00:00",
            },
        })


@pytest.mark.asyncio
async def test_meeting_structuring_rejects_empty_structured_fields(monkeypatch):
    from app.services.customer_activity_ai import structuring_agent as module

    monkeypatch.setattr(module.ai_config_crud, "get_config", lambda db, team_id: SimpleNamespace(
        api_host="https://example.com",
        model_name="test-model",
        temperature=0.1,
    ))
    monkeypatch.setattr(module.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "test-key")

    class EmptyMeetingRuntime:
        async def ainvoke_structured(self, **kwargs: Any):
            return MeetingStructuringResult.model_validate({
                "title": "线上会议",
                "summary": "### 会议要点\n- 讨论私有化部署",
                "content_json": {},
            })

    agent = ActivityStructuringAgent(runtime=EmptyMeetingRuntime())
    with pytest.raises(ActivityStructuringError, match="结构化 content_json"):
        await agent.structure(None, team_id=1, context={
            "current_activity": {
                "activity_category": "MEETING",
                "activity_label": "线上会议",
                "activity_kind": "ONLINE_MEETING",
                "source_content": "讨论了私有化部署架构、安全合规和商务报价。",
                "next_action": "",
                "occurred_at": "2026-11-27T10:00:00",
            },
        })


@pytest.mark.asyncio
async def test_follow_up_structuring_unescapes_single_line_literal_newlines(monkeypatch):
    from app.services.customer_activity_ai import structuring_agent as module

    monkeypatch.setattr(module.ai_config_crud, "get_config", lambda db, team_id: SimpleNamespace(
        api_host="https://example.com",
        model_name="test-model",
        temperature=0.1,
    ))
    monkeypatch.setattr(module.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "test-key")

    class EscapedNewlineRuntime:
        async def ainvoke_structured(self, **kwargs: Any):
            return FollowUpStructuringResult.model_validate({
                "title": "微信跟进",
                "summary": "### 沟通进展\\n- **节奏**：9 月底挂网\\n\\n### 下一步\\n- 周四交材料",
                "content_json": {
                    "content": "### 沟通进展\\n- **节奏**：9 月底挂网\\n\\n### 下一步\\n- 周四交材料",
                },
            })

    agent = ActivityStructuringAgent(runtime=EscapedNewlineRuntime())
    payload = await agent.structure(None, team_id=1, context={
        "current_activity": {
            "activity_category": "FOLLOW_UP",
            "activity_label": "微信跟进",
            "activity_kind": "WECHAT_FOLLOW_UP",
            "source_content": "9月底挂网，周四交材料。",
            "next_action": "",
            "occurred_at": "2026-11-27T10:00:00",
        },
    })

    assert "\\n" not in payload["summary"]
    assert payload["summary"].startswith("### 沟通进展\n- **节奏**")
    assert "\\n" not in payload["content_json"]["content"]
    assert payload["content_json"]["content"].startswith("### 沟通进展\n- **节奏**")
