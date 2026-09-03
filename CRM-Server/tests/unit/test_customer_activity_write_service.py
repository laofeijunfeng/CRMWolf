"""Architecture tests for the customer-activity transactional write seam."""

from contextlib import nullcontext
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

    def begin_nested(self):
        return nullcontext()


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
            activity_revision=1,
            activity_kind="WECHAT_FOLLOW_UP",
            title="反馈数据分类分级表",
            summary="已反馈数据分类分级表，待提供测试报告",  # noqa: RUF001
            source_content="已反馈数据分类分级表，待提供测试报告",  # noqa: RUF001
            next_action="提供测试报告",
            next_follow_time=None,
            occurred_at=None,
            submission_source="AGENT",
        )

    def apply_finalization(self, db, activity, **kwargs):
        assert kwargs["commit"] is False
        if kwargs["increment_revision"]:
            activity.activity_revision += 1
        for field, value in kwargs.items():
            if field not in {"commit", "increment_revision"}:
                setattr(activity, field, value)
        activity.processing_status = "COMPLETED"
        activity.effectiveness_status = "COMPLETED"
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

    def kick(self, request):
        self.kick_request = request


class _FakeOpportunitySuggestionJobs:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.enqueue_calls = []
        self.kick_calls = []

    def enqueue_in_transaction(self, db, *, activity):
        self.enqueue_calls.append((activity.id, activity.team_id, activity.activity_revision))
        if self.fail:
            raise RuntimeError("opportunity suggestion outbox unavailable")
        from app.services.customer_opportunity_suggestion_job_service import CustomerOpportunitySuggestionJobRequest

        return CustomerOpportunitySuggestionJobRequest(
            job_public_id="cosj_212",
            team_id=activity.team_id,
        )

    def kick(self, request):
        self.kick_calls.append(request)


class _FakeIntelligenceRefresh:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def enqueue_committed_event_refresh(self, db, *, event, scope):
        self.calls.append((event, scope))
        if self.fail:
            raise RuntimeError("customer intelligence outbox unavailable")
        return CustomerIntelligenceCommittedEventRequest(
            request_id=f"business-event-{event.trigger_type}-{event.event_key[:16]}",
            event=event,
            scope=scope,
        )

    def kick_committed_event_refresh(self, request):
        self.kick_request = request


class _FakeConfirmationCleanup:
    def __init__(self) -> None:
        self.calls = []

    def cancel_pending_cases_for_source_activity(self, db, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(cancelled_count=1)


def _activity_create():
    return SimpleNamespace(activity_kind="WECHAT_FOLLOW_UP", source_content="跟进内容")


def test_activity_intelligence_event_identity_changes_with_revision_without_changing_source_identity():
    event_service = CustomerIntelligenceEventService()
    activity = SimpleNamespace(
        id=212,
        team_id=1,
        customer_id=10,
        creator_id="1",
        activity_revision=1,
        activity_kind="WECHAT_FOLLOW_UP",
        title="反馈数据分类分级表",
        summary="第一次结构化结果",
        source_content="原始跟进",
        next_action=None,
        next_follow_time=None,
        occurred_at=None,
    )

    revision_one = event_service.from_customer_activity(activity, trigger_type="customer_activity_updated")
    activity.activity_revision = 2
    revision_two = event_service.from_customer_activity(activity, trigger_type="customer_activity_updated")

    assert revision_one is not None and revision_two is not None
    assert revision_one.event_key != revision_two.event_key
    assert revision_one.source.source_object_id == revision_two.source.source_object_id == "212"
    assert revision_two.payload["activity_revision"] == 2



class _FakeAIJobs:
    def __init__(self) -> None:
        self.enqueue_calls = []
        self.completed_calls = []

    def enqueue_in_transaction(self, db, *, activity):
        self.enqueue_calls.append((activity.id, activity.team_id, activity.activity_revision))
        return SimpleNamespace(job_public_id="caij_212", team_id=activity.team_id)

    def mark_completed_in_transaction(self, db, *, request, lease_token, result_json):
        self.completed_calls.append((request.job_public_id, lease_token, result_json))

    def kick(self, request):
        self.kicked_request = request


def _finalization():
    from app.services.customer_activity_write_service import CustomerActivityFinalization

    return CustomerActivityFinalization(
        title="客户确认测试计划",
        content_json={"content": "客户本周开始测试", "next_action": "下周确认测试结果"},
        summary="客户本周开始测试, 下周确认结果",
        next_action="下周确认测试结果",
        next_action_source="AGENT",
        next_follow_time=None,
        next_follow_time_source=None,
        effectiveness_score=82,
        effectiveness_is_valid=True,
        effectiveness_reason="信息完整且下一步明确",
        effectiveness_detail_json='{"clarity":{"score":20,"max_score":20}}',
    )


def test_create_pending_from_form_enqueues_only_durable_ai_job():
    db = _FakeSession()
    activity_crud = _FakeActivityCRUD()
    ai_jobs = _FakeAIJobs()
    post_commit_jobs = _FakePostCommitJobs()
    opportunity_suggestion_jobs = _FakeOpportunitySuggestionJobs()
    intelligence = _FakeIntelligenceRefresh()
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        ai_job_service=ai_jobs,
        post_commit_job_service=post_commit_jobs,
        opportunity_suggestion_job_service=opportunity_suggestion_jobs,
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=intelligence,
    )

    result = service.create_pending_from_form(
        db,
        obj_in=_activity_create(),
        customer_id=10,
        creator_id="1",
        owner_id="1",
        team_id=1,
        operator_name="Eddie",
    )

    assert result.activity.processing_status == "PENDING"
    assert result.activity.effectiveness_status == "PENDING"
    assert result.post_commit_job is None
    assert result.customer_intelligence_request is None
    assert result.ai_job.job_public_id == "caij_212"
    assert result.opportunity_suggestion_job is None
    assert ai_jobs.enqueue_calls == [(212, 1, 1)]
    assert post_commit_jobs.calls == []
    assert intelligence.calls == []
    assert activity_crud.calls[0]["submission_source"] == "FORM"
    service.kick(result)
    assert ai_jobs.kicked_request is result.ai_job
    assert db.commits == 1


def test_create_final_from_agent_persists_final_score_without_ai_job():
    db = _FakeSession()
    activity_crud = _FakeActivityCRUD()
    ai_jobs = _FakeAIJobs()
    post_commit_jobs = _FakePostCommitJobs()
    opportunity_suggestion_jobs = _FakeOpportunitySuggestionJobs()
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        ai_job_service=ai_jobs,
        post_commit_job_service=post_commit_jobs,
        opportunity_suggestion_job_service=opportunity_suggestion_jobs,
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=_FakeIntelligenceRefresh(),
    )

    result = service.create_final_from_agent(
        db,
        obj_in=_activity_create(),
        finalization=_finalization(),
        customer_id=10,
        creator_id="1",
        owner_id="1",
        team_id=1,
        operator_name="Eddie",
        post_commit_trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="1",
    )

    assert result.activity.processing_status == "COMPLETED"
    assert result.activity.effectiveness_status == "COMPLETED"
    assert result.activity.effectiveness_score == 82
    assert result.activity.effectiveness_reason == "信息完整且下一步明确"
    assert result.ai_job is None
    assert result.post_commit_job.job_public_id == "pcj_212"
    assert result.opportunity_suggestion_job.job_public_id == "cosj_212"
    assert ai_jobs.enqueue_calls == []
    assert activity_crud.calls[0]["submission_source"] == "AGENT"
    assert opportunity_suggestion_jobs.enqueue_calls == [(212, 1, 1)]
    service.kick(result)
    assert opportunity_suggestion_jobs.kick_calls == [result.opportunity_suggestion_job]


def test_agent_suggestion_outbox_failure_does_not_rollback_activity():
    db = _FakeSession()
    activity_crud = _FakeActivityCRUD()
    activity_crud.create = lambda db, **kwargs: SimpleNamespace(
        id=212,
        team_id=kwargs["team_id"],
        customer_id=10,
        creator_id=kwargs["creator_id"],
        activity_revision=1,
        submission_source="AGENT",
        activity_kind="WECHAT_FOLLOW_UP",
        title="反馈数据分类分级表",
        summary=None,
        source_content="跟进内容",
        next_action=None,
        next_follow_time=None,
        occurred_at=None,
    )
    suggestion_jobs = _FakeOpportunitySuggestionJobs(fail=True)
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        ai_job_service=_FakeAIJobs(),
        post_commit_job_service=_FakePostCommitJobs(),
        opportunity_suggestion_job_service=suggestion_jobs,
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=_FakeIntelligenceRefresh(),
    )

    result = service.create_final_from_agent(
        db,
        obj_in=_activity_create(),
        finalization=_finalization(),
        customer_id=10,
        creator_id="1",
        owner_id="1",
        team_id=1,
        post_commit_trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="1",
    )

    assert result.activity.id == 212
    assert result.opportunity_suggestion_job is None
    assert db.commits == 1
    assert db.rollbacks == 0


class _StructuredContentActivityCRUD(_FakeActivityCRUD):
    def __init__(
        self,
        *,
        next_action: str | None = "已有下一步",
        next_action_source: str | None = "USER",
        next_follow_time=None,
        next_follow_time_source: str | None = None,
    ) -> None:
        super().__init__()
        self.activity = SimpleNamespace(
            id=212,
            team_id=1,
            customer_id=10,
            creator_id="1",
            owner_id="1",
            activity_revision=1,
            activity_kind="WECHAT_FOLLOW_UP",
            title="原始标题",
            content_json='{"content":"原始内容"}',
            summary="原始摘要",
            source_content="原始内容",
            next_action=next_action,
            next_action_source=next_action_source,
            next_follow_time=next_follow_time,
            next_follow_time_source=next_follow_time_source,
            occurred_at=None,
            submission_source="FORM",
            processing_status="PENDING",
            processing_error=None,
            processed_at=None,
            effectiveness_status="PENDING",
            effectiveness_score=None,
            effectiveness_is_valid=None,
            effectiveness_reason=None,
            effectiveness_detail_json=None,
            effectiveness_evaluated_time=None,
            effectiveness_error_message=None,
        )

    def get_by_id(self, db, activity_id, team_id):
        return self.activity if activity_id == self.activity.id and team_id == self.activity.team_id else None

    def create(self, db, **kwargs):
        self.calls.append(kwargs)
        return self.activity


class _PendingActivityCRUD(_StructuredContentActivityCRUD):
    def __init__(self) -> None:
        super().__init__(
            next_action=None,
            next_action_source=None,
            next_follow_time=None,
            next_follow_time_source=None,
        )
        self.activity.submission_source = "FORM"
        self.activity.processing_status = "PENDING"
        self.activity.effectiveness_status = "PENDING"
        self.activity.effectiveness_score = None
        self.activity.effectiveness_is_valid = None
        self.activity.effectiveness_reason = None
        self.activity.effectiveness_detail_json = None
        self.activity.effectiveness_evaluated_time = None
        self.activity.effectiveness_error_message = None


def test_finalize_pending_from_ai_commits_score_post_commit_and_job_completion_together():
    db = _FakeSession()
    activity_crud = _PendingActivityCRUD()
    ai_jobs = _FakeAIJobs()
    post_commit_jobs = _FakePostCommitJobs()
    service = CustomerActivityWriteService(
        activity_crud=activity_crud,
        ai_job_service=ai_jobs,
        post_commit_job_service=post_commit_jobs,
        opportunity_suggestion_job_service=_FakeOpportunitySuggestionJobs(),
        intelligence_event_service=CustomerIntelligenceEventService(),
        intelligence_refresh_service=_FakeIntelligenceRefresh(),
        confirmation_cleanup_service=_FakeConfirmationCleanup(),
    )

    result = service.finalize_pending_from_ai(
        db,
        activity_id=212,
        team_id=1,
        expected_activity_revision=1,
        ai_job_public_id="caij_212",
        lease_token="lease-212",
        finalization=_finalization(),
        post_commit_trigger_type="ACTIVITY_AI_FINALIZED",
        actor_id=None,
    )

    assert result.activity.activity_revision == 2
    assert result.activity.processing_status == "COMPLETED"
    assert result.activity.effectiveness_status == "COMPLETED"
    assert result.activity.effectiveness_score == 82
    assert result.post_commit_job.job_public_id == "pcj_212"
    assert result.ai_job.job_public_id == "caij_212"
    assert ai_jobs.completed_calls == [
        (
            "caij_212",
            "lease-212",
            {
                "job_public_id": "caij_212",
                "activity_id": 212,
                "execution_status": "COMPLETED",
                "success": True,
                "retryable": False,
                "skip_reason": None,
                "error": None,
                "activity_revision": 2,
                "effectiveness_score": 82,
            },
        )
    ]
    assert db.commits == 1
