"""A2/A3: one authorized activity edit advances task authority by exactly one version."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

import json

import pytest

from app.models.assistant_turn import AssistantTurn
from app.models.customer_activity import CustomerActivity
from app.services.assistant import turns
from app.services.assistant.task_state import load_authority, load_waiting

from tests.unit.test_assistant_confirmation_contract import (  # noqa: F401 -- shared fixture
    db as confirmation_db,
)
from tests.unit.test_assistant_confirmation_contract import persisted_temporal_confirmation

NEW_DATE = "2026-12-07"
NEW_WAIT = "2026-12-07T09:00:00"


async def _submit(session, factory, *, task, key, input_data):
    """Submit one persisted turn with the signed waiting action bound."""
    waiting = load_waiting(task)
    assert waiting is not None
    turn, accepted = turns.accept_submit(
        session,
        task=task,
        key=key,
        input_data=input_data,
        action_id=waiting.action_id,
        expected_version=waiting.expected_version,
    )
    if accepted:
        await turns.execute_turn(turn.id, factory=factory)
        session.expire_all()
        session.refresh(task)
    return turn, accepted


@pytest.mark.asyncio
async def test_request_edit_does_not_bump_version(confirmation_db, monkeypatch):
    """A2 part 1: opening the edit form only replaces the signed waiting action."""
    session, factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    before = task.version
    assert load_waiting(task).type == "CONFIRMATION"

    await _submit(
        session, factory, task=task, key="a2-open-edit",
        input_data={"kind": "request_edit", "text": None, "choice": None},
    )

    edit_waiting = load_waiting(task)
    assert edit_waiting.type == "CONFIRMATION_EDIT"
    assert edit_waiting.form_revision == 1
    assert task.version == before


@pytest.mark.asyncio
async def test_one_form_edit_advances_authority_version_by_exactly_one(confirmation_db, monkeypatch):
    """A2 part 2 / A3: one authorized form edit is exactly one authority advance."""
    session, factory, _permissions = confirmation_db
    task, _coordinator, _gate, original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)

    await _submit(
        session, factory, task=task, key="a3-open-edit",
        input_data={"kind": "request_edit", "text": None, "choice": None},
    )
    form = load_waiting(task)
    assert form.type == "CONFIRMATION_EDIT"
    version_before_edit = task.version
    old_fingerprint = load_authority(task).frozen_activity_command["fingerprint"]

    await _submit(
        session, factory, task=task, key="a3-submit-edit",
        input_data={
            "kind": "submit_form", "text": None, "choice": None,
            "values": {"next_follow_time": NEW_DATE}, "form_revision": form.form_revision,
        },
    )

    current = load_waiting(task)
    command = load_authority(task).frozen_activity_command
    assert current.type == "CONFIRMATION"
    assert command["next_follow_time"] == NEW_WAIT
    assert task.version == version_before_edit + 1, (
        f"one edit advanced {version_before_edit} -> {task.version} "
        f"(delta {task.version - version_before_edit}); expected +1"
    )
    assert current.expected_version == task.version
    assert command["fingerprint"] != old_fingerprint
    assert command["source_segments"][0] == original
    assert session.query(CustomerActivity).count() == 0


@pytest.mark.asyncio
async def test_stale_signed_card_after_edit_is_rejected(confirmation_db, monkeypatch):
    """A3: the pre-edit action id and version are no longer accepted."""
    session, factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    stale = load_waiting(task)

    await _submit(
        session, factory, task=task, key="a3-stale-open",
        input_data={"kind": "request_edit", "text": None, "choice": None},
    )
    form = load_waiting(task)
    await _submit(
        session, factory, task=task, key="a3-stale-edit",
        input_data={
            "kind": "submit_form", "text": None, "choice": None,
            "values": {"next_follow_time": NEW_DATE}, "form_revision": form.form_revision,
        },
    )

    with pytest.raises(turns.AssistantStateConflict):
        turns.accept_submit(
            session,
            task=task, key="a3-stale-confirm",
            input_data={"kind": "confirm", "text": None, "choice": "confirm"},
            action_id=stale.action_id,
            expected_version=stale.expected_version,
        )


@pytest.mark.asyncio
async def test_replayed_edit_request_neither_rescores_nor_advances_again(confirmation_db, monkeypatch):
    """A3: replaying one request key is idempotent and does not re-run the gate."""
    session, factory, _permissions = confirmation_db
    task, _coordinator, gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)

    await _submit(
        session, factory, task=task, key="a3-replay-open",
        input_data={"kind": "request_edit", "text": None, "choice": None},
    )
    form = load_waiting(task)
    turn, accepted = turns.accept_submit(
        session,
        task=task, key="a3-replay-edit",
        input_data={
            "kind": "submit_form", "text": None, "choice": None,
            "values": {"next_follow_time": NEW_DATE}, "form_revision": form.form_revision,
        },
        action_id=form.action_id,
        expected_version=form.expected_version,
    )
    assert accepted
    await turns.execute_turn(turn.id, factory=factory)
    session.expire_all()
    session.refresh(task)
    settled_version = task.version
    gate_calls = len(gate.calls)
    turn_count = session.query(AssistantTurn).filter_by(task_id=task.id).count()

    replay, accepted = turns.accept_submit(
        session,
        task=task, key="a3-replay-edit",
        input_data={
            "kind": "submit_form", "text": None, "choice": None,
            "values": {"next_follow_time": NEW_DATE}, "form_revision": form.form_revision,
        },
        action_id=form.action_id,
        expected_version=form.expected_version,
    )
    assert not accepted and replay.id == turn.id
    await turns.execute_turn(replay.id, factory=factory)
    session.expire_all()
    session.refresh(task)

    assert task.version == settled_version
    assert len(gate.calls) == gate_calls
    assert session.query(AssistantTurn).filter_by(task_id=task.id).count() == turn_count
    assert session.query(CustomerActivity).count() == 0


@pytest.mark.asyncio
async def test_no_op_edit_keeps_version_and_restores_read_only_card(confirmation_db, monkeypatch):
    """An edit that changes nothing must not advance the authority."""
    session, factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)

    await _submit(
        session, factory, task=task, key="a3-noop-open",
        input_data={"kind": "request_edit", "text": None, "choice": None},
    )
    form = load_waiting(task)
    version_before = task.version
    fingerprint_before = load_authority(task).frozen_activity_command["fingerprint"]
    unchanged = load_authority(task).frozen_activity_command["next_follow_time"][:10]

    await _submit(
        session, factory, task=task, key="a3-noop-edit",
        input_data={
            "kind": "submit_form", "text": None, "choice": None,
            "values": {"next_follow_time": unchanged}, "form_revision": form.form_revision,
        },
    )

    restored = load_waiting(task)
    assert restored.type == "CONFIRMATION"
    assert task.version == version_before
    assert load_authority(task).frozen_activity_command["fingerprint"] == fingerprint_before


@pytest.mark.asyncio
async def test_superseded_command_cannot_commit_or_write(confirmation_db, monkeypatch):
    """The old frozen command is replaced, and no CRM row appears from the edit."""
    session, factory, _permissions = confirmation_db
    task, _coordinator, _gate, _original = await persisted_temporal_confirmation(confirmation_db, monkeypatch)
    stale = load_waiting(task)
    stale_command = json.loads(json.dumps(load_authority(task).frozen_activity_command))

    await _submit(
        session, factory, task=task, key="a3-supersede-open",
        input_data={"kind": "request_edit", "text": None, "choice": None},
    )
    form = load_waiting(task)
    await _submit(
        session, factory, task=task, key="a3-supersede-edit",
        input_data={
            "kind": "submit_form", "text": None, "choice": None,
            "values": {"next_follow_time": NEW_DATE}, "form_revision": form.form_revision,
        },
    )

    assert stale_command["fingerprint"] != load_authority(task).frozen_activity_command["fingerprint"]
    with pytest.raises(turns.AssistantStateConflict):
        turns.accept_submit(
            session,
            task=task, key="a3-supersede-confirm",
            input_data={"kind": "confirm", "text": None, "choice": "confirm"},
            action_id=stale.action_id,
            expected_version=stale.expected_version,
        )
    assert session.query(CustomerActivity).count() == 0
