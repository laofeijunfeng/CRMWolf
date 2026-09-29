"""Evidence-bound CRM commands executed only after individual user confirmation."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask

FACT_TYPES = frozenset({
    "alias", "need", "budget", "risk", "stage", "stakeholder_attitude",
    "competitor", "next_step", "preference", "summary",
})


def source_activity(db: Session, task: AssistantTask) -> CustomerActivity | None:
    committed_id = next(
        (item.get("public_id") for item in reversed(task.committed_json or [])
         if item.get("kind") == "customer_activity"), None,
    )
    authority_id = (task.authority_json or {}).get("activity_public_id")
    if not committed_id or (authority_id and str(authority_id) != str(committed_id)):
        return None
    try:
        identifier = int(committed_id)
    except (TypeError, ValueError):
        return None
    return db.query(CustomerActivity).filter(
        CustomerActivity.id == identifier, CustomerActivity.team_id == task.team_id,
    ).one_or_none()


def _customer(db: Session, task: AssistantTask, activity: CustomerActivity) -> Customer | None:
    authority_id = (task.authority_json or {}).get("customer_public_id")
    if not activity.customer_id:
        return None
    query = db.query(Customer).filter(Customer.id == activity.customer_id, Customer.team_id == task.team_id)
    if authority_id:
        query = query.filter(Customer.public_id == authority_id)
    return query.one_or_none()


def _user(db: Session, task: AssistantTask):
    from app.models.user import User, UserStatus
    from app.models.team import UserTeam

    user = db.query(User).filter(User.id == task.user_id, User.status == UserStatus.ACTIVE).one_or_none()
    membership = db.query(UserTeam).filter(UserTeam.user_id == task.user_id, UserTeam.team_id == task.team_id).first()
    if user is None or membership is None:
        raise PermissionError("当前用户已失去团队操作权限")
    return user


def _permissions(db: Session, task: AssistantTask) -> set[str]:
    from app.crud.permission import permission_crud

    _user(db, task)
    return {permission.code for permission in permission_crud.get_user_permissions(db, task.user_id, task.team_id)}


def _customer_edit(db: Session, task: AssistantTask, customer: Customer) -> None:
    from app.core.deps import check_customer_edit_permission

    check_customer_edit_permission(customer.public_id, task.team_id, _user(db, task), db)


def _opportunity(db: Session, task: AssistantTask, public_id: str):
    from app.models.opportunity import Opportunity

    return db.query(Opportunity).filter(
        Opportunity.public_id == public_id, Opportunity.team_id == task.team_id,
    ).one_or_none()


def _stage(db: Session, task: AssistantTask, opportunity, target_id: int):
    from app.crud.procurement import procurement_stage_template_crud
    from app.models.procurement import OpportunityStageSnapshot

    stages = procurement_stage_template_crud.get_by_method(db, opportunity.procurement_method_id, task.team_id)
    snapshot = db.query(OpportunityStageSnapshot).filter(
        OpportunityStageSnapshot.id == opportunity.current_stage_snapshot_id,
        OpportunityStageSnapshot.team_id == task.team_id,
    ).one_or_none() if opportunity.current_stage_snapshot_id else None
    if snapshot is not None:
        next_stage = next(
            (stage for stage in stages if stage.sort_order is not None
             and snapshot.template_sort_order is not None and stage.sort_order > snapshot.template_sort_order), None,
        )
    else:
        next_stage = next((stage for stage in stages if stage.is_default_start), stages[0] if stages else None)
    return next_stage if next_stage and int(next_stage.id) == target_id else None


def validate_candidate(db: Session, task: AssistantTask, candidate: dict) -> dict | None:
    """Bind model hints to persisted source and actual CRM rows, never model authority."""
    activity = source_activity(db, task)
    if activity is None:
        return None
    customer = _customer(db, task, activity)
    if customer is None:
        return None
    kind = candidate.get("kind")
    quote = candidate.get("evidence_quote")
    payload = candidate.get("payload")
    if not isinstance(quote, str) or not quote.strip() or quote.strip() not in (activity.source_content or ""):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        codes = _permissions(db, task)
        if kind == "customer_fact":
            if payload.get("fact_type") not in FACT_TYPES or not isinstance(payload.get("content"), str):
                return None
            if not payload["content"].strip() or payload["content"].strip() not in quote:
                return None
            _customer_edit(db, task, customer)
            from app.models.customer_fact import CustomerFact
            from app.services.customer_fact_service import CustomerFactService

            fact_key = CustomerFactService().fact_key(
                team_id=task.team_id, customer_id=customer.id,
                fact_type=payload["fact_type"], subject=payload.get("subject"),
            )
            existing = db.query(CustomerFact).filter(CustomerFact.fact_key == fact_key).one_or_none()
            if existing is not None and existing.content.strip() == payload["content"].strip():
                return None
            return {**candidate, "activity_id": activity.id, "customer_id": customer.id,
                    "source_revision": activity.activity_revision,
                    "prior_fact_version": existing.version if existing else None}
        if kind == "follow_up_task_create":
            from datetime import datetime, time
            from app.crud.sales_commitment import follow_up_task_crud
            from app.models.sales_commitment import FollowUpTaskSourceType

            title = payload.get("action")
            if not isinstance(title, str) or not title.strip() or title.strip() not in activity.source_content:
                return None
            if activity.owner_id != str(task.user_id):
                return None
            owner = str(payload.get("owner") or "").strip()
            user = _user(db, task)
            if owner and owner not in {str(task.user_id), user.name, "我", "本人"}:
                return None
            due_raw = payload.get("due_date")
            if not isinstance(due_raw, str) or not due_raw.strip():
                return None
            try:
                due = datetime.fromisoformat(due_raw.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
            if due_raw.strip() not in activity.source_content:
                return None
            if not any(title.strip() in clause and due_raw.strip() in clause for clause in
                       activity.source_content.replace("。", "；").replace(";", "；").split("；")):
                return None
            if len(due_raw.strip()) == 10:
                due = datetime.combine(due.date(), time(23, 59, 59))
            task_hash = sha256(f"{activity.id}:{title.strip()}:{due.isoformat()}".encode()).hexdigest()
            if follow_up_task_crud.get_by_source_hash(
                db, team_id=task.team_id, source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=f"activity:{activity.id}", task_hash=task_hash,
            ):
                return None
            return {**candidate, "activity_id": activity.id, "customer_id": customer.id,
                    "source_revision": activity.activity_revision, "task_hash": task_hash}
        if kind == "follow_up_task":
            action_name = payload.get("action")
            if action_name not in {"complete", "postpone", "cancel", "unrelated"} or not isinstance(candidate.get("target_public_id"), str):
                return None
            if action_name == "postpone" and not isinstance(payload.get("due_date"), str):
                return None
            row = db.query(FollowUpTask).filter(
                FollowUpTask.public_id == candidate["target_public_id"],
                FollowUpTask.team_id == task.team_id,
                FollowUpTask.customer_id == customer.id,
                FollowUpTask.status == FollowUpTaskStatus.OPEN,
            ).one_or_none()
            if row is None or row.title.strip() not in quote or (row.owner_id != str(task.user_id) and not codes.intersection(
                {"follow_up_task:operate:all", "follow_up_task:edit:all"}
            )):
                return None
            return {**candidate, "activity_id": activity.id, "customer_id": customer.id,
                    "source_revision": activity.activity_revision, "prior_status": row.status,
                    "task_owner_id": row.owner_id}
        if kind == "opportunity_stage":
            opportunity = _opportunity(db, task, str(candidate.get("target_public_id") or ""))
            if not opportunity or opportunity.customer_id != customer.id or str(opportunity.status) not in {"0", "OpportunityStatus.FOLLOWING"}:
                return None
            if not ("opportunity:edit:all" in codes or
                    ("opportunity:edit:own" in codes and opportunity.owner_id == str(task.user_id))):
                return None
            from app.api.opportunities import _ensure_opportunity_approved

            _ensure_opportunity_approved(db, opportunity, task.team_id)
            try:
                stage_id = int(payload.get("stage_template_id"))
            except (TypeError, ValueError):
                return None
            stage = _stage(db, task, opportunity, stage_id)
            if stage is None or stage.stage_name not in quote:
                return None
            return {**candidate, "activity_id": activity.id, "customer_id": customer.id,
                    "source_revision": activity.activity_revision,
                    "prior_stage_snapshot_id": opportunity.current_stage_snapshot_id,
                    "prior_version": opportunity.version}
        if kind == "opportunity_create":
            from app.schemas.opportunity import OpportunityCreate
            from pydantic import ValidationError

            if "opportunity:create" not in codes:
                return None
            _customer_edit(db, task, customer)
            try:
                data = OpportunityCreate.model_validate({**payload, "customer_id": customer.public_id})
            except ValidationError:
                return None
            if not all(str(value) in (activity.source_content or "") for value in (
                data.total_amount, data.user_count, data.expected_closing_date,
            )):
                return None
            from app.models.opportunity import Opportunity

            duplicate = db.query(Opportunity).filter(
                Opportunity.team_id == task.team_id, Opportunity.customer_id == customer.id,
                Opportunity.opportunity_name == data.opportunity_name,
            ).first() if data.opportunity_name else None
            if duplicate:
                return None
            return {**candidate, "activity_id": activity.id, "customer_id": customer.id,
                    "source_revision": activity.activity_revision}
    except (HTTPException, PermissionError, ValueError):
        return None
    return None


class RealCRMProposalExecutor:
    """Execute one currently valid proposal through existing CRM domain boundaries."""

    async def __call__(self, db: Session, task: AssistantTask, proposal: dict) -> dict:
        return await self.execute(db, task, proposal)

    async def execute(self, db: Session, task: AssistantTask, proposal: dict) -> dict:
        validated = validate_candidate(db, task, proposal)
        if validated is None:
            raise ValueError("提议的客户数据、证据或操作权限已变化，请刷新后重试")
        if any(validated.get(field) != proposal.get(field) for field in (
            "activity_id", "customer_id", "source_revision", "prior_status", "prior_stage_snapshot_id",
            "prior_version", "prior_fact_version", "task_hash", "task_owner_id",
        )):
            raise ValueError("CRM 状态已变化，不能继续执行旧提议")
        kind = proposal["kind"]
        payload = proposal["payload"]
        if kind == "customer_fact":
            from app.services.customer_fact_service import CustomerFactInput, CustomerFactSourceInput, CustomerFactService

            fact = CustomerFactService().upsert_fact(db, CustomerFactInput(
                tenant_id=task.team_id, team_id=task.team_id, customer_id=validated["customer_id"],
                fact_type=payload["fact_type"], subject=payload.get("subject"), content=payload["content"],
                confidence=1.0,
                source=CustomerFactSourceInput(
                    source_type="customer_activity", source_object_id=str(validated["activity_id"]),
                    evidence_id=proposal["key"], quote=proposal["evidence_quote"],
                ),
            ))
            return {"kind": "customer_fact", "public_id": str(fact.id)}
        if kind == "follow_up_task_create":
            from datetime import datetime, time
            from app.crud.sales_commitment import follow_up_task_crud, follow_up_task_event_crud
            from app.models.sales_commitment import FollowUpTaskEventType, FollowUpTaskSourceType
            from app.schemas.sales_commitment import FollowUpTaskInternalCreate

            due_raw = payload["due_date"].strip()
            due = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
            if len(due_raw) == 10:
                due = datetime.combine(due.date(), time(23, 59, 59))
            row = follow_up_task_crud.create(db, FollowUpTaskInternalCreate(
                team_id=task.team_id, customer_id=validated["customer_id"],
                owner_id=str(task.user_id), creator_id=str(task.user_id), title=payload["action"].strip(),
                due_at=due, due_at_text=due_raw, source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=f"activity:{validated['activity_id']}", source_activity_id=validated["activity_id"],
                task_hash=validated["task_hash"],
                evidence_json={"quote": proposal["evidence_quote"], "assistant_proposal": proposal["key"]},
            ), commit=False)
            follow_up_task_event_crud.record_status_change(
                db, task=row, event_type=FollowUpTaskEventType.CREATED, actor_id=str(task.user_id),
                previous_status=None, commit=False,
            )
            return {"kind": "follow_up_task_create", "public_id": row.public_id}
        if kind == "follow_up_task":
            from app.services.follow_up_task_transition_execution_service import (
                FollowUpTaskTransitionExecutionStatus, follow_up_task_transition_execution_service,
            )
            from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionAction, FollowUpTaskTransitionPlan
            from app.services.follow_up_task_reconciliation_evaluation_service import (
                FollowUpTaskReconciliationDecision, FollowUpTaskReconciliationTaskDecision,
            )

            target = proposal["target_public_id"]
            requested = {"complete": "COMPLETE", "postpone": "POSTPONE", "cancel": "CANCEL", "unrelated": "KEEP_OPEN"}[payload["action"]]
            if requested == "KEEP_OPEN":
                return {"kind": "follow_up_task", "public_id": target}
            action = FollowUpTaskTransitionAction(
                action=requested, task_public_id=target, confidence=1.0,
                executable=True, requires_confirmation=False, reason="assistant_confirmed_task_transition",
                evidence_terms=(proposal["evidence_quote"],),
                source_activity_public_id=str(validated["activity_id"]),
                proposed_due_at=payload.get("due_date"),
            )
            plan = FollowUpTaskTransitionPlan(
                decision=FollowUpTaskReconciliationDecision(
                    candidate_public_ids=(target,), task_decisions=(
                        FollowUpTaskReconciliationTaskDecision(decision=requested, confidence=1.0, task_public_id=target),
                    ),
                ),
                actions=(action,), plan_source="assistant_confirmation",
            )
            result = follow_up_task_transition_execution_service.execute_action(
                db, team_id=task.team_id, action=action, plan=plan,
                actor_id=str(task.user_id), expected_owner_id=validated["task_owner_id"], commit=False,
            )
            if result.status != FollowUpTaskTransitionExecutionStatus.EXECUTED:
                raise ValueError(result.skip_reason or "跟进任务状态未更新")
            return {"kind": "follow_up_task", "public_id": target}
        if kind == "opportunity_stage":
            from app.api.opportunities import move_opportunity_stage
            from app.schemas.opportunity import OpportunityMoveToStage

            result = await move_opportunity_stage(
                opportunity_id=proposal["target_public_id"],
                stage_move=OpportunityMoveToStage(stage_template_id=payload["stage_template_id"]),
                db_opportunity=_opportunity(db, task, proposal["target_public_id"]),
                current_user=_user(db, task), db=db,
            )
            if not result or not result.get("current_stage_snapshot") or result["current_stage_snapshot"].id == proposal.get("prior_stage_snapshot_id"):
                raise ValueError("商机阶段未更新")
            return {"kind": "opportunity_stage", "public_id": proposal["target_public_id"]}
        if kind == "opportunity_create":
            from app.api.opportunities import create_opportunity
            from app.schemas.opportunity import OpportunityCreate

            result = await create_opportunity(
                opportunity=OpportunityCreate.model_validate({**payload, "customer_id":
                    _customer(db, task, source_activity(db, task)).public_id}),
                team_id=task.team_id, current_user=_user(db, task), db=db,
            )
            if not result or not result.public_id:
                raise ValueError("商机创建失败")
            return {"kind": "opportunity_create", "public_id": result.public_id}
        raise ValueError("不支持的 CRM 提议")
