"""Unified customer intelligence retrieval context.

This service is the read-side boundary for customer intelligence. MySQL remains
the source of truth for CRM facts, while Qdrant contributes semantic evidence
that can help Agent reasoning and customer profile summarization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, joinedload

from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent, SalesCommitment
from app.services.customer_evidence_retriever import (
    CustomerEvidenceHit,
    CustomerEvidenceRetriever,
    EvidenceRetrievalState,
    customer_evidence_retriever,
)
from app.services.customer_fact_service import CustomerFactService, customer_fact_service
from app.services.industry_display_service import industry_display_service

if TYPE_CHECKING:
    from app.services.customer_qdrant_index_service import SourceType

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class CustomerIntelligenceContextNotFound(ValueError):
    """The requested customer is not visible within the owning team."""


@dataclass(frozen=True)
class CustomerFact:
    id: int
    public_id: str
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

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "public_id": self.public_id,
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
    deal_journey_id: int | None = None

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
            "deal_journey_id": self.deal_journey_id,
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
    deal_journey_id: int | None = None

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
            "deal_journey_id": self.deal_journey_id,
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
    deal_journey_id: int | None = None
    source_content: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "activity_kind": self.activity_kind,
            "title": self.title,
            "content": self.content,
            "next_action": self.next_action,
            "next_follow_time": self.next_follow_time,
            "occurred_at": self.occurred_at,
            "deal_journey_id": self.deal_journey_id,
            "source_content": self.source_content,
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
    deal_journeys: list[JsonObject] = field(default_factory=list)
    deal_journey_events: list[JsonObject] = field(default_factory=list)
    recorded_follow_ups: list[JsonObject] = field(default_factory=list)
    sales_commitments: list[JsonObject] = field(default_factory=list)
    follow_up_task_events: list[JsonObject] = field(default_factory=list)
    source_watermarks: JsonObject = field(default_factory=dict)

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
            "deal_journeys": self.deal_journeys,
            "deal_journey_events": self.deal_journey_events,
            "recorded_follow_ups": self.recorded_follow_ups,
            "sales_commitments": self.sales_commitments,
            "follow_up_task_events": self.follow_up_task_events,
            "source_watermarks": self.source_watermarks,
        }


@dataclass(frozen=True)
class CustomerIntelligenceContext:
    strong_context: CustomerStrongContext
    evidence_hits: list[CustomerEvidenceHit]
    retrieval_state: EvidenceRetrievalState
    source_watermark: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "strong_context": self.strong_context.to_dict(),
            "semantic_evidence": [item.to_dict() for item in self.evidence_hits],
            "retrieval": self.retrieval_state.to_dict(),
            "source_watermark": self.source_watermark or self.strong_context.source_watermarks,
        }

    def to_agent_payload(self) -> JsonObject:
        payload = self.to_dict()
        payload["usage_policy"] = {
            "strong_facts_source": "mysql",
            "semantic_evidence_source": "qdrant",
            "memory_source": "langgraph_store",
            "rule": "强业务事实以 strong_context 为准, semantic_evidence 只作为可引用证据和语义线索。",
            "grounding": {
                "ok": "可基于 citations 输出 grounded 回答。",
                "low_confidence": "只能基于 strong_context 和 customer_memory 回答, 并标记缺少高置信度语义证据。",
                "empty": "只能基于 strong_context 和 customer_memory 回答, 不得声称已使用语义证据。",
                "unavailable": "检索不可用时降级回答, 需要暴露 degraded answer_mode 给系统侧观测。",
            },
        }
        payload["citations"] = [item.to_citation() for item in self.evidence_hits]
        return payload


class CustomerIntelligenceContextService:
    def __init__(
        self,
        embedding_service: object | None = None,
        qdrant_index_service: object | None = None,
        evidence_retriever: CustomerEvidenceRetriever | None = None,
        fact_service: CustomerFactService | None = None,
    ) -> None:
        if evidence_retriever is not None:
            self.evidence_retriever = evidence_retriever
        elif embedding_service is not None or qdrant_index_service is not None:
            self.evidence_retriever = CustomerEvidenceRetriever(
                embedding_service=embedding_service,  # type: ignore[arg-type]
                qdrant_index_service=qdrant_index_service,  # type: ignore[arg-type]
            )
        else:
            self.evidence_retriever = customer_evidence_retriever
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
            raise CustomerIntelligenceContextNotFound("客户不存在或无权访问")
        return self._build_context_for_customer(
            db,
            customer=customer,
            team_id=team_id,
            query_text=query_text,
            evidence_limit=evidence_limit,
            source_types=source_types,
        )

    def build_context_by_public_id(
        self,
        db: Session,
        *,
        team_id: int,
        customer_public_id: str,
        query_text: str | None = None,
        evidence_limit: int = 8,
        source_types: list[SourceType] | None = None,
    ) -> CustomerIntelligenceContext:
        customer = (
            db.query(Customer)
            .filter(Customer.public_id == customer_public_id, Customer.team_id == team_id)
            .first()
        )
        if customer is None:
            raise CustomerIntelligenceContextNotFound("客户不存在或无权访问")
        return self._build_context_for_customer(
            db,
            customer=customer,
            team_id=team_id,
            query_text=query_text,
            evidence_limit=evidence_limit,
            source_types=source_types,
        )

    def _build_context_for_customer(
        self,
        db: Session,
        *,
        customer: Customer,
        team_id: int,
        query_text: str | None,
        evidence_limit: int,
        source_types: list[SourceType] | None,
    ) -> CustomerIntelligenceContext:
        strong_context = self._build_strong_context(db, customer=customer, team_id=team_id)
        retrieval_result = self.evidence_retriever.retrieve_customer_evidence(
            db=db,
            team_id=team_id,
            customer_id=customer.id,
            query_text=query_text,
            evidence_limit=evidence_limit,
            source_types=source_types,
        )
        return CustomerIntelligenceContext(
            strong_context=strong_context,
            evidence_hits=retrieval_result.hits,
            retrieval_state=retrieval_result.state,
            source_watermark=strong_context.source_watermarks or {},
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
            .order_by(CustomerActivity.occurred_at.desc(), CustomerActivity.id.desc())
            .limit(50)
            .all()
        )
        activity_deletions = (
            db.query(CustomerActivityDeletionTombstone)
            .filter(
                CustomerActivityDeletionTombstone.customer_id == customer.id,
                CustomerActivityDeletionTombstone.team_id == team_id,
            )
            .order_by(CustomerActivityDeletionTombstone.id.desc())
            .limit(200)
            .all()
        )
        deal_journeys = (
            db.query(CustomerDealJourney)
            .filter(CustomerDealJourney.customer_id == customer.id, CustomerDealJourney.team_id == team_id)
            .order_by(
                CustomerDealJourney.status.asc(),
                CustomerDealJourney.last_event_at.desc(),
                CustomerDealJourney.id.desc(),
            )
            .limit(50)
            .all()
        )
        journey_ids = [int(item.id) for item in deal_journeys]
        journey_events = (
            db.query(CustomerDealJourneyEvent)
            .filter(
                CustomerDealJourneyEvent.customer_id == customer.id,
                CustomerDealJourneyEvent.team_id == team_id,
                CustomerDealJourneyEvent.deal_journey_id.in_(journey_ids),
            )
            .order_by(CustomerDealJourneyEvent.event_time.desc(), CustomerDealJourneyEvent.id.desc())
            .limit(200)
            .all()
            if journey_ids
            else []
        )
        commitments = (
            db.query(SalesCommitment)
            .filter(SalesCommitment.customer_id == customer.id, SalesCommitment.team_id == team_id)
            .order_by(SalesCommitment.updated_time.desc(), SalesCommitment.id.desc())
            .limit(100)
            .all()
        )
        tasks = (
            db.query(FollowUpTask)
            .filter(FollowUpTask.customer_id == customer.id, FollowUpTask.team_id == team_id)
            .order_by(FollowUpTask.updated_time.desc(), FollowUpTask.id.desc())
            .limit(100)
            .all()
        )
        task_ids = [int(item.id) for item in tasks]
        task_events = (
            db.query(FollowUpTaskEvent)
            .filter(FollowUpTaskEvent.team_id == team_id, FollowUpTaskEvent.task_id.in_(task_ids))
            .order_by(FollowUpTaskEvent.created_time.desc(), FollowUpTaskEvent.id.desc())
            .limit(200)
            .all()
            if task_ids
            else []
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

        journey_payload = [_journey_to_dict(item) for item in deal_journeys]
        journey_event_payload = [_journey_event_to_dict(item) for item in journey_events]
        commitment_payload = [_commitment_to_dict(item) for item in commitments]
        task_payload = [_task_to_dict(item) for item in tasks]
        task_event_payload = [_task_event_to_dict(item) for item in task_events]
        recorded_follow_ups = [*task_payload, *commitment_payload]
        context_facts = self.fact_service.to_context_payload(
            db, team_id=team_id, customer_id=int(customer.id), limit=50
        )
        watermarks = _source_watermarks(
            customer=customer,
            contacts=contacts,
            opportunities=opportunities,
            contracts=contracts,
            payment_plans=[plan for contract in contracts for plan in (contract.payment_plans or [])],
            payment_records=[
                record
                for contract in contracts
                for plan in (contract.payment_plans or [])
                for record in (plan.payment_records or [])
            ],
            activities=activities,
            activity_deletions=activity_deletions,
            facts=context_facts,
            journeys=deal_journeys,
            journey_events=journey_events,
            tasks=tasks,
            commitments=commitments,
            task_events=task_events,
        )

        return CustomerStrongContext(
            customer=self._customer_fact(db, customer),
            customer_facts=context_facts,
            contacts=[self._contact_fact(item) for item in contacts],
            opportunities=[self._opportunity_fact(item) for item in opportunities],
            contracts=[self._contract_fact(item) for item in contracts],
            payment_plans=payment_plans,
            payment_records=payment_records,
            recent_activities=[self._activity_fact(item) for item in activities],
            same_industry_customers=[str(row[0]) for row in same_industry_rows],
            deal_journeys=journey_payload,
            deal_journey_events=journey_event_payload,
            recorded_follow_ups=recorded_follow_ups,
            sales_commitments=commitment_payload,
            follow_up_task_events=task_event_payload,
            source_watermarks=watermarks,
        )

    def _customer_fact(self, db: Session, customer: Customer) -> CustomerFact:
        return CustomerFact(
            id=int(customer.id),
            public_id=customer.public_id,
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
            deal_journey_id=self._optional_int(opportunity.deal_journey_id),
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
            deal_journey_id=self._optional_int(contract.deal_journey_id),
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
            deal_journey_id=self._optional_int(activity.deal_journey_id),
            source_content=activity.source_content,
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


def _iso(value: object) -> str | None:
    return value.isoformat() if isinstance(value, (date, datetime)) else None


def _json_metadata(value: object) -> JsonObject:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _journey_to_dict(journey: CustomerDealJourney) -> JsonObject:
    return {
        "id": int(journey.id),
        "name": journey.name,
        "status": journey.status,
        "primary_opportunity_id": journey.primary_opportunity_id,
        "started_at": _iso(journey.started_at),
        "closed_at": _iso(journey.closed_at),
        "last_event_at": _iso(journey.last_event_at),
        "created_time": _iso(journey.created_time),
        "updated_time": _iso(journey.updated_time),
        "public_id": getattr(journey, "public_id", None),
    }


def _journey_event_to_dict(event: CustomerDealJourneyEvent) -> JsonObject:
    return {
        "id": int(event.id),
        "deal_journey_id": int(event.deal_journey_id),
        "event_type": event.event_type,
        "event_time": _iso(event.event_time),
        "source_type": event.source_type,
        "source_id": event.source_id,
        "summary": event.summary,
        "metadata": _json_metadata(event.metadata_json),
        "created_time": _iso(event.created_time),
    }


def _commitment_to_dict(commitment: SalesCommitment) -> JsonObject:
    return {
        "id": int(commitment.id),
        "public_id": commitment.public_id,
        "kind": "commitment",
        "deal_journey_id": commitment.deal_journey_id,
        "title": commitment.title,
        "content": commitment.content,
        "status": commitment.status,
        "owner_id": commitment.owner_id,
        "due_at": _iso(commitment.due_at),
        "source_activity_id": commitment.source_activity_id,
        "source_public_id": commitment.source_public_id,
        "evidence": commitment.evidence_json if isinstance(commitment.evidence_json, dict) else {},
        "created_time": _iso(commitment.created_time),
        "updated_time": _iso(commitment.updated_time),
    }


def _task_to_dict(task: FollowUpTask) -> JsonObject:
    return {
        "id": int(task.id),
        "public_id": task.public_id,
        "kind": "task",
        "task_id": int(task.id),
        "commitment_id": task.commitment_id,
        "deal_journey_id": task.deal_journey_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "owner_id": task.owner_id,
        "due_at": _iso(task.due_at),
        "completed_at": _iso(task.completed_at),
        "cancelled_at": _iso(task.cancelled_at),
        "source_activity_id": task.source_activity_id,
        "source_public_id": task.source_public_id,
        "evidence": task.evidence_json if isinstance(task.evidence_json, dict) else {},
        "created_time": _iso(task.created_time),
        "updated_time": _iso(task.updated_time),
    }


def _task_event_to_dict(event: FollowUpTaskEvent) -> JsonObject:
    return {
        "id": int(event.id),
        "task_id": int(event.task_id),
        "event_type": event.event_type,
        "previous_status": event.previous_status,
        "new_status": event.new_status,
        "actor_id": event.actor_id,
        "source_activity_id": event.source_activity_id,
        "payload": event.payload_json if isinstance(event.payload_json, dict) else {},
        "created_time": _iso(event.created_time),
    }


def _source_watermarks(
    *,
    customer: Customer,
    contacts: list[Contact],
    opportunities: list[Opportunity],
    contracts: list[Contract],
    payment_plans: list[PaymentPlan],
    payment_records: list[PaymentRecord],
    activities: list[CustomerActivity],
    activity_deletions: list[CustomerActivityDeletionTombstone],
    facts: list[JsonObject],
    journeys: list[CustomerDealJourney],
    journey_events: list[CustomerDealJourneyEvent],
    tasks: list[FollowUpTask],
    commitments: list[SalesCommitment],
    task_events: list[FollowUpTaskEvent],
) -> JsonObject:
    return {
        "customer_id": int(customer.id),
        "customer_updated_at": _iso(customer.last_modified_time or customer.updated_time),
        "contact_id": max((int(item.id) for item in contacts), default=0),
        "opportunity_id": max((int(item.id) for item in opportunities), default=0),
        "contract_id": max((int(item.id) for item in contracts), default=0),
        "payment_plan_id": max((int(item.id) for item in payment_plans), default=0),
        "payment_record_id": max((int(item.id) for item in payment_records), default=0),
        "activity_id": max((int(item.id) for item in activities), default=0),
        "activity_deletion_id": max((int(item.id) for item in activity_deletions), default=0),
        "fact_id": max((int(item.get("id") or 0) for item in facts), default=0),
        "journey_id": max((int(item.id) for item in journeys), default=0),
        "journey_event_id": max((int(item.id) for item in journey_events), default=0),
        "task_id": max((int(item.id) for item in tasks), default=0),
        "commitment_id": max((int(item.id) for item in commitments), default=0),
        "task_event_id": max((int(item.id) for item in task_events), default=0),
        "latest_contact_at": max((_iso(item.created_time) or "" for item in contacts), default=None),
        "latest_opportunity_at": max((_iso(item.last_modified_time) or "" for item in opportunities), default=None),
        "latest_contract_at": max((_iso(item.last_modified_time) or "" for item in contracts), default=None),
        "latest_payment_plan_at": max((_iso(item.last_modified_time) or "" for item in payment_plans), default=None),
        "latest_payment_record_at": max((_iso(item.created_time) or "" for item in payment_records), default=None),
        "latest_activity_at": max((_iso(item.occurred_at) or "" for item in activities), default=None),
        "latest_activity_deleted_at": max(
            (_iso(item.deleted_at) or "" for item in activity_deletions),
            default=None,
        ),
        "latest_fact_at": max(
            (str(item.get("updated_at") or item.get("extracted_at") or "") for item in facts),
            default=None,
        ),
        "latest_journey_at": max((_iso(item.event_time) or "" for item in journey_events), default=None),
        "latest_task_at": max((_iso(item.updated_time) or "" for item in tasks), default=None),
        "latest_task_event_at": max((_iso(item.created_time) or "" for item in task_events), default=None),
        "latest_commitment_at": max((_iso(item.updated_time) or "" for item in commitments), default=None),
        "latest_journey_updated_at": max((_iso(item.updated_time) or "" for item in journeys), default=None),
        "fact_version": max((int(item.get("version") or 0) for item in facts), default=0),
    }


customer_intelligence_context_service = CustomerIntelligenceContextService()
