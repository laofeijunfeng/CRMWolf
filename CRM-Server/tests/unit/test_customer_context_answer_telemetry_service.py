from unittest.mock import Mock

from app.models.customer_context_answer_telemetry import CustomerContextAnswerTelemetry
from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.customer_context_answer_telemetry_service import CustomerContextAnswerTelemetryService


def test_customer_context_answer_telemetry_records_retrieval_quality() -> None:
    db = Mock()
    captured = {}
    db.add.side_effect = lambda item: captured.setdefault("telemetry", item)
    service = CustomerContextAnswerTelemetryService()

    result = CustomerContextAnswerResult(
        answer="客户处于 POC 阶段。",
        confidence=0.91,
        used_sections=["customer", "semantic_evidence"],
        missing_context=[],
        answer_mode="grounded",
        citations=[{"evidence_id": "ev-1", "score": 0.91}],
    )

    telemetry = service.record_answer(
        db,
        team_id=2,
        question="客户现在什么情况",
        customer_context={
            "strong_context": {"customer": {"id": 101, "account_name": "越秀金融"}},
            "semantic_evidence": [{"evidence_id": "ev-1"}],
            "retrieval": {
                "status": "ok",
                "strategy": "customer_semantic_qdrant",
                "top_score": 0.91,
                "min_score": 0.45,
                "raw_count": 2,
                "returned_count": 1,
                "dropped_count": 1,
            },
        },
        result=result,
        answer_source="langchain_structured_output",
        model="qwen-plus",
    )

    assert telemetry is captured["telemetry"]
    assert isinstance(telemetry, CustomerContextAnswerTelemetry)
    assert telemetry.team_id == 2
    assert telemetry.customer_id == 101
    assert telemetry.answer_mode == "grounded"
    assert telemetry.answer_source == "langchain_structured_output"
    assert telemetry.retrieval_status == "ok"
    assert telemetry.retrieval_strategy == "customer_semantic_qdrant"
    assert telemetry.semantic_evidence_count == 1
    assert telemetry.citation_count == 1
    assert telemetry.top_score == 0.91
    assert telemetry.min_score == 0.45
    assert telemetry.raw_count == 2
    assert telemetry.returned_count == 1
    assert telemetry.dropped_count == 1
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(telemetry)
