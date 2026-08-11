"""Confirmed AI-assisted lead write service tests."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models.agent import AgentIdempotencyStatus
from app.models.lead import FollowUpMethod
from app.services import lead_ai_confirmed_write_service as write_module
from app.services.lead_ai_confirmed_write_service import LeadAIConfirmedWriteService


class _FakeIdempotencyCRUD:
    def __init__(self, record=None) -> None:
        self.record = record or SimpleNamespace(status=AgentIdempotencyStatus.PENDING, result_json=None)
        self.created = []
        self.updated = []

    def get_or_create(self, db, obj_in):  # noqa: ANN001
        self.created.append(obj_in)
        return self.record

    def update(self, db, db_obj, obj_in):  # noqa: ANN001
        self.updated.append(obj_in)
        if obj_in.status is not None:
            db_obj.status = obj_in.status
        if obj_in.result_json is not None:
            db_obj.result_json = obj_in.result_json
        if obj_in.error_message is not None:
            db_obj.error_message = obj_in.error_message
        return db_obj


class _FakeLeadFollowUpCRUD:
    def __init__(self) -> None:
        self.created = []
        self.by_id = {}

    def create(self, **kwargs):  # noqa: ANN003
        self.created.append(kwargs)
        follow_up = SimpleNamespace(
            id=8001,
            team_id=kwargs["team_id"],
            content=kwargs["obj_in"].content,
            method=kwargs["obj_in"].method,
            next_follow_time=kwargs["obj_in"].next_follow_time,
            next_action=kwargs["obj_in"].next_action,
        )
        self.by_id[follow_up.id] = follow_up
        return follow_up

    def get_by_id(self, db, follow_up_id):  # noqa: ANN001, ANN201
        return self.by_id.get(follow_up_id)


@pytest.mark.asyncio
async def test_confirmed_ai_lead_follow_up_uses_agent_temporal_resolver(monkeypatch):
    fake_idempotency = _FakeIdempotencyCRUD()
    fake_follow_up = _FakeLeadFollowUpCRUD()
    monkeypatch.setattr(write_module, "agent_idempotency_key_crud", fake_idempotency)
    monkeypatch.setattr(write_module, "lead_follow_up_crud", fake_follow_up)
    monkeypatch.setattr(write_module, "business_now", lambda: datetime(2026, 8, 10, 0, 45, 25))

    result = await LeadAIConfirmedWriteService().create_lead_follow_up(
        db=SimpleNamespace(),
        lead_id=12,
        lead_public_id="lead_12",
        team_id=1,
        user_id=1,
        content="客户有明确兴趣",
        method=FollowUpMethod.OTHER,
        next_action="确认试用反馈",
        next_follow_time_text="2 个月后",
    )

    assert result.follow_up.id == 8001
    assert result.next_follow_time_iso == "2026-10-10T09:00:00"
    created_payload = fake_follow_up.created[0]["obj_in"]
    assert created_payload.next_follow_time == datetime(2026, 10, 10, 9, 0, 0)
    assert fake_idempotency.updated[0].status == AgentIdempotencyStatus.SUCCESS
    assert fake_idempotency.updated[0].result_json["source_type"] == "manual_ai_confirmed"


@pytest.mark.asyncio
async def test_confirmed_ai_lead_follow_up_replays_successful_idempotency(monkeypatch):
    existing_follow_up = SimpleNamespace(id=8001, team_id=1)
    fake_record = SimpleNamespace(
        status=AgentIdempotencyStatus.SUCCESS,
        result_json={"follow_up_id": 8001, "next_follow_time": "2026-10-10T09:00:00"},
    )
    fake_idempotency = _FakeIdempotencyCRUD(fake_record)
    fake_follow_up = _FakeLeadFollowUpCRUD()
    fake_follow_up.by_id[8001] = existing_follow_up
    monkeypatch.setattr(write_module, "agent_idempotency_key_crud", fake_idempotency)
    monkeypatch.setattr(write_module, "lead_follow_up_crud", fake_follow_up)
    monkeypatch.setattr(write_module, "business_now", lambda: datetime(2026, 8, 10, 0, 45, 25))

    result = await LeadAIConfirmedWriteService().create_lead_follow_up(
        db=SimpleNamespace(),
        lead_id=12,
        lead_public_id="lead_12",
        team_id=1,
        user_id=1,
        content="客户有明确兴趣",
        method=FollowUpMethod.OTHER,
        next_action="确认试用反馈",
        next_follow_time_text="2 个月后",
    )

    assert result.follow_up is existing_follow_up
    assert result.idempotent_replay is True
    assert fake_follow_up.created == []
