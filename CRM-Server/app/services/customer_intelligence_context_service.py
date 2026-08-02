"""Unified customer intelligence retrieval context.

This service is the read-side boundary for customer intelligence. MySQL remains
the source of truth for CRM facts, while Qdrant contributes semantic evidence
that can help Agent reasoning and customer profile summarization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session, joinedload

from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.services.customer_embedding_service import (
    CustomerEmbeddingService,
    CustomerEmbeddingUnavailableError,
    customer_embedding_service,
)
from app.services.industry_display_service import industry_display_service
from app.services.customer_fact_service import CustomerFactService, customer_fact_service
from app.services.customer_qdrant_index_service import (
    CustomerEvidenceSearchResult,
    CustomerQdrantIndexService,
    SourceType,
    customer_qdrant_index_service,
)

logger = logging.getLogger(__name__)

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class CustomerFact:
    id: int
    account_name: str
    industry_code: str | None
    industry_name: str | None
    city: str | None
    address: str | None
    company_scale: str | None
    source: str | None
    status: int | None
    created_time: str | None
    returned_time: str | None
    return_reason: str | None
    loss_reason: str | None
    profile_status: str | None
    company_background: str | None
    main_business: str | None
    project_background: str | None
    similar_customers: str | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "account_name": self.account_name,
            "industry_code": self.industry_code,
            "industry_name": self.industry_name,
            "city": self.city,
            "address": self.address,
            "company_scale": self.company_scale,
            "source": self.source,
            "status": self.status,
            "created_time": self.created_time,
            "returned_time": self.returned_time,
            "return_reason": self.return_reason,
            "loss_reason": self.loss_reason,
            "profile_status": self.profile_status,
            "company_background": self.company_background,
            "main_business": self.main_business,
            "project_background": self.project_background,
            "similar_customers": self.similar_customers,
        }


@dataclass(frozen=True)
class ContactFact:
    id: int
    name: str
    position: str | None
    is_primary: bool
    is_decision_maker: bool
    remark: str | None
    reports_to: int | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "name": self.name,
            "position": self.position,
            "is_primary": self.is_primary,
            "is_decision_maker": self.is_decision_maker,
            "remark": self.remark,
            "reports_to": self.reports_to,
        }


@dataclass(frozen=True)
class OpportunityFact:
    id: int
    name: str
    stage: str | None
    win_probability: int | None
    amount: str | None
    user_count: int | None
    license_type: str | None
    purchase_type: str | None
    decision_maker_count: int | None
    expected_closing_date: str | None
    status: int | None
    approval_phase: str | None
    actual_amount: str | None
    subscription_years: int | None
    loss_reason: str | None
    created_time: str | None
    actual_closing_date: str | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "name": self.name,
            "stage": self.stage,
            "win_probability": self.win_probability,
            "amount": self.amount,
            "user_count": self.user_count,
            "license_type": self.license_type,
            "purchase_type": self.purchase_type,
            "decision_maker_count": self.decision_maker_count,
            "expected_closing_date": self.expected_closing_date,
            "status": self.status,
            "approval_phase": self.approval_phase,
            "actual_amount": self.actual_amount,
            "subscription_years": self.subscription_years,
            "loss_reason": self.loss_reason,
            "created_time": self.created_time,
            "actual_closing_date": self.actual_closing_date,
        }


@dataclass(frozen=True)
class ContractFact:
    id: int
    contract_number: str
    contract_name: str
    opportunity_id: int | None
    amount: str | None
    user_count: int | None
    license_type: str | None
    subscription_years: int | None
    status: str | None
    approval_phase: str | None
    payment_status: str | None
    total_paid_amount: str | None
    signing_date: str | None
    effective_date: str | None
    created_time: str | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "contract_number": self.contract_number,
            "contract_name": self.contract_name,
            "opportunity_id": self.opportunity_id,
            "amount": self.amount,
            "user_count": self.user_count,
            "license_type": self.license_type,
            "subscription_years": self.subscription_years,
            "status": self.status,
            "approval_phase": self.approval_phase,
            "payment_status": self.payment_status,
            "total_paid_amount": self.total_paid_amount,
            "signing_date": self.signing_date,
            "effective_date": self.effective_date,
            "created_time": self.created_time,
        }


@dataclass(frozen=True)
class PaymentPlanFact:
    id: int
    contract_id: int
    stage_name: str
    planned_amount: str | None
    due_date: str | None
    status: str | None
    notes: str | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "stage_name": self.stage_name,
            "planned_amount": self.planned_amount,
            "due_date": self.due_date,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PaymentRecordFact:
    id: int
    payment_plan_id: int
    contract_id: int | None
    actual_amount: str | None
    payment_date: str | None
    confirmation_status: str | None
    approval_phase: str | None
    notes: str | None
    record_number: str | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "payment_plan_id": self.payment_plan_id,
            "contract_id": self.contract_id,
            "actual_amount": self.actual_amount,
            "payment_date": self.payment_date,
            "confirmation_status": self.confirmation_status,
            "approval_phase": self.approval_phase,
            "notes": self.notes,
            "record_number": self.record_number,
        }


@dataclass(frozen=True)
class ActivityFact:
    id: int
    activity_kind: str
    title: str | None
    content: str
    next_action: str | None
    next_follow_time: str | None
    occurred_at: str | None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "activity_kind": self.activity_kind,
            "title": self.title,
            "content": self.content,
            "next_action": self.next_action,
            "next_follow_time": self.next_follow_time,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class CustomerEvidenceHit:
    evidence_id: str
    score: float
    source_type: str | None
    source_object_id: str | None
    business_object_type: str | None
    business_object_id: str | None
    title: str | None
    text: str | None

    def to_dict(self) -> JsonObject:
        return {
            "evidence_id": self.evidence_id,
            "score": round(self.score, 4),
            "source_type": self.source_type,
            "source_object_id": self.source_object_id,
            "business_object_type": self.business_object_type,
            "business_object_id": self.business_object_id,
            "title": self.title,
            "text": self.text,
        }


@dataclass(frozen=True)
class EvidenceRetrievalState:
    status: str
    enabled: bool
    error_message: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "status": self.status,
            "enabled": self.enabled,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class CustomerStrongContext:
    customer: CustomerFact
    customer_facts: list[JsonObject]
    contacts: list[ContactFact]
    opportunities: list[OpportunityFact]
    contracts: list[ContractFact]
    payment_plans: list[PaymentPlanFact]
    payment_records: list[PaymentRecordFact]
    recent_activities: list[ActivityFact]
    same_industry_customers: list[str]

    def to_dict(self) -> JsonObject:
        return {
            "customer": self.customer.to_dict(),
            "customer_facts": self.customer_facts,
            "contacts": [item.to_dict() for item in self.contacts],
            "opportunities": [item.to_dict() for item in self.opportunities],
            "contracts": [item.to_dict() for item in self.contracts],
            "payment_plans": [item.to_dict() for item in self.payment_plans],
            "payment_records": [item.to_dict() for item in self.payment_records],
            "recent_activities": [item.to_dict() for item in self.recent_activities],
            "same_industry_customers": self.same_industry_customers,
        }


@dataclass(frozen=True)
class CustomerIntelligenceContext:
    strong_context: CustomerStrongContext
    evidence_hits: list[CustomerEvidenceHit]
    retrieval_state: EvidenceRetrievalState

    def to_dict(self) -> JsonObject:
        return {
            "strong_context": self.strong_context.to_dict(),
            "semantic_evidence": [item.to_dict() for item in self.evidence_hits],
            "retrieval": self.retrieval_state.to_dict(),
        }

    def to_agent_payload(self) -> JsonObject:
        payload = self.to_dict()
        payload["usage_policy"] = {
            "strong_facts_source": "mysql",
            "semantic_evidence_source": "qdrant",
            "rule": "强业务事实以 strong_context 为准, semantic_evidence 只作为可引用证据和语义线索。",
        }
        return payload


class CustomerIntelligenceContextService:
    def __init__(
        self,
        embedding_service: CustomerEmbeddingService | None = None,
        qdrant_index_service: CustomerQdrantIndexService | None = None,
        fact_service: CustomerFactService | None = None,
    ) -> None:
        self.embedding_service = embedding_service or customer_embedding_service
        self.qdrant_index_service = qdrant_index_service or customer_qdrant_index_service
        self.fact_service = fact_service or customer_fact_service

    def build_context(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        query_text: str | None = None,
        evidence_limit: int = 8,
        source_types: list[SourceType] | None = None,
    ) -> CustomerIntelligenceContext:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id, Customer.team_id == team_id)
            .first()
        )
        if customer is None:
            raise ValueError("客户不存在或无权访问")

        strong_context = self._build_strong_context(db, customer=customer, team_id=team_id)
        evidence_hits, retrieval_state = self._retrieve_evidence(
            db=db,
            team_id=team_id,
            customer_id=customer_id,
            query_text=query_text,
            evidence_limit=evidence_limit,
            source_types=source_types,
        )
        return CustomerIntelligenceContext(
            strong_context=strong_context,
            evidence_hits=evidence_hits,
            retrieval_state=retrieval_state,
        )

    def _build_strong_context(self, db: Session, *, customer: Customer, team_id: int) -> CustomerStrongContext:
        contacts = (
            db.query(Contact)
            .filter(Contact.customer_id == customer.id, Contact.team_id == team_id)
            .order_by(Contact.is_primary.desc(), Contact.is_decision_maker.desc(), Contact.created_time.asc())
            .limit(50)
            .all()
        )
        opportunities = (
            db.query(Opportunity)
            .filter(Opportunity.customer_id == customer.id, Opportunity.team_id == team_id)
            .order_by(Opportunity.status.asc(), Opportunity.last_modified_time.desc())
            .limit(50)
            .all()
        )
        contracts = (
            db.query(Contract)
            .options(joinedload(Contract.payment_plans).joinedload(PaymentPlan.payment_records))
            .filter(Contract.customer_id == customer.id, Contract.team_id == team_id, Contract.deleted_at.is_(None))
            .order_by(Contract.created_time.desc())
            .limit(50)
            .all()
        )
        activities = (
            db.query(CustomerActivity)
            .filter(CustomerActivity.customer_id == customer.id, CustomerActivity.team_id == team_id)
            .order_by(CustomerActivity.occurred_at.desc())
            .limit(50)
            .all()
        )
        same_industry_rows = (
            db.query(Customer.account_name)
            .filter(Customer.team_id == team_id, Customer.id != customer.id, Customer.industry == customer.industry)
            .order_by(Customer.last_modified_time.desc())
            .limit(10)
            .all()
            if customer.industry
            else []
        )

        payment_plans: list[PaymentPlanFact] = []
        payment_records: list[PaymentRecordFact] = []
        for contract in contracts:
            for plan in sorted(contract.payment_plans or [], key=lambda item: item.due_date or date.min):
                payment_plans.append(self._payment_plan_fact(plan))
                for record in sorted(plan.payment_records or [], key=lambda item: item.payment_date or date.min):
                    payment_records.append(self._payment_record_fact(record, plan.contract_id))

        return CustomerStrongContext(
            customer=self._customer_fact(db, customer),
            customer_facts=self.fact_service.to_context_payload(db, team_id=team_id, customer_id=int(customer.id), limit=50),
            contacts=[self._contact_fact(item) for item in contacts],
            opportunities=[self._opportunity_fact(item) for item in opportunities],
            contracts=[self._contract_fact(item) for item in contracts],
            payment_plans=payment_plans,
            payment_records=payment_records,
            recent_activities=[self._activity_fact(item) for item in activities],
            same_industry_customers=[str(row[0]) for row in same_industry_rows],
        )

    def _retrieve_evidence(
        self,
        *,
        db: Session,
        team_id: int,
        customer_id: int,
        query_text: str | None,
        evidence_limit: int,
        source_types: list[SourceType] | None,
    ) -> tuple[list[CustomerEvidenceHit], EvidenceRetrievalState]:
        if not self.qdrant_index_service.enabled:
            return [], EvidenceRetrievalState(status="disabled", enabled=False)
        if not query_text or not query_text.strip():
            return [], EvidenceRetrievalState(status="skipped_empty_query", enabled=True)

        try:
            vector = self.embedding_service.embed_query(db, team_id, query_text)
            results = self.qdrant_index_service.search_customer_evidence(
                query_vector=vector,
                tenant_id=team_id,
                team_id=team_id,
                customer_id=customer_id,
                limit=evidence_limit,
                source_types=source_types,
            )
        except CustomerEmbeddingUnavailableError as exc:
            logger.info("客户智能证据检索跳过: %s", exc)
            return [], EvidenceRetrievalState(status="embedding_unavailable", enabled=True, error_message=str(exc))
        except Exception as exc:
            logger.exception("客户智能证据检索失败: customer_id=%s", customer_id)
            return [], EvidenceRetrievalState(status="failed", enabled=True, error_message=str(exc))

        return [self._evidence_hit(item) for item in results], EvidenceRetrievalState(status="ok", enabled=True)

    def _customer_fact(self, db: Session, customer: Customer) -> CustomerFact:
        return CustomerFact(
            id=int(customer.id),
            account_name=customer.account_name,
            industry_code=customer.industry,
            industry_name=industry_display_service.display_name(db, customer.industry),
            city=customer.city,
            address=customer.address,
            company_scale=customer.company_scale,
            source=customer.source,
            status=self._optional_int(customer.status),
            created_time=self._datetime(customer.created_time),
            returned_time=self._datetime(customer.returned_time),
            return_reason=customer.return_reason,
            loss_reason=customer.loss_reason,
            profile_status=customer.profile_status,
            company_background=customer.company_background,
            main_business=customer.main_business,
            project_background=customer.project_background,
            similar_customers=customer.similar_customers,
        )

    def _contact_fact(self, contact: Contact) -> ContactFact:
        return ContactFact(
            id=int(contact.id),
            name=contact.name,
            position=contact.position,
            is_primary=bool(contact.is_primary),
            is_decision_maker=bool(contact.is_decision_maker),
            remark=contact.remark,
            reports_to=self._optional_int(contact.reports_to),
        )

    def _opportunity_fact(self, opportunity: Opportunity) -> OpportunityFact:
        return OpportunityFact(
            id=int(opportunity.id),
            name=opportunity.opportunity_name,
            stage=opportunity.current_stage_name,
            win_probability=self._optional_int(opportunity.current_win_probability),
            amount=self._decimal(opportunity.total_amount),
            user_count=self._optional_int(opportunity.user_count),
            license_type=opportunity.license_type,
            purchase_type=opportunity.purchase_type,
            decision_maker_count=self._optional_int(opportunity.decision_maker_count),
            expected_closing_date=self._date(opportunity.expected_closing_date),
            status=self._optional_int(opportunity.status),
            approval_phase=opportunity.approval_phase,
            actual_amount=self._decimal(opportunity.actual_amount),
            subscription_years=self._optional_int(opportunity.subscription_years),
            loss_reason=opportunity.loss_reason,
            created_time=self._datetime(opportunity.created_time),
            actual_closing_date=self._date(opportunity.actual_closing_date),
        )

    def _contract_fact(self, contract: Contract) -> ContractFact:
        return ContractFact(
            id=int(contract.id),
            contract_number=contract.contract_number,
            contract_name=contract.contract_name,
            opportunity_id=self._optional_int(contract.opportunity_id),
            amount=self._decimal(contract.total_amount),
            user_count=self._optional_int(contract.user_count),
            license_type=contract.license_type,
            subscription_years=self._optional_int(contract.subscription_years),
            status=contract.status,
            approval_phase=contract.approval_phase,
            payment_status=contract.payment_status,
            total_paid_amount=self._decimal(contract.total_paid_amount),
            signing_date=self._date(contract.signing_date),
            effective_date=self._date(contract.effective_date),
            created_time=self._datetime(contract.created_time),
        )

    def _payment_plan_fact(self, plan: PaymentPlan) -> PaymentPlanFact:
        return PaymentPlanFact(
            id=int(plan.id),
            contract_id=int(plan.contract_id),
            stage_name=plan.stage_name,
            planned_amount=self._decimal(plan.planned_amount),
            due_date=self._date(plan.due_date),
            status=plan.status,
            notes=plan.notes,
        )

    def _payment_record_fact(self, record: PaymentRecord, contract_id: int | None) -> PaymentRecordFact:
        return PaymentRecordFact(
            id=int(record.id),
            payment_plan_id=int(record.payment_plan_id),
            contract_id=self._optional_int(contract_id),
            actual_amount=self._decimal(record.actual_amount),
            payment_date=self._date(record.payment_date),
            confirmation_status=record.confirmation_status,
            approval_phase=record.approval_phase,
            notes=record.notes,
            record_number=record.record_number,
        )

    def _activity_fact(self, activity: CustomerActivity) -> ActivityFact:
        return ActivityFact(
            id=int(activity.id),
            activity_kind=activity.activity_kind,
            title=activity.title,
            content=activity.summary or activity.source_content,
            next_action=activity.next_action,
            next_follow_time=self._datetime(activity.next_follow_time),
            occurred_at=self._datetime(activity.occurred_at),
        )

    def _evidence_hit(self, result: CustomerEvidenceSearchResult) -> CustomerEvidenceHit:
        return CustomerEvidenceHit(
            evidence_id=result.id,
            score=result.score,
            source_type=result.source_type,
            source_object_id=result.source_object_id,
            business_object_type=result.business_object_type,
            business_object_id=result.business_object_id,
            title=result.title,
            text=result.text,
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, Enum):
            return int(value.value)
        return int(value)

    @staticmethod
    def _decimal(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)

    @staticmethod
    def _date(value: date | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value else None


customer_intelligence_context_service = CustomerIntelligenceContextService()
