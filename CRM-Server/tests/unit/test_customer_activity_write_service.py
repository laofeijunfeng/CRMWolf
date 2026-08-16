"""Architecture tests for the customer-activity transactional write seam."""

from types import SimpleNamespace

import pytest

from app.services.customer_activity_post_commit_job_service import CustomerActivityPostCommitJobRequest
from app.services.customer_activity_write_service import CustomerActivityWriteService
from app.services.customer_intelligence_event_service import CustomerIntelligenceEventService
from app.services.customer_intelligence_refresh_service import CustomerIntelligenceCommittedEventRequest


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = []

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, value) -> None:
        self.refreshes.append(value)


class _FakeActivityCRUD:
    def __init__(self) -> None:
        self.calls = []

    def create(self, db, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["commit"] is False
        return SimpleNamespace(
            id=212,
            team_id=kwargs["team_id"],
            customer_id=10,
            creator_id=kwargs["creator_id"],
            post_commit_revision=1,
            activity_kind="WECHAT_FOLLOW_UP",
            title="反馈数据分类分级表",
            summary="已反馈数据分类分级表，待提供测试报告",  # noqa: RUF001
            source_content="已反馈数据分类分级表，待提供测试报告",  # noqa: RUF001
            next_action="提供测试报告",
            next_follow_time=None,
            occurred_at=None,
        )

    def update(self, db, activity, obj_in, *, commit):
        assert commit is False
        activity.post_commit_revision += 1
        activity.summary = "第二版跟进"
        return activity


class _FakePostCommitJobs:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def enqueue_in_transaction(self, db, *, activity, trigger_type, actor_id):
        self.calls.append((activity.id, trigger_type, actor_id))
        if self.fail:
            raise RuntimeError("post-commit outbox unavailable")
        return CustomerActivityPostCommitJobRequest(job_public_id="pcj_212", team_id=activity.team_id)


class _FakeIntelligenceRefresh:
    def __init__(self) -> None:
        self.calls = []

    def enqueue_committed_event_refresh(self, db, *, event, scope):
        self.calls.append((event, scope))
        return CustomerIntelligenceCommittedEventRequest(
            request_id=f"business-event-{event.trigger_type}-{event.event_key[:16]}",
            event=event,
            scope=scope,
        )


class _FakeConfirmationCleanup:
    def __init__(self) -> None:
        self.calls = []

    def cancel_pending_cases_for_source_activity(self, db, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(cancelled_count=1)


def _activity_create():
    return SimpleNamespace(activity_kind="WECHAT_FOLLOW_UP", source_content="跟进内容")


def test_create_commits_activity_and_both_durable_work_items_once():
    db = _FakeSession()
    activity_crud = _FakeActivityCRUD()
    post_commit_jobs = _FakePostCommitJobs()
    intelligence = _FakeIntelligenceRefresh()
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        post_commit_job_service=post_commit_jobs,
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=intelligence,
    )

    result = service.create(
        db,
        obj_in=_activity_create(),
        customer_id=10,
        creator_id="1",
        owner_id="1",
        team_id=1,
        operator_name="Eddie",
        post_commit_trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="1",
    )

    assert result.activity.id == 212
    assert result.activity_revision == 1
    assert result.post_commit_job.job_public_id == "pcj_212"
    assert result.customer_intelligence_request is not None
    assert result.customer_intelligence_request.event.payload["activity_revision"] == 1
    assert db.commits == 1
    assert db.rollbacks == 0
    assert db.refreshes == [result.activity]
    assert post_commit_jobs.calls == [(212, "ACTIVITY_CREATED_DETERMINISTIC", "1")]
    assert len(intelligence.calls) == 1


def test_create_does_not_cancel_confirmation_cases_without_a_prior_revision():
    db = _FakeSession()
    cleanup = _FakeConfirmationCleanup()
    service = CustomerActivityWriteService(
        activity_crud=_FakeActivityCRUD(),
        post_commit_job_service=_FakePostCommitJobs(),
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=_FakeIntelligenceRefresh(),
        confirmation_cleanup_service=cleanup,
    )

    service.create(
        db,
        obj_in=_activity_create(),
        customer_id=10,
        creator_id="1",
        owner_id="1",
        team_id=1,
        operator_name="Eddie",
        post_commit_trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="1",
    )

    assert cleanup.calls == []


def test_create_rolls_back_activity_when_durable_post_commit_enqueue_fails():
    db = _FakeSession()
    service = CustomerActivityWriteService(
        activity_crud=_FakeActivityCRUD(),
        post_commit_job_service=_FakePostCommitJobs(fail=True),
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=_FakeIntelligenceRefresh(),
    )

    with pytest.raises(RuntimeError, match="post-commit outbox unavailable"):
        service.create(
            db,
            obj_in=_activity_create(),
            customer_id=10,
            creator_id="1",
            owner_id="1",
            team_id=1,
            operator_name="Eddie",
            post_commit_trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
            actor_id="1",
        )

    assert db.commits == 0
    assert db.rollbacks == 1


def test_revision_change_cancels_superseded_confirmation_cases_in_same_write_transaction():
    db = _FakeSession()
    activity_crud = _FakeActivityCRUD()
    cleanup = _FakeConfirmationCleanup()
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        post_commit_job_service=_FakePostCommitJobs(),
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=_FakeIntelligenceRefresh(),
        confirmation_cleanup_service=cleanup,
    )
    activity = activity_crud.create(db, team_id=1, creator_id="1", commit=False)

    result = service.update(
        db,
        activity=activity,
        obj_in=SimpleNamespace(),
        post_commit_trigger_type="ACTIVITY_UPDATED_DETERMINISTIC",
        actor_id="1",
    )

    assert result.activity_revision == 2
    assert cleanup.calls == [
        {
            "team_id": 1,
            "source_activity_id": 212,
            "actor_id": "1",
            "reason": "SOURCE_ACTIVITY_REVISION_SUPERSEDED",
            "commit": False,
        }
    ]
    assert db.commits == 1


def test_update_without_revision_change_neither_cancels_cases_nor_enqueues_new_work():
    class NoRevisionChangeActivityCRUD(_FakeActivityCRUD):
        def update(self, db, activity, obj_in, *, commit):
            assert commit is False
            return activity

    db = _FakeSession()
    activity_crud = NoRevisionChangeActivityCRUD()
    post_commit_jobs = _FakePostCommitJobs()
    intelligence = _FakeIntelligenceRefresh()
    cleanup = _FakeConfirmationCleanup()
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        post_commit_job_service=post_commit_jobs,
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=intelligence,
        confirmation_cleanup_service=cleanup,
    )
    activity = activity_crud.create(db, team_id=1, creator_id="1", commit=False)

    result = service.update(
        db,
        activity=activity,
        obj_in=SimpleNamespace(),
        post_commit_trigger_type="ACTIVITY_UPDATED_DETERMINISTIC",
        actor_id="1",
    )

    assert result.activity_revision == 1
    assert result.post_commit_job is None
    assert result.customer_intelligence_request is None
    assert cleanup.calls == []
    assert post_commit_jobs.calls == []
    assert intelligence.calls == []
    assert db.commits == 1


def test_activity_intelligence_event_identity_changes_with_revision_without_changing_source_identity():
    event_service = CustomerIntelligenceEventService()
    activity = SimpleNamespace(
        id=212,
        team_id=1,
        customer_id=10,
        creator_id="1",
        post_commit_revision=1,
        activity_kind="WECHAT_FOLLOW_UP",
        title="反馈数据分类分级表",
        summary="第一次结构化结果",
        source_content="原始跟进",
        next_action=None,
        next_follow_time=None,
        occurred_at=None,
    )

    revision_one = event_service.from_customer_activity(activity, trigger_type="customer_activity_updated")
    activity.post_commit_revision = 2
    revision_two = event_service.from_customer_activity(activity, trigger_type="customer_activity_updated")

    assert revision_one is not None and revision_two is not None
    assert revision_one.event_key != revision_two.event_key
    assert revision_one.source.source_object_id == revision_two.source.source_object_id == "212"
    assert revision_two.payload["activity_revision"] == 2
