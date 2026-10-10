"""Unified customer intelligence retrieval context.

This service is the read-side boundary for customer intelligence. MySQL remains
the source of truth for CRM facts, while Qdrant contributes semantic evidence
that can help Agent reasoning and customer profile summarization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import Session, joinedload

from app.crud.product import product_crud
from app.crud.product_intent import product_intent_payload
from app.models.contract import Contract
from app.models.customer import Contact, Customer, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyEventType
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
from app.services.legacy_profile_source import (
    LEGACY_ACTIVITY_SOURCES,
    LEGACY_PROFILE_SOURCE_POLICY,
    event_origin,
    follow_up_origin,
    task_event_source_status,
)

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
    product_public_id: str | None = None
    product_name: str | None = None
    products: list[JsonObject] = field(default_factory=list)

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
            "product_public_id": self.product_public_id,
            "product_name": self.product_name,
            "products": self.products,
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
    product_public_id: str | None = None
    product_name: str | None = None

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
            "product_public_id": self.product_public_id,
            "product_name": self.product_name,
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
    product_catalog: list[JsonObject] = field(default_factory=list)

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
            "product_catalog": self.strong_context.product_catalog,
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
            .options(joinedload(Customer.product_links).joinedload(CustomerProduct.product))
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
            .options(joinedload(Customer.product_links).joinedload(CustomerProduct.product))
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
            exclude_assistant2=True,
        )
        return CustomerIntelligenceContext(
            strong_context=strong_context,
            evidence_hits=retrieval_result.hits,
            retrieval_state=retrieval_result.state,
            source_watermark=strong_context.source_watermarks or {},
        )

    def _build_strong_context(self, db: Session, *, customer: Customer, team_id: int) -> CustomerStrongContext:
        all_contacts = db.query(Contact).filter(Contact.customer_id == customer.id, Contact.team_id == team_id).all()
        contacts = sorted(all_contacts, key=lambda item: (
            -int(bool(item.is_primary)), -int(bool(item.is_decision_maker)), item.created_time or datetime.min,
        ))[:50]
        all_opportunities = db.query(Opportunity).options(joinedload(Opportunity.product)).filter(
            Opportunity.customer_id == customer.id, Opportunity.team_id == team_id,
        ).all()
        opportunities = sorted(all_opportunities, key=lambda item: (
            item.last_modified_time or datetime.min, int(item.id),
        ), reverse=True)[:50]
        all_contracts = db.query(Contract).options(
            joinedload(Contract.payment_plans).joinedload(PaymentPlan.payment_records)
        ).filter(Contract.customer_id == customer.id, Contract.team_id == team_id,
                 Contract.deleted_at.is_(None)).all()
        contracts = sorted(all_contracts, key=lambda item: item.created_time or datetime.min, reverse=True)[:50]
        all_activities = db.query(CustomerActivity).filter(
            CustomerActivity.customer_id == customer.id, CustomerActivity.team_id == team_id,
            CustomerActivity.submission_source.in_(LEGACY_ACTIVITY_SOURCES),
        ).all()
        activities = sorted(all_activities, key=lambda item: (item.occurred_at or datetime.min, int(item.id)), reverse=True)[:50]
        all_deletions = db.query(CustomerActivityDeletionTombstone).filter(
            CustomerActivityDeletionTombstone.team_id == team_id,
            CustomerActivityDeletionTombstone.customer_id == customer.id,
            CustomerActivityDeletionTombstone.submission_source.in_(LEGACY_ACTIVITY_SOURCES),
        ).all()
        # Build the eligible contribution set before ordering and display
        # limits; the shared journey aggregate is not a legacy source.
        all_journeys = db.query(CustomerDealJourney).filter(
            CustomerDealJourney.customer_id == customer.id,
            CustomerDealJourney.team_id == team_id,
        ).all()
        all_events = db.query(CustomerDealJourneyEvent).filter(
            CustomerDealJourneyEvent.customer_id == customer.id,
            CustomerDealJourneyEvent.team_id == team_id,
        ).all()
        eligible_events = [event for event in all_events if event_origin(db, event, team_id, int(customer.id))]
        event_dates = {}
        for event in eligible_events:
            key = int(event.deal_journey_id)
            event_dates[key] = max(event_dates.get(key, event.event_time), event.event_time)
        all_commitments = db.query(SalesCommitment).filter(
            SalesCommitment.customer_id == customer.id, SalesCommitment.team_id == team_id,
        ).all()
        eligible_commitments = [row for row in all_commitments if follow_up_origin(db, row, team_id, int(customer.id))]
        all_tasks = db.query(FollowUpTask).filter(
            FollowUpTask.customer_id == customer.id, FollowUpTask.team_id == team_id,
        ).all()
        eligible_tasks = [row for row in all_tasks if follow_up_origin(db, row, team_id, int(customer.id))]
        eligible_journeys = [journey for journey in all_journeys if int(journey.id) in event_dates
                             or any(item.deal_journey_id == journey.id for item in all_opportunities)
                             or any(item.deal_journey_id == journey.id for item in all_contracts)]
        deal_journeys = sorted(eligible_journeys, key=lambda item: (
            event_dates.get(int(item.id), datetime.min), int(item.id),
        ), reverse=True)[:50]
        journey_ids = {int(item.id) for item in deal_journeys}
        journey_events = sorted((event for event in eligible_events if int(event.deal_journey_id) in journey_ids),
                                key=lambda item: (item.event_time, int(item.id)), reverse=True)[:200]
        commitments = sorted(eligible_commitments, key=lambda item: (item.updated_time or datetime.min, int(item.id)), reverse=True)[:100]
        tasks = sorted(eligible_tasks, key=lambda item: (item.updated_time or datetime.min, int(item.id)), reverse=True)[:100]
        eligible_task_ids = {int(item.id) for item in eligible_tasks}
        eligible_task_by_id = {int(item.id): item for item in eligible_tasks}
        all_task_events = db.query(FollowUpTaskEvent).filter(
            FollowUpTaskEvent.team_id == team_id,
            FollowUpTaskEvent.task_id.in_(eligible_task_ids),
        ).all() if eligible_task_ids else []
        eligible_task_events = [event for event in all_task_events if task_event_source_status(
            db, event, eligible_task_by_id[int(event.task_id)], team_id, int(customer.id),
        ) == "VERIFIED"]
        task_events = sorted((event for event in eligible_task_events if event.task_id in {item.id for item in tasks}),
                             key=lambda item: (item.created_time or datetime.min, int(item.id)), reverse=True)[:200]

        payment_plans: list[PaymentPlanFact] = []
        payment_records: list[PaymentRecordFact] = []
        for contract in contracts:
            for plan in sorted(contract.payment_plans or [], key=lambda item: item.due_date or date.min):
                payment_plans.append(self._payment_plan_fact(plan))
                for record in sorted(plan.payment_records or [], key=lambda item: item.payment_date or date.min):
                    payment_records.append(self._payment_record_fact(record, plan.contract_id))

        opportunities_by_id = {int(item.id): item for item in all_opportunities}
        journey_payload = [
            _journey_to_dict(
                item,
                legacy_events=[event for event in eligible_events if event.deal_journey_id == item.id],
                opportunity=opportunities_by_id.get(int(item.primary_opportunity_id))
                if item.primary_opportunity_id is not None else None,
            )
            for item in deal_journeys
        ]
        journey_event_payload = [_journey_event_to_dict(item) for item in journey_events]
        commitment_payload = [_commitment_to_dict(item) for item in commitments]
        task_payload = [_task_to_dict(item) for item in tasks]
        task_event_payload = [_task_event_to_dict(item) for item in task_events]
        recorded_follow_ups = [*task_payload, *commitment_payload]
        catalog = [
            {"public_id": item.public_id, "name": item.name, "is_active": True}
            for item in product_crud.list(db, team_id, is_active=True)
        ]
        opportunity_snapshot = _snapshot_rows(all_opportunities)
        for row in opportunity_snapshot:
            product = opportunities_by_id[int(row["id"])].product
            row["product_public_id"] = product.public_id if product is not None else None
            row["product_name"] = product.name if product is not None else None
        source_snapshot = {
            "customer": self._customer_fact(db, customer).to_dict(),
            "contacts": _snapshot_rows(all_contacts),
            "opportunities": opportunity_snapshot,
            "contracts": _snapshot_rows(all_contracts),
            "payment_plans": _snapshot_rows(
                plan for contract in all_contracts for plan in (contract.payment_plans or [])
            ),
            "payment_records": _snapshot_rows(
                record for contract in all_contracts for plan in (contract.payment_plans or [])
                for record in (plan.payment_records or [])
            ),
            "activities": _snapshot_rows(all_activities),
            "activity_deletions": _snapshot_rows(all_deletions),
            "facts": [],
            "journeys": sorted(
                (_journey_to_dict(
                    item,
                    legacy_events=[event for event in eligible_events if event.deal_journey_id == item.id],
                    opportunity=opportunities_by_id.get(int(item.primary_opportunity_id))
                    if item.primary_opportunity_id is not None else None,
                ) for item in eligible_journeys),
                key=lambda item: int(item["id"]),
            ),
            "journey_events": _snapshot_rows(eligible_events),
            "tasks": _snapshot_rows(eligible_tasks),
            "commitments": _snapshot_rows(eligible_commitments),
            "task_events": _snapshot_rows(eligible_task_events),
            "product_catalog": sorted(catalog, key=lambda item: str(item["public_id"])),
        }
        watermarks = _source_watermarks(
            customer=customer,
            contacts=all_contacts,
            opportunities=all_opportunities,
            contracts=all_contracts,
            payment_plans=[plan for contract in all_contracts for plan in (contract.payment_plans or [])],
            payment_records=[record for contract in all_contracts for plan in (contract.payment_plans or [])
                             for record in (plan.payment_records or [])],
            activities=all_activities,
            activity_deletions=all_deletions,
            facts=[],
            journeys=eligible_journeys,
            journey_events=eligible_events,
            tasks=eligible_tasks,
            commitments=eligible_commitments,
            task_events=eligible_task_events,
        )
        watermarks.update({
            "eligible_revision": 0,
            "deletion_revision": 0,
            "source_policy_version": LEGACY_PROFILE_SOURCE_POLICY,
            "source_provenance_status": "UNVERIFIED",
            "source_snapshot_hash": hashlib.sha256(
                json.dumps(source_snapshot, sort_keys=True, ensure_ascii=False, default=str,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        })

        return CustomerStrongContext(
            customer=self._customer_fact(db, customer),
            customer_facts=[],
            contacts=[self._contact_fact(item) for item in contacts],
            opportunities=[self._opportunity_fact(item) for item in opportunities],
            contracts=[self._contract_fact(item) for item in contracts],
            payment_plans=payment_plans,
            payment_records=payment_records,
            recent_activities=[self._activity_fact(item) for item in activities],
            same_industry_customers=[],
            deal_journeys=journey_payload,
            deal_journey_events=journey_event_payload,
            recorded_follow_ups=recorded_follow_ups,
            sales_commitments=commitment_payload,
            follow_up_task_events=task_event_payload,
            source_watermarks=watermarks,
            product_catalog=catalog,
        )

    def _customer_fact(self, db: Session, customer: Customer) -> CustomerFact:
        intent = product_intent_payload(customer.product_links)
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
            product_public_id=intent["product_public_id"],
            product_name=intent["product_name"],
            products=list(intent["products"]),
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
        product = opportunity.product
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
            product_public_id=product.public_id if product is not None else None,
            product_name=product.name if product is not None else None,
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


def _journey_to_dict(
    journey: CustomerDealJourney, *, legacy_events: list[CustomerDealJourneyEvent],
    opportunity: Opportunity | None,
) -> JsonObject:
    event_times = [event.event_time for event in legacy_events]
    terminal_events = [event for event in legacy_events if event.event_type in {
        DealJourneyEventType.OPPORTUNITY_WON, DealJourneyEventType.OPPORTUNITY_LOST,
    }]
    last_event = max(event_times, default=None)
    status = "ACTIVE"
    latest_terminal = None
    if terminal_events:
        latest_terminal = max(terminal_events, key=lambda event: (event.event_time, int(event.id)))
        status = "WON" if latest_terminal.event_type == DealJourneyEventType.OPPORTUNITY_WON else "LOST"
    elif opportunity is not None:
        status = {1: "WON", 2: "LOST"}.get(opportunity.status, "ACTIVE")
    start = min(event_times, default=None)
    if opportunity is not None and opportunity.created_time is not None:
        start = min(start, opportunity.created_time) if start else opportunity.created_time
    return {
        "id": int(journey.id),
        "name": opportunity.opportunity_name if opportunity is not None else "业务旅程",
        "status": status,
        "primary_opportunity_id": opportunity.id if opportunity is not None else None,
        "started_at": _iso(start),
        "closed_at": _iso(latest_terminal.event_time if latest_terminal is not None else None),
        "last_event_at": _iso(last_event),
        "created_time": _iso(last_event),
        "updated_time": _iso(last_event),
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


def _snapshot_rows(rows: object) -> list[JsonObject]:
    """Freeze every eligible row, including those beyond presentation limits."""
    return sorted(
        (
            {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs}
            for row in rows
        ),
        key=lambda item: int(item["id"]),
    )


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
        "latest_journey_updated_at": max((_iso(item.event_time) or "" for item in journey_events), default=None),
        "fact_version": max((int(item.get("version") or 0) for item in facts), default=0),
    }


customer_intelligence_context_service = CustomerIntelligenceContextService()
