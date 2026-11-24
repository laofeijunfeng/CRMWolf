"""Server-owned disposition of open follow-up tasks after a follow-up write.

The model does not nominate relevance or choose a task action. The task row
holds the frozen batch; the card is only a projection.
"""
# ruff: noqa: RUF001

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from json import dumps
from time import monotonic
from typing import TYPE_CHECKING

from sqlalchemy import Table, or_, true
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.assistant import AssistantTask, AssistantWaitingType
from app.models.assistant_open_follow_up_suppression import AssistantOpenFollowUpSuppression
from app.models.assistant_turn import AssistantTurn
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus
from app.services.assistant.activity_channel import FOLLOW_UP_KINDS
from app.services.assistant.contracts import TaskWaiting
from app.services.assistant.crm_proposal_commands import source_activity
from app.services.assistant.events import stage
from app.services.assistant.task_state import TaskUpdate, apply_task_update, load_authority, load_waiting
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session
    from sqlalchemy.sql.dml import Insert

    from app.services.assistant.events import ProgressReporter

logger = logging.getLogger(__name__)


MAX_CANDIDATES = 100
DEFAULT_VISIBLE_CANDIDATES = 10
GENERIC_FRAGMENTS = frozenset({
    "跟进客户",
    "联系客户",
    "客户跟进",
    "跟进一下",
    "继续跟进",
    "客户沟通",
})
_STALE = ("关联已失效", "跟进内容已变化，任务未改动", "RELATION_STALE")
_HANDLED = ("已被处理", "任务已不是未完成状态", "ALREADY_HANDLED")
_UNKNOWN = ("结果待核对", "请在客户追踪页核对是否已完成", "UNKNOWN_COMMIT_RESULT")


@dataclass(frozen=True)
class DispositionOutcome:
    task: AssistantTask
    message: str
    start_followup: bool


def public_disposition(task: AssistantTask) -> dict[str, object] | None:
    """Read-only card payload. Server fields such as owner ids stay in authority."""

    batch = _batch(task)
    if batch is None:
        return None
    items = batch.get("items")
    if not isinstance(items, list):
        return None
    activity_id = _accepted_activity_id(task, batch)
    settling = isinstance(batch.get("settlement"), dict) and batch.get("status") == "ACTIVE"
    projected: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        disposition = item.get("disposition")
        state = "waiting" if disposition in (None, "attempting") else str(disposition)
        projected.append({
            "item_id": item.get("item_id"),
            "task_public_id": item.get("task_public_id")
            if isinstance(item.get("task_public_id"), str) and item["task_public_id"].strip() else None,
            "title": item.get("title"),
            "owner_line": item.get("owner_line"),
            "related": bool(item.get("related")),
            "evidence_quote": item.get("evidence_quote"),
            "evidence_reason": item.get("evidence_reason"),
            "state": state,
            "result_title": item.get("result_title"),
            "result_message": item.get("result_message"),
            "failure_code": item.get("failure_code"),
        })
    return {
        "batch_id": _public_batch_id(task, batch, activity_id),
        "activity_public_id": activity_id,
        "status": batch.get("status"),
        "customer_name": batch.get("customer_name") or "",
        "customer_public_id": load_authority(task).customer_public_id,
        "activity_kind_label": batch.get("activity_kind_label") or "",
        "total": len(projected),
        "current_index": None,
        "visible_count": min(DEFAULT_VISIBLE_CANDIDATES, len(projected)),
        "settling": settling,
        "suppression_status": batch.get("suppression_status"),
        "items": projected,
    }


def disposition_choice_ids(task: AssistantTask) -> tuple[str, ...]:
    """Derive issued bulk choices from authority, including old scalar waits."""
    batch = _batch(task)
    if batch is None or batch.get("status") != "ACTIVE" or batch.get("settlement") is not None:
        return ()
    return tuple(str(item["item_id"]) for item in _pending_items(batch))


def _pending_items(batch: dict[str, object]) -> list[dict[str, object]]:
    items = batch.get("items", [])
    if not isinstance(items, list):
        raise TypeError("invalid open follow-up batch items")
    return [
        item for item in items
        if isinstance(item, dict) and item.get("disposition") is None
    ]


def _settlement_items(batch: dict[str, object]) -> list[dict[str, object]]:
    items = batch["items"]
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise TypeError("invalid open follow-up settlement items")
    return items


def _accepted_activity_id(task: AssistantTask, batch: dict[str, object]) -> str | None:
    committed_id = next(
        (
            item.get("public_id")
            for item in reversed(task.committed_json or [])
            if isinstance(item, dict) and item.get("kind") == "customer_activity"
        ),
        None,
    )
    if not isinstance(committed_id, str) or not committed_id.strip():
        return None
    authority_id = (task.authority_json or {}).get("activity_public_id")
    if authority_id is not None and str(authority_id) != committed_id:
        return None
    # source_activity resolves the accepted receipt's string ID to CustomerActivity.id.
    activity_id = batch.get("activity_id")
    if not isinstance(activity_id, (int, str)) or isinstance(activity_id, bool) or str(activity_id) != committed_id:
        return None
    return committed_id


def _public_batch_id(task: AssistantTask, batch: dict[str, object], activity_id: str | None) -> str | None:
    batch_id = batch.get("disposition_batch_id")
    if isinstance(batch_id, str) and batch_id.strip():
        return batch_id
    # Old snapshots have no minted identity. Only a complete frozen fingerprint
    # can relate them; never allocate or persist an identity while reading.
    revision = batch.get("activity_revision")
    source_hash = batch.get("source_sha256")
    if (
        not isinstance(task.public_id, str) or not task.public_id.strip()
        or activity_id is None
        or not isinstance(revision, int) or isinstance(revision, bool) or revision < 1
        or not isinstance(source_hash, str) or len(source_hash) != 64
        or any(char not in "0123456789abcdef" for char in source_hash)
    ):
        return None
    items = batch.get("items")
    if not isinstance(items, list) or not items:
        return None
    identities: list[tuple[str, str]] = []
    item_ids: set[str] = set()
    task_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            return None
        item_id = item.get("item_id")
        task_id = item.get("task_public_id")
        if (
            not isinstance(item_id, str) or not item_id.strip() or item_id in item_ids
            or not isinstance(task_id, str) or not task_id.strip() or task_id in task_ids
        ):
            return None
        identities.append((item_id, task_id))
        item_ids.add(item_id)
        task_ids.add(task_id)
    fingerprint = dumps([task.public_id, activity_id, revision, source_hash, sorted(identities)], separators=(",", ":"))
    return f"afb_legacy_{sha256(fingerprint.encode()).hexdigest()[:32]}"


def relate_title(title: str, source: str) -> tuple[str, str, str] | None:
    """Return phrase, exact source quote, and reason when the title is explicitly in the source."""

    cleaned = title.strip()
    if len(cleaned) < 4 or not source:
        return None
    for length in range(len(cleaned), 3, -1):
        for start in range(0, len(cleaned) - length + 1):
            phrase = cleaned[start:start + length]
            if phrase in GENERIC_FRAGMENTS or phrase not in source:
                continue
            quote = _quote(source, phrase)
            if phrase not in quote or quote not in source:
                continue
            reason = f"本次跟进与任务均明确提到“{phrase}”，且属于同一客户。"
            return phrase, quote, reason
    return None


async def advance_open_follow_up(
    db: Session, task: AssistantTask, *, reporter: ProgressReporter | None = None
) -> DispositionOutcome | None:
    """Offer the frozen batch, or return None so the existing proposal chain continues."""

    batch = _batch(task)
    if batch is not None and batch.get("status") in {"DONE", "OVERFLOW", "QUERY_FAILED"}:
        return None
    if batch is not None and batch.get("status") == "ACTIVE":
        if batch.get("settlement") is not None:
            return DispositionOutcome(task, "历史跟进任务结果待核对", False)
        return refresh_open_follow_up_waiting(db, task)
    activity = source_activity(db, task)
    if activity is None or activity.activity_kind not in FOLLOW_UP_KINDS:
        return None
    try:
        customer_id = activity.customer_id
        if isinstance(customer_id, int) and _is_suppressed(db, task, customer_id):
            return None
        if reporter is not None:
            reporter.stage_start(stage("judge"))
        started = monotonic()
        built = _build_batch(db, task, activity)
    except (PermissionError, SQLAlchemyError):
        return _record_terminal(
            db,
            task,
            {
                "status": "QUERY_FAILED",
                "disposition_batch_id": generate_public_id("afb"),
                "activity_id": activity.id,
                "customer_name": "",
                "activity_kind_label": "",
                "items": [],
            },
            "历史任务暂时查不到，任务未改动",
            start_followup=False,
        )
    if reporter is not None:
        reporter.stage_done(stage("judge"), ms=int((monotonic() - started) * 1000))
    if built is None:
        return _record_terminal(
            db,
            task,
            {
                "status": "OVERFLOW",
                "disposition_batch_id": generate_public_id("afb"),
                "activity_id": activity.id,
                "activity_revision": activity.activity_revision,
                "source_sha256": _source_hash(activity.source_content or ""),
                "customer_name": _customer_name(db, task, activity.customer_id),
                "activity_kind_label": _kind_label(activity.activity_kind),
                "items": [],
            },
            "未完成任务超过 100 条，请到任务列表处理",
            start_followup=True,
        )
    if not built["items"]:
        built["status"] = "DONE"
        _save_batch(db, task, built, waiting=None, action_name="skip_open_follow_up_batch")
        return None
    waiting = _waiting_for(task, built)
    result = _save_batch(db, task, built, waiting=waiting, action_name="offer_open_follow_up_batch")
    return DispositionOutcome(result, waiting.prompt, False)


async def settle_open_follow_up(
    db: Session, task: AssistantTask, *, choices: list[str], suppress_week: bool = False,
) -> DispositionOutcome:
    """Settle the accepted selection, committing each CRM effect with its row receipt."""

    raw = _batch(task)
    if (
        raw is None or raw.get("status") != "ACTIVE"
        or task.waiting_type != AssistantWaitingType.FOLLOW_UP_DISPOSITION
    ):
        raise ValueError("没有可处理的历史跟进任务")
    if (
        not isinstance(choices, list) or len(choices) > MAX_CANDIDATES
        or any(not isinstance(choice, str) or not 1 <= len(choice) <= 64 for choice in choices)
        or len(set(choices)) != len(choices) or not isinstance(suppress_week, bool)
    ):
        raise ValueError("请选择这张卡上的历史任务")

    batch = deepcopy(raw)
    selected = set(choices)
    turn_id = task.active_turn_id
    submission = {"choices": sorted(selected), "suppress_week": suppress_week, "turn_id": turn_id}
    frozen = batch.get("settlement")
    waiting = load_waiting(task)
    if frozen is None:
        issued = disposition_choice_ids(task)
        if not issued or not selected.issubset(issued):
            raise ValueError("请选择这张卡上的历史任务")
        _fence(db, task, turn_id)
        if "customer_id" not in batch:
            # A legacy card did not store the customer separately from the accepted activity.
            batch["customer_id"] = _legacy_customer_id(db, task, batch)
        turn = db.get(AssistantTurn, task.active_turn_id) if task.active_turn_id is not None else None
        submitted_at = turn.created_time if turn is not None else business_now()
        batch["settlement"] = {**submission, "week_start": _week_start(submitted_at).isoformat()}
        _save_batch(db, task, batch, waiting=waiting, action_name="settle_open_follow_up_begin", action_input={
            "choices": submission["choices"], "suppress_week": suppress_week,
        })
        try:
            db.commit()
        except SQLAlchemyError:
            persisted = _reload_settlement(db, task, batch["settlement"], turn_id, allow_unbound=True)
            if persisted.get("settlement") is None:
                raise
            batch = persisted
    elif not isinstance(frozen, dict) or any(frozen.get(key) != value for key, value in submission.items()):
        raise ValueError("历史任务已提交，不能更改处理结果")

    items = _settlement_items(batch)
    for item in items:
        disposition = item.get("disposition")
        if disposition not in (None, "attempting"):
            continue
        _fence(db, task, turn_id)
        complete = item["item_id"] in selected
        if disposition == "attempting":
            # A prior worker reserved a write but left no authoritative receipt.
            _observe(item, "unknown", *_UNKNOWN)
        elif not complete:
            _settle_item(db, task, batch, item, complete=False, turn_id=turn_id)
        else:
            item["disposition"] = "attempting"
            key = str(item["idempotency_key"])
            try:
                _save_batch(db, task, batch, waiting=waiting, action_name="settle_open_follow_up_claim", action_input={
                    "item_id": item["item_id"], "idempotency_key": key,
                }, event_key=key)
                db.commit()
            except SQLAlchemyError:
                persisted = _reload_settlement(db, task, batch["settlement"], turn_id)
                durable_item = _settlement_item(persisted, item)
                if durable_item.get("disposition") is None:
                    # The claim was not committed. The executor has not run.
                    _observe(item, "failed", "未能完成", "任务未改动", code="SERVICE_REJECTED")
                elif durable_item["disposition"] == "attempting":
                    _observe(item, "unknown", *_UNKNOWN)
                else:
                    item.update(durable_item)
                    continue
            else:
                _fence(db, task, turn_id)
                _settle_item(db, task, batch, item, complete=True, turn_id=turn_id)

        try:
            _save_batch(
                db, task, batch, waiting=waiting, action_name="settle_open_follow_up_item",
                action_input={"item_id": item["item_id"], "selected": complete},
                action_result={"state": item["disposition"], "failure_code": item.get("failure_code")},
                append_committed=_receipt_for(item),
            )
            db.commit()
        except SQLAlchemyError:
            persisted = _reload_settlement(db, task, batch["settlement"], turn_id)
            durable_item = _settlement_item(persisted, item)
            if durable_item.get("disposition") not in (None, "attempting"):
                item.update(durable_item)
                receipt = _receipt_for(item)
                if receipt is None or receipt[0] in (task.committed_json or []):
                    continue
            if item.get("disposition") == "complete":
                _observe(item, "unknown", *_UNKNOWN)
            _save_batch(
                db, task, batch, waiting=waiting, action_name="settle_open_follow_up_item",
                action_input={"item_id": item["item_id"], "selected": complete},
                action_result={"state": item["disposition"], "failure_code": item.get("failure_code")},
            )
            db.commit()

    # This update, suppression, and publication share the enclosing turn's final transaction.
    _fence(db, task, turn_id)
    if suppress_week:
        _apply_suppression(db, task, batch)
    batch["status"] = "DONE"
    message = _summary(items, batch.get("suppression_status"))
    result = _save_batch(db, task, batch, waiting=None, action_name="settle_open_follow_up_batch")
    return DispositionOutcome(result, message, True)


def _settle_item(
    db: Session, task: AssistantTask, batch: dict[str, object], item: dict[str, object], *,
    complete: bool, turn_id: int | None,
) -> None:
    try:
        failure = _revalidate(db, task, batch, item, lock=complete)
    except (SQLAlchemyError, PermissionError) as exc:
        db.rollback()
        _fence(db, task, turn_id)
        failure = (
            ("无权限", "任务未改动", "NO_PERMISSION")
            if isinstance(exc, PermissionError)
            else ("未能核对", "请到客户追踪页处理", "REVALIDATION_FAILED")
        )
    if not complete and failure is not None and failure[2] != "ALREADY_HANDLED":
        # Nothing is written for an unticked item, so a stale relation is not its failure.
        failure = None
    if failure is not None:
        _observe(item, "failed", *failure)
        return
    if not complete:
        _observe(item, "hold", "保持", "日期不变")
        return
    from app.services.assistant.turns import AssistantStateConflict

    try:
        _apply_complete(db, task, batch, item)
    except AssistantStateConflict:
        raise
    except Exception:
        logger.exception("follow-up disposition completion could not be verified")
        _observe(item, "unknown", *_UNKNOWN)
    if item["disposition"] != "complete":
        db.rollback()
        _fence(db, task, turn_id)


def _fence(db: Session, task: AssistantTask, turn_id: int | None) -> None:
    from app.services.assistant.turns import AssistantStateConflict, assert_owned_execution_lease

    if task.active_turn_id != turn_id:
        raise AssistantStateConflict("任务轮次归属已变化")
    assert_owned_execution_lease(db, task)


def _reload_settlement(
    db: Session, task: AssistantTask, settlement: object, turn_id: int | None, *, allow_unbound: bool = False,
) -> dict[str, object]:
    from app.services.assistant.turns import AssistantStateConflict

    db.rollback()
    db.refresh(task)
    _fence(db, task, turn_id)
    persisted = _batch(task)
    if persisted is None or persisted.get("status") != "ACTIVE":
        raise AssistantStateConflict("历史任务处理轮次已变化")
    binding = persisted.get("settlement")
    if binding != settlement and not (allow_unbound and binding is None):
        raise AssistantStateConflict("历史任务处理轮次已变化")
    return deepcopy(persisted)


def _settlement_item(batch: dict[str, object], item: dict[str, object]) -> dict[str, object]:
    return next(row for row in _settlement_items(batch) if row["item_id"] == item["item_id"])


def _legacy_customer_id(db: Session, task: AssistantTask, batch: dict[str, object]) -> int | None:
    accepted_id = _accepted_activity_id(task, batch)
    if accepted_id is None:
        return None
    for receipt in reversed(task.committed_json or []):
        if receipt.get("kind") == "customer_activity" and receipt.get("public_id") == accepted_id:
            receipt_customer_id = receipt.get("customer_id")
            if receipt_customer_id is not None:
                return receipt_customer_id if isinstance(receipt_customer_id, int) else None
            break
    activity = source_activity(db, task)
    if (
        activity is not None and activity.activity_revision == batch.get("activity_revision")
        and _source_hash(_activity_source(activity)) == batch.get("source_sha256")
    ):
        customer_id = activity.customer_id
        return customer_id if isinstance(customer_id, int) else None
    return None


def _apply_complete(db: Session, task: AssistantTask, batch: dict[str, object], item: dict[str, object]) -> None:
    from app.services.follow_up_task_reconciliation_evaluation_service import (
        FollowUpTaskReconciliationDecision,
        FollowUpTaskReconciliationTaskDecision,
    )
    from app.services.follow_up_task_transition_execution_service import (
        FollowUpTaskTransitionExecutionStatus,
        follow_up_task_transition_execution_service,
    )
    from app.services.follow_up_task_transition_plan_service import (
        FollowUpTaskTransitionAction,
        FollowUpTaskTransitionPlan,
    )

    target = str(item["task_public_id"])
    action = FollowUpTaskTransitionAction(
        action="COMPLETE",
        task_public_id=target,
        confidence=1.0,
        executable=True,
        requires_confirmation=False,
        reason="assistant_open_follow_up_disposition",
        evidence_terms=(str(item.get("evidence_quote") or item.get("title") or ""),),
        source_activity_public_id=str(batch.get("activity_id") or ""),
    )
    plan = FollowUpTaskTransitionPlan(
        decision=FollowUpTaskReconciliationDecision(
            candidate_public_ids=(target,),
            task_decisions=(FollowUpTaskReconciliationTaskDecision(
                decision="COMPLETE", confidence=1.0, task_public_id=target,
            ),),
        ),
        actions=(action,),
        plan_source="assistant_open_follow_up_disposition",
    )
    result = follow_up_task_transition_execution_service.execute_action(
        db,
        team_id=task.team_id,
        action=action,
        plan=plan,
        actor_id=str(task.user_id),
        expected_owner_id=str(item.get("owner_id") or ""),
        commit=False,
    )
    db.flush()
    row = _task_row(db, task, target, lock=True)
    if (
        result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED
        and row is not None
        and row.status == FollowUpTaskStatus.COMPLETED
    ):
        _observe(item, "complete", "完成", None)
        return
    if result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED:
        _observe(item, "unknown", *_UNKNOWN)
        return
    if result.skip_reason in {"TASK_NOT_OPEN", "TASK_OWNER_MISMATCH", "TASK_NOT_FOUND"}:
        _observe(item, "failed", *_HANDLED)
        return
    _observe(item, "failed", "未能完成", "请到客户追踪页处理", code="SERVICE_REJECTED")


def _revalidate(
    db: Session, task: AssistantTask, batch: dict[str, object], item: dict[str, object], *, lock: bool,
) -> tuple[str, str, str] | None:
    query = db.query(CustomerActivity).filter(
        CustomerActivity.id == _accepted_activity_id(task, batch), CustomerActivity.team_id == task.team_id,
    ).populate_existing()
    activity = (query.with_for_update() if lock else query).one_or_none()
    if (
        activity is None or activity.activity_kind not in FOLLOW_UP_KINDS
        or activity.activity_revision != batch.get("activity_revision")
        or _source_hash(activity.source_content or "") != batch.get("source_sha256")
        or (batch.get("customer_id") is not None and batch["customer_id"] != activity.customer_id)
    ):
        return _STALE
    row = _task_row(db, task, str(item.get("task_public_id") or ""), lock=lock)
    if row is None or row.customer_id != activity.customer_id or row.source_activity_id == activity.id:
        return _HANDLED
    if not _can_operate(db, task, row):
        return ("无权限", "任务未改动", "NO_PERMISSION")
    if row.status != FollowUpTaskStatus.OPEN or row.owner_id != item.get("owner_id"):
        return _HANDLED
    title = row.title
    fresh = relate_title(title if isinstance(title, str) else "", activity.source_content or "")
    if bool(fresh) != bool(item.get("related")) or (fresh and fresh[1] != item.get("evidence_quote")):
        return _STALE
    legacy = "customer_id" not in batch or not batch.get("precise_timestamp")
    if row.title != item.get("title") or _stamp(row.updated_time, legacy=legacy) != item.get("updated_time"):
        return _HANDLED
    return None


def _build_batch(db: Session, task: AssistantTask, activity: CustomerActivity) -> dict[str, object] | None:
    codes = _permission_codes(db, task)
    privileged = bool(codes.intersection({"follow_up_task:operate:all", "follow_up_task:edit:all"}))
    operable_filter = true() if privileged else FollowUpTask.owner_id == str(task.user_id)
    rows = (
        db.query(FollowUpTask)
        .filter(
            FollowUpTask.team_id == task.team_id,
            FollowUpTask.customer_id == activity.customer_id,
            FollowUpTask.status == FollowUpTaskStatus.OPEN,
            or_(FollowUpTask.source_activity_id.is_(None), FollowUpTask.source_activity_id != activity.id),
            operable_filter,
        )
        .order_by(FollowUpTask.due_at.asc(), FollowUpTask.id.asc())
        .limit(MAX_CANDIDATES + 1)
        .all()
    )
    if len(rows) > MAX_CANDIDATES:
        return None
    source = _activity_source(activity)
    ranked = [(row, relate_title(row.title or "", source)) for row in rows]
    ranked.sort(key=lambda pair: pair[1] is None)
    items: list[dict[str, object]] = []
    for index, (row, related) in enumerate(ranked, start=1):
        items.append({
            "item_id": f"i{index}",
            "task_public_id": row.public_id,
            "title": row.title,
            "owner_id": row.owner_id,
            "owner_line": _owner_line(db, task, row),
            "updated_time": _stamp(row.updated_time),
            "related": related is not None,
            "evidence_phrase": related[0] if related else None,
            "evidence_quote": related[1] if related else None,
            "evidence_reason": related[2] if related else None,
            "disposition": None,
            "result_title": None,
            "result_message": None,
            "idempotency_key": f"follow_up_disposition:{task.public_id}:i{index}:complete",
        })
    customer_id = activity.customer_id
    kind = activity.activity_kind
    return {
        "status": "ACTIVE",
        "disposition_batch_id": generate_public_id("afb"),
        "activity_id": activity.id,
        "customer_id": activity.customer_id,
        "precise_timestamp": True,
        "activity_revision": activity.activity_revision,
        "source_sha256": _source_hash(source),
        "customer_name": _customer_name(db, task, customer_id if isinstance(customer_id, int) else None),
        "activity_kind_label": _kind_label(kind if isinstance(kind, str) else ""),
        "items": items,
    }


def refresh_open_follow_up_waiting(db: Session, task: AssistantTask) -> DispositionOutcome:
    """Reissue a legacy wait without applying its obsolete scalar choice."""
    batch = _batch(task)
    if batch is None or not disposition_choice_ids(task):
        raise ValueError("没有可处理的历史跟进任务")
    waiting = _waiting_for(task, batch)
    result = _save_batch(db, task, batch, waiting=waiting, action_name="restore_open_follow_up_batch")
    return DispositionOutcome(result, waiting.prompt, False)


def _record_terminal(
    db: Session,
    task: AssistantTask,
    batch: dict[str, object],
    message: str,
    *,
    start_followup: bool,
) -> DispositionOutcome:
    result = _save_batch(db, task, batch, waiting=None, action_name="close_open_follow_up_batch")
    return DispositionOutcome(result, message, start_followup)


def _save_batch(
    db: Session,
    task: AssistantTask,
    batch: dict[str, object],
    *,
    waiting: TaskWaiting | None,
    action_name: str,
    action_input: dict[str, object] | None = None,
    append_committed: list[dict[str, object]] | None = None,
    action_result: dict[str, object] | None = None,
    event_key: str | None = None,
) -> AssistantTask:
    authority = load_authority(task).model_copy(update={"open_follow_up_batch": batch})
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            authority=authority,
            waiting=waiting,
            clear_waiting=waiting is None,
            append_committed=append_committed,
            action_actor="SYSTEM" if action_name.startswith(("offer", "restore", "skip", "close")) else "USER",
            action_name=action_name,
            action_input=action_input or {"status": batch.get("status"), "count": len(batch.get("items") or [])},
            action_result=action_result or {"status": batch.get("status")},
            event_key=event_key,
        ),
    )
    return result.task


def _waiting_for(task: AssistantTask, batch: dict[str, object]) -> TaskWaiting:
    items = _pending_items(batch)
    prompt = "历史跟进任务"
    return TaskWaiting(
        type=AssistantWaitingType.FOLLOW_UP_DISPOSITION,
        field="follow_up_disposition",
        question_id=f"q_fut_{task.public_id}_batch",
        prompt=prompt,
        candidates=[
            {"id": str(item["item_id"]), "label": str(item["title"])} for item in items
        ],
    )


def _batch(task: AssistantTask) -> dict[str, object] | None:
    raw = (task.authority_json or {}).get("open_follow_up_batch")
    if not isinstance(raw, dict):
        return None
    return raw


def _permission_codes(db: Session, task: AssistantTask) -> set[str]:
    from app.services.assistant.crm_proposal_commands import _permissions

    return _permissions(db, task)


def _can_operate(db: Session, task: AssistantTask, row: FollowUpTask, codes: set[str] | None = None) -> bool:
    if row.owner_id == str(task.user_id):
        return True
    granted = codes if codes is not None else _permission_codes(db, task)
    return bool(granted.intersection({"follow_up_task:operate:all", "follow_up_task:edit:all"}))


def _task_row(db: Session, task: AssistantTask, public_id: str, *, lock: bool = False) -> FollowUpTask | None:
    if not public_id:
        return None
    query = db.query(FollowUpTask).filter(
        FollowUpTask.team_id == task.team_id, FollowUpTask.public_id == public_id,
    ).populate_existing()
    return (query.with_for_update() if lock else query).one_or_none()


def _customer_name(db: Session, task: AssistantTask, customer_id: int | None) -> str:
    if customer_id is None:
        return ""
    from app.models.customer import Customer

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id, Customer.team_id == task.team_id)
            .one_or_none()
        )
    except SQLAlchemyError:
        return ""
    return customer.account_name if customer is not None and customer.account_name else ""


def _kind_label(kind: str) -> str:
    from app.services.customer_activity_kinds import get_activity_kind_meta

    meta = get_activity_kind_meta(kind)
    label = meta.get("label") if isinstance(meta, dict) else ""
    return str(label or "")


def _owner_line(db: Session, task: AssistantTask, row: FollowUpTask) -> str:
    due = f"计划 {row.due_at.month} 月 {row.due_at.day} 日" if row.due_at is not None else ""
    if row.owner_id == str(task.user_id):
        return due
    who = _other_owner(db, row.owner_id)
    if not who:
        return due
    return f"{who} · {due}" if due else who


def _other_owner(db: Session, owner_id: str) -> str:
    try:
        user_id = int(owner_id)
    except (TypeError, ValueError):
        return ""
    from app.models.user import User

    try:
        user = db.query(User).filter(User.id == user_id).one_or_none()
    except SQLAlchemyError:
        return ""
    if user is None or not getattr(user, "name", None):
        return ""
    return str(user.name)


def _observe(
    item: dict[str, object], disposition: str, title: str, message: str | None, code: str | None = None,
) -> None:
    item["disposition"] = disposition
    item["result_title"] = title
    item["result_message"] = message
    if code is not None:
        item["failure_code"] = code
    if code == "RELATION_STALE":
        item["related"] = False


def _summary(items: list[dict[str, object]], suppression_status: object) -> str:
    counts = (
        ("完成", sum(item.get("disposition") == "complete" for item in items)),
        ("保持", sum(item.get("disposition") == "hold" for item in items)),
        ("跳过", sum(item.get("disposition") == "skip" for item in items)),
        ("已被处理", sum(item.get("failure_code") == "ALREADY_HANDLED" for item in items)),
        ("未能处理", sum(
            item.get("disposition") == "failed" and item.get("failure_code") != "ALREADY_HANDLED"
            for item in items
        )),
        ("结果待核对", sum(item.get("disposition") == "unknown" for item in items)),
    )
    summary = "历史跟进任务：" + "，".join(f"{count} 条{label}" for label, count in counts if count)
    if suppression_status == "applied":
        return summary + "。本周不再提示此客户的历史任务。"
    if suppression_status == "stale":
        return summary + "。客户关联已失效，未设置本周免提示。"
    return summary


def _receipt_for(item: dict[str, object]) -> list[dict[str, object]] | None:
    if item.get("disposition") != "complete" or not item.get("task_public_id") or not item.get("idempotency_key"):
        return None
    return [{
        "kind": "follow_up_task",
        "public_id": item["task_public_id"],
        "proposal_key": item["idempotency_key"],
    }]


def _week_start(value: datetime) -> date:
    return value.date() - timedelta(days=value.weekday())


def _is_suppressed(db: Session, task: AssistantTask, customer_id: int) -> bool:
    return db.query(AssistantOpenFollowUpSuppression.id).filter_by(
        team_id=task.team_id, customer_id=customer_id, week_start=_week_start(business_now()),
    ).first() is not None


def _apply_suppression(db: Session, task: AssistantTask, batch: dict[str, object]) -> None:
    activity = source_activity(db, task)
    customer_id = batch.get("customer_id")
    if (
        customer_id is None or _accepted_activity_id(task, batch) is None
        or activity is None or activity.customer_id != customer_id
    ):
        batch["suppression_status"] = "stale"
        return
    settlement = batch["settlement"]
    if not isinstance(settlement, dict):
        raise TypeError("invalid open follow-up settlement")
    week_start = settlement["week_start"]
    if not isinstance(week_start, str):
        raise TypeError("invalid open follow-up settlement week")
    values = {
        "team_id": task.team_id,
        "customer_id": customer_id,
        "week_start": date.fromisoformat(week_start),
    }
    table = AssistantOpenFollowUpSuppression.__table__
    if not isinstance(table, Table):
        raise TypeError("open follow-up suppression requires a mapped table")
    statement: Insert
    if db.get_bind().dialect.name == "sqlite":
        statement = sqlite_insert(table).values(**values).on_conflict_do_nothing(
            index_elements=["team_id", "customer_id", "week_start"],
        )
    else:
        statement = mysql_insert(table).values(**values).on_duplicate_key_update(week_start=table.c.week_start)
    db.execute(statement)
    batch["suppression_status"] = "applied"


def _activity_source(activity: CustomerActivity) -> str:
    source = activity.source_content or ""
    if not isinstance(source, str):
        raise TypeError("invalid activity source content")
    return source


def _source_hash(source: str) -> str:
    return sha256(source.encode()).hexdigest()


def _quote(source: str, phrase: str) -> str:
    index = source.find(phrase)
    if index < 0:
        return phrase
    boundaries = [source.rfind(mark, 0, index) for mark in "。！？\n"]
    boundary = max(boundaries)
    start = 0 if boundary < 0 else boundary + 1
    endings = [source.find(mark, index + len(phrase)) for mark in "。！？\n"]
    endings = [found for found in endings if found >= 0]
    end = min(endings) + 1 if endings else len(source)
    quote = source[start:end].strip()
    if phrase in quote and quote in source and len(quote) <= 80:
        return quote
    if len(phrase) > 80 and phrase in source:
        return phrase
    left = max(0, index - 20)
    right = min(len(source), index + len(phrase) + 20)
    window = source[left:right].strip()
    if phrase in window and window in source:
        return window[:80] if len(window) > 80 and phrase in window[:80] else window
    return phrase


def _stamp(value: datetime | None, *, legacy: bool = False) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="seconds" if legacy else "microseconds")
