"""Retire DELETE_PENDING customer evidence points and verify absence in Qdrant."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.customer_vector_document import CustomerVectorDocument, CustomerVectorDocumentSyncStatus


@dataclass(frozen=True)
class RetirementReport:
    pending_count: int
    deleted_count: int
    verified_absent_count: int


class VectorRetirementIncomplete(RuntimeError):
    """Raised when a Qdrant point still exists after deletion."""


class CustomerProfileVectorRetirementService:
    def retire_pending_documents(self, db: Session, qdrant_client: object) -> RetirementReport:
        documents = (
            db.query(CustomerVectorDocument)
            .filter(CustomerVectorDocument.sync_status == CustomerVectorDocumentSyncStatus.DELETE_PENDING)
            .all()
        )
        delete_points = getattr(qdrant_client, "delete_points", None)
        point_exists = getattr(qdrant_client, "point_exists", None)
        if delete_points is None or point_exists is None:
            raise VectorRetirementIncomplete("qdrant client lacks delete_points/point_exists")

        point_ids = [document.qdrant_point_id for document in documents]
        if point_ids:
            delete_points(point_ids)

        remaining = [pid for pid in point_ids if point_exists(pid)]
        if remaining:
            raise VectorRetirementIncomplete(f"{len(remaining)} points still present after deletion")

        return RetirementReport(
            pending_count=len(documents),
            deleted_count=len(point_ids),
            verified_absent_count=len(point_ids) - len(remaining),
        )


customer_profile_vector_retirement_service = CustomerProfileVectorRetirementService()
