from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.customer_context_answer_evaluation_service import (
    CustomerContextAnswerEvaluationCase,
    CustomerContextAnswerEvaluationService,
)


def test_customer_context_answer_evaluation_accepts_grounded_answer_with_citations():
    service = CustomerContextAnswerEvaluationService()

    evaluation = service.evaluate_case(
        CustomerContextAnswerEvaluationCase(
            name="grounded_customer_summary",
            result=CustomerContextAnswerResult(
                answer="客户正在 POC，近期重点是确认采购流程。",
                confidence=0.91,
                used_sections=["customer", "evidence"],
                missing_context=[],
                answer_mode="grounded",
                citations=[{"evidence_id": "ev-1", "score": 0.88}],
            ),
            retrieval_status="ok",
            allowed_answer_modes={"grounded"},
            require_citations=True,
        ),
    )

    assert evaluation.passed is True
    assert evaluation.failures == []


def test_customer_context_answer_evaluation_rejects_weak_retrieval_citations():
    service = CustomerContextAnswerEvaluationService()

    evaluation = service.evaluate_case(
        CustomerContextAnswerEvaluationCase(
            name="weak_retrieval_fallback",
            result=CustomerContextAnswerResult(
                answer="客户有业务上下文，但语义证据不足。",
                confidence=0.74,
                used_sections=["customer"],
                missing_context=["缺少可引用的高置信度语义证据"],
                answer_mode="fallback",
                citations=[{"evidence_id": "ev-1", "score": 0.21}],
            ),
            retrieval_status="low_confidence",
            allowed_answer_modes={"fallback", "insufficient"},
            forbid_citations=True,
            required_missing_context_terms=("高置信度语义证据",),
        ),
    )

    assert evaluation.passed is False
    assert "citations_forbidden" in evaluation.failures
    assert "citations_present_without_ok_retrieval" in evaluation.failures


def test_customer_context_answer_evaluation_summarizes_failed_contract_checks():
    service = CustomerContextAnswerEvaluationService()

    summary = service.evaluate_many([
        CustomerContextAnswerEvaluationCase(
            name="valid_degraded",
            result=CustomerContextAnswerResult(
                answer="客户档案显示项目处于调研阶段。",
                confidence=0.67,
                used_sections=["profile"],
                missing_context=[],
                answer_mode="degraded",
                citations=[],
            ),
            retrieval_status="embedding_unavailable",
            allowed_answer_modes={"degraded"},
            forbid_citations=True,
        ),
        CustomerContextAnswerEvaluationCase(
            name="leaks_internal_field",
            result=CustomerContextAnswerResult(
                answer="根据 source_type=follow_up 的证据，客户正在推进。",
                confidence=0.9,
                used_sections=["evidence"],
                missing_context=[],
                answer_mode="grounded",
                citations=[],
            ),
            retrieval_status="ok",
            allowed_answer_modes={"grounded"},
            require_citations=True,
        ),
    ])

    assert summary.ok is False
    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.results[1].failures == [
        "citations_missing",
        "forbidden_token:source_type",
    ]


def test_customer_context_answer_evaluation_checks_required_terms_and_confidence():
    service = CustomerContextAnswerEvaluationService()

    evaluation = service.evaluate_case(
        CustomerContextAnswerEvaluationCase(
            name="missing_business_fact",
            result=CustomerContextAnswerResult(
                answer="客户目前资料较少。",
                confidence=0.42,
                used_sections=["customer"],
                missing_context=[],
                answer_mode="fallback",
                citations=[],
            ),
            allowed_answer_modes={"fallback"},
            min_confidence=0.7,
            required_answer_terms=("POC",),
        ),
    )

    assert evaluation.passed is False
    assert evaluation.failures == [
        "confidence_too_low:0.42",
        "answer_term_absent:POC",
    ]
