"""Evidence-bound CRM commands executed only after individual user confirmation."""
# ruff: noqa: RUF001

from __future__ import annotations

import json
from hashlib import sha256
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict

from fastapi import HTTPException

from app.constants.opportunity_loss import CONTRACT_LOSS_BLOCK_REASON
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.services.assistant.action_evidence import validate_action_evidence
from app.services.assistant.crm_effects import AssistantCRMCommand, AssistantCRMNoEffect, checked_effect
from app.services.assistant.opportunity_target_matching import match_opportunity_target

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy.orm import Session

    from app.models.assistant import AssistantTask
    from app.models.assistant_crm_effect import AssistantCRMEffect
    from app.models.opportunity import Opportunity
    from app.models.procurement import OpportunityStageSnapshot, ProcurementStageTemplate
    from app.models.user import User
    from app.services.assistant.contracts import ProposalKind

# Proposal payloads keep the exact serialized shape, including omitted keys.
CONTRACT_BLOCK_REASON = CONTRACT_LOSS_BLOCK_REASON
ProposalData = dict[str, Any]


class ProposalOutcome(TypedDict):
    kind: ProposalKind
    public_id: str
    approval_phase: NotRequired[Literal["pending_review"]]
    approval_id: NotRequired[int]


def source_activity(db: Session, task: AssistantTask) -> CustomerActivity | None:
    committed_id = next(
        (
            item.get("public_id")
            for item in reversed(task.committed_json or [])
            if item.get("kind") == "customer_activity"
        ),
        None,
    )
    authority_id = (task.authority_json or {}).get("activity_public_id")
    if not committed_id or (authority_id and str(authority_id) != str(committed_id)):
        return None
    try:
        identifier = int(committed_id)
    except (TypeError, ValueError):
        return None
    return (
        db.query(CustomerActivity)
        .filter(
            CustomerActivity.id == identifier,
            CustomerActivity.team_id == task.team_id,
        )
        .one_or_none()
    )


def _customer(db: Session, task: AssistantTask, activity: CustomerActivity) -> Customer | None:
    authority_id = (task.authority_json or {}).get("customer_public_id")
    if not activity.customer_id:
        return None
    query = db.query(Customer).filter(Customer.id == activity.customer_id, Customer.team_id == task.team_id)
    if authority_id:
        query = query.filter(Customer.public_id == authority_id)
    return query.one_or_none()


def _user(db: Session, task: AssistantTask) -> User:
    from app.models.team import UserTeam
    from app.models.user import User, UserStatus

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


def _opportunity(db: Session, task: AssistantTask, public_id: str) -> Opportunity | None:
    from app.models.opportunity import Opportunity

    return (
        db.query(Opportunity)
        .filter(
            Opportunity.public_id == public_id,
            Opportunity.team_id == task.team_id,
        )
        .one_or_none()
    )


def adjacent_stage(
    db: Session, task: AssistantTask, opportunity: Opportunity
) -> tuple[OpportunityStageSnapshot | None, ProcurementStageTemplate] | None:
    """Resolve the current snapshot and only legal next template for this opportunity."""
    from app.crud.procurement import procurement_stage_template_crud
    from app.models.procurement import OpportunityStageSnapshot

    if opportunity.team_id != task.team_id or opportunity.procurement_method_id is None:
        return None
    snapshot = None
    if opportunity.current_stage_snapshot_id is not None:
        snapshot = (
            db.query(OpportunityStageSnapshot)
            .filter(
                OpportunityStageSnapshot.id == opportunity.current_stage_snapshot_id,
                OpportunityStageSnapshot.team_id == task.team_id,
                OpportunityStageSnapshot.opportunity_id == opportunity.id,
            )
            .one_or_none()
        )
        if snapshot is None:
            return None
    stages = procurement_stage_template_crud.get_by_method(db, opportunity.procurement_method_id, task.team_id)
    if snapshot is not None:
        next_stage = next(
            (
                stage
                for stage in stages
                if stage.sort_order is not None
                and snapshot.template_sort_order is not None
                and stage.sort_order > snapshot.template_sort_order
            ),
            None,
        )
    else:
        next_stage = next((stage for stage in stages if stage.is_default_start), stages[0] if stages else None)
    return (snapshot, next_stage) if next_stage is not None else None


ProposalRejection = Literal["schema", "literal", "target", "permission"]


def _source_segments(activity: CustomerActivity) -> list[tuple[str, str]]:
    content_json: str | None = attrgetter("content_json")(activity)
    source_content: str = attrgetter("source_content")(activity) or ""
    try:
        content = json.loads(content_json or "{}")
    except (TypeError, ValueError):
        content = {}
    records = content.get("source_records") if isinstance(content, dict) else None
    segments = [
        (str(record["segment_id"]), str(record["text"]))
        for record in (records if isinstance(records, list) else [])
        if isinstance(record, dict) and record.get("segment_id") and record.get("text")
    ]
    return segments or [("seg_primary", source_content)]


def _matches_create_segment(activity: CustomerActivity, segment_id: object, quote: str) -> bool:
    if not isinstance(segment_id, str) or not segment_id:
        return False
    matches = [text for identifier, text in _source_segments(activity) if identifier == segment_id]
    return len(matches) == 1 and quote in matches[0]


def _matches_current_loss_evidence(
    activity: CustomerActivity,
    *,
    segment_id: object,
    quote: str,
    loss_reason: str,
) -> bool:
    if not isinstance(segment_id, str) or not segment_id:
        return False
    segments = _source_segments(activity)
    matching = [
        index for index, (identifier, text) in enumerate(segments)
        if identifier == segment_id and quote in text
    ]
    if len(matching) != 1:
        return False
    index = matching[0]
    if loss_reason not in segments[index][1]:
        return False
    later_text = "\n".join(text for _, text in segments[index + 1:])
    if not later_text:
        return True
    correction_markers = (
        "更正", "纠正", "不是", "改为", "改到", "应为", "而是",
        "继续推进", "继续跟进", "重新推进",
    )
    return not any(marker in later_text for marker in correction_markers) or loss_reason in later_text


def validate_candidate(
    db: Session,
    task: AssistantTask,
    candidate: Mapping[str, object],
    *,
    on_reject: Callable[[ProposalRejection], None] | None = None,
) -> ProposalData | None:
    """Bind model hints to persisted source and tenant-scoped CRM rows."""

    def reject(reason: ProposalRejection) -> None:
        if on_reject is not None:
            on_reject(reason)

    kind = candidate.get("kind")
    if kind not in ("follow_up_task_create", "opportunity_stage", "opportunity_create", "opportunity_lose"):
        reject("schema")
        return None
    activity = source_activity(db, task)
    if activity is None:
        reject("target")
        return None
    customer = _customer(db, task, activity)
    if customer is None:
        reject("target")
        return None
    # Legacy Column declarations describe the SQL expression, not the instance value.
    source_content: str = attrgetter("source_content")(activity)
    quote = candidate.get("evidence_quote")
    payload = candidate.get("payload")
    if not isinstance(quote, str) or not quote.strip():
        reject("schema")
        return None
    if quote.strip() not in (source_content or ""):
        reject("literal")
        return None
    if not isinstance(payload, dict):
        reject("schema")
        return None
    if kind in {"opportunity_stage", "opportunity_lose"} and not candidate.get("target_public_id"):
        reject("schema")
        return None
    try:
        from app.crud.contract import contract_crud
        codes = _permissions(db, task)
        if kind == "follow_up_task_create":
            from datetime import datetime, time

            from app.crud.sales_commitment import follow_up_task_crud
            from app.models.sales_commitment import FollowUpTaskSourceType

            title = payload.get("action")
            if not isinstance(title, str) or not title.strip():
                reject("schema")
                return None
            if title.strip() not in (source_content or ""):
                reject("literal")
                return None
            if activity.owner_id != str(task.user_id):
                reject("permission")
                return None
            owner = str(payload.get("owner") or "").strip()
            user = _user(db, task)
            if owner and owner not in {str(task.user_id), user.name, "我", "本人"}:
                reject("permission")
                return None

            action_id = candidate.get("action_id")
            if not isinstance(action_id, str) or not owner:
                reject("schema")
                return None
            content_json: str | None = attrgetter("content_json")(activity)
            try:
                canonical = json.loads(content_json or "{}")
            except (ValueError, TypeError):
                reject("schema")
                return None
            evidence = validate_action_evidence(canonical, action_id, source_content=source_content or "")
            if (
                evidence is None
                or evidence.due_at is None
                or (title, owner, quote)
                != (
                    evidence.action,
                    evidence.owner,
                    evidence.evidence_quote,
                )
                or payload.get("due_date") != evidence.due_at.isoformat()
            ):
                reject("literal")
                return None
            due = evidence.due_at
            if evidence.granularity == "DATE":
                due = datetime.combine(due.date(), time(23, 59, 59))
            task_hash = sha256(f"{activity.id}:{action_id}:{evidence.revision}:{due.isoformat()}".encode()).hexdigest()
            if follow_up_task_crud.get_by_source_hash(
                db,
                team_id=task.team_id,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=f"activity:{activity.id}",
                task_hash=task_hash,
            ):
                reject("target")
                return None
            return {
                **candidate,
                "activity_id": activity.id,
                "customer_id": customer.id,
                "source_revision": activity.activity_revision,
                "task_hash": task_hash,
                "due_date_granularity": evidence.granularity,
                # Cards and receipts show the resolved owner; `owner` stays the spoken evidence.
                "payload": {**payload, "owner_name": user.name or owner},
            }
        if kind == "opportunity_stage":
            opportunity = _opportunity(db, task, str(candidate.get("target_public_id") or ""))
            if (
                not opportunity
                or opportunity.customer_id != customer.id
                or str(opportunity.status) not in {"0", "OpportunityStatus.FOLLOWING"}
            ):
                reject("target")
                return None
            if not (
                "opportunity:edit:all" in codes
                or ("opportunity:edit:own" in codes and opportunity.owner_id == str(task.user_id))
            ):
                reject("permission")
                return None
            from app.api.opportunities import _ensure_opportunity_approved

            _ensure_opportunity_approved(db, opportunity, task.team_id)
            transition = adjacent_stage(db, task, opportunity)
            if transition is None:
                reject("target")
                return None
            snapshot, stage = transition
            stage_name: str = attrgetter("stage_name")(stage)
            # A ref identifies the transition offered to the model, not whatever happens to be next later.
            if "_nominated_transition" in candidate and candidate["_nominated_transition"] != (
                activity.activity_revision,
                opportunity.current_stage_snapshot_id,
                opportunity.version,
                stage.id,
                stage_name,
            ):
                reject("target")
                return None
            if stage_name not in quote:
                reject("literal")
                return None
            stage_payload = {
                "stage_template_id": stage.id,
                "stage_name": stage_name,
                "current_stage_name": snapshot.stage_name if snapshot is not None else None,
                "opportunity_name": opportunity.opportunity_name,
            }
            fences = {
                "activity_id": activity.id,
                "customer_id": customer.id,
                "source_revision": activity.activity_revision,
                "prior_stage_snapshot_id": opportunity.current_stage_snapshot_id,
                "prior_version": opportunity.version,
            }
            if "prior_version" in candidate and (
                any(candidate.get(field) != value for field, value in fences.items())
                or payload.get("stage_template_id") != stage.id
                or any(field in payload and payload[field] != value for field, value in stage_payload.items())
            ):
                reject("target")
                return None
            return {
                "kind": kind,
                "target_public_id": opportunity.public_id,
                "evidence_quote": quote,
                "payload": stage_payload,
                **fences,
            }
        if kind == "opportunity_create":
            from pydantic import ValidationError

            from app.schemas.opportunity import OpportunityCreate

            if "opportunity:create" not in codes:
                reject("permission")
                return None
            _customer_edit(db, task, customer)
            segment_id = candidate.get("segment_id")
            if segment_id is not None and not _matches_create_segment(activity, segment_id, quote.strip()):
                reject("literal")
                return None
            execution_values = candidate.get("form_values")
            if "form_values" in candidate:
                if not isinstance(execution_values, dict) or execution_values.get("customer_id") != customer.public_id:
                    reject("target")
                    return None
                data = OpportunityCreate.model_validate(execution_values)
                if data.model_dump(mode="json") != execution_values:
                    reject("schema")
                    return None
            elif payload:
                # Only a hint with enough information to identify a target can
                # be deduplicated here. Missing form fields never block nomination.
                try:
                    data = OpportunityCreate.model_validate({**payload, "customer_id": customer.public_id})
                except ValidationError:
                    data = None
                customer_id: int = attrgetter("id")(customer)
                if data is not None and match_opportunity_target(
                    db, team_id=task.team_id, customer_id=customer_id, data=data,
                ).status != "DISTINCT":
                    reject("target")
                    return None
            return {
                **candidate,
                "activity_id": activity.id,
                "customer_id": customer.id,
                "source_revision": activity.activity_revision,
            }
        if kind == "opportunity_lose":
            opportunity = _opportunity(db, task, str(candidate.get("target_public_id") or ""))
            if not opportunity or opportunity.customer_id != customer.id:
                reject("target")
                return None
            from app.models.opportunity import OpportunityStatus
            if opportunity.status != OpportunityStatus.WON.value:
                reject("target")
                return None
            contract_blocked = contract_crud.has_active_contract_for_opportunity(db, opportunity.id, task.team_id)
            if not (
                "opportunity:lose" in codes
                and (
                    "opportunity:edit:all" in codes
                    or ("opportunity:edit:own" in codes and opportunity.owner_id == str(task.user_id))
                )
            ):
                reject("permission")
                return None
            from app.api.opportunities import _ensure_opportunity_approved
            _ensure_opportunity_approved(db, opportunity, task.team_id)
            loss_reason = payload.get("loss_reason")
            if not isinstance(loss_reason, str) or not loss_reason.strip() or len(loss_reason.strip()) > 500:
                reject("schema")
                return None
            segment_id = candidate.get("segment_id")
            if not _matches_current_loss_evidence(
                activity,
                segment_id=segment_id,
                quote=quote.strip(),
                loss_reason=loss_reason.strip(),
            ):
                reject("literal")
                return None
            if "_nominated_loss_target" in candidate and candidate["_nominated_loss_target"] != (
                activity.activity_revision, opportunity.public_id, opportunity.version,
            ):
                reject("target")
                return None
            fences = {
                "activity_id": activity.id,
                "customer_id": customer.id,
                "source_revision": activity.activity_revision,
                "prior_version": opportunity.version,
            }
            if "prior_version" in candidate and any(candidate.get(field) != value for field, value in fences.items()):
                reject("target")
                return None
            bound_payload = {
                "loss_reason": loss_reason.strip(),
                "opportunity_name": opportunity.opportunity_name,
            }
            if contract_blocked:
                bound_payload["block_reason"] = CONTRACT_BLOCK_REASON
            return {
                "kind": kind,
                "target_public_id": opportunity.public_id,
                "evidence_quote": quote,
                "segment_id": segment_id,
                "payload": bound_payload,
                **fences,
            }
    except (HTTPException, PermissionError):
        reject("permission")
        return None
    except ValueError:
        reject("schema")
        return None
    reject("schema")
    return None


def build_proposal_command(task: AssistantTask, proposal: ProposalData) -> AssistantCRMCommand:
    """Bind the frozen proposal to one durable, actor-scoped target transaction."""
    fingerprint = proposal["key"]
    if proposal["kind"] == "opportunity_create" and "form_values" in proposal:
        frozen_input = json.dumps(
            {"candidate_key": proposal["key"], "form_values": proposal["form_values"]},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        )
        fingerprint = sha256(frozen_input.encode()).hexdigest()
    return AssistantCRMCommand(
        command_id=sha256(f"assistant:{task.team_id}:{task.public_id}:{proposal['key']}".encode()).hexdigest(),
        team_id=task.team_id,
        actor_id=task.user_id,
        fingerprint=fingerprint,
        expected_snapshot_id=proposal.get("prior_stage_snapshot_id")
        if proposal["kind"] == "opportunity_stage" else None,
        expected_version=proposal.get("prior_version")
        if proposal["kind"] in {"opportunity_stage", "opportunity_lose"} else None,
    )
def opportunity_create_receipt_outcome(effect: AssistantCRMEffect | None) -> ProposalOutcome | None:
    """Project the original submission outcome from an already checked receipt."""
    if effect is None or not (effect.target_public_id or "").strip() or effect.approval_id is None:
        return None
    # The creation transaction records an approval ID only when it submits for review.
    return {
        "kind": "opportunity_create",
        "public_id": effect.target_public_id,
        "approval_phase": "pending_review",
        "approval_id": effect.approval_id,
    }


class RealCRMProposalExecutor:
    """Execute one currently valid proposal through existing CRM domain boundaries."""

    async def __call__(self, db: Session, task: AssistantTask, proposal: ProposalData) -> ProposalOutcome:
        return await self.execute(db, task, proposal)

    async def execute(self, db: Session, task: AssistantTask, proposal: ProposalData) -> ProposalOutcome:
        kind = proposal["kind"]
        rejection_error = ValueError
        if kind == "opportunity_create":
            from app.crud.product import product_crud

            rejection_error = AssistantCRMNoEffect
            if not isinstance(proposal.get("form_values"), dict):
                raise AssistantCRMNoEffect("请先提交并校验商机表单")
            # The CRM creation path takes this same fence before writing. Take
            # it before reading current state and keep it through the commit.
            product_crud.lock_catalog_team(db, task.team_id)
        validated = validate_candidate(db, task, proposal)
        if validated is None:
            raise rejection_error("CRM 状态已变化，或提议的证据或操作权限已失效，请刷新后重试")
        if kind == "opportunity_lose" and validated["payload"].get("block_reason") == CONTRACT_BLOCK_REASON:
            raise AssistantCRMNoEffect(CONTRACT_BLOCK_REASON)
        if any(
            validated.get(field) != proposal.get(field)
            for field in (
                "activity_id",
                "customer_id",
                "source_revision",
                "prior_status",
                "prior_stage_snapshot_id",
                "prior_version",
                "prior_fact_version",
                "task_hash",
                "task_owner_id",
                "due_date_granularity",
            )
        ):
            raise rejection_error("CRM 状态已变化，不能继续执行旧提议")
        payload = proposal["payload"]
        if kind == "follow_up_task_create":
            from datetime import datetime, time

            from app.crud.sales_commitment import follow_up_task_crud, follow_up_task_event_crud
            from app.models.sales_commitment import FollowUpTaskEventType, FollowUpTaskSourceType
            from app.schemas.sales_commitment import FollowUpTaskInternalCreate

            activity = source_activity(db, task)
            evidence = validate_action_evidence(
                json.loads(activity.content_json), proposal["action_id"], source_content=activity.source_content or ""
            )
            if evidence is None or evidence.due_at is None:
                raise ValueError("行动日期证据已失效")
            due = evidence.due_at
            if evidence.granularity == "DATE":
                due = datetime.combine(due.date(), time(23, 59, 59))
            row = follow_up_task_crud.create(
                db,
                FollowUpTaskInternalCreate(
                    team_id=task.team_id,
                    customer_id=validated["customer_id"],
                    owner_id=str(task.user_id),
                    creator_id=str(task.user_id),
                    title=payload["action"].strip(),
                    due_at=due,
                    due_at_text=evidence.due_at_text,
                    due_at_granularity=evidence.granularity,
                    due_at_timezone=evidence.timezone,
                    source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                    source_key=f"activity:{validated['activity_id']}",
                    source_activity_id=validated["activity_id"],
                    task_hash=validated["task_hash"],
                    evidence_json={**evidence.model_dump(mode="json"), "assistant_proposal": proposal["key"]},
                ),
                commit=False,
            )
            follow_up_task_event_crud.record_status_change(
                db,
                task=row,
                event_type=FollowUpTaskEventType.CREATED,
                actor_id=str(task.user_id),
                previous_status=None,
                commit=False,
            )
            return {"kind": "follow_up_task_create", "public_id": attrgetter("public_id")(row)}
        if kind == "opportunity_lose":
            from app.crud.opportunity import opportunity_crud
            from app.schemas.opportunity import OpportunityLose

            command = build_proposal_command(task, proposal)
            existing = checked_effect(db, command, kind)
            if existing is not None:
                if existing.target_public_id != proposal["target_public_id"]:
                    raise ValueError("商机输单命令目标不匹配")
                return {"kind": kind, "public_id": existing.target_public_id}
            try:
                opportunity_crud.mark_as_lost(
                    db, _opportunity(db, task, proposal["target_public_id"]),
                    OpportunityLose(loss_reason=payload["loss_reason"]), str(task.user_id),
                    assistant_command=command,
                )
            except ValueError as exc:
                if str(exc) == CONTRACT_BLOCK_REASON:
                    raise AssistantCRMNoEffect(str(exc)) from exc
                raise
            from app.services.opportunity_loss_side_effect_service import enqueue_opportunity_loss_side_effects

            enqueue_opportunity_loss_side_effects(
                db,
                _opportunity(db, task, proposal["target_public_id"]),
                actor_id=str(task.user_id),
                loss_reason=payload["loss_reason"],
            )
            effect = checked_effect(db, command, kind)
            if effect is None or effect.target_public_id != proposal["target_public_id"]:
                raise ValueError("商机输单命令缺少精确提交凭据")
            return {"kind": kind, "public_id": proposal["target_public_id"]}
        if kind == "opportunity_stage":
            from app.api.opportunities import move_opportunity_stage
            from app.schemas.opportunity import OpportunityMoveToStage

            stage_id = validated["payload"]["stage_template_id"]
            if stage_id != payload.get("stage_template_id"):
                raise ValueError("CRM 状态已变化，不能继续执行旧提议")
            command = build_proposal_command(task, proposal)
            await move_opportunity_stage(
                opportunity_id=proposal["target_public_id"],
                stage_move=OpportunityMoveToStage(stage_template_id=stage_id),
                db_opportunity=_opportunity(db, task, proposal["target_public_id"]),
                current_user=_user(db, task),
                db=db,
                assistant_command=command,
            )
            effect = checked_effect(db, command, kind)
            if effect is None or effect.target_public_id != proposal["target_public_id"]:
                raise ValueError("商机阶段命令缺少精确提交凭据")
            return {"kind": "opportunity_stage", "public_id": proposal["target_public_id"]}
        if kind == "opportunity_create":
            from app.api.opportunities import create_opportunity
            from app.schemas.opportunity import OpportunityCreate

            command = build_proposal_command(task, validated)
            existing = checked_effect(db, command, kind)
            if existing is not None:
                outcome = opportunity_create_receipt_outcome(existing)
                if outcome is None:
                    raise ValueError("商机创建命令缺少精确审批凭据")
                return outcome
            data = OpportunityCreate.model_validate(validated["form_values"])
            if match_opportunity_target(
                db, team_id=task.team_id, customer_id=validated["customer_id"], data=data,
                current_read=True,
            ).status != "DISTINCT":
                raise AssistantCRMNoEffect("已存在相同或无法区分的商机，未创建新商机")
            result = await create_opportunity(
                opportunity=data,
                team_id=task.team_id,
                current_user=_user(db, task),
                db=db,
                assistant_command=command,
            )
            outcome = opportunity_create_receipt_outcome(checked_effect(db, command, kind))
            if outcome is None or not result or outcome["public_id"] != result.public_id:
                raise ValueError("商机创建命令缺少精确提交凭据")
            return outcome
        raise ValueError("不支持的 CRM 提议")
