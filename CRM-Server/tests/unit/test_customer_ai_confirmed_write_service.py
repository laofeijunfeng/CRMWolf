"""Confirmed AI-assisted CRM write service tests."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models.agent import AgentIdempotencyStatus
from app.services import customer_ai_confirmed_write_service as write_module
from app.services.customer_activity_post_commit_job_service import CustomerActivityPostCommitJobRequest
from app.services.customer_activity_write_service import CustomerActivityWriteResult
from app.services.customer_ai_confirmed_write_service import CustomerAIConfirmedWriteService
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEvent,
    CustomerIntelligenceSource,
)
from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest


class _FakeIdempotencyCRUD:
    def __init__(self, record=None) -> None:
        self.record = record or SimpleNamespace(status=AgentIdempotencyStatus.PENDING, result_json=None)
        self.created = []
        self.updated = []

    def get_or_create(self, db, obj_in, *, commit=True):  # noqa: ANN001
        self.created.append({"obj_in": obj_in, "commit": commit})
        return self.record

    def get_by_action_key(self, db, team_id, user_id, action_key):  # noqa: ANN001
        return self.record

    def update(self, db, db_obj, obj_in, *, commit=True):  # noqa: ANN001
        self.updated.append({"obj_in": obj_in, "commit": commit})
        if obj_in.status is not None:
            db_obj.status = obj_in.status
        if obj_in.result_json is not None:
            db_obj.result_json = obj_in.result_json
        if obj_in.error_message is not None:
            db_obj.error_message = obj_in.error_message
        return db_obj


class _FakeActivityCRUD:
    def __init__(self) -> None:
        self.by_id = {}

    def get_by_id(self, db, activity_id, team_id=None):  # noqa: ANN001, ANN201
        return self.by_id.get(activity_id)


class _FakeActivityWriteService:
    def __init__(self, *, activity=None, intelligence_request=None) -> None:
        self.activity = activity or SimpleNamespace(
            id=9001,
            customer_id=144,
            post_commit_revision=2,
            activity_kind="WECHAT_FOLLOW_UP",
            next_follow_time=None,
            next_action=None,
        )
        self.intelligence_request = intelligence_request or _intelligence_request()
        self.create_calls = []
        self.kick_calls = []

    def create(self, db, *, before_commit=None, **kwargs):  # noqa: ANN001, ANN003
        self.create_calls.append(kwargs)
        result = CustomerActivityWriteResult(
            activity=self.activity,
            activity_revision=2,
            post_commit_job=CustomerActivityPostCommitJobRequest(job_public_id="pcj_exact", team_id=1),
            customer_intelligence_request=self.intelligence_request,
        )
        if before_commit is not None:
            before_commit(result)
        return result

    def kick(self, result):  # noqa: ANN001
        self.kick_calls.append(result)


class _FakeProcessingService:
    def __init__(self) -> None:
        self.processing_calls = []

    async def trigger_processing(self, activity_id, team_id):  # noqa: ANN001
        self.processing_calls.append({"activity_id": activity_id, "team_id": team_id})


class _FakeRunService:
    def __init__(self, run=None) -> None:
        self.run = run
        self.calls = []

    def get_by_request_id(self, db, *, team_id, request_id):  # noqa: ANN001
        self.calls.append({"team_id": team_id, "request_id": request_id})
        return self.run


class _FakeEventService:
    def from_dict(self, payload):  # noqa: ANN001
        return CustomerIntelligenceEvent(
            event_key=str(payload["event_key"]),
            trigger_type="customer_activity_created",
            tenant_id=int(payload["tenant_id"]),
            team_id=int(payload["team_id"]),
            customer_id=int(payload["customer_id"]),
            occurred_at=None,
            source=CustomerIntelligenceSource(
                source_type="customer_activity",
                source_object_id="9001",
            ),
        )


def _intelligence_request() -> CustomerIntelligenceCommittedEventRequest:
    event = CustomerIntelligenceEvent(
        event_key="activity-event-exact",
        trigger_type="customer_activity_created",
        tenant_id=1,
        team_id=1,
        customer_id=144,
        occurred_at=datetime(2026, 8, 10, 9, 0, 0),
        source=CustomerIntelligenceSource(
            source_type="customer_activity",
            source_object_id="9001",
            business_object_type="customer_activity",
            business_object_id="9001",
        ),
        summary="微信跟进",
        payload={"activity_revision": 2},
        actor_id="1",
    )
    return CustomerIntelligenceCommittedEventRequest(
        request_id="business-event-customer_activity_created-exact",
        event=event,
        scope="brief",
    )


@pytest.mark.asyncio
async def test_confirmed_ai_write_uses_transactional_write_seam_and_persists_full_durable_snapshot(monkeypatch):
    fake_idempotency = _FakeIdempotencyCRUD()
    fake_write = _FakeActivityWriteService()
    fake_processing = _FakeProcessingService()
    monkeypatch.setattr(write_module, "business_now", lambda: datetime(2026, 8, 10, 0, 45, 25))

    result = await CustomerAIConfirmedWriteService(
        idempotency_crud=fake_idempotency,
        activity_write_service=fake_write,
        processing_service=fake_processing,
    ).create_customer_activity(
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
    created_payload = fake_write.create_calls[0]["obj_in"]
    assert created_payload.next_follow_time == datetime(2026, 10, 10, 9, 0, 0)
    assert created_payload.next_follow_time_source == "AI_EXTRACTED"
    assert fake_write.kick_calls == [result.durable_work]
    assert fake_processing.processing_calls == [{"activity_id": 9001, "team_id": 1}]
    assert fake_idempotency.created[0]["commit"] is False
    update = fake_idempotency.updated[0]
    assert update["commit"] is False
    assert update["obj_in"].status == AgentIdempotencyStatus.SUCCESS
    snapshot = update["obj_in"].result_json
    assert snapshot["activity_revision"] == 2
    assert snapshot["post_commit_job_public_id"] == "pcj_exact"
    assert snapshot["customer_intelligence_request_id"] == result.durable_work.customer_intelligence_request.request_id
    assert snapshot["customer_intelligence_scope"] == "brief"
    assert snapshot["customer_intelligence_event"]["customer_id"] == 144


@pytest.mark.asyncio
async def test_confirmed_ai_write_replays_exact_durable_metadata_without_recreating_or_kicking(monkeypatch):
    existing_activity = SimpleNamespace(
        id=9001,
        customer_id=144,
        post_commit_revision=2,
        activity_kind="WECHAT_FOLLOW_UP",
    )
    request_id = "business-event-customer_activity_created-exact"
    fake_record = SimpleNamespace(
        status=AgentIdempotencyStatus.SUCCESS,
        result_json={
            "activity_id": 9001,
            "activity_revision": 2,
            "post_commit_job_public_id": "pcj_exact",
            "customer_intelligence_request_id": request_id,
            "customer_intelligence_scope": "brief",
            "customer_intelligence_event": {"event_key": "activity-event-exact"},
            "next_follow_time": "2026-10-10T09:00:00",
        },
    )
    fake_idempotency = _FakeIdempotencyCRUD(fake_record)
    fake_activity = _FakeActivityCRUD()
    fake_activity.by_id[9001] = existing_activity
    fake_write = _FakeActivityWriteService(activity=existing_activity)
    fake_processing = _FakeProcessingService()
    fake_run = _FakeRunService(
        SimpleNamespace(
            request_id=request_id,
            team_id=1,
            customer_id=144,
            scope="brief",
            event_json={
                "event_key": "activity-event-exact",
                "tenant_id": 1,
                "team_id": 1,
                "customer_id": 144,
            },
        )
    )
    monkeypatch.setattr(write_module, "business_now", lambda: datetime(2026, 8, 10, 0, 45, 25))

    result = await CustomerAIConfirmedWriteService(
        idempotency_crud=fake_idempotency,
        activity_crud=fake_activity,
        activity_write_service=fake_write,
        processing_service=fake_processing,
        intelligence_run_service=fake_run,
        intelligence_event_service=_FakeEventService(),
    ).create_customer_activity(
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
    assert result.durable_work is not None
    assert result.durable_work.activity_revision == 2
    assert result.durable_work.post_commit_job.job_public_id == "pcj_exact"
    assert result.durable_work.customer_intelligence_request.request_id == request_id
    assert result.durable_work.customer_intelligence_request.kick_required is False
    assert fake_run.calls == [{"team_id": 1, "request_id": request_id}]
    assert fake_write.create_calls == []
    assert fake_write.kick_calls == []
    assert fake_processing.processing_calls == []
