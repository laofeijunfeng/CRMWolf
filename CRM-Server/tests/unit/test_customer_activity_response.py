"""Response contract tests for customer activities."""

from datetime import datetime
from types import SimpleNamespace

from app.api import customer_activities as customer_activities_api


def test_activity_response_exposes_submission_provenance(monkeypatch):
    monkeypatch.setattr(customer_activities_api, "_load_user_info", lambda *_: None)
    occurred_at = datetime(2026, 9, 2, 9, 30)
    activity = SimpleNamespace(
        id=212,
        customer_id=None,
        original_lead_id=None,
        deal_journey_id=None,
        activity_kind="WECHAT_FOLLOW_UP",
        title="客户确认进入测试阶段",
        source_content="客户确认本周开始测试, 下周反馈结果。",
        submission_source="AGENT",
        submission_id="agent-command-212",
        content_json=None,
        summary="客户确认进入测试阶段",
        processing_status="COMPLETED",
        processing_error=None,
        processed_at=occurred_at,
        next_follow_time=None,
        next_follow_time_source=None,
        next_action="下周确认测试结果",
        next_action_source="AGENT",
        occurred_at=occurred_at,
        creator_id="1",
        owner_id="1",
        created_time=occurred_at,
        updated_time=occurred_at,
        effectiveness_score=82,
        effectiveness_is_valid=True,
        effectiveness_reason="信息明确且包含可执行下一步",
        effectiveness_detail_json='{"clarity": 82}',
        effectiveness_status="COMPLETED",
        effectiveness_evaluated_time=occurred_at,
        effectiveness_error_message=None,
    )

    response = customer_activities_api._build_activity_response(SimpleNamespace(), activity)

    assert response.submission_source == "AGENT"
    assert response.submission_id == "agent-command-212"
