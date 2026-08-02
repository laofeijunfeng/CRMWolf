from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.core.qdrant import get_qdrant_client

PayloadScalar = str | int | float | bool | None
PayloadValue = PayloadScalar | list[str]
EvidencePayload = dict[str, PayloadValue]

SourceType = Literal[
    "customer",
    "customer_profile",
    "customer_brief",
    "follow_up",
    "business_flow",
    "opportunity",
    "contract",
    "payment",
    "contact",
    "agent_judgement",
]


@dataclass(frozen=True)
class CustomerEvidenceDocument:
    id: str
    tenant_id: int
    team_id: int
    customer_id: int
    source_type: SourceType
    source_object_id: str
    text: str
    vector: Sequence[float]
    title: str
    business_object_type: str | None = None
    business_object_id: str | None = None
    text_hash: str | None = None
    occurred_at: datetime | None = None
    confidence: float | None = None
    visibility_scope: str = "team"
    metadata_version: int = 1


@dataclass(frozen=True)
class CustomerEvidenceSearchResult:
    id: str
    score: float
    tenant_id: int | None
    team_id: int | None
    customer_id: int | None
    source_type: str | None
    source_object_id: str | None
    business_object_type: str | None
    business_object_id: str | None
    title: str | None
    text: str | None


class CustomerQdrantSchemaMismatchError(Exception):
    """Raised when an existing Qdrant collection cannot accept the configured embedding vector."""


class CustomerEvidenceVectorClient(Protocol):
    def collection_exists(self, collection_name: str) -> bool:
        raise NotImplementedError

    def get_collection(self, collection_name: str) -> qmodels.CollectionInfo:
        raise NotImplementedError

    def create_collection(self, collection_name: str, vectors_config: qmodels.VectorParams) -> bool:
        raise NotImplementedError

    def delete_collection(self, collection_name: str) -> bool:
        raise NotImplementedError

    def upsert(self, collection_name: str, points: Sequence[qmodels.PointStruct], wait: bool) -> object:
        raise NotImplementedError

    def query_points(
        self,
        collection_name: str,
        query: Sequence[float],
        query_filter: qmodels.Filter,
        limit: int,
        with_payload: bool,
    ) -> qmodels.QueryResponse:
        raise NotImplementedError

    def delete(self, collection_name: str, points_selector: qmodels.FilterSelector, wait: bool) -> object:
        raise NotImplementedError


class CustomerQdrantIndexService:
    def __init__(
        self,
        client: CustomerEvidenceVectorClient | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.enabled = settings.QDRANT_ENABLED
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_CUSTOMER_EVIDENCE
        self.vector_size = vector_size or settings.QDRANT_VECTOR_SIZE
        self._client = client

    @property
    def client(self) -> CustomerEvidenceVectorClient:
        if self._client is None:
            self._client = get_qdrant_client()
        return self._client

    def ensure_collection(self) -> bool:
        if not self.enabled:
            return False
        if self.client.collection_exists(self.collection_name):
            collection_info = self.client.get_collection(self.collection_name)
            existing_vector_size = self._collection_vector_size(collection_info)
            if existing_vector_size == self.vector_size:
                return False
            points_count = self._collection_points_count(collection_info)
            if points_count == 0:
                self.client.delete_collection(self.collection_name)
                self._create_collection()
                return True
            raise CustomerQdrantSchemaMismatchError(
                f"客户证据 Qdrant collection 维度不匹配: collection={self.collection_name}, "
                f"existing={existing_vector_size}, expected={self.vector_size}, points_count={points_count}"
            )
        self._create_collection()
        return True

    def _create_collection(self) -> None:
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )

    @staticmethod
    def _collection_vector_size(collection_info: qmodels.CollectionInfo) -> int | None:
        config = getattr(collection_info, "config", None)
        params = getattr(config, "params", None)
        vectors = getattr(params, "vectors", None)
        size = getattr(vectors, "size", None)
        if isinstance(size, int):
            return size
        if isinstance(vectors, dict) and len(vectors) == 1:
            only_vector = next(iter(vectors.values()))
            only_size = getattr(only_vector, "size", None)
            return only_size if isinstance(only_size, int) else None
        return None

    @staticmethod
    def _collection_points_count(collection_info: qmodels.CollectionInfo) -> int:
        points_count = getattr(collection_info, "points_count", None)
        if isinstance(points_count, int):
            return points_count
        vectors_count = getattr(collection_info, "vectors_count", None)
        if isinstance(vectors_count, int):
            return vectors_count
        return 1

    def upsert_evidence(self, document: CustomerEvidenceDocument) -> None:
        if not self.enabled:
            return
        self.ensure_collection()
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                qmodels.PointStruct(
                    id=self._to_point_id(document.id),
                    vector=list(document.vector),
                    payload=self._build_payload(document),
                )
            ],
            wait=True,
        )

    def search_customer_evidence(
        self,
        query_vector: Sequence[float],
        tenant_id: int,
        team_id: int,
        customer_id: int,
        limit: int = 8,
        source_types: Sequence[SourceType] | None = None,
        business_object_type: str | None = None,
    ) -> list[CustomerEvidenceSearchResult]:
        if not self.enabled:
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=self._build_customer_filter(
                tenant_id=tenant_id,
                team_id=team_id,
                customer_id=customer_id,
                source_types=source_types,
                business_object_type=business_object_type,
            ),
            limit=limit,
            with_payload=True,
        )
        return [self._to_search_result(point) for point in response.points]

    def search_team_customer_evidence(
        self,
        query_vector: Sequence[float],
        tenant_id: int,
        team_id: int,
        limit: int = 20,
        source_types: Sequence[SourceType] | None = None,
        business_object_type: str | None = None,
    ) -> list[CustomerEvidenceSearchResult]:
        """Search customer evidence across the current team before a customer is resolved."""
        if not self.enabled:
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=self._build_team_filter(
                tenant_id=tenant_id,
                team_id=team_id,
                source_types=source_types,
                business_object_type=business_object_type,
            ),
            limit=limit,
            with_payload=True,
        )
        return [self._to_search_result(point) for point in response.points]

    def delete_by_source(
        self,
        tenant_id: int,
        team_id: int,
        source_type: SourceType,
        source_object_id: str,
    ) -> None:
        if not self.enabled:
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        self._match("tenant_id", tenant_id),
                        self._match("team_id", team_id),
                        self._match("source_type", source_type),
                        self._match("source_object_id", source_object_id),
                    ]
                )
            ),
            wait=True,
        )

    def _build_payload(self, document: CustomerEvidenceDocument) -> EvidencePayload:
        return {
            "tenant_id": document.tenant_id,
            "team_id": document.team_id,
            "customer_id": document.customer_id,
            "source_type": document.source_type,
            "source_object_id": document.source_object_id,
            "business_object_type": document.business_object_type,
            "business_object_id": document.business_object_id,
            "title": document.title,
            "text": document.text,
            "text_hash": document.text_hash,
            "occurred_at": document.occurred_at.isoformat() if document.occurred_at else None,
            "confidence": document.confidence,
            "visibility_scope": document.visibility_scope,
            "metadata_version": document.metadata_version,
        }

    def _build_customer_filter(
        self,
        tenant_id: int,
        team_id: int,
        customer_id: int,
        source_types: Sequence[SourceType] | None,
        business_object_type: str | None,
    ) -> qmodels.Filter:
        conditions = [
            self._match("tenant_id", tenant_id),
            self._match("team_id", team_id),
            self._match("customer_id", customer_id),
        ]
        if source_types:
            conditions.append(
                qmodels.FieldCondition(
                    key="source_type",
                    match=qmodels.MatchAny(any=list(source_types)),
                )
            )
        if business_object_type:
            conditions.append(self._match("business_object_type", business_object_type))
        return qmodels.Filter(must=conditions)

    def _build_team_filter(
        self,
        tenant_id: int,
        team_id: int,
        source_types: Sequence[SourceType] | None,
        business_object_type: str | None,
    ) -> qmodels.Filter:
        conditions = [
            self._match("tenant_id", tenant_id),
            self._match("team_id", team_id),
        ]
        if source_types:
            conditions.append(
                qmodels.FieldCondition(
                    key="source_type",
                    match=qmodels.MatchAny(any=list(source_types)),
                )
            )
        if business_object_type:
            conditions.append(self._match("business_object_type", business_object_type))
        return qmodels.Filter(must=conditions)

    def _to_search_result(self, point: qmodels.ScoredPoint) -> CustomerEvidenceSearchResult:
        payload = point.payload or {}
        return CustomerEvidenceSearchResult(
            id=str(point.id),
            score=float(point.score),
            tenant_id=self._payload_int(payload, "tenant_id"),
            team_id=self._payload_int(payload, "team_id"),
            customer_id=self._payload_int(payload, "customer_id"),
            source_type=self._payload_str(payload, "source_type"),
            source_object_id=self._payload_str(payload, "source_object_id"),
            business_object_type=self._payload_str(payload, "business_object_type"),
            business_object_id=self._payload_str(payload, "business_object_id"),
            title=self._payload_str(payload, "title"),
            text=self._payload_str(payload, "text"),
        )

    @staticmethod
    def _match(key: str, value: str | int) -> qmodels.FieldCondition:
        return qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))

    @staticmethod
    def _to_point_id(raw_id: str) -> str:
        try:
            return str(UUID(raw_id))
        except ValueError:
            return str(uuid5(NAMESPACE_URL, f"crmwolf:customer-evidence:{raw_id}"))

    @staticmethod
    def _payload_str(payload: dict[str, object], key: str) -> str | None:
        value = payload.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _payload_int(payload: dict[str, object], key: str) -> int | None:
        value = payload.get(key)
        return value if isinstance(value, int) else None


customer_qdrant_index_service = CustomerQdrantIndexService()
