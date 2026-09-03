"""Decision and safety tests for Agent opportunity-suggestion execution."""

from app.models.opportunity import OpportunityStatus
from app.services.agent.schemas import AgentBusinessSuggestion, AgentSuggestionResult
from app.services.agent.suggestion import AgentSuggestionEnvelope
from app.services.customer_opportunity_suggestion_job_service import (
    CustomerOpportunitySuggestionJobRequest,
    CustomerOpportunitySuggestionJobService,
)

REQUEST = CustomerOpportunitySuggestionJobRequest(job_public_id="cosj_1", team_id=1)


def _suggestion(**overrides):
    values = {
        "action": "CREATE_OPPORTUNITY",
        "title": "补充商机",
        "reason": "客户已明确项目采购计划",
        "priority": "high",
        "requires_confirmation": True,
        "missing_fields": [],
        "related_object_type": None,
        "related_object_id": None,
        "execution_payload": {},
        "risk_notes": [],
        "confidence": 0.9,
    }
    values.update(overrides)
    return AgentBusinessSuggestion.model_validate(values)


def _envelope(*suggestions):
    return AgentSuggestionEnvelope(
        result=AgentSuggestionResult(
            summary="客户有明确采购机会",
            suggestions=list(suggestions),
            need_user_choice=True,
        ),
        suggestion_source="test",
        model="test-model",
    )


def _job_data(suggestions, opportunities=None):
    return {
        "activity_id": 212,
        "context": {"opportunities": opportunities or []},
    }


def test_active_opportunity_status_normalizes_enum_name_and_storage_value():
    assert CustomerOpportunitySuggestionJobService._is_active_opportunity_status(OpportunityStatus.FOLLOWING)
    assert CustomerOpportunitySuggestionJobService._is_active_opportunity_status(0)
    assert CustomerOpportunitySuggestionJobService._is_active_opportunity_status("FOLLOWING")
    assert not CustomerOpportunitySuggestionJobService._is_active_opportunity_status(OpportunityStatus.WON)
    assert not CustomerOpportunitySuggestionJobService._is_active_opportunity_status("2")


def test_high_confidence_related_existing_opportunity_is_silently_ignored():
    service = CustomerOpportunitySuggestionJobService()
    suggestion = _suggestion(related_object_id="opp_existing")

    result = service._decision_result(
        REQUEST,
        _job_data(
            [suggestion],
            [{"id": "opp_existing", "status": OpportunityStatus.FOLLOWING.value}],
        ),
        _envelope(suggestion),
    )

    assert result.decision == "NO_ACTION"
    assert result.silent_reason == "HIGH_CONFIDENCE_EXISTING_OPPORTUNITY"
    assert result.suggestion is None


def test_structured_business_identity_can_silently_match_without_related_id():
    service = CustomerOpportunitySuggestionJobService()
    suggestion = _suggestion(
        execution_payload={
            "purchase_type": "NEW",
            "license_type": "SUBSCRIPTION",
            "user_count": 200,
            "total_amount": 100000,
        }
    )

    result = service._decision_result(
        REQUEST,
        _job_data(
            [suggestion],
            [
                {
                    "id": "opp_existing",
                    "status": "FOLLOWING",
                    "purchase_type": "NEW",
                    "license_type": "SUBSCRIPTION",
                    "user_count": 200,
                    "total_amount": 100000,
                }
            ],
        ),
        _envelope(suggestion),
    )

    assert result.decision == "NO_ACTION"
    assert result.silent_reason == "HIGH_CONFIDENCE_EXISTING_OPPORTUNITY"


def test_weak_or_nonmatching_existing_opportunity_remains_a_visible_suggestion():
    service = CustomerOpportunitySuggestionJobService()
    suggestion = _suggestion(execution_payload={"purchase_type": "EXPANSION"})

    result = service._decision_result(
        REQUEST,
        _job_data(
            [suggestion],
            [
                {
                    "id": "opp_existing",
                    "status": 0,
                    "purchase_type": "NEW",
                    "license_type": "SUBSCRIPTION",
                    "user_count": 200,
                    "total_amount": 100000,
                }
            ],
        ),
        _envelope(suggestion),
    )

    assert result.decision == "CREATE_OPPORTUNITY"
    assert result.suggestion is not None
    assert result.silent_reason is None


def test_non_opportunity_actions_are_not_executed_by_suggestion_job():
    service = CustomerOpportunitySuggestionJobService()
    unsupported = _suggestion(action="CREATE_CONTACT")

    result = service._decision_result(REQUEST, _job_data([unsupported]), _envelope(unsupported))

    assert result.decision == "NO_ACTION"
    assert result.suggestion is None
