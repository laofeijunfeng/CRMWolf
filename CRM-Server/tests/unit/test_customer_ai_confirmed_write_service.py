"""Confirmed AI-assisted CRM write service tests."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models.agent import AgentIdempotencyStatus
from app.services import customer_ai_confirmed_write_service as write_module
from app.services.customer_ai_confirmed_write_service import CustomerAIConfirmedWriteService


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


class _FakeActivityCRUD:
    def __init__(self) -> None:
        self.created = []
        self.by_id = {}

    def create(self, **kwargs):  # noqa: ANN003
        self.created.append(kwargs)
        activity = SimpleNamespace(
            id=9001,
            activity_kind=kwargs["obj_in"].activity_kind,
            next_follow_time=kwargs["obj_in"].next_follow_time,
            next_action=kwargs["obj_in"].next_action,
        )
        self.by_id[activity.id] = activity
        return activity

    def get_by_id(self, db, activity_id, team_id=None):  # noqa: ANN001, ANN201
        return self.by_id.get(activity_id)


class _FakeProcessingService:
    def __init__(self) -> None:
        self.post_commit_calls = []
        self.processing_calls = []

    async def trigger_post_commit_workflow(self, **kwargs):  # noqa: ANN003
        self.post_commit_calls.append(kwargs)

    async def trigger_processing(self, activity_id, team_id):  # noqa: ANN001
        self.processing_calls.append({"activity_id": activity_id, "team_id": team_id})


@pytest.mark.asyncio
async def test_confirmed_ai_write_uses_agent_temporal_resolver_and_post_commit(monkeypatch):
    fake_idempotency = _FakeIdempotencyCRUD()
    fake_activity = _FakeActivityCRUD()
    fake_processing = _FakeProcessingService()
    monkeypatch.setattr(write_module, "agent_idempotency_key_crud", fake_idempotency)
    monkeypatch.setattr(write_module, "customer_activity_crud", fake_activity)
    monkeypatch.setattr(write_module, "customer_activity_processing_service", fake_processing)
    monkeypatch.setattr(write_module, "business_now", lambda: datetime(2026, 8, 10, 0, 45, 25))

    result = await CustomerAIConfirmedWriteService().create_customer_activity(
        db=SimpleNamespace(),
        customer_id=144,
        customer_public_id="cus_144",
        team_id=1,
        user_id=1,
        content="等 2 个月后再找客户确认 CLI+Skill 使用情况",
        method="微信",
        next_action="确认 CLI+Skill 使用情况",
        next_follow_time_text="2 个月后",
        operator_name="Eddie",
    )

    assert result.activity.id == 9001
    assert result.next_follow_time_iso == "2026-10-10T09:00:00"
    created_payload = fake_activity.created[0]["obj_in"]
    assert created_payload.next_follow_time == datetime(2026, 10, 10, 9, 0, 0)
    assert created_payload.next_follow_time_source == "AI_EXTRACTED"
    assert fake_processing.post_commit_calls[0]["activity_id"] == 9001
    assert fake_processing.processing_calls == [{"activity_id": 9001, "team_id": 1}]
    assert fake_idempotency.updated[0].status == AgentIdempotencyStatus.SUCCESS
    assert fake_idempotency.updated[0].result_json["source_type"] == "manual_ai_confirmed"


@pytest.mark.asyncio
async def test_confirmed_ai_write_replays_successful_idempotency_without_duplicate_create(monkeypatch):
    existing_activity = SimpleNamespace(id=9001, activity_kind="WECHAT_FOLLOW_UP")
    fake_record = SimpleNamespace(
        status=AgentIdempotencyStatus.SUCCESS,
        result_json={"activity_id": 9001, "next_follow_time": "2026-10-10T09:00:00"},
    )
    fake_idempotency = _FakeIdempotencyCRUD(fake_record)
    fake_activity = _FakeActivityCRUD()
    fake_activity.by_id[9001] = existing_activity
    fake_processing = _FakeProcessingService()
    monkeypatch.setattr(write_module, "agent_idempotency_key_crud", fake_idempotency)
    monkeypatch.setattr(write_module, "customer_activity_crud", fake_activity)
    monkeypatch.setattr(write_module, "customer_activity_processing_service", fake_processing)
    monkeypatch.setattr(write_module, "business_now", lambda: datetime(2026, 8, 10, 0, 45, 25))

    result = await CustomerAIConfirmedWriteService().create_customer_activity(
        db=SimpleNamespace(),
        customer_id=144,
        customer_public_id="cus_144",
        team_id=1,
        user_id=1,
        content="等 2 个月后再找客户确认 CLI+Skill 使用情况",
        method="微信",
        next_action="确认 CLI+Skill 使用情况",
        next_follow_time_text="2 个月后",
    )

    assert result.activity is existing_activity
    assert result.idempotent_replay is True
    assert fake_activity.created == []
    assert fake_processing.post_commit_calls == []
    assert fake_processing.processing_calls == []
