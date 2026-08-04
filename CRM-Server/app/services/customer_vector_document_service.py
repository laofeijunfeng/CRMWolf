"""Persistence service for customer evidence metadata."""

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import (
    CustomerVectorDocument,
    CustomerVectorDocumentSourceType,
    CustomerVectorDocumentSyncStatus,
)
from app.models.deal_journey import CustomerDealJourneyEvent
from app.services.customer_evidence_builder import BuiltCustomerEvidence, customer_evidence_builder
from app.services.industry_display_service import industry_display_service
from app.utils.time import business_now


class CustomerVectorDocumentService:
    def list_sync_candidates(self, db: Session, limit: int) -> list[CustomerVectorDocument]:
        return (
            db.query(CustomerVectorDocument)
            .filter(
                CustomerVectorDocument.sync_status.in_(
                    [
                        CustomerVectorDocumentSyncStatus.PENDING,
                        CustomerVectorDocumentSyncStatus.FAILED,
                        CustomerVectorDocumentSyncStatus.DELETE_PENDING,
                    ]
                )
            )
            .order_by(CustomerVectorDocument.updated_time.asc(), CustomerVectorDocument.id.asc())
            .limit(limit)
            .all()
        )

    def requeue_indexable_documents(self, db: Session, *, commit: bool = True) -> int:
        documents = (
            db.query(CustomerVectorDocument)
            .filter(
                CustomerVectorDocument.sync_status.in_(
                    [
                        CustomerVectorDocumentSyncStatus.SYNCED,
                        CustomerVectorDocumentSyncStatus.FAILED,
                    ]
                )
            )
            .all()
        )
        for document in documents:
            document.sync_status = CustomerVectorDocumentSyncStatus.PENDING
            document.sync_error = None
            document.synced_at = None
            document.updated_time = business_now()
        if documents:
            if commit:
                db.commit()
            else:
                db.flush()
        return len(documents)

    def list_stale_customer_profile_customers(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        metadata_version: int | None = None,
        limit: int = 100,
    ) -> list[Customer]:
        target_metadata_version = metadata_version or customer_evidence_builder.metadata_version
        profile_document_join = and_(
            CustomerVectorDocument.team_id == Customer.team_id,
            CustomerVectorDocument.customer_id == Customer.id,
            CustomerVectorDocument.source_type == CustomerVectorDocumentSourceType.CUSTOMER_PROFILE,
        )
        query = (
            db.query(Customer)
            .outerjoin(CustomerVectorDocument, profile_document_join)
            .filter(
                Customer.account_name.isnot(None),
                Customer.account_name != "",
                (
                    (CustomerVectorDocument.id.is_(None))
                    | (CustomerVectorDocument.metadata_version < target_metadata_version)
                    | (
                        CustomerVectorDocument.sync_status.in_([
                            CustomerVectorDocumentSyncStatus.FAILED,
                            CustomerVectorDocumentSyncStatus.DELETED,
                        ])
                    )
                ),
            )
        )
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        return query.order_by(Customer.id.asc()).limit(max(1, min(limit, 500))).all()

    def rebuild_stale_customer_profiles(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        metadata_version: int | None = None,
        limit: int = 100,
        commit: bool = True,
    ) -> list[int]:
        customers = self.list_stale_customer_profile_customers(
            db,
            team_id=team_id,
            metadata_version=metadata_version,
            limit=limit,
        )
        rebuilt_customer_ids: list[int] = []
        for customer in customers:
            document = self.upsert_customer_profile(db, customer, commit=False)
            if document is not None:
                rebuilt_customer_ids.append(int(customer.id))
        if rebuilt_customer_ids:
            if commit:
                db.commit()
            else:
                db.flush()
        return rebuilt_customer_ids

    def upsert_evidence_metadata(
        self,
        db: Session,
        evidence: BuiltCustomerEvidence,
        *,
        commit: bool = True,
    ) -> CustomerVectorDocument:
        existing = (
            db.query(CustomerVectorDocument)
            .filter(CustomerVectorDocument.document_key == evidence.document_key)
            .first()
        )
        if existing:
            existing.tenant_id = evidence.tenant_id
            existing.team_id = evidence.team_id
            existing.customer_id = evidence.customer_id
            existing.source_type = evidence.source_type
            existing.source_object_id = evidence.source_object_id
            existing.business_object_type = evidence.business_object_type
            existing.business_object_id = evidence.business_object_id
            existing.title = evidence.title
            existing.text = evidence.text
            existing.text_hash = evidence.text_hash
            existing.qdrant_point_id = evidence.qdrant_point_id
            existing.occurred_at = evidence.occurred_at
            existing.confidence = evidence.confidence
            existing.visibility_scope = evidence.visibility_scope
            existing.metadata_version = evidence.metadata_version
            existing.sync_status = CustomerVectorDocumentSyncStatus.PENDING
            existing.sync_error = None
            existing.synced_at = None
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(existing)
            return existing

        document = CustomerVectorDocument(
            document_key=evidence.document_key,
            tenant_id=evidence.tenant_id,
            team_id=evidence.team_id,
            customer_id=evidence.customer_id,
            source_type=evidence.source_type,
            source_object_id=evidence.source_object_id,
            business_object_type=evidence.business_object_type,
            business_object_id=evidence.business_object_id,
            title=evidence.title,
            text=evidence.text,
            text_hash=evidence.text_hash,
            qdrant_point_id=evidence.qdrant_point_id,
            occurred_at=evidence.occurred_at,
            confidence=evidence.confidence,
            visibility_scope=evidence.visibility_scope,
            metadata_version=evidence.metadata_version,
            sync_status=CustomerVectorDocumentSyncStatus.PENDING,
        )
        db.add(document)
        if commit:
            db.commit()
            db.refresh(document)
        else:
            db.flush()
        return document

    def upsert_customer_activity(
        self,
        db: Session,
        activity: CustomerActivity,
        *,
        commit: bool = True,
    ) -> CustomerVectorDocument | None:
        evidence = customer_evidence_builder.from_customer_activity(activity)
        if evidence is None:
            return None
        return self.upsert_evidence_metadata(db, evidence, commit=commit)

    def upsert_customer_profile(
        self,
        db: Session,
        customer: Customer,
        *,
        commit: bool = True,
    ) -> CustomerVectorDocument | None:
        evidence = customer_evidence_builder.from_customer_profile(
            customer,
            industry_display_name=industry_display_service.display_name(db, customer.industry),
        )
        if evidence is None:
            return None
        return self.upsert_evidence_metadata(db, evidence, commit=commit)

    def upsert_customer_brief(
        self,
        db: Session,
        customer: Customer,
        *,
        commit: bool = True,
    ) -> CustomerVectorDocument | None:
        evidence = customer_evidence_builder.from_customer_brief(customer)
        if evidence is None:
            return None
        return self.upsert_evidence_metadata(db, evidence, commit=commit)

    def upsert_deal_journey_event(
        self,
        db: Session,
        event: CustomerDealJourneyEvent,
        *,
        commit: bool = True,
    ) -> CustomerVectorDocument | None:
        evidence = customer_evidence_builder.from_deal_journey_event(event)
        if evidence is None:
            return None
        return self.upsert_evidence_metadata(db, evidence, commit=commit)

    def mark_source_deleted(self, db: Session, team_id: int, source_type: str, source_object_id: str) -> int:
        documents = (
            db.query(CustomerVectorDocument)
            .filter(
                CustomerVectorDocument.team_id == team_id,
                CustomerVectorDocument.source_type == source_type,
                CustomerVectorDocument.source_object_id == source_object_id,
                CustomerVectorDocument.sync_status.notin_(
                    [
                        CustomerVectorDocumentSyncStatus.DELETE_PENDING,
                        CustomerVectorDocumentSyncStatus.DELETED,
                    ]
                ),
            )
            .all()
        )
        for document in documents:
            document.sync_status = CustomerVectorDocumentSyncStatus.DELETE_PENDING
            document.sync_error = None
            document.updated_time = business_now()
        if documents:
            db.commit()
        return len(documents)

    def mark_customer_activity_deleted(self, db: Session, activity: CustomerActivity) -> int:
        return self.mark_source_deleted(
            db=db,
            team_id=int(activity.team_id),
            source_type=CustomerVectorDocumentSourceType.FOLLOW_UP,
            source_object_id=str(activity.id),
        )

    def mark_synced(self, db: Session, document: CustomerVectorDocument) -> CustomerVectorDocument:
        document.sync_status = CustomerVectorDocumentSyncStatus.SYNCED
        document.sync_error = None
        document.synced_at = business_now()
        db.commit()
        db.refresh(document)
        return document

    def mark_sync_failed(
        self,
        db: Session,
        document: CustomerVectorDocument,
        error_message: str,
    ) -> CustomerVectorDocument:
        document.sync_status = CustomerVectorDocumentSyncStatus.FAILED
        document.sync_error = error_message[:2000]
        db.commit()
        db.refresh(document)
        return document

    def mark_delete_synced(self, db: Session, document: CustomerVectorDocument) -> CustomerVectorDocument:
        document.sync_status = CustomerVectorDocumentSyncStatus.DELETED
        document.sync_error = None
        document.synced_at = business_now()
        db.commit()
        db.refresh(document)
        return document


customer_vector_document_service = CustomerVectorDocumentService()
