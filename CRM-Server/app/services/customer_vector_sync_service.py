"""Synchronize customer evidence metadata rows to the vector index."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.customer_vector_document import CustomerVectorDocument, CustomerVectorDocumentSyncStatus
from app.services.customer_embedding_service import CustomerEmbeddingService, customer_embedding_service
from app.services.customer_qdrant_index_service import (
    CustomerEvidenceDocument,
    SourceType,
    customer_qdrant_index_service,
)
from app.services.customer_vector_document_service import (
    CustomerVectorDocumentService,
    customer_vector_document_service,
)

logger = logging.getLogger(__name__)


class CustomerVectorIndexWriter(Protocol):
    def ensure_collection(self) -> bool:
        raise NotImplementedError

    def upsert_evidence(self, document: CustomerEvidenceDocument) -> None:
        raise NotImplementedError

    def delete_by_source(
        self,
        tenant_id: int,
        team_id: int,
        source_type: SourceType,
        source_object_id: str,
    ) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class CustomerEvidenceSyncStats:
    scanned: int = 0
    upserted: int = 0
    deleted: int = 0
    failed: int = 0


class CustomerVectorSyncService:
    def __init__(
        self,
        metadata_service: CustomerVectorDocumentService | None = None,
        embedding_service: CustomerEmbeddingService | None = None,
        index_writer: CustomerVectorIndexWriter | None = None,
    ) -> None:
        self.metadata_service = metadata_service or customer_vector_document_service
        self.embedding_service = embedding_service or customer_embedding_service
        self.index_writer = index_writer or customer_qdrant_index_service

    def sync_once(self, db: Session, limit: int | None = None) -> CustomerEvidenceSyncStats:
        settings = get_settings()
        batch_limit = limit or settings.CUSTOMER_EVIDENCE_SYNC_BATCH_SIZE
        collection_created_or_recreated = self.index_writer.ensure_collection()
        if collection_created_or_recreated:
            requeued = self.metadata_service.requeue_indexable_documents(db)
            if requeued > 0:
                logger.info("客户证据向量索引已重建, 历史证据重新入队: count=%s", requeued)
        candidates = self.metadata_service.list_sync_candidates(db, batch_limit)

        upserted = 0
        deleted = 0
        failed = 0
        for document in candidates:
            try:
                if document.sync_status == CustomerVectorDocumentSyncStatus.DELETE_PENDING:
                    self._delete_document(db, document)
                    deleted += 1
                else:
                    self._upsert_document(db, document)
                    upserted += 1
            except Exception as exc:
                failed += 1
                logger.exception("客户证据向量同步失败: document_id=%s", document.id)
                self.metadata_service.mark_sync_failed(db, document, _safe_error_message(exc))

        return CustomerEvidenceSyncStats(
            scanned=len(candidates),
            upserted=upserted,
            deleted=deleted,
            failed=failed,
        )

    def _upsert_document(self, db: Session, document: CustomerVectorDocument) -> None:
        vector = self.embedding_service.embed_query(db, int(document.team_id), document.text)
        self.index_writer.upsert_evidence(self._to_evidence_document(document, vector))
        self.metadata_service.mark_synced(db, document)

    def _delete_document(self, db: Session, document: CustomerVectorDocument) -> None:
        self.index_writer.delete_by_source(
            tenant_id=int(document.tenant_id),
            team_id=int(document.team_id),
            source_type=cast("SourceType", document.source_type),
            source_object_id=document.source_object_id,
        )
        self.metadata_service.mark_delete_synced(db, document)

    def _to_evidence_document(
        self,
        document: CustomerVectorDocument,
        vector: Sequence[float],
    ) -> CustomerEvidenceDocument:
        return CustomerEvidenceDocument(
            id=document.qdrant_point_id,
            tenant_id=int(document.tenant_id),
            team_id=int(document.team_id),
            customer_id=int(document.customer_id),
            source_type=cast("SourceType", document.source_type),
            source_object_id=document.source_object_id,
            text=document.text,
            vector=vector,
            title=document.title,
            business_object_type=document.business_object_type,
            business_object_id=document.business_object_id,
            text_hash=document.text_hash,
            occurred_at=document.occurred_at,
            confidence=document.confidence,
            visibility_scope=document.visibility_scope,
            metadata_version=int(document.metadata_version),
        )


def _safe_error_message(exc: BaseException, limit: int = 2000) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:limit]


customer_vector_sync_service = CustomerVectorSyncService()
