"""Customer knowledge candidate recall tests."""
from __future__ import annotations

from app.models.customer import Customer
from app.services.customer_knowledge_candidate_service import CustomerKnowledgeCandidateService
from app.services.customer_qdrant_index_service import CustomerEvidenceSearchResult


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def embed_query(self, db: object, team_id: int, query: str) -> list[float]:
        self.calls.append((team_id, query))
        return [0.1, 0.2, 0.3]


class FakeQdrantIndexService:
    def __init__(self, hits: list[CustomerEvidenceSearchResult] | None = None) -> None:
        self.enabled = True
        self.hits = hits or []
        self.calls: list[dict[str, object]] = []

    def search_team_customer_evidence(
        self,
        *,
        query_vector: list[float],
        tenant_id: int,
        team_id: int,
        limit: int,
        source_types: object = None,
    ) -> list[CustomerEvidenceSearchResult]:
        self.calls.append({
            "query_vector": query_vector,
            "tenant_id": tenant_id,
            "team_id": team_id,
            "limit": limit,
            "source_types": source_types,
        })
        return self.hits


class FakeCustomerQuery:
    def __init__(self, customers: list[Customer]) -> None:
        self.customers = customers

    def filter(self, *criteria: object) -> FakeCustomerQuery:
        return self

    def all(self) -> list[Customer]:
        return self.customers


class FakeDb:
    def __init__(self, customers: list[Customer]) -> None:
        self.customers = customers
        self.queried_models: list[object] = []

    def query(self, model: object) -> FakeCustomerQuery:
        self.queried_models.append(model)
        return FakeCustomerQuery(self.customers)


def test_recall_groups_customer_evidence_and_loads_customer_master_data() -> None:
    embedding_service = FakeEmbeddingService()
    qdrant_service = FakeQdrantIndexService(hits=[
        _hit(customer_id=301, score=0.82, title="跟进记录", text="客户简称中科院信工所。"),
        _hit(customer_id=301, score=0.93, title="客户概况", text="中国科学院信息工程研究所有国产化需求。"),
    ])
    customer = Customer(id=301, team_id=1, account_name="中国科学院信息工程研究所")
    service = CustomerKnowledgeCandidateService(
        embedding_service=embedding_service,
        qdrant_index_service=qdrant_service,
    )

    result = service.recall(FakeDb([customer]), team_id=1, query_text="中科院开始 POC", limit=5)

    assert embedding_service.calls == [(1, "中科院开始 POC")]
    assert qdrant_service.calls[0]["limit"] == 15
    assert result.retrieval_event == {
        "event": "customer_knowledge_candidates",
        "status": "ok",
        "candidate_count": 1,
    }
    assert result.candidates[0]["id"] == 301
    assert result.candidates[0]["account_name"] == "中国科学院信息工程研究所"
    assert result.candidates[0]["match"] == {
        "source": "customer_knowledge",
        "score": 0.93,
        "reason": "客户知识库语义匹配",
        "evidence": [
            {"title": "跟进记录", "snippet": "客户简称中科院信工所。", "score": 0.82},
            {"title": "客户概况", "snippet": "中国科学院信息工程研究所有国产化需求。", "score": 0.93},
        ],
    }


def test_recall_skips_embedding_when_qdrant_is_disabled() -> None:
    embedding_service = FakeEmbeddingService()
    qdrant_service = FakeQdrantIndexService()
    qdrant_service.enabled = False
    service = CustomerKnowledgeCandidateService(
        embedding_service=embedding_service,
        qdrant_index_service=qdrant_service,
    )

    result = service.recall(FakeDb([]), team_id=1, query_text="中科院", limit=5)

    assert embedding_service.calls == []
    assert qdrant_service.calls == []
    assert result.candidates == []
    assert result.retrieval_event["status"] == "disabled"


def _hit(*, customer_id: int, score: float, title: str, text: str) -> CustomerEvidenceSearchResult:
    return CustomerEvidenceSearchResult(
        id=f"hit-{customer_id}-{score}",
        score=score,
        tenant_id=1,
        team_id=1,
        customer_id=customer_id,
        source_type="follow_up",
        source_object_id="activity_1",
        business_object_type=None,
        business_object_id=None,
        title=title,
        text=text,
    )
