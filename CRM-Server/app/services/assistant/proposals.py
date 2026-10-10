"""Offer evidence-bound, individually confirmed CRM changes after activity commit."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING

from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus, AssistantWaitingType
from app.services.assistant.contracts import TaskWaiting
from app.services.assistant.crm_proposal_commands import source_activity, validate_candidate
from app.services.assistant.task_state import TaskUpdate, apply_task_update

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.orm import Session

# ruff: noqa: RUF001

_PROMPTS = {
    "opportunity_create": "根据这次活动，为客户创建商机吗？",
    "opportunity_stage": "根据这次活动，推进这条商机到下一阶段吗？",
    "follow_up_task": "根据这次活动，把这条跟进任务标记完成吗？",
    "follow_up_task_create": "根据这次活动，为你建立这项跟进任务吗？",
    "customer_fact": "将这条已确认的信息写入客户档案吗？",
}


def _candidate_key(candidate: dict) -> str:
    fields = {field: candidate.get(field) for field in (
        "kind", "target_public_id", "payload", "evidence_quote", "activity_id",
        "customer_id", "source_revision", "prior_status", "task_owner_id", "prior_stage_snapshot_id",
        "prior_version", "prior_fact_version", "task_hash",
    )}
    return sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _candidate_hints(db: Session, task: AssistantTask) -> list[dict]:
    activity = source_activity(db, task)
    if activity is None:
        return []
    authority = task.authority_json or {}
    hints = authority.get("proposal_candidates")
    if not isinstance(hints, list):
        hints = []
    try:
        content = json.loads(activity.content_json or "{}")
    except (ValueError, TypeError):
        content = {}
    if not isinstance(content, dict):
        content = {}
    for action in content.get("action_items", []) if isinstance(content.get("action_items"), list) else []:
        if isinstance(action, dict) and isinstance(action.get("action"), str):
            hints.append({"kind": "follow_up_task_create", "evidence_quote": action["action"],
                          "payload": {"action": action["action"], "due_date": action.get("due_date"),
                                      "owner": action.get("owner")}})
    return [candidate for candidate in hints if isinstance(candidate, dict)]


def next_proposal(db: Session, task: AssistantTask) -> dict | None:
    """Derive actual distinct unsatisfied objects; no kind-level carousel."""
    if not any(item.get("kind") == "customer_activity" for item in task.committed_json or []):
        return None
    settled = {item.get("proposal_key") for item in task.committed_json or [] if item.get("proposal_key")}
    seen = set(settled)
    for candidate in _candidate_hints(db, task):
        bound = validate_candidate(db, task, candidate)
        if bound is None:
            continue
        key = _candidate_key(bound)
        if key in seen:
            continue
        seen.add(key)
        return {**bound, "key": key}
    return None


def proposal_waiting(task: AssistantTask, proposal: dict) -> TaskWaiting:
    kind = proposal["kind"]
    label = _PROMPTS[kind]
    payload = proposal.get("payload", {})
    detail = proposal.get("target_public_id") or payload.get("content") or payload.get("opportunity_name") or ""
    if detail:
        label = f"{str(detail)[:80]}：{label}"
    return TaskWaiting(
        type=AssistantWaitingType.CONFIRMATION,
        field=f"proposal:{kind}",
        question_id=f"q_prop_{task.public_id}_{task.version}",
        prompt=label,
        confirmation_payload=proposal,
    )


async def readback_outcome(db: Session, task: AssistantTask, proposal: dict) -> dict | None:
    """Prove a claimed CRM command's outcome from target-CRM state, never by re-running it."""

    kind = proposal.get("kind")
    if kind == "opportunity_stage":
        from app.models.opportunity import Opportunity

        row = db.query(Opportunity).filter(
            Opportunity.public_id == proposal.get("target_public_id"),
            Opportunity.team_id == task.team_id,
        ).one_or_none()
        if row is None:
            return None
        prior_snapshot = proposal.get("prior_stage_snapshot_id")
        if (row.current_stage_snapshot_id is not None and prior_snapshot is not None
                and int(row.current_stage_snapshot_id) != int(prior_snapshot)):
            return {"kind": "opportunity_stage", "public_id": row.public_id}
        return None
    if kind == "opportunity_create":
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity

        activity = source_activity(db, task)
        if activity is None:
            return None
        row = db.query(Opportunity).filter(
            Opportunity.team_id == task.team_id, Opportunity.customer_id == activity.customer_id,
            Opportunity.opportunity_name == (proposal.get("payload") or {}).get("opportunity_name"),
        ).one_or_none()
        if row is not None:
            return {"kind": "opportunity_create", "public_id": row.public_id}
        return None
    return None


async def offer_next_proposal(db: Session, task: AssistantTask) -> tuple[AssistantTask, str, bool]:
    if source_activity(db, task) is None:
        raise ValueError("committed customer activity is missing")
    proposal = next_proposal(db, task)
    if proposal is None:
        result = apply_task_update(db, task, TaskUpdate(
            status=AssistantTaskStatus.COMPLETED,
            action_actor="SYSTEM", action_name="complete_after_proposals",
            action_result={"reason": "no_more_proposals"},
        ))
        return result.task, "本次任务已完成。", False
    waiting = proposal_waiting(task, proposal)
    result = apply_task_update(db, task, TaskUpdate(
        waiting=waiting, action_actor="SYSTEM", action_name="offer_proposal",
        action_result={"field": waiting.field, "proposal_key": proposal["key"]},
    ))
    return result.task, waiting.prompt, True


async def settle_proposal(
    db: Session,
    task: AssistantTask,
    *,
    accepted: bool,
    executor: Callable[[Session, AssistantTask, dict], Awaitable[dict]] | None = None,
) -> tuple[AssistantTask, str, bool]:
    """Record this decision only; a separate durable turn must offer what follows."""
    waiting_field = task.waiting_field or ""
    payload = (task.waiting_json or {}).get("payload")
    proposal = payload.get("confirmation_payload") if isinstance(payload, dict) else None
    if not waiting_field.startswith("proposal:") or not isinstance(proposal, dict):
        raise ValueError("no bound proposal on the table")
    if proposal.get("kind") != waiting_field.split(":", 1)[1] or proposal.get("key") != _candidate_key(proposal):
        raise ValueError("proposal identity changed")
    if any(item.get("proposal_key") == proposal["key"] for item in task.committed_json or []):
        raise ValueError("proposal already settled")
    if proposal["kind"] in {"opportunity_create", "opportunity_stage"}:
        prior_claims = db.query(AssistantAction).filter(
            AssistantAction.task_id == task.id, AssistantAction.team_id == task.team_id,
            AssistantAction.action == "proposal_command_claim",
        ).all()
        claimed = next((row for row in prior_claims if row.result_json.get("proposal_key") == proposal["key"]), None)
        if claimed is not None:
            proven = await readback_outcome(db, task, proposal)
            if proven is None:
                _mark_claim_status(db, claimed, "UNKNOWN")
                from app.services.assistant.turns import AssistantUnknownCommitResultError

                raise AssistantUnknownCommitResultError(
                    "CRM 命令结果待核对（UNKNOWN_COMMIT_RESULT）；请人工对账后再确认下一笔"
                )
            _mark_claim_status(db, claimed, "RECONCILED", public_id=proven["public_id"])
            result = apply_task_update(db, task, TaskUpdate(
                clear_waiting=True,
                append_committed=[{"kind": proposal["kind"], "public_id": proven["public_id"],
                                   "proposal_key": proposal["key"]}],
                action_actor="SYSTEM", action_name="reconcile_proposal_claim",
                action_result={"kind": proposal["kind"], "proposal_key": proposal["key"],
                               "public_id": proven["public_id"], "reconciled": True},
            ))
            return result.task, "CRM 命令已按目标系统实际结果核对完成。", True
    if accepted:
        if executor is None:
            raise RuntimeError("CRM proposal executor is required")
        if proposal["kind"] in {"opportunity_create", "opportunity_stage"}:
            from app.services.assistant.turns import assert_owned_execution_lease

            assert_owned_execution_lease(db, task)
            claimed = apply_task_update(db, task, TaskUpdate(
                action_actor="SYSTEM", action_name="proposal_command_claim",
                action_input={"kind": proposal["kind"]},
                action_result={"proposal_key": proposal["key"], "status": "CLAIMED"},
            ))
            task = claimed.task
            db.commit()
        outcome = await executor(db, task, proposal)
        if (not isinstance(outcome, dict) or not isinstance(outcome.get("public_id"), str)
                or not outcome["public_id"].strip() or outcome.get("success") is False
                or outcome.get("status", "EXECUTED") not in {"EXECUTED", "COMPLETED", "SUCCESS"}
                or outcome.get("kind", proposal["kind"]) != proposal["kind"]):
            raise RuntimeError("CRM proposal executor did not confirm a completed command")
        if proposal["kind"] in {"opportunity_create", "opportunity_stage"}:
            claim_rows = db.query(AssistantAction).filter(
                AssistantAction.task_id == task.id, AssistantAction.team_id == task.team_id,
                AssistantAction.action == "proposal_command_claim",
            ).all()
            claim_row = next(
                (row for row in claim_rows if (row.result_json or {}).get("proposal_key") == proposal["key"]),
                None,
            )
            if claim_row is not None:
                _mark_claim_status(db, claim_row, "SUCCEEDED", public_id=outcome["public_id"])
        committed = {"kind": proposal["kind"], "public_id": outcome["public_id"],
                     "proposal_key": proposal["key"]}
    else:
        committed = {"kind": f"refused:{proposal['kind']}", "proposal_key": proposal["key"]}
    result = apply_task_update(db, task, TaskUpdate(
        clear_waiting=True, append_committed=[committed], action_actor="USER",
        action_name="accept_proposal" if accepted else "refuse_proposal",
        action_result={"kind": proposal["kind"], "proposal_key": proposal["key"]},
    ))
    return result.task, "已执行这条 CRM 提议。" if accepted else "已拒绝这条 CRM 提议。", True

def _mark_claim_status(db: Session, claim: AssistantAction, status: str, *, public_id: str | None = None) -> None:
    """Track one CRM command claim's lifecycle for operations queries.

    UNKNOWN is committed independently: it must survive the caller's rollback
    because it is the durable signal for manual reconciliation.
    """

    result = dict(claim.result_json or {})
    result["status"] = status
    if public_id is not None:
        result["public_id"] = public_id
    claim.result_json = result
    if status == "UNKNOWN":
        db.commit()
    else:
        db.flush()


def list_unresolved_command_claims(db: Session, *, team_id: int) -> list[dict[str, object]]:
    """TRD §8: surface UNKNOWN CRM command claims for manual reconciliation."""

    from app.models.assistant import AssistantTask


    rows = db.query(AssistantAction).join(AssistantTask, AssistantTask.id == AssistantAction.task_id).filter(
        AssistantAction.team_id == team_id,
        AssistantAction.action == "proposal_command_claim",
    ).all()
    unresolved: list[dict[str, object]] = []
    for row in rows:
        result = row.result_json or {}
        if result.get("status") not in {"UNKNOWN"}:
            continue
        task = db.get(AssistantTask, row.task_id)
        unresolved.append({
            "proposal_key": result.get("proposal_key"),
            "kind": result.get("kind") or (row.input_json or {}).get("kind"),
            "status": result["status"],
            "task_public_id": task.public_id if task is not None else None,
            "action_public_id": row.public_id,
            "created_time": row.created_time.isoformat() if row.created_time else None,
        })
    return unresolved
