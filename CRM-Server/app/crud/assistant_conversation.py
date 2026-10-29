"""Owned persistence and CAS for assistant conversations (no CRM business writes)."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
from app.models.assistant_turn import AssistantTurn, AssistantTurnEvent
from app.services.assistant.failure_contract import ROOT_RETRYABLE_FAILURE_CODES
from app.services.assistant.turns import fingerprint
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ConversationConflict(ValueError):
    """A request key, focus, or owned conversation lease has changed."""


def owned_conversation(db: Session, *, team_id: int, user_id: int) -> AssistantConversation | None:
    return db.query(AssistantConversation).filter_by(team_id=team_id, user_id=user_id).one_or_none()


def open_conversation(db: Session, *, team_id: int, user_id: int) -> tuple[AssistantConversation, bool]:
    previous = owned_conversation(db, team_id=team_id, user_id=user_id)
    if previous is not None:
        return previous, False
    conversation = AssistantConversation(team_id=team_id, user_id=user_id)
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = owned_conversation(db, team_id=team_id, user_id=user_id)
        if previous is None:
            raise
        return previous, False
    db.refresh(conversation)
    return conversation, True


def owned_task(db: Session, conversation: AssistantConversation, public_id: str | None) -> AssistantTask | None:
    if public_id is None:
        return None
    return (
        db.query(AssistantTask)
        .filter_by(public_id=public_id, team_id=conversation.team_id, user_id=conversation.user_id)
        .one_or_none()
    )


def candidates(db: Session, conversation: AssistantConversation) -> list[AssistantTask]:
    items = (
        db.query(AssistantTask)
        .filter(
            AssistantTask.team_id == conversation.team_id,
            AssistantTask.user_id == conversation.user_id,
            or_(AssistantTask.status == "ACTIVE", AssistantTask.public_id == conversation.focused_task_public_id),
        )
        .order_by(AssistantTask.id.desc())
        .limit(20)
        .all()
    )
    focus = owned_task(db, conversation, conversation.focused_task_public_id)
    if focus is not None and all(item.id != focus.id for item in items):
        items = [focus, *items[:19]]
    return items


def referenced_candidates(
    db: Session, conversation: AssistantConversation, *, customer_reference: str
) -> list[AssistantTask]:
    """Retrieve labels from the structured Root reference, never infer intent here."""
    reference = customer_reference.strip()
    if not reference:
        return []
    items = (
        db.query(AssistantTask)
        .filter(
            AssistantTask.team_id == conversation.team_id,
            AssistantTask.user_id == conversation.user_id,
            AssistantTask.status == "ACTIVE",
            AssistantTask.draft_json["customer"]["value"].as_string().contains(reference, autoescape=True),
        )
        .order_by(AssistantTask.id.desc())
        .limit(21)
        .all()
    )
    # Do not bind against an arbitrary truncated subset of indistinguishable drafts.
    return items if len(items) <= 20 else []


def owned_entry(db: Session, conversation: AssistantConversation, public_id: str) -> AssistantConversationEntry | None:
    return (
        db.query(AssistantConversationEntry)
        .filter_by(
            conversation_id=conversation.id,
            team_id=conversation.team_id,
            user_id=conversation.user_id,
            public_id=public_id,
        )
        .one_or_none()
    )


def request_entry(db: Session, conversation: AssistantConversation, key: str) -> AssistantConversationEntry | None:
    return (
        db.query(AssistantConversationEntry)
        .filter_by(
            conversation_id=conversation.id,
            team_id=conversation.team_id,
            user_id=conversation.user_id,
            client_request_id=key,
        )
        .one_or_none()
    )


def page(
    db: Session, conversation: AssistantConversation, *, before: int | None = None, limit: int = 30
) -> tuple[list[AssistantConversationEntry], int | None]:
    query = db.query(AssistantConversationEntry).filter_by(
        conversation_id=conversation.id, team_id=conversation.team_id, user_id=conversation.user_id
    )
    if before is not None:
        query = query.filter(AssistantConversationEntry.id < before)
    rows = query.order_by(AssistantConversationEntry.id.desc()).limit(limit + 1).all()
    return list(reversed(rows[:limit])), rows[limit - 1].id if len(rows) > limit else None


def claim(
    db: Session,
    conversation: AssistantConversation,
    *,
    key: str,
    payload: dict[str, object],
    text: str,
    expected_version: int,
    choice_id: str | None = None,
) -> tuple[AssistantConversationEntry, bool, int]:
    digest = fingerprint(payload)
    previous = request_entry(db, conversation, key)
    if previous is not None:
        if previous.input_fingerprint != digest:
            raise ConversationConflict("这次发送的内容与原请求不一致，请刷新后重试。")
        if previous.state not in {"ROUTING", "ROUTED"}:
            return previous, False, conversation.version
        now = business_now()
        if conversation.busy_entry_id != previous.public_id or (
            conversation.lease_expires_at is not None and conversation.lease_expires_at > now
        ):
            raise ConversationConflict("这句话仍在处理中，请同步会话状态。")
        changed = db.execute(
            update(AssistantConversation)
            .where(
                AssistantConversation.id == conversation.id,
                AssistantConversation.team_id == conversation.team_id,
                AssistantConversation.user_id == conversation.user_id,
                AssistantConversation.busy_entry_id == previous.public_id,
                AssistantConversation.lease_expires_at <= now,
            )
            .values(version=AssistantConversation.version + 1, lease_expires_at=now + timedelta(seconds=120))
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise ConversationConflict("会话状态已变化，请刷新后重试。")
        db.commit()
        db.refresh(conversation)
        return previous, True, conversation.version
    if conversation.pending_choice_id != choice_id:
        raise ConversationConflict("请先回答当前这句的两个选择。")
    identifier = generate_public_id("acm")
    changed = db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == conversation.id,
            AssistantConversation.team_id == conversation.team_id,
            AssistantConversation.user_id == conversation.user_id,
            AssistantConversation.version == expected_version,
            AssistantConversation.busy_entry_id.is_(None),
        )
        .values(
            version=AssistantConversation.version + 1,
            busy_entry_id=identifier,
            lease_expires_at=business_now() + timedelta(seconds=120),
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ConversationConflict("会话已在其他窗口更新，请刷新后再发送。")
    entry = AssistantConversationEntry(
        public_id=identifier,
        conversation_id=conversation.id,
        team_id=conversation.team_id,
        user_id=conversation.user_id,
        client_request_id=key,
        input_fingerprint=digest,
        user_text=text,
        command_json=payload,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConversationConflict("会话已在其他窗口更新，请刷新后再发送。") from exc
    db.refresh(conversation)
    db.refresh(entry)
    return entry, True, conversation.version


def save(
    db: Session,
    conversation: AssistantConversation,
    entry: AssistantConversationEntry,
    *,
    lease_version: int,
    finish: bool = False,
    pending_choice: str | None = None,
    focus: str | None = None,
) -> None:
    now = business_now()
    values: dict[str, object] = {}
    if finish:
        values.update(busy_entry_id=None, lease_expires_at=None, pending_choice_id=pending_choice)
    if focus is not None:
        values["focused_task_public_id"] = focus
    if not values:
        values["lease_expires_at"] = now + timedelta(seconds=120)
    changed = db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == conversation.id,
            AssistantConversation.team_id == conversation.team_id,
            AssistantConversation.user_id == conversation.user_id,
            AssistantConversation.busy_entry_id == entry.public_id,
            AssistantConversation.version == lease_version,
            AssistantConversation.lease_expires_at > now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ConversationConflict("会话处理权已变化，请同步最新状态。")
    db.commit()
    db.refresh(conversation)


def renew_model_lease(
    db: Session,
    conversation: AssistantConversation,
    entry: AssistantConversationEntry,
    *,
    lease_version: int,
    seconds: int,
) -> None:
    """Extend an unexpired owned lease without moving the conversation version."""
    now = business_now()
    changed = db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == conversation.id,
            AssistantConversation.team_id == conversation.team_id,
            AssistantConversation.user_id == conversation.user_id,
            AssistantConversation.busy_entry_id == entry.public_id,
            AssistantConversation.version == lease_version,
            AssistantConversation.lease_expires_at > now,
        )
        .values(lease_expires_at=now + timedelta(seconds=seconds))
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ConversationConflict("会话处理权已变化，请同步最新状态。")
    db.commit()
    db.refresh(conversation)


def claim_root_retry(
    db: Session,
    conversation: AssistantConversation,
    entry: AssistantConversationEntry,
    *,
    expected_version: int,
) -> int:
    """Reopen one owned Root failure without creating another entry."""
    now = business_now()
    command = entry.command_json if isinstance(entry.command_json, dict) else {}
    eligible = (
        entry.conversation_id == conversation.id
        and entry.team_id == conversation.team_id
        and entry.user_id == conversation.user_id
        and entry.state == "READY"
        and bool(entry.error_retryable)
        and entry.error_code in {code.value for code in ROOT_RETRYABLE_FAILURE_CODES}
        and command.get("operation") == "text"
        and entry.task_public_id is None
        and entry.turn_public_id is None
        and entry.task_snapshot_json is None
        and conversation.pending_choice_id is None
        and conversation.busy_entry_id is None
        and (conversation.lease_expires_at is None or conversation.lease_expires_at <= now)
    )
    if not eligible:
        raise ConversationConflict("会话状态已变化，请刷新后重试。")
    changed = db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == conversation.id,
            AssistantConversation.team_id == conversation.team_id,
            AssistantConversation.user_id == conversation.user_id,
            AssistantConversation.version == expected_version,
            AssistantConversation.busy_entry_id.is_(None),
            AssistantConversation.pending_choice_id.is_(None),
            or_(
                AssistantConversation.lease_expires_at.is_(None),
                AssistantConversation.lease_expires_at <= now,
            ),
        )
        .values(
            version=AssistantConversation.version + 1,
            busy_entry_id=entry.public_id,
            lease_expires_at=now + timedelta(seconds=120),
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ConversationConflict("会话状态已变化，请刷新后重试。")
    reopened = db.execute(
        update(AssistantConversationEntry)
        .where(
            AssistantConversationEntry.id == entry.id,
            AssistantConversationEntry.team_id == conversation.team_id,
            AssistantConversationEntry.user_id == conversation.user_id,
            AssistantConversationEntry.state == "READY",
            AssistantConversationEntry.error_retryable.is_(True),
            AssistantConversationEntry.error_code.in_([code.value for code in ROOT_RETRYABLE_FAILURE_CODES]),
            AssistantConversationEntry.task_public_id.is_(None),
            AssistantConversationEntry.turn_public_id.is_(None),
            AssistantConversationEntry.task_snapshot_json.is_(None),
        )
        .values(state="ROUTING", reply_text=None, error_code=None, error_retryable=None)
        .execution_options(synchronize_session=False)
    )
    if reopened.rowcount != 1:
        db.rollback()
        raise ConversationConflict("会话状态已变化，请刷新后重试。")
    db.commit()
    db.refresh(conversation)
    db.refresh(entry)
    return conversation.version


def owned_turn(
    db: Session, conversation: AssistantConversation, task: AssistantTask, public_id: str
) -> AssistantTurn | None:
    return (
        db.query(AssistantTurn)
        .filter_by(public_id=public_id, task_id=task.id, team_id=conversation.team_id, user_id=conversation.user_id)
        .one_or_none()
    )


def turn_events(db: Session, turn: AssistantTurn) -> list[AssistantTurnEvent]:
    return db.query(AssistantTurnEvent).filter_by(turn_id=turn.id).order_by(AssistantTurnEvent.seq).all()


def legacy_actions(db: Session, conversation: AssistantConversation, task: AssistantTask) -> list[AssistantAction]:
    return (
        db.query(AssistantAction)
        .filter_by(task_id=task.id, team_id=conversation.team_id)
        .order_by(AssistantAction.id)
        .all()
    )


def bootstrap_active(db: Session, conversation: AssistantConversation) -> None:
    """Keep the former resumable task without scanning all old completed history."""
    task = (
        db.query(AssistantTask)
        .filter_by(team_id=conversation.team_id, user_id=conversation.user_id, status="ACTIVE")
        .order_by(AssistantTask.id.desc())
        .first()
    )
    if task is None:
        return
    from app.services.assistant.presentation import task_view

    view = task_view(task, db)
    changed = db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == conversation.id,
            AssistantConversation.team_id == conversation.team_id,
            AssistantConversation.user_id == conversation.user_id,
            AssistantConversation.version == 0,
            AssistantConversation.busy_entry_id.is_(None),
            AssistantConversation.pending_choice_id.is_(None),
            AssistantConversation.focused_task_public_id.is_(None),
        )
        .values(focused_task_public_id=task.public_id)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        db.refresh(conversation)
        return
    entry = AssistantConversationEntry(
        conversation_id=conversation.id,
        team_id=conversation.team_id,
        user_id=conversation.user_id,
        client_request_id=f"legacy-{task.public_id}",
        input_fingerprint=fingerprint({"legacy": task.public_id}),
        user_text=task.goal,
        command_json={"operation": "legacy"},
        state="READY",
        task_public_id=task.public_id,
        reply_text=view.waiting.prompt if view.waiting else None,
        task_snapshot_json=view.model_dump(mode="json"),
    )
    db.add(entry)
    db.commit()
    db.refresh(conversation)
