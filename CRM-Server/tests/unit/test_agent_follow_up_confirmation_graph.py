"""Tests for the follow-up confirmation domain subgraph boundary."""

import pytest

from app.services.agent.follow_up_confirmation_graph import FollowUpConfirmationGraphService


class FakeChannelService:
    def __init__(self):
        self.prepare_calls = []
        self.list_calls = []
        self.resolve_calls = []
        self.project_calls = []

    def prepare_case_prompt_by_public_ids(
        self,
        db,
        *,
        team_id,
        user_id,
        case_public_ids,
        interaction_scope,
    ):
        self.prepare_calls.append({
            "db": db,
            "team_id": team_id,
            "user_id": user_id,
            "case_public_ids": case_public_ids,
            "interaction_scope": interaction_scope,
        })
        if case_public_ids == ["fuc_inbox"]:
            return {
                "event": "follow_up_task_confirmation_case_prompt",
                "case_public_id": "fuc_inbox",
                "interaction": {"payload": {"case_public_id": "fuc_inbox"}},
            }
        return None

    def list_pending_cases(self, db, *, team_id, user_id, skip=0, limit=20):
        self.list_calls.append({
            "db": db,
            "team_id": team_id,
            "user_id": user_id,
            "skip": skip,
            "limit": limit,
        })
        return {
            "items": [{"public_id": "fuc_inbox"}],
            "total": 1,
            "skip": skip,
            "limit": limit,
        }

    def resolve_reply_event(self, db, *, team_id, user_id, case_public_id, reply_text):
        self.resolve_calls.append({
            "db": db,
            "team_id": team_id,
            "user_id": user_id,
            "case_public_id": case_public_id,
            "reply_text": reply_text,
        })
        return {"event": "follow_up_task_confirmation_resolved", "case_public_id": case_public_id}

    def mark_projection_projected(self, db, *, team_id, prompt_key):
        self.project_calls.append({"db": db, "team_id": team_id, "prompt_key": prompt_key})
        return {"status": "PROJECTED"}


@pytest.mark.asyncio
async def test_prepare_compensates_from_durable_owner_inbox_when_current_turn_has_no_case_ids():
    channel = FakeChannelService()
    service = FollowUpConfirmationGraphService(channel_service=channel)
    db = object()

    event = await service.prepare(
        db=db,
        team_id=2,
        user_id=3,
        case_public_ids=[],
        interaction_scope="crm_agent:2:3:4:abc",
        include_owner_inbox_fallback=True,
    )

    assert event["case_public_id"] == "fuc_inbox"
    assert channel.list_calls == [{
        "db": db,
        "team_id": 2,
        "user_id": 3,
        "skip": 0,
        "limit": 1,
    }]
    assert [call["case_public_ids"] for call in channel.prepare_calls] == [[], ["fuc_inbox"]]


@pytest.mark.asyncio
async def test_resolve_delegates_mutation_to_channel_application_boundary():
    channel = FakeChannelService()
    service = FollowUpConfirmationGraphService(channel_service=channel)
    db = object()

    event = await service.resolve(
        db=db,
        team_id=2,
        user_id=3,
        case_public_id="fuc_inbox",
        reply_text="已完成",
    )

    assert event["event"] == "follow_up_task_confirmation_resolved"
    assert channel.resolve_calls == [{
        "db": db,
        "team_id": 2,
        "user_id": 3,
        "case_public_id": "fuc_inbox",
        "reply_text": "已完成",
    }]
