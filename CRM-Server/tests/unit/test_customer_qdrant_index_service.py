from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from qdrant_client.http import models as qmodels

from app.services.customer_qdrant_index_service import (
    CustomerEvidenceDocument,
    CustomerQdrantSchemaMismatchError,
    CustomerQdrantIndexService,
)


class FakeQdrantClient:
    def __init__(self) -> None:
        self.collection_exists_result = False
        self.collection_vector_size = 3
        self.collection_points_count = 0
        self.created_collections: list[tuple[str, qmodels.VectorParams]] = []
        self.deleted_collections: list[str] = []
        self.upserted_points: list[qmodels.PointStruct] = []
        self.search_filter: qmodels.Filter | None = None
        self.deleted_selector: qmodels.FilterSelector | None = None

    def collection_exists(self, collection_name: str) -> bool:
        return self.collection_exists_result

    def get_collection(self, collection_name: str):
        return SimpleNamespace(
            points_count=self.collection_points_count,
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(size=self.collection_vector_size),
                )
            ),
        )

    def create_collection(self, collection_name: str, vectors_config: qmodels.VectorParams) -> bool:
        self.created_collections.append((collection_name, vectors_config))
        return True

    def delete_collection(self, collection_name: str) -> bool:
        self.deleted_collections.append(collection_name)
        self.collection_exists_result = False
        return True

    def upsert(self, collection_name: str, points: Sequence[qmodels.PointStruct], wait: bool) -> object:
        self.upserted_points.extend(points)
        return object()

    def query_points(
        self,
        collection_name: str,
        query: Sequence[float],
        query_filter: qmodels.Filter,
        limit: int,
        with_payload: bool,
    ) -> qmodels.QueryResponse:
        self.search_filter = query_filter
        return qmodels.QueryResponse(
            points=[
                qmodels.ScoredPoint(
                    id="6f630ed4-e139-521e-952c-0044f7ead911",
                    version=1,
                    score=0.91,
                    payload={
                        "tenant_id": 1,
                        "team_id": 2,
                        "customer_id": 3,
                        "source_type": "follow_up",
                        "source_object_id": "activity_9",
                        "business_object_type": "opportunity",
                        "business_object_id": "opp_8",
                        "title": "跟进记录",
                        "text": "张总说本周开始 POC。",
                    },
                )
            ]
        )

    def delete(self, collection_name: str, points_selector: qmodels.FilterSelector, wait: bool) -> object:
        self.deleted_selector = points_selector
        return object()


def _condition_keys(filter_: qmodels.Filter) -> list[str]:
    return [condition.key for condition in filter_.must or [] if isinstance(condition, qmodels.FieldCondition)]


def test_upsert_evidence_creates_collection_and_keeps_business_payload() -> None:
    fake_client = FakeQdrantClient()
    service = CustomerQdrantIndexService(
        client=fake_client,
        collection_name="crm_customer_evidence",
        vector_size=3,
    )

    service.upsert_evidence(
        CustomerEvidenceDocument(
            id="follow_up:9",
            tenant_id=1,
            team_id=2,
            customer_id=3,
            source_type="follow_up",
            source_object_id="activity_9",
            business_object_type="opportunity",
            business_object_id="opp_8",
            title="跟进记录",
            text="张总说本周开始 POC。",
            vector=[0.1, 0.2, 0.3],
            confidence=0.92,
        )
    )

    assert fake_client.created_collections[0][0] == "crm_customer_evidence"
    assert fake_client.created_collections[0][1].size == 3
    assert fake_client.upserted_points[0].payload == {
        "tenant_id": 1,
        "team_id": 2,
        "customer_id": 3,
        "source_type": "follow_up",
        "source_object_id": "activity_9",
        "business_object_type": "opportunity",
        "business_object_id": "opp_8",
        "title": "跟进记录",
        "text": "张总说本周开始 POC。",
        "text_hash": None,
        "occurred_at": None,
        "confidence": 0.92,
        "visibility_scope": "team",
        "metadata_version": 1,
    }


def test_ensure_collection_keeps_matching_existing_collection() -> None:
    fake_client = FakeQdrantClient()
    fake_client.collection_exists_result = True
    fake_client.collection_vector_size = 3
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=3)

    created = service.ensure_collection()

    assert created is False
    assert fake_client.deleted_collections == []
    assert fake_client.created_collections == []


def test_ensure_collection_recreates_empty_mismatched_collection() -> None:
    fake_client = FakeQdrantClient()
    fake_client.collection_exists_result = True
    fake_client.collection_vector_size = 1536
    fake_client.collection_points_count = 0
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=1024)

    created = service.ensure_collection()

    assert created is True
    assert fake_client.deleted_collections == ["crm_customer_evidence"]
    assert fake_client.created_collections[0][1].size == 1024


def test_ensure_collection_blocks_nonempty_mismatched_collection() -> None:
    fake_client = FakeQdrantClient()
    fake_client.collection_exists_result = True
    fake_client.collection_vector_size = 1536
    fake_client.collection_points_count = 12
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=1024)

    with pytest.raises(CustomerQdrantSchemaMismatchError, match="维度不匹配"):
        service.ensure_collection()

    assert fake_client.deleted_collections == []
    assert fake_client.created_collections == []


def test_search_customer_evidence_filters_by_tenant_team_customer_and_source() -> None:
    fake_client = FakeQdrantClient()
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=3)

    results = service.search_customer_evidence(
        query_vector=[0.1, 0.2, 0.3],
        tenant_id=1,
        team_id=2,
        customer_id=3,
        source_types=["follow_up", "business_flow"],
        business_object_type="opportunity",
    )

    assert results[0].source_type == "follow_up"
    assert results[0].text == "张总说本周开始 POC。"
    assert fake_client.search_filter is not None
    assert _condition_keys(fake_client.search_filter) == [
        "tenant_id",
        "team_id",
        "customer_id",
        "source_type",
        "business_object_type",
    ]


def test_search_team_customer_evidence_filters_by_tenant_team_without_customer() -> None:
    fake_client = FakeQdrantClient()
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=3)

    results = service.search_team_customer_evidence(
        query_vector=[0.1, 0.2, 0.3],
        tenant_id=1,
        team_id=2,
        source_types=["customer", "customer_brief"],
    )

    assert results[0].customer_id == 3
    assert fake_client.search_filter is not None
    assert _condition_keys(fake_client.search_filter) == [
        "tenant_id",
        "team_id",
        "source_type",
    ]


def test_delete_by_source_uses_source_filter() -> None:
    fake_client = FakeQdrantClient()
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=3)

    service.delete_by_source(tenant_id=1, team_id=2, source_type="follow_up", source_object_id="activity_9")

    assert fake_client.deleted_selector is not None
    assert _condition_keys(fake_client.deleted_selector.filter) == [
        "tenant_id",
        "team_id",
        "source_type",
        "source_object_id",
    ]


def test_disabled_service_does_not_call_qdrant() -> None:
    fake_client = FakeQdrantClient()
    service = CustomerQdrantIndexService(client=fake_client, collection_name="crm_customer_evidence", vector_size=3)
    service.enabled = False

    service.upsert_evidence(
        CustomerEvidenceDocument(
            id="follow_up:9",
            tenant_id=1,
            team_id=2,
            customer_id=3,
            source_type="follow_up",
            source_object_id="activity_9",
            title="跟进记录",
            text="张总说本周开始 POC。",
            vector=[0.1, 0.2, 0.3],
        )
    )

    assert fake_client.created_collections == []
    assert fake_client.upserted_points == []
