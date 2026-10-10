"""Kind classification, canonical activity structuring and quality intake."""
# ruff: noqa: RUF001

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.models.assistant import AssistantTask, AssistantWaitingType
from app.services.assistant.action_evidence import (
    append_source,
    is_action_deadline_correction,
    reconcile_action_evidence,
)
from app.services.assistant.contracts import DraftField, TaskDraft, TaskWaiting
from app.services.assistant.events import (
    NullProgressReporter,
    ProgressReporter,
)
from app.services.assistant.events import (
    stage as mk_stage,
)
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.quality_gate import QualityGateOutcome
from app.services.assistant.task_state import TaskUpdate, apply_task_update
from app.services.customer_activity_ai.schemas import FollowUpContent, MeetingContent

_S_CLASSIFY = mk_stage("classify")


def _has_pending_kind_question(task: AssistantTask) -> bool:
    from app.services.assistant.task_state import load_waiting

    waiting = load_waiting(task)
    return waiting is not None and waiting.type == "ACTIVITY_KIND"


_S_STRUCTURE = mk_stage("structure")
_S_GATE = mk_stage("quality_gate")

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.assistant.intake import KindStructurer
    from app.services.assistant.quality_gate import QualityGate as QualityGateProtocol


_KIND_PROMPT = "这条记录属于线上会议、线下会议还是普通跟进？"


def kind_waiting(task: AssistantTask) -> TaskWaiting:
    return TaskWaiting(
        type=AssistantWaitingType.ACTIVITY_KIND,
        field="activity_kind",
        question_id=f"q_kind_{task.public_id}_{task.version}",
        prompt=_KIND_PROMPT,
    )


def _merge_text(previous: str, incoming: str) -> str:
    previous, incoming = previous.strip(), incoming.strip()
    if not incoming or incoming == previous or incoming in previous:
        return previous
    if not previous or previous in incoming:
        return incoming
    return f"{previous}\n{incoming}"


def _merge_canonical(
    kind: str, previous: dict[str, object], incoming: dict[str, object], *, correction_text: str = ""
) -> dict[str, object]:
    schema = FollowUpContent if kind == "FOLLOW_UP" else MeetingContent
    old = schema.model_validate(previous).model_dump(mode="json")
    new = schema.model_validate(incoming).model_dump(mode="json")
    merged = dict(old)
    for name in ("action_evidence", "source_records"):
        if name in previous:
            merged[name] = previous[name]
    for name, value in new.items():
        if isinstance(value, str):
            if name in {
                "content",
                "customer_feedback",
                "current_progress",
                "next_step_summary",
                "meeting_background",
                "communication_context",
            }:
                merged[name] = _merge_text(str(old[name]), value)
            elif value.strip():
                merged[name] = value
        elif isinstance(value, list):
            if name == "action_items":
                actions = []
                corrected = list(old[name])
                correction_ids = {}
                for replacement in value:
                    owner, action = replacement["owner"].strip(), replacement["action"].strip()
                    matches = [
                        entry
                        for entry in corrected
                        if (entry["owner"].strip(), entry["action"].strip()) == (owner, action)
                    ]
                    if len(matches) == 1 and is_action_deadline_correction(correction_text, owner, action):
                        prior = matches[0]
                        corrected.remove(prior)
                        correction_ids[(owner, action, replacement.get("due_date"))] = prior.get("item_id")
                for item in [*corrected, *value]:
                    if not item.get("action", "").strip():
                        continue
                    key = (item["owner"].strip(), item["action"].strip(), item.get("due_date"))
                    if any((entry["owner"], entry["action"], entry.get("due_date")) == key for entry in actions):
                        continue
                    stable_id = next(
                        (
                            entry.get("item_id")
                            for entry in old[name]
                            if (entry["owner"].strip(), entry["action"].strip(), entry.get("due_date")) == key
                        ),
                        None,
                    )
                    actions.append(
                        {
                            **item,
                            "owner": key[0],
                            "action": key[1],
                            "item_id": stable_id
                            or correction_ids.get(key)
                            or f"act_{hashlib.sha256(repr(key).encode()).hexdigest()[:16]}",
                        }
                    )
                merged[name] = actions
            else:
                merged[name] = list(old[name])
                for item in value:
                    if item and item not in merged[name]:
                        merged[name].append(item)
        elif isinstance(value, dict):
            merged[name] = {key: list(dict.fromkeys([*old[name].get(key, []), *items])) for key, items in value.items()}
    return merged


def apply_structured_draft(task: AssistantTask, structured: object, *, correction_text: str = "") -> TaskDraft:
    """Merge typed model facts while preserving user-accepted scalar slots."""
    draft = TaskDraft.model_validate(task.draft_json or {})
    kind = task.activity_kind or getattr(structured, "kind_confirmed", "FOLLOW_UP")
    payload = getattr(structured, "content_json", None)
    if payload is None:
        payload = (
            {
                "content": getattr(structured, "content", ""),
                "next_action": getattr(structured, "next_action", ""),
                "next_follow_time_text": getattr(structured, "next_follow_time_text", ""),
            }
            if kind == "FOLLOW_UP"
            else {
                "meeting_subject": getattr(structured, "meeting_subject", ""),
                "key_minutes": [getattr(structured, "content", "")] if getattr(structured, "content", "") else [],
                "next_step_summary": getattr(structured, "next_action", ""),
            }
        )
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    draft.content_json = _merge_canonical(kind, draft.content_json, payload, correction_text=correction_text)
    for slot_name, canonical_name in (
        ("content", "content" if kind == "FOLLOW_UP" else "key_minutes"),
        ("next_action", "next_action" if kind == "FOLLOW_UP" else "next_step_summary"),
        ("next_follow_time", "next_follow_time_text"),
        ("meeting_subject", "meeting_subject"),
    ):
        slot = getattr(draft, slot_name)
        if slot.status not in {"ACCEPTED", "EXPLICITLY_NONE"} or canonical_name not in draft.content_json:
            continue
        if slot.status == "EXPLICITLY_NONE":
            text = ""
            if slot_name == "next_action" and slot.value:
                draft.content_json["next_action_absence_reason"] = slot.value
        else:
            text = slot.value or ""
        draft.content_json[canonical_name] = (
            [text] if text and canonical_name == "key_minutes" else ([] if canonical_name == "key_minutes" else text)
        )
    if draft.next_action.status == "EXPLICITLY_NONE":
        draft.content_json["next_action" if kind == "FOLLOW_UP" else "next_step_summary"] = ""
        if kind != "FOLLOW_UP":
            draft.content_json["action_items"] = []
        draft.content_json["next_follow_time_text"] = ""
        draft.next_follow_time = DraftField(status="MISSING")

    def _patch(name: str, value: str, *, accumulate: bool = False) -> None:
        text = value.strip()
        if not text:
            return
        current = getattr(draft, name)
        if current.status in {"ACCEPTED", "EXPLICITLY_NONE"}:
            return
        merged = _merge_text(current.value or "", text) if accumulate else text
        setattr(draft, name, DraftField(status="CANDIDATE", value=merged))

    canonical = draft.content_json
    _patch("content", str(canonical.get("content") or "\n".join(canonical.get("key_minutes", []))), accumulate=False)
    _patch("next_action", str(canonical.get("next_action") or getattr(structured, "next_action", "")))
    if draft.next_action.status != "EXPLICITLY_NONE":
        _patch(
            "next_follow_time",
            str(canonical.get("next_follow_time_text") or getattr(structured, "next_follow_time_text", "")),
        )
    _patch("meeting_subject", str(canonical.get("meeting_subject") or getattr(structured, "meeting_subject", "")))
    _patch("participants", str(getattr(structured, "participants", "")))
    _patch("customer", str(getattr(structured, "customer_name", "")))
    return draft


def apply_quality_score(draft: TaskDraft, score: int) -> TaskDraft:
    """Record the server gate score onto the draft for card display."""

    draft.quality_score = DraftField(status="CANDIDATE", value=str(score))
    return draft


async def intake_step(
    db: Session,
    task: AssistantTask,
    user_text: str,
    structurer: KindStructurer,
    gate: QualityGateProtocol | None = None,
    reporter: ProgressReporter | None = None,
    from_waiting: bool = False,
    accept_source: bool = True,
) -> tuple[AssistantTask, str, TaskWaiting | None, bool]:
    """Run one intake pass; returns (task, message, waiting, failed)."""

    if reporter is None:
        reporter = NullProgressReporter()

    accepted_draft = TaskDraft.model_validate(task.draft_json or {})
    accepted = append_source(db, task, accepted_draft, user_text) if accept_source else False
    if accept_source and not accepted and accepted_draft.quality_score.status == "CANDIDATE":
        return task, "整理稿已就绪。", None, False
    accepted_draft.quality_score = DraftField(status="MISSING")
    accepted_draft.score_reason = None
    accepted_draft.score_detail = {}
    if accepted_draft.model_dump(mode="json") != (task.draft_json or {}):
        task = apply_task_update(
            db,
            task,
            TaskUpdate(
                draft=accepted_draft,
                action_actor="USER",
                action_name="accept_source",
                action_result={
                    "segment_id": accepted_draft.source_records[-1].segment_id
                    if accepted_draft.source_records
                    else None
                },
            ),
        ).task
    kind_hinted = task.activity_kind is not None and user_text.strip() != "" and not _has_pending_kind_question(task)
    if from_waiting:
        if task.activity_kind is None:
            raise ValueError("field answer requires a selected activity kind")
    elif kind_hinted:
        # Explicitly chosen kinds do not need another model classification.
        from app.services.assistant.llm_contracts import KindDecision

        decision = KindDecision(kind=task.activity_kind, reason="用户指定类型")
        reporter.stage_start(_S_CLASSIFY)
        reporter.stage_done(_S_CLASSIFY, ms=0)
    elif task.activity_kind is None:
        reporter.stage_start(_S_CLASSIFY)
        _t0 = time.monotonic()
        decision = await structurer.classify(db, team_id=task.team_id, user_text=user_text)
        reporter.stage_done(_S_CLASSIFY, ms=int((time.monotonic() - _t0) * 1000))
        if decision.kind == "UNCLEAR":
            waiting = kind_waiting(task)
            original_draft = TaskDraft.model_validate(task.draft_json or {})
            result = apply_task_update(
                db,
                task,
                TaskUpdate(
                    waiting=waiting,
                    draft=original_draft,
                    action_actor="SYSTEM",
                    action_name="ask_activity_kind",
                    action_result={"reason": decision.reason},
                ),
            )
            return result.task, waiting.prompt, waiting, False
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                activity_kind=decision.kind,
                action_actor="SYSTEM",
                action_name="set_activity_kind",
                action_result={"kind": decision.kind, "source": "classifier"},
            ),
        )
        task = result.task

    draft = TaskDraft.model_validate(task.draft_json or {})

    reporter.stage_start(_S_STRUCTURE)
    _t0 = time.monotonic()
    try:
        structured = await structurer.structure(
            db, team_id=task.team_id, kind=task.activity_kind or "FOLLOW_UP", user_text=user_text
        )
        reporter.stage_done(_S_STRUCTURE, ms=int((time.monotonic() - _t0) * 1000))
    except (AssistantLLMError, TimeoutError, ValueError, TypeError, ValidationError):
        draft.quality_score = DraftField(status="MISSING")
        draft.score_reason = None
        draft.score_detail = {}
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                # Transient LLM failure must not kill the task: it stays
                # ACTIVE so the user can retry when the provider recovers.
                draft=draft,
                error_code="STRUCTURING_UNAVAILABLE",
                action_actor="SYSTEM",
                action_name="structure_draft",
                action_result={"accepted": False, "retryable": True},
            ),
        )
        return result.task, "整理暂时没有完成，请稍后重试。", None, True

    try:
        draft = apply_structured_draft(task, structured, correction_text=user_text)
        reconcile_action_evidence(draft, task.activity_kind or "FOLLOW_UP")
    except (ValueError, TypeError, ValidationError):
        draft = TaskDraft.model_validate(task.draft_json or {})
        draft.quality_score = DraftField(status="MISSING")
        draft.score_reason = None
        draft.score_detail = {}
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                draft=draft,
                error_code="STRUCTURING_UNAVAILABLE",
                action_actor="SYSTEM",
                action_name="structure_draft",
                action_result={"accepted": False, "retryable": True},
            ),
        )
        return result.task, "整理暂时没有完成，请稍后重试。", None, True
    draft.quality_score = DraftField(status="MISSING")
    draft.score_reason = None
    draft.score_detail = {}
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            draft=draft,
            action_actor="SYSTEM",
            action_name="structure_draft",
            action_result={"accepted": True, "kind_confirmed": getattr(structured, "kind_confirmed", None)},
        ),
    )
    task = result.task

    if gate is None:
        return task, "已整理完成。", None, False

    draft = TaskDraft.model_validate(task.draft_json or {})
    reporter.stage_start(_S_GATE)
    _t0 = time.monotonic()
    try:
        gate_outcome = await gate.evaluate(
            db,
            team_id=task.team_id,
            user_text="\n".join(draft.source_segments),
            content=draft.content.value or "",
            next_action=draft.next_action.value or "",
            kind=task.activity_kind or "FOLLOW_UP",
            content_json=draft.content_json,
        )
        if (
            not isinstance(gate_outcome, QualityGateOutcome)
            or not isinstance(gate_outcome.score, int)
            or isinstance(gate_outcome.score, bool)
            or not 0 <= gate_outcome.score <= 100
            or not isinstance(gate_outcome.passed, bool)
            or not isinstance(gate_outcome.reason, str)
            or not gate_outcome.reason.strip()
            or (gate_outcome.detail is not None and not isinstance(gate_outcome.detail, dict))
        ):
            raise ValueError("quality gate returned an invalid outcome")
        reporter.stage_done(_S_GATE, ms=int((time.monotonic() - _t0) * 1000), score=gate_outcome.score)
    except (AssistantLLMError, TimeoutError, ValueError, TypeError):
        result = apply_task_update(
            db,
            task,
            TaskUpdate(
                error_code="QUALITY_GATE_UNAVAILABLE",
                action_actor="SYSTEM",
                action_name="quality_gate",
                action_result={"passed": False, "retryable": True},
            ),
        )
        return result.task, "评分暂时没有完成，请稍后重试。", None, True

    draft.score_reason = gate_outcome.reason
    draft.score_detail = {
        **(gate_outcome.detail or {}),
        "structuring_model_name": getattr(structured, "structuring_model", "") or None,
    }
    # Scoring and next-action presence are independent prerequisites.
    action_present = draft.next_action.status == "EXPLICITLY_NONE" or bool((draft.next_action.value or "").strip())
    passed = gate_outcome.passed and action_present
    if passed:
        apply_quality_score(draft, gate_outcome.score)
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            draft=draft,
            action_actor="SYSTEM",
            action_name="quality_gate",
            action_result={"passed": passed, "score": gate_outcome.score, "reason": gate_outcome.reason},
        ),
    )
    task = result.task
    if passed:
        return task, "已整理完成。", None, False

    if not action_present:
        gap_field, question = "next_action", "下一步是谁在什么时间做什么？如暂无下一步，请明确说明。"
    else:
        gap_field = gate_outcome.gap_field or "content"
        question = gate_outcome.question or "请补充这次沟通的关键信息。"

    gap = TaskWaiting(
        type=AssistantWaitingType.FIELD,
        field=gap_field,
        question_id=f"q_gap_{task.public_id}_{task.version}",
        prompt=question,
    )
    result = apply_task_update(
        db,
        task,
        TaskUpdate(
            waiting=gap,
            action_actor="SYSTEM",
            action_name="ask_quality_gap",
            action_result={"prompt": gap.prompt},
        ),
    )
    return result.task, gap.prompt, gap, False
