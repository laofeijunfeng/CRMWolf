from app.services.agent.schemas import WorkSummaryNarrativeItem, WorkSummaryNarrativeResult
from app.services.work_summary_evaluation_service import (
    WorkSummaryEvaluationCase,
    WorkSummaryEvaluationService,
    WorkSummaryHumanCorrection,
)


def _facts():
    return {
        "items": [
            {
                "fact_id": "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",
                "fact_type": "completed_follow_up_task",
                "source_group": "task",
                "occurred_at": "2026-08-05T17:30:00",
                "title": "确认预算进展",
                "customer": {"id": "cus_test_101", "name": "测试客户"},
                "attribution": {"user_id": "2", "field": "owner_id"},
            },
            {
                "fact_id": "customer_activity:微信同步试用:2026-08-06T09:00:00",
                "fact_type": "customer_activity",
                "source_group": "activity",
                "occurred_at": "2026-08-06T09:00:00",
                "title": "微信同步试用",
                "customer": {"id": "cus_test_101", "name": "测试客户"},
                "attribution": {"user_id": "2", "field": "owner_id"},
            },
        ],
        "source_total_counts": {
            "completed_follow_up_task": 1,
            "customer_activity": 1,
        },
        "filters": {
            "starts_at": "2026-08-03T00:00:00",
            "ends_at": "2026-08-10T00:00:00",
        },
    }


def _result():
    return WorkSummaryNarrativeResult(
        answer="本周完成预算确认，并记录了测试客户的试用沟通。",
        highlights=[
            WorkSummaryNarrativeItem(
                category="completed_work",
                title="预算确认",
                summary="预算进展已确认。",
                fact_ids=["completed_follow_up_task:fut_test_001:2026-08-05T17:30:00"],
            ),
            WorkSummaryNarrativeItem(
                category="process_record",
                title="试用沟通",
                summary="记录了微信同步试用。",
                fact_ids=["customer_activity:微信同步试用:2026-08-06T09:00:00"],
            ),
        ],
        customer_summaries=[],
        confidence=0.9,
        citations=[
            {"fact_id": "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00"},
            {"fact_id": "customer_activity:微信同步试用:2026-08-06T09:00:00"},
        ],
    )


def test_work_summary_evaluation_accepts_grounded_narrative_and_corrections():
    service = WorkSummaryEvaluationService()

    evaluation = service.evaluate_case(
        WorkSummaryEvaluationCase(
            name="valid_summary",
            work_facts=_facts(),
            result=_result(),
            required_fact_ids=(
                "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",
                "customer_activity:微信同步试用:2026-08-06T09:00:00",
            ),
            required_fact_types=("completed_follow_up_task", "customer_activity"),
            expected_source_total_counts={"completed_follow_up_task": 1, "customer_activity": 1},
            expected_owner_id="2",
            min_confidence=0.85,
            human_corrections=(
                WorkSummaryHumanCorrection(
                    correction_type="rewrite_summary",
                    target_fact_id="customer_activity:微信同步试用:2026-08-06T09:00:00",
                    replacement_text="强调这是过程记录。",
                    note="人工复核确认活动不能写成任务完成。",
                ),
            ),
        )
    )

    assert evaluation.passed is True
    assert evaluation.failures == []


def test_work_summary_evaluation_rejects_hallucinated_missing_and_wrong_category_refs():
    service = WorkSummaryEvaluationService()
    bad_result = WorkSummaryNarrativeResult(
        answer="本周完成了试用沟通，还推进了一个不存在的合同。",
        highlights=[
            WorkSummaryNarrativeItem(
                category="completed_work",
                title="试用沟通",
                summary="错误地把过程记录写成完成任务。",
                fact_ids=["customer_activity:微信同步试用:2026-08-06T09:00:00"],
            ),
            WorkSummaryNarrativeItem(
                category="business_progress",
                title="不存在的合同",
                summary="这条没有事实支撑。",
                fact_ids=["contract_signed:C-404:2026-08-06T00:00:00"],
            ),
        ],
        customer_summaries=[],
        confidence=0.7,
        citations=[{"fact_id": "customer_activity:微信同步试用:2026-08-06T09:00:00"}],
    )

    evaluation = service.evaluate_case(
        WorkSummaryEvaluationCase(
            name="bad_summary",
            work_facts=_facts(),
            result=bad_result,
            required_fact_ids=("completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",),
            expected_owner_id="2",
            min_confidence=0.8,
        )
    )

    assert evaluation.passed is False
    assert "fact_required_missing:completed_follow_up_task:fut_test_001:2026-08-05T17:30:00" in evaluation.failures
    assert "hallucinated_fact_ref:contract_signed:C-404:2026-08-06T00:00:00" in evaluation.failures
    assert "category_unexpected:customer_activity:微信同步试用:2026-08-06T09:00:00:completed_work:process_record" in evaluation.failures
    assert "citation_missing:contract_signed:C-404:2026-08-06T00:00:00" not in evaluation.failures
    assert "confidence_too_low:0.7" in evaluation.failures


def test_work_summary_evaluation_computes_accuracy_metrics():
    service = WorkSummaryEvaluationService()
    summary = service.evaluate_many([
        WorkSummaryEvaluationCase(
            name="valid_summary",
            work_facts=_facts(),
            result=_result(),
            required_fact_ids=(
                "completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",
                "customer_activity:微信同步试用:2026-08-06T09:00:00",
            ),
            expected_owner_id="2",
        ),
        WorkSummaryEvaluationCase(
            name="owner_bad",
            work_facts={
                **_facts(),
                "items": [
                    {
                        **_facts()["items"][0],
                        "attribution": {"user_id": "9", "field": "owner_id"},
                    }
                ],
            },
            result=WorkSummaryNarrativeResult(
                answer="引用了不存在事实。",
                highlights=[
                    WorkSummaryNarrativeItem(
                        category="business_progress",
                        title="不存在",
                        summary="没有事实。",
                        fact_ids=["phantom_fact"],
                    )
                ],
                customer_summaries=[],
                confidence=0.6,
                citations=[],
            ),
            required_fact_ids=("completed_follow_up_task:fut_test_001:2026-08-05T17:30:00",),
            expected_owner_id="2",
        ),
    ])

    metrics = summary.metrics.to_dict()

    assert summary.ok is False
    assert metrics["fact_recall"]["count"] == 2
    assert metrics["fact_recall"]["denominator"] == 3
    assert metrics["hallucination_rate"]["count"] == 1
    assert metrics["owner_attribution_errors"]["case_names"] == ["owner_bad"]
