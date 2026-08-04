from app.services.customer_evidence_retriever import CustomerEvidenceRetriever
from app.services.customer_qdrant_index_service import CustomerEvidenceSearchResult


class FakeEmbeddingService:
    def embed_query(self, db, team_id, text):
        return [0.1, 0.2, 0.3]


class WeightedQdrantIndexService:
    enabled = True

    def __init__(self) -> None:
        self.calls = []

    def search_customer_evidence(self, **kwargs):
        self.calls.append(kwargs)
        return [
            CustomerEvidenceSearchResult(
                id="brief",
                score=0.80,
                tenant_id=2,
                team_id=2,
                customer_id=101,
                source_type="customer_brief",
                source_object_id="brief-1",
                business_object_type=None,
                business_object_id=None,
                title="客户概况",
                text="客户正在推进 POC。",
            ),
            CustomerEvidenceSearchResult(
                id="follow-up",
                score=0.79,
                tenant_id=2,
                team_id=2,
                customer_id=101,
                source_type="follow_up",
                source_object_id="act-1",
                business_object_type="customer_activity",
                business_object_id="act-1",
                title="电话跟进",
                text="张总确认本周开始 POC。",
            ),
        ]


def test_customer_evidence_retriever_overfetches_and_reranks_by_source_weight() -> None:
    qdrant = WeightedQdrantIndexService()
    retriever = CustomerEvidenceRetriever(
        embedding_service=FakeEmbeddingService(),
        qdrant_index_service=qdrant,
        min_score=0.45,
    )

    result = retriever.retrieve_customer_evidence(
        object(),
        team_id=2,
        customer_id=101,
        query_text="客户 POC 怎么样",
        evidence_limit=1,
    )

    assert qdrant.calls[0]["limit"] == 3
    assert result.state.status == "ok"
    assert result.state.strategy == "customer_semantic_qdrant_source_weighted"
    assert result.hits[0].evidence_id == "follow-up"
    assert result.hits[0].adjusted_score > 0.80
