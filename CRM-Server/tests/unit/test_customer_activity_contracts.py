"""Contract tests for the canonical customer-activity workflow vocabulary."""

import pytest
from sqlalchemy import CheckConstraint

from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob
from app.services.customer_activity_contracts import (
    CustomerActivityAIJobStatus,
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
    CustomerActivitySuggestionJobStatus,
)


def test_agent_finalized_activity_contract_rejects_non_passing_evaluation() -> None:
    from pydantic import ValidationError

    from app.schemas.customer_activity import CustomerActivityAgentFinalizedCreate

    payload = {
        "activity_kind": "PHONE_FOLLOW_UP",
        "source_content": "客户还在评估",
        "effectiveness_score": 59,
        "effectiveness_is_valid": True,
        "effectiveness_reason": "信息不足",
    }

    with pytest.raises(ValidationError, match="Agent 最终评分未通过"):
        CustomerActivityAgentFinalizedCreate(**payload)

    payload["effectiveness_score"] = 80
    payload["effectiveness_is_valid"] = False
    with pytest.raises(ValidationError, match="Agent 最终评分未通过"):
        CustomerActivityAgentFinalizedCreate(**payload)


def test_agent_activity_tool_requires_planner_final_evaluation():
    from pydantic import ValidationError

    from app.services.agent.tool_registry import CreateCustomerActivityInput

    with pytest.raises(ValidationError):
        CreateCustomerActivityInput(
            customer_id="cus_101",
            source_content="客户反馈项目正在立项",
        )


def test_activity_submission_sources_are_canonical_and_complete():
    assert {item.value for item in CustomerActivitySubmissionSource} == {
        "AGENT",
        "FORM",
        "CUTOVER_MIGRATION",
    }


def test_activity_processing_and_effectiveness_statuses_are_canonical():
    assert {item.value for item in CustomerActivityProcessingStatus} == {
        "PENDING",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
    }
    assert {item.value for item in CustomerActivityEffectivenessStatus} == {
        "PENDING",
        "GENERATING",
        "COMPLETED",
        "FAILED",
    }


def test_durable_activity_job_statuses_are_canonical():
    expected = {"QUEUED", "RUNNING", "RETRY_PENDING", "COMPLETED", "SKIPPED", "EXHAUSTED"}
    assert {item.value for item in CustomerActivityAIJobStatus} == expected
    assert {item.value for item in CustomerActivitySuggestionJobStatus} == expected


def test_activity_uses_canonical_revision_and_submission_contract():
    assert "activity_revision" in CustomerActivity.__table__.columns
    assert "post_commit_revision" not in CustomerActivity.__table__.columns
    assert CustomerActivity.__table__.columns.submission_source.default.arg == "FORM"
    assert CustomerActivity.__table__.columns.submission_id.nullable is True


def test_activity_and_job_tables_expose_status_constraints():
    activity_constraints = {
        constraint.sqltext.text
        for constraint in CustomerActivity.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    job_constraints = {
        constraint.sqltext.text
        for constraint in CustomerActivityPostCommitJob.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert any("processing_status" in text for text in activity_constraints)
    assert any("effectiveness_status" in text for text in activity_constraints)
    assert any("status" in text for text in job_constraints)
