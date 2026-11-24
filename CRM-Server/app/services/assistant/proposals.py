"""Offer evidence-bound, individually confirmed CRM changes after activity commit."""
# ruff: noqa: RUF001

from __future__ import annotations

import json
import logging
from hashlib import sha256
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import update as sql_update
from sqlalchemy.exc import SQLAlchemyError

from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.action_evidence import validate_action_evidence
from app.services.assistant.contracts import ProposalCandidate, ProposalConfirmation, TaskAuthority, TaskWaiting
from app.services.assistant.crm_effects import AssistantCRMNoEffect, checked_effect
from app.services.assistant.crm_proposal_commands import build_proposal_command, source_activity, validate_candidate
from app.services.assistant.events import stage
from app.services.assistant.failure_contract import AssistantFailureCode
from app.services.assistant.model_transport import AssistantLLMError
from app.services.assistant.task_state import (
    TaskStateConflictError,
    TaskUpdate,
    apply_task_update,
    load_authority,
    load_waiting,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from pydantic import JsonValue
    from sqlalchemy.orm import Session

    from app.services.assistant.crm_proposal_commands import ProposalData, ProposalOutcome, ProposalRejection
    from app.services.assistant.events import ProgressReporter

    ProposalExecutor = Callable[[Session, AssistantTask, ProposalData], Awaitable[Mapping[str, object]]]

logger = logging.getLogger(__name__)
PROPOSAL_UNAVAILABLE_TEXT = "活动已记录。本次没能生成后续建议，可在客户页手动处理。"


class _CommittedActivityMissing(ValueError):
    """The task claims an activity receipt that no longer exists; the task must not complete."""



_PROMPTS = {
    "opportunity_create": "根据这次活动，为客户创建商机吗？",
    "opportunity_stage": "根据这次活动，推进这条商机到下一阶段吗？",
    "opportunity_lose": "根据这次活动，将这条商机标记为输单吗？",
    "follow_up_task_create": "根据这次活动，为你建立这项跟进任务吗？",
}


def _candidate_key(candidate: ProposalData) -> str:
    fields = {
        field: candidate.get(field)
        for field in (
            "kind",
            "target_public_id",
            "payload",
            "evidence_quote",
            "activity_id",
            "customer_id",
            "source_revision",
            "prior_status",
            "task_owner_id",
            "prior_stage_snapshot_id",
            "prior_version",
            "prior_fact_version",
            "task_hash",
            "action_id",
            "due_date_granularity",
        )
    }
    if candidate.get("segment_id") is not None:
        fields["segment_id"] = candidate["segment_id"]
    return sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _candidate_hints(db: Session, task: AssistantTask) -> list[ProposalData]:
    activity = source_activity(db, task)
    if activity is None:
        return []
    try:
        content = json.loads(activity.content_json or "{}")
    except (ValueError, TypeError):
        content = {}
    if not isinstance(content, dict):
        content = {}
    hints: list[ProposalData] = []
    for action in content.get("action_evidence", []) if isinstance(content.get("action_evidence"), list) else []:
        if not isinstance(action, dict) or not isinstance(action.get("action_id"), str):
            continue
        evidence = validate_action_evidence(content, action["action_id"], source_content=activity.source_content or "")
        if evidence is not None and evidence.due_at is not None:
            hints.append(
                {
                    "kind": "follow_up_task_create",
                    "action_id": evidence.action_id,
                    "evidence_quote": evidence.evidence_quote,
                    "payload": {
                        "action": evidence.action,
                        "due_date": evidence.due_at.isoformat(),
                        "owner": evidence.owner,
                    },
                }
            )
    return hints

_PRIORITY = {"opportunity_stage": 0, "opportunity_lose": 1, "opportunity_create": 2, "follow_up_task_create": 3}


def _bind_candidate(
    db: Session, task: AssistantTask, candidate: ProposalData, rejected: list[dict[str, str]],
) -> ProposalData | None:
    reasons: list[ProposalRejection] = []
    bound = validate_candidate(db, task, candidate, on_reject=reasons.append)
    kind = candidate.get("kind")
    if bound is None:
        rejected.append({
            "kind": kind if isinstance(kind, str) and kind in _PRIORITY else "unknown",
            "reason": next(iter(reasons), "schema"),
            **_rejection_trail(candidate),
        })
        return None
    return {**bound, "key": _candidate_key(bound)}

def _rejection_trail(candidate: Mapping[str, object]) -> dict[str, str]:
    """Which target and quote a dropped candidate referred to, for the action audit."""
    trail: dict[str, str] = {}
    for key, field, limit in (("target", "target_public_id", 128), ("quote", "evidence_quote", 200)):
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            trail[key] = value.strip()[:limit]
    return trail


def _take_queued_candidate(
    db: Session, task: AssistantTask, queue: list[ProposalCandidate], rejected: list[dict[str, str]],
) -> ProposalCandidate | None:
    settled = {receipt.get("proposal_key") for receipt in task.committed_json or []}
    while queue:
        candidate = queue.pop(0)
        if candidate.key in settled:
            continue
        hint = candidate.model_dump(mode="json", exclude_unset=True)
        rebound = _bind_candidate(db, task, hint, rejected)
        if rebound is None:
            continue
        if rebound["key"] != candidate.key:
            rejected.append({"kind": candidate.kind, "reason": "target",
                             **_rejection_trail(candidate.model_dump(mode="json", exclude_unset=True))})
            continue
        return candidate
    return None

def proposal_waiting(task: AssistantTask, proposal: ProposalData) -> TaskWaiting:
    kind = proposal["kind"]
    payload = proposal.get("payload") or {}
    # Lead with the server-resolved target name; a raw id is only the last resort.
    detail = payload.get("opportunity_name") or payload.get("action") or proposal.get("target_public_id") or ""
    label = _PROMPTS[kind]
    if detail:
        label = f"{str(detail)[:80]}：{label}"
    return TaskWaiting(
        type="CONFIRMATION",
        field=f"proposal:{kind}",
        question_id=f"q_prop_{task.public_id}_{task.version}",
        prompt=label,
        confirmation_payload=ProposalConfirmation.model_validate(
            {"kind": "proposal", "proposal_kind": kind, "candidate": proposal},
        ),
    )


async def readback_outcome(db: Session, task: AssistantTask, proposal: ProposalData) -> ProposalOutcome | None:
    """Only an exact CRM transaction receipt proves this frozen proposal ran."""
    kind = proposal["kind"]
    if kind not in {"opportunity_create", "opportunity_stage", "opportunity_lose"}:
        return None
    command = build_proposal_command(task, proposal)
    try:
        effect = checked_effect(db, command, kind)
    except (AssistantCRMNoEffect, ValueError):
        return None
    if effect is None:
        return None
    if kind in {"opportunity_stage", "opportunity_lose"} and (
        effect.target_public_id != proposal.get("target_public_id")
        or command.expected_version is None
        or effect.previous_version != command.expected_version
        or effect.resulting_version != command.expected_version + 1
        or (
            kind == "opportunity_stage"
            and command.expected_snapshot_id is not None
            and effect.previous_snapshot_id != command.expected_snapshot_id
        )
    ):
        return None
    if kind == "opportunity_create":
        from app.services.assistant.crm_proposal_commands import opportunity_create_receipt_outcome
        return opportunity_create_receipt_outcome(effect)
    return {"kind": kind, "public_id": effect.target_public_id}


async def offer_next_proposal(
    db: Session, task: AssistantTask, *, reporter: ProgressReporter | None = None
) -> tuple[AssistantTask, str, bool]:
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    action_name = "proposal_none"
    action_result: dict[str, object] = {}
    proposal_outcome: Literal["proposal_failed", "proposal_rejected"] | None = None
    rejected: list[dict[str, str]] = []
    saved = load_authority(task).proposal_queue
    queue = list(saved) if saved is not None else []
    started: float | None = None
    try:
        # A failed PostgreSQL read aborts its transaction. Keep the already
        # committed activity and turn claim outside the proposal savepoint.
        with db.begin_nested():
            activity = source_activity(db, task)
            if activity is None:
                raise _CommittedActivityMissing("committed customer activity is missing")
            if saved is None:
                if reporter is not None:
                    reporter.stage_start(stage("propose"))
                started = monotonic()
                hints = [*await OpportunityNominator().nominate(db, task, activity), *_candidate_hints(db, task)]
                bound_by_key: dict[str, ProposalCandidate] = {}
                for hint in hints:
                    bound = _bind_candidate(db, task, {**hint, "payload": hint.get("payload", {})}, rejected)
                    if bound is not None:
                        candidate = ProposalCandidate.model_validate(bound)
                        bound_by_key[candidate.key] = candidate
                queue = sorted(bound_by_key.values(), key=lambda candidate: _PRIORITY[candidate.kind])
            proposal = _take_queued_candidate(db, task, queue, rejected)
            if rejected:
                action_result = {"rejected": rejected}
            if proposal is None and rejected:
                # Nothing offerable is left: say so instead of reporting a normal completion.
                action_name = proposal_outcome = "proposal_rejected"
            elif saved is not None:
                action_name = "complete_after_proposals"
    except (AssistantLLMError, TimeoutError, SQLAlchemyError) as exc:
        if started is not None and reporter is not None:
            reporter.stage_failed(stage("propose"))
        if isinstance(exc, SQLAlchemyError):
            if not db.is_active or getattr(exc, "connection_invalidated", False):
                raise
            reason = "db_error"
        elif isinstance(exc, TimeoutError) or exc.code == AssistantFailureCode.UPSTREAM_TIMEOUT:
            reason = "timeout"
        else:
            reason = "llm_error"
        logger.warning("后续建议不可用: %s", reason)
        action_name = proposal_outcome = "proposal_failed"
        # Rejections found before the failure stay in the audit record.
        action_result = {"rejected": rejected} if rejected else {}
        action_result["reason"] = reason
        proposal = None
    except _CommittedActivityMissing:
        raise
    except Exception as exc:
        # The activity is already committed: any other failure is still only "no suggestions".
        if started is not None and reporter is not None:
            reporter.stage_failed(stage("propose"))
        logger.warning("后续建议不可用: internal_error (%s)", type(exc).__name__)
        action_name = proposal_outcome = "proposal_failed"
        action_result = {"rejected": rejected} if rejected else {}
        action_result["reason"] = "internal_error"
        proposal = None
    else:
        if started is not None and reporter is not None:
            if proposal_outcome == "proposal_rejected":
                reporter.stage_failed(stage("propose"))
            else:
                reporter.stage_done(stage("propose"), ms=int((monotonic() - started) * 1000))
    if proposal is None:
        unavailable = proposal_outcome is not None
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                status="COMPLETED",
                action_actor="SYSTEM",
                action_name=action_name,
                action_result=action_result,
                authority=TaskAuthority(proposal_outcome=proposal_outcome, proposal_queue=[]),
            ),
        )
        return result.task, PROPOSAL_UNAVAILABLE_TEXT if unavailable else "本次任务已完成。", False
    waiting = proposal_waiting(task, proposal.model_dump(mode="json", exclude_unset=True))
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            waiting=waiting,
            authority=TaskAuthority(proposal_queue=queue),
            action_actor="SYSTEM",
            action_name="offer_proposal",
            action_result={"field": waiting.field, "proposal_key": proposal.key, "rejected": rejected},
        ),
    )
    return result.task, waiting.prompt, True


def _proposal_form_waiting(
    spec: dict[str, Any], revision: int, errors: dict[str, str] | None = None,
    submitted: dict[str, JsonValue] | None = None,
) -> TaskWaiting:
    from app.services.agent.ui.schemas import InteractionField

    fields = []
    for field in spec["fields"]:
        key = field["key"]
        options = []
        parent = {"stage_id": "procurement_method_id", "product_module_public_ids": "product_public_id"}.get(key)
        for option in spec["options"].get(key, []):
            bound = {k: v for k, v in option.items() if k not in {"product_public_id", "procurement_method_id"}}
            if parent is not None:
                bound["depends_on_value"] = option[parent]
            options.append(bound)
        fields.append(InteractionField.model_validate({
            **field, "options": options,
            # A rejected submission comes back with what the user typed, not the frozen defaults.
            "default_value": submitted[key] if submitted and key in submitted else spec["defaults"].get(key),
            "depends_on_key": parent if options else None,
            "source_label": spec["sources"].get(key, {}).get("label"),
            "error_message": (errors or {}).get(key),
        }).model_dump(mode="json"))
    heading = f"为{spec['customer_name']}新建商机"
    notice = spec.get("option_notice")
    hint = (errors or {}).get("form") or (f"{notice}核对后提交；客户已锁定。" if notice else "核对后提交；客户已锁定。")
    return TaskWaiting(
        type="PROPOSAL_FORM", field="proposal:opportunity_create",
        question_id=f"q_form_{spec['task_public_id']}_{revision}", prompt=heading,
        form_revision=revision, form_fields=fields, hint=hint[:400],
    )


def _proposal_from_waiting(waiting: TaskWaiting) -> ProposalData:
    if waiting.type == AssistantWaitingType.CONFIRMATION and isinstance(
        waiting.confirmation_payload, ProposalConfirmation,
    ):
        return waiting.confirmation_payload.candidate.model_dump(mode="json", exclude_unset=True)
    raise ValueError("no bound proposal on the table")


def open_opportunity_proposal_form(db: Session, task: AssistantTask, waiting: TaskWaiting) -> AssistantTask:
    from app.services.assistant.opportunity_form import prepare_opportunity_form

    candidate = _proposal_from_waiting(waiting)
    spec = prepare_opportunity_form(db, task, candidate)
    return apply_task_update(db, task, TaskUpdate(
        waiting=_proposal_form_waiting(spec, 1),
        authority=TaskAuthority(proposal_form={"candidate": candidate, "spec": spec}),
        action_actor="USER", action_name="open_opportunity_form", action_result={"proposal_key": candidate["key"]},
    )).task


def validate_proposal_form_submission(
    db: Session, task: AssistantTask, waiting: TaskWaiting, *, values: dict[str, JsonValue] | None,
) -> tuple[ProposalData, AssistantTask | None]:
    from app.services.assistant.opportunity_form import OpportunityFormError, validate_opportunity_form

    form = load_authority(task).proposal_form
    if form is None or waiting.form_revision is None:
        raise ValueError("missing frozen opportunity form")
    candidate = ProposalCandidate.model_validate(form["candidate"]).model_dump(mode="json", exclude_unset=True)
    if candidate["key"] != _candidate_key(candidate) or candidate["kind"] != "opportunity_create":
        raise ValueError("invalid frozen opportunity candidate")
    if values is None:
        return candidate, None
    claimed = _proposal_claim(db, task, candidate)
    if claimed is not None:
        canonical = (claimed.result_json or {}).get("form_values")
        if not isinstance(canonical, dict):
            raise ValueError("missing claimed form values")
        return {**candidate, "form_values": canonical}, None
    spec = form["spec"]
    if not isinstance(spec, dict):
        raise ValueError("invalid frozen opportunity form")
    try:
        canonical = validate_opportunity_form(db, task, candidate, spec, values)
    except OpportunityFormError as exc:
        updated = apply_task_update(db, task, TaskUpdate(
            waiting=_proposal_form_waiting(spec, waiting.form_revision + 1, exc.field_errors, values),
            action_actor="USER", action_name="reject_opportunity_form",
            action_result={"proposal_key": candidate["key"], "fields": list(exc.field_errors)},
        )).task
        return candidate, updated
    return {**candidate, "form_values": canonical}, None


def _proposal_claim(db: Session, task: AssistantTask, proposal: ProposalData) -> AssistantAction | None:
    rows = db.query(AssistantAction).filter(
        AssistantAction.task_id == task.id, AssistantAction.team_id == task.team_id,
        AssistantAction.action == "proposal_command_claim",
    ).all()
    return next((row for row in rows if (row.result_json or {}).get("proposal_key") == proposal["key"]), None)


def has_proposal_claim(db: Session, task: AssistantTask, waiting: TaskWaiting) -> bool:
    """A previously claimed confirmation can only be settled by readback."""
    return _proposal_claim(db, task, _proposal_from_waiting(waiting)) is not None

def has_unresolved_proposal_claim(db: Session, task: AssistantTask) -> bool:
    if task.waiting_field not in {
        "proposal:opportunity_create",
        "proposal:opportunity_stage",
        "proposal:opportunity_lose",
    }:
        return False
    rows = db.query(AssistantAction.result_json).filter_by(
        task_id=task.id, team_id=task.team_id, action="proposal_command_claim",
    ).all()
    return any((result or {}).get("status") in {"CLAIMED", "UNKNOWN"} for (result,) in rows)


def _proposal_receipt(
    task: AssistantTask, proposal: ProposalData, outcome: Mapping[str, object],
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "kind": proposal["kind"], "public_id": outcome["public_id"],
        "proposal_key": proposal["key"], "customer_id": proposal["customer_id"],
    }
    customer_public_id = load_authority(task).customer_public_id
    if customer_public_id:
        receipt["customer_public_id"] = customer_public_id
    payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
    form_values = proposal.get("form_values") if isinstance(proposal.get("form_values"), dict) else {}
    name = {
        "opportunity_stage": payload.get("opportunity_name"),
        "opportunity_lose": payload.get("opportunity_name"),
        "opportunity_create": form_values.get("opportunity_name"),
        "follow_up_task_create": payload.get("action"),
    }.get(proposal["kind"])
    if isinstance(name, str) and name.strip():
        name = name.strip()[:200]
        receipt["name"] = name
    else:
        name = None
    if proposal["kind"] == "opportunity_stage" and name and payload.get("stage_name"):
        current_stage = payload.get("current_stage_name") or "未开始"
        receipt["detail"] = f"{name}：{current_stage} → {payload['stage_name']}"
    elif proposal["kind"] == "opportunity_lose" and name and payload.get("loss_reason"):
        receipt["detail"] = f"{name}：输单原因：{payload['loss_reason']}"
    elif proposal["kind"] == "follow_up_task_create" and name:
        receipt["detail"] = name
    if proposal["kind"] == "opportunity_create" and outcome.get("approval_phase") == "pending_review":
        receipt.update(approval_phase="pending_review", approval_id=outcome["approval_id"])
    return receipt


async def _advance_settled_proposal(
    db: Session, task: AssistantTask, message: str, *, reporter: ProgressReporter | None = None,
) -> tuple[AssistantTask, str, bool]:
    if load_authority(task).proposal_queue is None:
        # Old waits had no frozen queue. Never nominate again on this decision.
        task = apply_task_update(db, task, TaskUpdate(
            status="COMPLETED", action_actor="SYSTEM", action_name="complete_legacy_proposals",
        )).task
        return task, message, False
    updated, prompt, offered = await offer_next_proposal(db, task, reporter=reporter)
    return updated, prompt if offered or load_authority(updated).proposal_outcome else message, False


async def adjudicate_proposal_claim(
    db: Session, claim: AssistantAction, *, operator_id: int, reason: str,
) -> None:
    """Settle only the original, provable effect. The caller owns the transaction."""
    correlation = claim.result_json or {}
    claim_status = correlation.get("status")
    if claim_status not in {"CLAIMED", "UNKNOWN"}:
        raise TaskStateConflictError("该命令已结算，不可裁决。")
    task = db.query(AssistantTask).filter_by(id=claim.task_id, team_id=claim.team_id).one_or_none()
    if task is None or task.status != AssistantTaskStatus.ACTIVE or task.active_turn_id is not None:
        raise TaskStateConflictError("当前任务不能裁决此命令。")
    waiting = load_waiting(task)
    if waiting is None or not waiting.action_id or waiting.field != task.waiting_field:
        raise TaskStateConflictError("缺少当前确认动作。")
    is_form = waiting.type == AssistantWaitingType.PROPOSAL_FORM
    if is_form:
        form = load_authority(task).proposal_form
        canonical = correlation.get("form_values")
        if form is None or waiting.form_revision is None or not isinstance(canonical, dict):
            raise TaskStateConflictError("缺少原命令的冻结表单。")
        proposal = ProposalCandidate.model_validate(form.get("candidate")).model_dump(mode="json", exclude_unset=True)
        proposal["form_values"] = canonical
    else:
        proposal = _proposal_from_waiting(waiting)
    kind = proposal["kind"]
    if (
        kind not in {"opportunity_create", "opportunity_stage", "opportunity_lose"}
        or (is_form and kind != "opportunity_create")
        or waiting.field != f"proposal:{kind}"
        or proposal["key"] != _candidate_key(proposal)
        or correlation.get("proposal_key") != proposal["key"]
        or any(item.get("proposal_key") == proposal["key"] for item in task.committed_json or [])
    ):
        raise TaskStateConflictError("待确认提议已变化，不能裁决此命令。")
    command = build_proposal_command(task, proposal)
    if correlation.get("command_id") != command.command_id or correlation.get("fingerprint") != command.fingerprint:
        raise TaskStateConflictError("命令与当前冻结提议不匹配。")
    proven = await readback_outcome(db, task, proposal)
    if proven is None:
        raise TaskStateConflictError("缺少可归因的目标提交回执，结果仍待核对。")

    resolved = apply_task_update(db, task, TaskUpdate(
        require_no_active_turn=True,
        clear_waiting=True,
        clear_proposal_form=is_form,
        append_committed=[_proposal_receipt(task, proposal, proven)],
        action_actor="SYSTEM",
        action_name="reconcile_proposal_claim",
        action_result={"proposal_key": proposal["key"], "public_id": proven["public_id"],
                       "reconciled": True, "adjudicated_by": operator_id},
    )).task
    changed = db.execute(sql_update(AssistantAction).where(
        AssistantAction.id == claim.id,
        AssistantAction.team_id == task.team_id,
        AssistantAction.task_id == task.id,
        AssistantAction.action == "proposal_command_claim",
        AssistantAction.result_json["status"].as_string() == claim_status,
        AssistantAction.result_json["proposal_key"].as_string() == proposal["key"],
        AssistantAction.result_json["command_id"].as_string() == command.command_id,
        AssistantAction.result_json["fingerprint"].as_string() == command.fingerprint,
    ).values(result_json={**correlation, "status": "RECONCILED", "public_id": proven["public_id"],
                         "adjudicated_by": operator_id, "adjudication_reason": reason})
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise TaskStateConflictError("待核对命令已变化。")
    await _advance_settled_proposal(db, resolved, "CRM 命令已按目标系统实际结果核对完成。")


async def settle_proposal(
    db: Session,
    task: AssistantTask,
    *,
    accepted: bool,
    executor: ProposalExecutor | None = None,
    form_proposal: ProposalData | None = None,
    reporter: ProgressReporter | None = None,
) -> tuple[AssistantTask, str, bool]:
    """Settle exactly one authorized CRM effect, then advance the frozen queue."""
    from app.services.assistant.turns import AssistantUnknownCommitResultError, assert_owned_execution_lease

    waiting = load_waiting(task)
    if waiting is None or waiting.field != task.waiting_field:
        raise ValueError("no bound proposal on the table")
    if form_proposal is not None:
        if waiting.type != AssistantWaitingType.PROPOSAL_FORM or (accepted and "form_values" not in form_proposal):
            raise ValueError("no bound proposal form on the table")
        proposal = form_proposal
    else:
        proposal = _proposal_from_waiting(waiting)
    if proposal["key"] != _candidate_key(proposal):
        raise ValueError("proposal identity changed")
    if any(item.get("proposal_key") == proposal["key"] for item in task.committed_json or []):
        raise ValueError("proposal already settled")
    command = (
        build_proposal_command(task, proposal)
        if proposal["kind"] in {"opportunity_create", "opportunity_stage", "opportunity_lose"}
        else None
    )
    if command is not None:
        claimed = _proposal_claim(db, task, proposal)
        if claimed is not None:
            if not accepted:
                raise AssistantUnknownCommitResultError("商机提交结果待核对，暂不能取消。")
            correlation = claimed.result_json or {}
            proven = (
                await readback_outcome(db, task, proposal)
                if (
                    correlation.get("command_id") == command.command_id
                    and correlation.get("fingerprint") == command.fingerprint
                )
                else None
            )
            if proven is None:
                _publish_unknown_claim(db, task, proposal)
                raise AssistantUnknownCommitResultError(
                    "结果待核对，请先在客户活动里确认是否已写入，再继续下一笔"
                )
            assert_owned_execution_lease(db, task)
            _mark_claim_status(db, claimed, "RECONCILED", public_id=proven["public_id"])
            result = apply_task_update(
                db, task,
                TaskUpdate(
                    clear_waiting=True,
                    clear_proposal_form=form_proposal is not None,
                    append_committed=[_proposal_receipt(task, proposal, proven)],
                    action_actor="SYSTEM", action_name="reconcile_proposal_claim",
                    action_result={"kind": proposal["kind"], "proposal_key": proposal["key"],
                                   "public_id": proven["public_id"], "reconciled": True},
                ),
            )
            return await _advance_settled_proposal(
                db, result.task, "CRM 命令已按目标系统实际结果核对完成。", reporter=reporter,
            )
    if accepted:
        if executor is None:
            raise RuntimeError("CRM proposal executor is required")
        claim_row: AssistantAction | None = None
        if command is not None:
            assert_owned_execution_lease(db, task)
            claimed_transition = apply_task_update(
                db,
                task,
                TaskUpdate(
                    action_actor="SYSTEM",
                    action_name="proposal_command_claim",
                    action_input={"kind": proposal["kind"]},
                    action_result={
                        "proposal_key": proposal["key"],
                        "status": "CLAIMED",
                        "command_id": command.command_id,
                        "fingerprint": command.fingerprint,
                        **({"form_values": proposal["form_values"]} if "form_values" in proposal else {}),
                    },
                ),
            )
            task = claimed_transition.task
            claim_row = claimed_transition.action
            try:
                db.commit()
            except SQLAlchemyError as exc:
                db.rollback()
                persisted = _proposal_claim(db, task, proposal)
                if persisted is None:
                    # The claim did not commit, and execution did not start.
                    raise
                _publish_unknown_claim(db, task, proposal)

                raise AssistantUnknownCommitResultError("商机提交结果待核对。") from exc
            # The claim commit releases the earlier turn lock. Reacquire it
            # before invoking CRM, which can commit its own transaction.
            assert_owned_execution_lease(db, task)
        try:
            if proposal["kind"] not in _PRIORITY:
                # A retired kind cannot run any more: settle it as the stale proposal it is.
                raise AssistantCRMNoEffect("该提议类型已下线，未执行")
            outcome = await executor(db, task, proposal)
        except AssistantCRMNoEffect as exc:
            db.rollback()
            if command is not None:
                assert claim_row is not None
                assert_owned_execution_lease(db, task)
                _mark_claim_status(db, claim_row, "NO_EFFECT")
            result = apply_task_update(db, task, TaskUpdate(
                clear_waiting=True, clear_proposal_form=form_proposal is not None,
                append_committed=[{"kind": f"refused:{proposal['kind']}", "proposal_key": proposal["key"]}],
                action_actor="SYSTEM", action_name="reject_stale_proposal",
                action_result={"proposal_key": proposal["key"], "reason": str(exc)},
            ))
            return await _advance_settled_proposal(db, result.task, str(exc), reporter=reporter)
        except SQLAlchemyError as exc:
            if command is None:
                raise
            _publish_unknown_claim(db, task, proposal)
            raise AssistantUnknownCommitResultError("商机提交结果待核对。") from exc
        public_id = outcome.get("public_id") if isinstance(outcome, dict) else None
        if (
            not isinstance(public_id, str)
            or not public_id.strip()
            or outcome.get("success") is False
            or outcome.get("status", "EXECUTED") not in {"EXECUTED", "COMPLETED", "SUCCESS"}
            or outcome.get("kind", proposal["kind"]) != proposal["kind"]
        ):
            raise RuntimeError("CRM proposal executor did not confirm a completed command")
        if command is not None:
            proven = await readback_outcome(db, task, proposal)
            if proven is None or proven["public_id"] != public_id:
                _publish_unknown_claim(db, task, proposal)

                raise AssistantUnknownCommitResultError(
                    "结果待核对，请先在客户活动里确认是否已写入，再继续下一笔"
                )
            assert claim_row is not None
            assert_owned_execution_lease(db, task)
            _mark_claim_status(db, claim_row, "SUCCEEDED", public_id=proven["public_id"])
            committed = _proposal_receipt(task, proposal, proven)
        else:
            committed = _proposal_receipt(task, proposal, outcome)
    else:
        committed = {"kind": f"refused:{proposal['kind']}", "proposal_key": proposal["key"]}
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            clear_waiting=True,
            clear_proposal_form=form_proposal is not None,
            append_committed=[committed],
            action_actor="USER",
            action_name="accept_proposal" if accepted else "refuse_proposal",
            action_result={"kind": proposal["kind"], "proposal_key": proposal["key"]},
        ),
    )
    return await _advance_settled_proposal(
        db, result.task, "已执行这条 CRM 提议。" if accepted else "已拒绝这条 CRM 提议。", reporter=reporter,
    )


def _mark_claim_status(db: Session, claim: AssistantAction, status: str, *, public_id: str | None = None) -> None:
    """Stage a claim result in the caller's transaction."""

    result = dict(claim.result_json or {})
    result["status"] = status
    if public_id is not None:
        result["public_id"] = public_id
    claim.result_json = result
    db.flush()


def _publish_unknown_claim(db: Session, task: AssistantTask, proposal: ProposalData) -> None:
    from app.services.assistant.turns import AssistantUnknownCommitResultError, assert_owned_execution_lease

    # The preceding CRM transaction may contain unproven, uncommitted writes.
    # Never publish UNKNOWN by committing that transaction.
    db.rollback()
    assert_owned_execution_lease(db, task)
    claim = _proposal_claim(db, task, proposal)
    if claim is None:
        raise AssistantUnknownCommitResultError("商机提交结果待核对。")
    if (claim.result_json or {}).get("status") in {"CLAIMED", "UNKNOWN"}:
        _mark_claim_status(db, claim, "UNKNOWN")
        db.commit()


def list_unresolved_command_claims(
    db: Session,
    *,
    team_id: int,
    owner_user_id: int | None = None,
    include_claimed: bool = False,
) -> list[dict[str, object]]:
    """TRD §7.1/§8: owner sees own claims; team operators see team-scope including CLAIMED."""

    from app.models.assistant import AssistantTask

    statuses = {"UNKNOWN", "CLAIMED"} if include_claimed else {"UNKNOWN"}
    query = (
        db.query(AssistantAction)
        .join(AssistantTask, AssistantTask.id == AssistantAction.task_id)
        .filter(
            AssistantAction.team_id == team_id,
            AssistantAction.action == "proposal_command_claim",
        )
    )
    if owner_user_id is not None:
        query = query.filter(AssistantTask.user_id == owner_user_id)

    unresolved: list[dict[str, object]] = []
    for row in query.all():
        result = row.result_json or {}
        if result.get("status") not in statuses:
            continue
        task = db.get(AssistantTask, row.task_id)
        unresolved.append(
            {
                "proposal_key": result.get("proposal_key"),
                "kind": result.get("kind") or (row.input_json or {}).get("kind"),
                "status": result["status"],
                "task_public_id": task.public_id if task is not None else None,
                "action_public_id": row.public_id,
                "created_time": row.created_time.isoformat() if row.created_time else None,
                "last_checked_at": row.updated_time.isoformat() if getattr(row, "updated_time", None) else None,
            }
        )
    return unresolved
