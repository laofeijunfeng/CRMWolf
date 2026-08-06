from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.crud.permission import permission_crud
from app.models.contract import Contract
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.invoice import InvoiceApplication
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.procurement import OpportunityStageSnapshot
from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus
from app.utils import time as business_time
from app.utils.time import calculate_follow_up_task_due_window

WORK_SUMMARY_WINDOWS = {"today", "this_week", "last_week", "this_month", "custom"}


@dataclass(frozen=True)
class WorkSummaryWindow:
    name: str
    starts_at: datetime
    ends_at: datetime
    starts_on: date
    ends_before: date
    timezone: str


class WorkSummaryService:
    """Builds structured work facts for Agent summaries.

    MySQL remains the source of truth. LLM callers should summarize these facts,
    not invent completed work from vector evidence alone.
    """

    def list_completed_work(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        window: str = "this_week",
        customer_public_id: str | None = None,
        include_tasks: bool = True,
        include_activities: bool = True,
        include_business_events: bool = True,
        start_at: date | datetime | str | None = None,
        end_at: date | datetime | str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("工作总结 limit 必须大于 0")
        summary_window = self._resolve_window(window, start_at=start_at, end_at=end_at)
        customer = self._resolve_visible_customer(db, team_id=team_id, user_id=user_id, public_id=customer_public_id)
        offset = self._decode_cursor(cursor)
        fetch_limit = offset + limit + 1

        facts: list[dict[str, Any]] = []
        source_status: dict[str, str] = {}
        source_total_counts: dict[str, int] = {}
        per_source_limit = max(fetch_limit, 20)
        if include_tasks:
            task_facts = self._completed_task_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer.id if customer else None,
                window=summary_window,
                limit=per_source_limit,
            )
            facts.extend(task_facts)
            source_total_counts.update(
                self._completed_task_counts(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    customer_id=customer.id if customer else None,
                    window=summary_window,
                )
            )
            source_status["completed_tasks"] = "queried"
        else:
            source_status["completed_tasks"] = "skipped"

        if include_activities:
            activity_facts = self._customer_activity_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer.id if customer else None,
                window=summary_window,
                limit=per_source_limit,
            )
            facts.extend(activity_facts)
            source_total_counts.update(
                self._customer_activity_counts(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    customer_id=customer.id if customer else None,
                    window=summary_window,
                )
            )
            source_status["customer_activities"] = "queried"
        else:
            source_status["customer_activities"] = "skipped"

        if include_business_events:
            business_facts = self._business_event_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer.id if customer else None,
                window=summary_window,
                limit=per_source_limit,
            )
            facts.extend(business_facts)
            source_total_counts.update(
                self._business_event_counts(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    customer_id=customer.id if customer else None,
                    window=summary_window,
                )
            )
            source_status["business_events"] = "queried"
        else:
            source_status["business_events"] = "skipped"

        facts = sorted(
            facts,
            key=lambda item: (str(item.get("occurred_at") or ""), str(item.get("fact_id") or "")),
            reverse=True,
        )
        page_facts = facts[offset : offset + limit]
        available_total = sum(source_total_counts.values())
        truncated = available_total > offset + len(page_facts)
        next_cursor = self._encode_cursor(offset + len(page_facts)) if truncated else None
        completed_tasks = [fact["payload"] for fact in page_facts if fact["fact_type"] == "completed_follow_up_task"]
        activities = [fact["payload"] for fact in page_facts if fact["fact_type"] == "customer_activity"]
        business_events = [fact for fact in page_facts if fact["source_group"] == "business_event"]
        return {
            "items": page_facts,
            "completed_tasks": completed_tasks,
            "activities": activities,
            "business_events": business_events,
            "total": len(page_facts),
            "available_total": available_total,
            "truncated": truncated,
            "next_cursor": next_cursor,
            "source_counts": self._source_counts(page_facts),
            "source_total_counts": source_total_counts,
            "pagination": {
                "limit": limit,
                "cursor": cursor,
                "offset": offset,
                "next_cursor": next_cursor,
                "truncated": truncated,
                "available_total": available_total,
            },
            "source_status": source_status,
            "filters": {
                "window": window,
                "starts_at": summary_window.starts_at.isoformat(),
                "ends_at": summary_window.ends_at.isoformat(),
                "starts_on": summary_window.starts_on.isoformat(),
                "ends_before": summary_window.ends_before.isoformat(),
                "timezone": summary_window.timezone,
                "customer_id": customer.public_id if customer else None,
                "include_tasks": include_tasks,
                "include_activities": include_activities,
                "include_business_events": include_business_events,
                "start_at": start_at.isoformat() if isinstance(start_at, (date, datetime)) else start_at,
                "end_at": end_at.isoformat() if isinstance(end_at, (date, datetime)) else end_at,
            },
            "fact_source_scope": {
                "completed_follow_up_task": {
                    "table": "crm_follow_up_tasks",
                    "time_field": "completed_at",
                    "owner_field": "owner_id",
                    "identifier_policy": "public_id",
                },
                "customer_activity": {
                    "table": "crm_customer_activities",
                    "time_field": "occurred_at",
                    "owner_field": "owner_id",
                    "identifier_policy": "no_internal_id",
                },
                "opportunity_stage": {
                    "table": "crm_opportunity_stage_snapshots",
                    "time_field": "entered_at",
                    "owner_field": "crm_opportunities.owner_id",
                    "identifier_policy": "opportunity_public_id",
                },
                "contract": {
                    "table": "crm_contracts",
                    "time_field": "signing_date_or_created_time",
                    "owner_field": "owner_id",
                    "identifier_policy": "contract_number",
                },
                "payment_record": {
                    "table": "crm_payment_records",
                    "time_field": "payment_date_or_created_time",
                    "owner_field": "creator_id_or_commission_member_id",
                    "identifier_policy": "record_number",
                },
                "invoice_application": {
                    "table": "crm_invoice_applications",
                    "time_field": "issued_time_or_reviewed_time_or_created_time",
                    "owner_field": "applicant_id",
                    "identifier_policy": "application_number",
                },
                "license_application": {
                    "table": "crm_license_applications",
                    "time_field": "approved_time_or_created_time",
                    "owner_field": "applicant_id",
                    "identifier_policy": "application_number",
                },
            },
            "usage_policy": {
                "fact_source": "mysql",
                "summary_role": "Agent/LLM 只能基于 items 中的结构化事实做归纳总结，不能把向量证据当作完成事实。",
                "ownership_rule": "工作归属按各业务事实 owner/applicant/creator 字段判断；客户 owner 不自动决定跟进任务或活动归属。",
                "pagination_rule": "当 truncated=true 时，Agent 必须继续使用 next_cursor 获取后续 facts，或在回答中明确当前总结基于部分事实。",
            },
        }

    def _completed_task_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.owner_id == str(user_id),
            FollowUpTask.status == FollowUpTaskStatus.COMPLETED,
            FollowUpTask.completed_at.isnot(None),
            FollowUpTask.completed_at >= window.starts_at,
            FollowUpTask.completed_at < window.ends_at,
        )
        if customer_id is not None:
            query = query.filter(FollowUpTask.customer_id == customer_id)
        tasks = query.order_by(FollowUpTask.completed_at.desc(), FollowUpTask.id.desc()).limit(limit).all()
        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[task.customer_id for task in tasks])
        return [
            self._fact(
                fact_type="completed_follow_up_task",
                source_group="task",
                source_table="crm_follow_up_tasks",
                occurred_at=task.completed_at,
                customer=customers_by_id.get(task.customer_id),
                payload=self._task_payload(task, customers_by_id.get(task.customer_id)),
                title=task.title,
                source_public_id=task.public_id,
                attribution={
                    "user_id": task.owner_id,
                    "field": "owner_id",
                    "source": "crm_follow_up_tasks.owner_id",
                },
            )
            for task in tasks
        ]

    def _customer_activity_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = db.query(CustomerActivity).filter(
            CustomerActivity.team_id == team_id,
            CustomerActivity.owner_id == str(user_id),
            CustomerActivity.occurred_at >= window.starts_at,
            CustomerActivity.occurred_at < window.ends_at,
        )
        if customer_id is not None:
            query = query.filter(CustomerActivity.customer_id == customer_id)
        activities = query.order_by(CustomerActivity.occurred_at.desc(), CustomerActivity.id.desc()).limit(limit).all()
        customers_by_id = self._customers_by_id(
            db,
            team_id=team_id,
            customer_ids=[activity.customer_id for activity in activities if activity.customer_id],
        )
        return [
            self._fact(
                fact_type="customer_activity",
                source_group="activity",
                source_table="crm_customer_activities",
                occurred_at=activity.occurred_at,
                customer=customers_by_id.get(activity.customer_id),
                payload=self._activity_payload(activity, customers_by_id.get(activity.customer_id)),
                title=activity.title or activity.summary or activity.source_content[:80],
                source_public_id=None,
                attribution={
                    "user_id": activity.owner_id,
                    "field": "owner_id",
                    "source": "crm_customer_activities.owner_id",
                },
            )
            for activity in activities
        ]

    def _business_event_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        facts.extend(
            self._opportunity_stage_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
                limit=limit,
            )
        )
        facts.extend(
            self._contract_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
                limit=limit,
            )
        )
        facts.extend(
            self._payment_record_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
                limit=limit,
            )
        )
        facts.extend(
            self._invoice_application_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
                limit=limit,
            )
        )
        facts.extend(
            self._license_application_facts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
                limit=limit,
            )
        )
        return facts

    def _completed_task_counts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> dict[str, int]:
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.owner_id == str(user_id),
            FollowUpTask.status == FollowUpTaskStatus.COMPLETED,
            FollowUpTask.completed_at.isnot(None),
            FollowUpTask.completed_at >= window.starts_at,
            FollowUpTask.completed_at < window.ends_at,
        )
        if customer_id is not None:
            query = query.filter(FollowUpTask.customer_id == customer_id)
        return {"completed_follow_up_task": query.count()}

    def _customer_activity_counts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> dict[str, int]:
        query = db.query(CustomerActivity).filter(
            CustomerActivity.team_id == team_id,
            CustomerActivity.owner_id == str(user_id),
            CustomerActivity.occurred_at >= window.starts_at,
            CustomerActivity.occurred_at < window.ends_at,
        )
        if customer_id is not None:
            query = query.filter(CustomerActivity.customer_id == customer_id)
        return {"customer_activity": query.count()}

    def _business_event_counts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> dict[str, int]:
        counts = {
            "opportunity_stage_entered": self._opportunity_stage_count(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
            ),
            "payment_recorded": self._payment_record_count(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
            ),
            "invoice_application": self._invoice_application_count(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
            ),
            "license_application": self._license_application_count(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
            ),
        }
        counts.update(
            self._contract_counts(
                db,
                team_id=team_id,
                user_id=user_id,
                customer_id=customer_id,
                window=window,
            )
        )
        return counts

    def _opportunity_stage_count(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> int:
        query = (
            db.query(OpportunityStageSnapshot.id)
            .join(Opportunity, Opportunity.id == OpportunityStageSnapshot.opportunity_id)
            .filter(
                OpportunityStageSnapshot.team_id == team_id,
                Opportunity.team_id == team_id,
                Opportunity.owner_id == str(user_id),
                OpportunityStageSnapshot.entered_at >= window.starts_at,
                OpportunityStageSnapshot.entered_at < window.ends_at,
            )
        )
        if customer_id is not None:
            query = query.filter(Opportunity.customer_id == customer_id)
        return query.count()

    def _contract_counts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> dict[str, int]:
        base_query = db.query(Contract.id).filter(
            Contract.team_id == team_id,
            Contract.owner_id == str(user_id),
            Contract.deleted_at.is_(None),
        )
        if customer_id is not None:
            base_query = base_query.filter(Contract.customer_id == customer_id)
        signed_count = base_query.filter(
            Contract.signing_date.isnot(None),
            Contract.signing_date >= window.starts_on,
            Contract.signing_date < window.ends_before,
        ).count()
        created_count = base_query.filter(
            Contract.signing_date.is_(None),
            Contract.created_time >= window.starts_at,
            Contract.created_time < window.ends_at,
        ).count()
        return {"contract_signed": signed_count, "contract_created": created_count}

    def _payment_record_count(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> int:
        query = (
            db.query(PaymentRecord.id)
            .join(PaymentPlan, PaymentPlan.id == PaymentRecord.payment_plan_id)
            .join(Contract, Contract.id == PaymentPlan.contract_id)
            .filter(
                PaymentRecord.team_id == team_id,
                PaymentPlan.team_id == team_id,
                Contract.team_id == team_id,
                or_(PaymentRecord.creator_id == str(user_id), PaymentRecord.commission_member_id == str(user_id)),
                or_(
                    and_(
                        PaymentRecord.payment_date.isnot(None),
                        PaymentRecord.payment_date >= window.starts_on,
                        PaymentRecord.payment_date < window.ends_before,
                    ),
                    and_(
                        PaymentRecord.payment_date.is_(None),
                        PaymentRecord.created_time >= window.starts_at,
                        PaymentRecord.created_time < window.ends_at,
                    ),
                ),
            )
        )
        if customer_id is not None:
            query = query.filter(Contract.customer_id == customer_id)
        return query.count()

    def _invoice_application_count(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> int:
        query = db.query(InvoiceApplication.id).filter(
            InvoiceApplication.team_id == team_id,
            InvoiceApplication.applicant_id == str(user_id),
            or_(
                and_(
                    InvoiceApplication.issued_time.isnot(None),
                    InvoiceApplication.issued_time >= window.starts_at,
                    InvoiceApplication.issued_time < window.ends_at,
                ),
                and_(
                    InvoiceApplication.issued_time.is_(None),
                    InvoiceApplication.reviewed_time.isnot(None),
                    InvoiceApplication.reviewed_time >= window.starts_at,
                    InvoiceApplication.reviewed_time < window.ends_at,
                ),
                and_(
                    InvoiceApplication.issued_time.is_(None),
                    InvoiceApplication.reviewed_time.is_(None),
                    InvoiceApplication.created_time >= window.starts_at,
                    InvoiceApplication.created_time < window.ends_at,
                ),
            ),
        )
        if customer_id is not None:
            query = query.filter(InvoiceApplication.customer_id == customer_id)
        return query.count()

    def _license_application_count(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
    ) -> int:
        query = db.query(LicenseApplication.id).filter(
            LicenseApplication.team_id == team_id,
            LicenseApplication.applicant_id == str(user_id),
            or_(
                and_(
                    LicenseApplication.approved_time.isnot(None),
                    LicenseApplication.approved_time >= window.starts_at,
                    LicenseApplication.approved_time < window.ends_at,
                ),
                and_(
                    LicenseApplication.approved_time.is_(None),
                    LicenseApplication.created_time >= window.starts_at,
                    LicenseApplication.created_time < window.ends_at,
                ),
            ),
        )
        if customer_id is not None:
            query = query.filter(LicenseApplication.customer_id == customer_id)
        return query.count()

    def _opportunity_stage_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            db.query(OpportunityStageSnapshot, Opportunity)
            .join(Opportunity, Opportunity.id == OpportunityStageSnapshot.opportunity_id)
            .filter(
                OpportunityStageSnapshot.team_id == team_id,
                Opportunity.team_id == team_id,
                Opportunity.owner_id == str(user_id),
                OpportunityStageSnapshot.entered_at >= window.starts_at,
                OpportunityStageSnapshot.entered_at < window.ends_at,
            )
        )
        if customer_id is not None:
            query = query.filter(Opportunity.customer_id == customer_id)
        rows = query.order_by(OpportunityStageSnapshot.entered_at.desc(), OpportunityStageSnapshot.id.desc()).limit(limit).all()
        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[opportunity.customer_id for _, opportunity in rows])
        return [
            self._fact(
                fact_type="opportunity_stage_entered",
                source_group="business_event",
                source_table="crm_opportunity_stage_snapshots",
                occurred_at=snapshot.entered_at,
                customer=customers_by_id.get(opportunity.customer_id),
                payload={
                    "opportunity": self._opportunity_payload(opportunity),
                    "stage_name": snapshot.stage_name,
                    "win_probability": snapshot.win_probability,
                },
                title=f"{opportunity.opportunity_name} 进入 {snapshot.stage_name}",
                source_public_id=opportunity.public_id,
                attribution={
                    "user_id": opportunity.owner_id,
                    "field": "owner_id",
                    "source": "crm_opportunities.owner_id",
                },
            )
            for snapshot, opportunity in rows
        ]

    def _contract_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = db.query(Contract).filter(
            Contract.team_id == team_id,
            Contract.owner_id == str(user_id),
            Contract.deleted_at.is_(None),
            or_(
                and_(
                    Contract.signing_date.isnot(None),
                    Contract.signing_date >= window.starts_on,
                    Contract.signing_date < window.ends_before,
                ),
                and_(
                    Contract.signing_date.is_(None),
                    Contract.created_time >= window.starts_at,
                    Contract.created_time < window.ends_at,
                ),
            ),
        )
        if customer_id is not None:
            query = query.filter(Contract.customer_id == customer_id)
        contracts = query.order_by(Contract.created_time.desc(), Contract.id.desc()).limit(limit * 2).all()
        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[contract.customer_id for contract in contracts])
        facts = []
        for contract in contracts:
            occurred_at = self._date_or_datetime_for_window(contract.signing_date, contract.created_time, window)
            if occurred_at is None:
                continue
            facts.append(
                self._fact(
                    fact_type="contract_signed" if contract.signing_date else "contract_created",
                    source_group="business_event",
                    source_table="crm_contracts",
                    occurred_at=occurred_at,
                    customer=customers_by_id.get(contract.customer_id),
                    payload={
                        "contract_number": contract.contract_number,
                        "contract_name": contract.contract_name,
                        "status": contract.status,
                        "approval_phase": contract.approval_phase,
                        "total_amount": self._decimal(contract.total_amount),
                        "payment_status": contract.payment_status,
                    },
                    title=contract.contract_name,
                    business_key=contract.contract_number,
                    attribution={
                        "user_id": contract.owner_id,
                        "field": "owner_id",
                        "source": "crm_contracts.owner_id",
                    },
                )
            )
        return facts[:limit]

    def _payment_record_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            db.query(PaymentRecord, PaymentPlan, Contract)
            .join(PaymentPlan, PaymentPlan.id == PaymentRecord.payment_plan_id)
            .join(Contract, Contract.id == PaymentPlan.contract_id)
            .filter(
                PaymentRecord.team_id == team_id,
                PaymentPlan.team_id == team_id,
                Contract.team_id == team_id,
                or_(PaymentRecord.creator_id == str(user_id), PaymentRecord.commission_member_id == str(user_id)),
                or_(
                    and_(
                        PaymentRecord.payment_date.isnot(None),
                        PaymentRecord.payment_date >= window.starts_on,
                        PaymentRecord.payment_date < window.ends_before,
                    ),
                    and_(
                        PaymentRecord.payment_date.is_(None),
                        PaymentRecord.created_time >= window.starts_at,
                        PaymentRecord.created_time < window.ends_at,
                    ),
                ),
            )
        )
        if customer_id is not None:
            query = query.filter(Contract.customer_id == customer_id)
        rows = query.order_by(PaymentRecord.created_time.desc(), PaymentRecord.id.desc()).limit(limit * 2).all()
        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[contract.customer_id for _, _, contract in rows])
        facts = []
        for record, plan, contract in rows:
            occurred_at = self._date_or_datetime_for_window(record.payment_date, record.created_time, window)
            if occurred_at is None:
                continue
            facts.append(
                self._fact(
                    fact_type="payment_recorded",
                    source_group="business_event",
                    source_table="crm_payment_records",
                    occurred_at=occurred_at,
                    customer=customers_by_id.get(contract.customer_id),
                    payload={
                        "record_number": record.record_number,
                        "contract_number": contract.contract_number,
                        "contract_name": contract.contract_name,
                        "stage_name": plan.stage_name,
                        "actual_amount": self._decimal(record.actual_amount),
                        "confirmation_status": record.confirmation_status,
                        "approval_phase": record.approval_phase,
                    },
                    title=f"{contract.contract_name} 回款 {self._decimal(record.actual_amount)}",
                    business_key=record.record_number,
                    attribution={
                        "user_id": record.creator_id
                        if record.creator_id == str(user_id)
                        else record.commission_member_id,
                        "field": "creator_id"
                        if record.creator_id == str(user_id)
                        else "commission_member_id",
                        "source": "crm_payment_records.creator_id_or_commission_member_id",
                    },
                )
            )
        return facts[:limit]

    def _invoice_application_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = db.query(InvoiceApplication).filter(
            InvoiceApplication.team_id == team_id,
            InvoiceApplication.applicant_id == str(user_id),
            or_(
                and_(
                    InvoiceApplication.issued_time.isnot(None),
                    InvoiceApplication.issued_time >= window.starts_at,
                    InvoiceApplication.issued_time < window.ends_at,
                ),
                and_(
                    InvoiceApplication.issued_time.is_(None),
                    InvoiceApplication.reviewed_time.isnot(None),
                    InvoiceApplication.reviewed_time >= window.starts_at,
                    InvoiceApplication.reviewed_time < window.ends_at,
                ),
                and_(
                    InvoiceApplication.issued_time.is_(None),
                    InvoiceApplication.reviewed_time.is_(None),
                    InvoiceApplication.created_time >= window.starts_at,
                    InvoiceApplication.created_time < window.ends_at,
                ),
            ),
        )
        if customer_id is not None:
            query = query.filter(InvoiceApplication.customer_id == customer_id)
        invoices = query.order_by(InvoiceApplication.created_time.desc(), InvoiceApplication.id.desc()).limit(limit * 2).all()
        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[invoice.customer_id for invoice in invoices])
        facts = []
        for invoice in invoices:
            occurred_at = self._first_datetime_in_window(
                window,
                invoice.issued_time,
                invoice.reviewed_time,
                invoice.created_time,
            )
            if occurred_at is None:
                continue
            facts.append(
                self._fact(
                    fact_type="invoice_application",
                    source_group="business_event",
                    source_table="crm_invoice_applications",
                    occurred_at=occurred_at,
                    customer=customers_by_id.get(invoice.customer_id),
                    payload={
                        "application_number": invoice.application_number,
                        "invoice_amount": self._decimal(invoice.invoice_amount),
                        "invoice_type": invoice.invoice_type,
                        "status": invoice.status,
                        "approval_phase": invoice.approval_phase,
                        "invoice_title_text": invoice.invoice_title_text,
                    },
                    title=f"开票申请 {invoice.application_number}",
                    business_key=invoice.application_number,
                    attribution={
                        "user_id": invoice.applicant_id,
                        "field": "applicant_id",
                        "source": "crm_invoice_applications.applicant_id",
                    },
                )
            )
        return facts[:limit]

    def _license_application_facts(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer_id: int | None,
        window: WorkSummaryWindow,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = db.query(LicenseApplication).filter(
            LicenseApplication.team_id == team_id,
            LicenseApplication.applicant_id == str(user_id),
            or_(
                and_(
                    LicenseApplication.approved_time.isnot(None),
                    LicenseApplication.approved_time >= window.starts_at,
                    LicenseApplication.approved_time < window.ends_at,
                ),
                and_(
                    LicenseApplication.approved_time.is_(None),
                    LicenseApplication.created_time >= window.starts_at,
                    LicenseApplication.created_time < window.ends_at,
                ),
            ),
        )
        if customer_id is not None:
            query = query.filter(LicenseApplication.customer_id == customer_id)
        applications = query.order_by(LicenseApplication.created_time.desc(), LicenseApplication.id.desc()).limit(limit * 2).all()
        customers_by_id = self._customers_by_id(db, team_id=team_id, customer_ids=[application.customer_id for application in applications])
        facts = []
        for application in applications:
            occurred_at = self._first_datetime_in_window(window, application.approved_time, application.created_time)
            if occurred_at is None:
                continue
            facts.append(
                self._fact(
                    fact_type="license_application",
                    source_group="business_event",
                    source_table="crm_license_applications",
                    occurred_at=occurred_at,
                    customer=customers_by_id.get(application.customer_id),
                    payload={
                        "application_number": application.application_number,
                        "license_type": application.license_type,
                        "authorized_users": application.authorized_users,
                        "status": application.status,
                        "approval_phase": application.approval_phase,
                        "expiry_date": application.expiry_date.isoformat() if application.expiry_date else None,
                    },
                    title=f"License 申请 {application.application_number}",
                    business_key=application.application_number,
                    attribution={
                        "user_id": application.applicant_id,
                        "field": "applicant_id",
                        "source": "crm_license_applications.applicant_id",
                    },
                )
            )
        return facts[:limit]

    def _resolve_window(
        self,
        window: str,
        *,
        start_at: date | datetime | str | None = None,
        end_at: date | datetime | str | None = None,
    ) -> WorkSummaryWindow:
        if window not in WORK_SUMMARY_WINDOWS:
            raise ValueError("未知工作总结时间窗口")
        if start_at is not None or end_at is not None or window == "custom":
            starts_at = self._parse_window_start(start_at)
            ends_at = self._parse_window_end(end_at)
            if starts_at is None or ends_at is None:
                raise ValueError("自定义工作总结时间范围必须提供 start_at 和 end_at")
            if starts_at >= ends_at:
                raise ValueError("工作总结 start_at 必须早于 end_at")
            return WorkSummaryWindow(
                name="custom",
                starts_at=starts_at,
                ends_at=ends_at,
                starts_on=starts_at.date(),
                ends_before=self._date_upper_bound_for_exclusive_end(ends_at),
                timezone="Asia/Shanghai",
            )
        if window in {"today", "this_week"}:
            due_window = calculate_follow_up_task_due_window(window)
            if due_window.starts_at is None or due_window.ends_at is None:
                raise ValueError("工作总结必须使用有起止时间的窗口")
            return WorkSummaryWindow(
                name=window,
                starts_at=due_window.starts_at,
                ends_at=due_window.ends_at,
                starts_on=due_window.starts_at.date(),
                ends_before=due_window.ends_at.date(),
                timezone=due_window.timezone,
            )
        anchor_now = business_time.business_now()
        if window == "last_week":
            this_week_start = self._start_of_week(anchor_now)
            starts_at = this_week_start - timedelta(days=7)
            ends_at = this_week_start
        else:
            starts_at = anchor_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if starts_at.month == 12:
                ends_at = starts_at.replace(year=starts_at.year + 1, month=1)
            else:
                ends_at = starts_at.replace(month=starts_at.month + 1)
        return WorkSummaryWindow(
            name=window,
            starts_at=starts_at,
            ends_at=ends_at,
            starts_on=starts_at.date(),
            ends_before=ends_at.date(),
            timezone="Asia/Shanghai",
        )

    @staticmethod
    def _parse_window_start(value: date | datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return business_time.to_business_naive(value)
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        parsed = WorkSummaryService._parse_iso_date_or_datetime(value)
        if isinstance(parsed, datetime):
            return business_time.to_business_naive(parsed)
        return datetime.combine(parsed, time.min)

    @staticmethod
    def _parse_window_end(value: date | datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return business_time.to_business_naive(value)
        if isinstance(value, date):
            return datetime.combine(value, time.min) + timedelta(days=1)
        parsed = WorkSummaryService._parse_iso_date_or_datetime(value)
        if isinstance(parsed, datetime):
            return business_time.to_business_naive(parsed)
        return datetime.combine(parsed, time.min) + timedelta(days=1)

    @staticmethod
    def _parse_iso_date_or_datetime(value: str) -> date | datetime:
        text = value.strip()
        if not text:
            raise ValueError("工作总结时间不能为空")
        try:
            if len(text) == 10:
                return date.fromisoformat(text)
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("工作总结时间必须是 ISO 日期或日期时间") from exc

    @staticmethod
    def _start_of_week(value: datetime) -> datetime:
        day_start = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start - timedelta(days=value.weekday())

    @staticmethod
    def _date_upper_bound_for_exclusive_end(ends_at: datetime) -> date:
        if ends_at.time() == time.min:
            return ends_at.date()
        return ends_at.date() + timedelta(days=1)

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if not cursor:
            return 0
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
            offset = int(payload.get("offset", 0))
        except Exception as exc:
            raise ValueError("工作总结 cursor 无效") from exc
        if offset < 0:
            raise ValueError("工作总结 cursor 无效")
        return offset

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        payload = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def _resolve_visible_customer(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        public_id: str | None,
    ) -> Customer | None:
        if public_id is None:
            return None
        customer = db.query(Customer).filter(Customer.team_id == team_id, Customer.public_id == public_id).first()
        if customer is None:
            raise ValueError("客户不存在")
        if not self._can_view_customer(db, team_id=team_id, user_id=user_id, customer=customer):
            raise PermissionError("无权查看该客户")
        return customer

    def _can_view_customer(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        customer: Customer | None,
    ) -> bool:
        if customer is None:
            return False
        permission_codes = {permission.code for permission in permission_crud.get_user_permissions(db, user_id, team_id)}
        user_id_text = str(user_id)
        if "customer:view:all" in permission_codes:
            return True
        if "customer:view:own" in permission_codes and customer.owner_id == user_id_text:
            return True
        if customer.owner_id == user_id_text:
            return True
        return db.query(CustomerMember.id).filter(
            CustomerMember.team_id == team_id,
            CustomerMember.customer_id == customer.id,
            CustomerMember.user_id == user_id_text,
            CustomerMember.is_active.is_(True),
        ).first() is not None

    def _date_or_datetime_for_window(
        self,
        preferred_date: date | datetime | None,
        fallback_datetime: datetime | None,
        window: WorkSummaryWindow,
    ) -> datetime | None:
        if isinstance(preferred_date, datetime):
            return preferred_date if self._datetime_in_window(preferred_date, window) else None
        if isinstance(preferred_date, date):
            if window.starts_on <= preferred_date < window.ends_before:
                return datetime.combine(preferred_date, datetime.min.time())
            return None
        if fallback_datetime is not None and self._datetime_in_window(fallback_datetime, window):
            return fallback_datetime
        return None

    def _first_datetime_in_window(self, window: WorkSummaryWindow, *values: datetime | None) -> datetime | None:
        for value in values:
            if value is not None and self._datetime_in_window(value, window):
                return value
        return None

    @staticmethod
    def _datetime_in_window(value: datetime, window: WorkSummaryWindow) -> bool:
        return window.starts_at <= value < window.ends_at

    @staticmethod
    def _customers_by_id(db: Session, *, team_id: int, customer_ids: list[int]) -> dict[int, Customer]:
        ids = list(dict.fromkeys(customer_id for customer_id in customer_ids if customer_id))
        if not ids:
            return {}
        rows = db.query(Customer).filter(Customer.team_id == team_id, Customer.id.in_(ids)).all()
        return {customer.id: customer for customer in rows}

    def _fact(
        self,
        *,
        fact_type: str,
        source_group: str,
        source_table: str,
        occurred_at: datetime | None,
        customer: Customer | None,
        payload: dict[str, Any] | None,
        title: str | None,
        source_public_id: str | None = None,
        business_key: str | None = None,
        attribution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        occurred_at_text = occurred_at.isoformat() if occurred_at else None
        fact_id_parts = [fact_type, source_public_id or business_key or title or "", occurred_at_text or ""]
        return {
            "fact_id": ":".join(str(part) for part in fact_id_parts if part),
            "fact_type": fact_type,
            "source_group": source_group,
            "source_table": source_table,
            "source_public_id": source_public_id,
            "business_key": business_key,
            "occurred_at": occurred_at_text,
            "customer": self._customer_payload(customer),
            "attribution": attribution,
            "title": title,
            "payload": payload or {},
        }

    def _task_payload(self, task: FollowUpTask, customer: Customer | None) -> dict[str, Any]:
        return {
            "id": task.public_id,
            "public_id": task.public_id,
            "customer": self._customer_payload(customer),
            "owner_id": task.owner_id,
            "creator_id": task.creator_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "due_at_text": task.due_at_text,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    def _activity_payload(self, activity: CustomerActivity, customer: Customer | None) -> dict[str, Any]:
        return {
            "customer": self._customer_payload(customer),
            "activity_kind": activity.activity_kind,
            "title": activity.title,
            "summary": activity.summary,
            "next_action": activity.next_action,
            "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
            "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
            "owner_id": activity.owner_id,
        }

    @staticmethod
    def _opportunity_payload(opportunity: Opportunity) -> dict[str, Any]:
        return {
            "id": opportunity.public_id,
            "public_id": opportunity.public_id,
            "opportunity_name": opportunity.opportunity_name,
            "current_stage_name": opportunity.current_stage_name,
            "status": opportunity.status,
            "approval_phase": opportunity.approval_phase,
        }

    @staticmethod
    def _customer_payload(customer: Customer | None) -> dict[str, Any] | None:
        if customer is None:
            return None
        return {
            "id": customer.public_id,
            "public_id": customer.public_id,
            "name": customer.account_name,
            "account_name": customer.account_name,
        }

    @staticmethod
    def _source_counts(facts: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fact in facts:
            fact_type = str(fact.get("fact_type") or "")
            counts[fact_type] = counts.get(fact_type, 0) + 1
        return counts

    @staticmethod
    def _decimal(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        return float(value)


work_summary_service = WorkSummaryService()
