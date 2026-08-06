from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_vector_document import (
    CustomerVectorDocument,
    CustomerVectorDocumentSourceType,
    CustomerVectorDocumentSyncStatus,
)
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.services.customer_evidence_builder import BuiltCustomerEvidence, customer_evidence_builder
from app.services.customer_vector_document_service import (
    CustomerVectorDocumentService,
    customer_vector_document_service,
)
from app.utils.time import business_now

TASK_VECTOR_SOURCE_TYPES = (
    CustomerVectorDocumentSourceType.FOLLOW_UP_TASK,
    CustomerVectorDocumentSourceType.SALES_COMMITMENT,
)


@dataclass(frozen=True)
class CustomerVectorEvidenceReconciliationItem:
    document_id: int
    source_type: str
    source_object_id: str
    action: str
    reason: str
    business_object_id: str | None = None


@dataclass(frozen=True)
class CustomerVectorEvidenceReconciliationResult:
    scanned: int = 0
    refreshed: int = 0
    delete_pending: int = 0
    unchanged: int = 0
    items: list[CustomerVectorEvidenceReconciliationItem] = field(default_factory=list)

    def as_event(self) -> dict[str, Any]:
        return {
            "event": "customer_vector_evidence_reconciliation",
            "scanned": self.scanned,
            "refreshed": self.refreshed,
            "delete_pending": self.delete_pending,
            "unchanged": self.unchanged,
            "items": [
                {
                    "document_id": item.document_id,
                    "source_type": item.source_type,
                    "source_object_id": item.source_object_id,
                    "business_object_id": item.business_object_id,
                    "action": item.action,
                    "reason": item.reason,
                }
                for item in self.items
            ],
        }


class CustomerVectorEvidenceReconciliationService:
    """Keep task/commitment vector metadata aligned with MySQL facts."""

    def __init__(
        self,
        *,
        vector_document_service: CustomerVectorDocumentService | None = None,
    ) -> None:
        self.vector_document_service = vector_document_service or customer_vector_document_service

    def reconcile_once(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        limit: int = 200,
        commit: bool = True,
    ) -> CustomerVectorEvidenceReconciliationResult:
        documents = self._list_documents(db, team_id=team_id, limit=limit)
        items: list[CustomerVectorEvidenceReconciliationItem] = []
        refreshed = 0
        delete_pending = 0
        unchanged = 0

        for document in documents:
            item = self._reconcile_document(db, document)
            items.append(item)
            if item.action == "refreshed":
                refreshed += 1
            elif item.action == "delete_pending":
                delete_pending += 1
            else:
                unchanged += 1

        if refreshed or delete_pending:
            if commit:
                db.commit()
            else:
                db.flush()

        return CustomerVectorEvidenceReconciliationResult(
            scanned=len(documents),
            refreshed=refreshed,
            delete_pending=delete_pending,
            unchanged=unchanged,
            items=items,
        )

    def _list_documents(
        self,
        db: Session,
        *,
        team_id: int | None,
        limit: int,
    ) -> list[CustomerVectorDocument]:
        query = db.query(CustomerVectorDocument).filter(CustomerVectorDocument.source_type.in_(TASK_VECTOR_SOURCE_TYPES))
        if team_id is not None:
            query = query.filter(CustomerVectorDocument.team_id == team_id)
        return query.order_by(CustomerVectorDocument.updated_time.asc(), CustomerVectorDocument.id.asc()).limit(
            max(1, min(limit, 1000))
        ).all()

    def _reconcile_document(
        self,
        db: Session,
        document: CustomerVectorDocument,
    ) -> CustomerVectorEvidenceReconciliationItem:
        if document.source_type == CustomerVectorDocumentSourceType.FOLLOW_UP_TASK:
            return self._reconcile_task_document(db, document)
        if document.source_type == CustomerVectorDocumentSourceType.SALES_COMMITMENT:
            return self._reconcile_commitment_document(db, document)
        return self._unchanged(document, "unsupported_source_type")

    def _reconcile_task_document(
        self,
        db: Session,
        document: CustomerVectorDocument,
    ) -> CustomerVectorEvidenceReconciliationItem:
        task_public_id = self._public_id_from_document(document, metadata_key="task_public_id", expected_prefix="fut_")
        if not task_public_id:
            return self._mark_delete_pending(document, "invalid_task_public_id")

        task = (
            db.query(FollowUpTask)
            .filter(
                FollowUpTask.team_id == document.team_id,
                FollowUpTask.public_id == task_public_id,
            )
            .first()
        )
        if task is None:
            return self._mark_delete_pending(document, "task_not_found", business_object_id=task_public_id)

        expected = self._build_task_evidence(db, task)
        if expected is None:
            return self._mark_delete_pending(document, "task_evidence_empty", business_object_id=task_public_id)
        if self._document_matches_evidence(document, expected):
            return self._unchanged(document, "metadata_current", business_object_id=task_public_id)

        self.vector_document_service.upsert_follow_up_task(db, task, commit=False)
        return self._refreshed(document, "metadata_stale", business_object_id=task_public_id)

    def _reconcile_commitment_document(
        self,
        db: Session,
        document: CustomerVectorDocument,
    ) -> CustomerVectorEvidenceReconciliationItem:
        commitment_public_id = self._public_id_from_document(
            document,
            metadata_key="commitment_public_id",
            expected_prefix="scm_",
        )
        if not commitment_public_id:
            return self._mark_delete_pending(document, "invalid_commitment_public_id")

        commitment = (
            db.query(SalesCommitment)
            .filter(
                SalesCommitment.team_id == document.team_id,
                SalesCommitment.public_id == commitment_public_id,
            )
            .first()
        )
        if commitment is None:
            return self._mark_delete_pending(
                document,
                "commitment_not_found",
                business_object_id=commitment_public_id,
            )

        expected = self._build_commitment_evidence(db, commitment)
        if expected is None:
            return self._mark_delete_pending(
                document,
                "commitment_evidence_empty",
                business_object_id=commitment_public_id,
            )
        if self._document_matches_evidence(document, expected):
            return self._unchanged(document, "metadata_current", business_object_id=commitment_public_id)

        self.vector_document_service.upsert_sales_commitment(db, commitment, commit=False)
        return self._refreshed(document, "metadata_stale", business_object_id=commitment_public_id)

    def _build_task_evidence(self, db: Session, task: FollowUpTask) -> BuiltCustomerEvidence | None:
        customer = self._get_customer(db, customer_id=int(task.customer_id), team_id=int(task.team_id))
        commitment = None
        if task.commitment_id is not None:
            commitment = (
                db.query(SalesCommitment)
                .filter(
                    SalesCommitment.id == task.commitment_id,
                    SalesCommitment.team_id == task.team_id,
                )
                .first()
            )
        return customer_evidence_builder.from_follow_up_task(task, customer=customer, commitment=commitment)

    def _build_commitment_evidence(
        self,
        db: Session,
        commitment: SalesCommitment,
    ) -> BuiltCustomerEvidence | None:
        customer = self._get_customer(db, customer_id=int(commitment.customer_id), team_id=int(commitment.team_id))
        return customer_evidence_builder.from_sales_commitment(commitment, customer=customer)

    def _get_customer(self, db: Session, *, customer_id: int, team_id: int) -> Customer | None:
        return db.query(Customer).filter(Customer.id == customer_id, Customer.team_id == team_id).first()

    def _document_matches_evidence(
        self,
        document: CustomerVectorDocument,
        expected: BuiltCustomerEvidence,
    ) -> bool:
        return (
            document.tenant_id == expected.tenant_id
            and document.team_id == expected.team_id
            and document.customer_id == expected.customer_id
            and document.source_type == expected.source_type
            and document.source_object_id == expected.source_object_id
            and document.business_object_type == expected.business_object_type
            and document.business_object_id == expected.business_object_id
            and document.title == expected.title
            and document.text_hash == expected.text_hash
            and self._json_value(document.metadata_json) == self._json_value(expected.metadata_json)
            and document.qdrant_point_id == expected.qdrant_point_id
            and document.occurred_at == expected.occurred_at
            and float(document.confidence or 0) == float(expected.confidence)
            and document.visibility_scope == expected.visibility_scope
            and document.metadata_version == expected.metadata_version
            and document.sync_status
            not in (
                CustomerVectorDocumentSyncStatus.DELETE_PENDING,
                CustomerVectorDocumentSyncStatus.DELETED,
            )
        )

    def _public_id_from_document(
        self,
        document: CustomerVectorDocument,
        *,
        metadata_key: str,
        expected_prefix: str,
    ) -> str | None:
        metadata = self._json_value(document.metadata_json)
        for value in (
            metadata.get(metadata_key) if isinstance(metadata, dict) else None,
            document.business_object_id,
            document.source_object_id,
        ):
            if isinstance(value, str) and value.startswith(expected_prefix):
                return value
        return None

    def _mark_delete_pending(
        self,
        document: CustomerVectorDocument,
        reason: str,
        *,
        business_object_id: str | None = None,
    ) -> CustomerVectorEvidenceReconciliationItem:
        if document.sync_status not in (
            CustomerVectorDocumentSyncStatus.DELETE_PENDING,
            CustomerVectorDocumentSyncStatus.DELETED,
        ):
            document.sync_status = CustomerVectorDocumentSyncStatus.DELETE_PENDING
            document.sync_error = None
            document.synced_at = None
            document.updated_time = business_now()
            action = "delete_pending"
        else:
            action = "unchanged"
        return CustomerVectorEvidenceReconciliationItem(
            document_id=int(document.id),
            source_type=str(document.source_type),
            source_object_id=str(document.source_object_id),
            business_object_id=business_object_id,
            action=action,
            reason=reason,
        )

    def _refreshed(
        self,
        document: CustomerVectorDocument,
        reason: str,
        *,
        business_object_id: str | None,
    ) -> CustomerVectorEvidenceReconciliationItem:
        return CustomerVectorEvidenceReconciliationItem(
            document_id=int(document.id),
            source_type=str(document.source_type),
            source_object_id=str(document.source_object_id),
            business_object_id=business_object_id,
            action="refreshed",
            reason=reason,
        )

    def _unchanged(
        self,
        document: CustomerVectorDocument,
        reason: str,
        *,
        business_object_id: str | None = None,
    ) -> CustomerVectorEvidenceReconciliationItem:
        return CustomerVectorEvidenceReconciliationItem(
            document_id=int(document.id),
            source_type=str(document.source_type),
            source_object_id=str(document.source_object_id),
            business_object_id=business_object_id,
            action="unchanged",
            reason=reason,
        )

    def _json_value(self, value: Any) -> Any:
        return value if isinstance(value, dict) else {}


customer_vector_evidence_reconciliation_service = CustomerVectorEvidenceReconciliationService()
