from app.services.customer_fact_extraction_service import CustomerFactExtractionResult, ExtractedCustomerFact


def test_customer_fact_extraction_result_cleans_optional_text():
    result = CustomerFactExtractionResult(
        summary="本次提炼客户动态",
        facts=[
            ExtractedCustomerFact(
                fact_type="need",
                subject="  POC  ",
                content="  客户需要安排 POC 环境。  ",
                confidence=0.86,
                action="upsert",
                evidence_quote="  今天开始 POC  ",
                reason="  原文明确  ",
            ),
        ],
    )

    fact = result.facts[0]

    assert fact.subject == "POC"
    assert fact.content == "客户需要安排 POC 环境。"
    assert fact.evidence_quote == "今天开始 POC"
    assert fact.reason == "原文明确"


def test_customer_fact_extraction_result_allows_review_and_ignore_actions():
    result = CustomerFactExtractionResult(
        facts=[
            ExtractedCustomerFact(
                fact_type="risk",
                subject=" ",
                content="审批链较长。",
                confidence=0.61,
                action="review",
                evidence_quote="",
            ),
            ExtractedCustomerFact(
                fact_type="summary",
                content="无明确新增事实。",
                confidence=0.2,
                action="ignore",
            ),
        ],
    )

    assert result.facts[0].subject is None
    assert result.facts[0].evidence_quote is None
    assert result.facts[0].action == "review"
    assert result.facts[1].action == "ignore"


def test_customer_fact_extraction_result_allows_alias_fact():
    result = CustomerFactExtractionResult(
        facts=[
            ExtractedCustomerFact(
                fact_type="alias",
                subject="中科院信工所",
                content="中科院信工所",
                confidence=0.9,
                action="upsert",
                evidence_quote="客户内部常说中科院信工所",
            ),
        ],
    )

    assert result.facts[0].fact_type == "alias"
