"""Immutable correlation receipts written in the CRM target transaction."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.assistant_crm_effect import AssistantCRMEffect



@dataclass(frozen=True)
class AssistantCRMCommand:
    command_id: str
    team_id: int
    actor_id: int
    fingerprint: str
    expected_snapshot_id: int | None = None
    expected_version: int | None = None


class AssistantCRMFingerprintConflict(ValueError):
    """The same command ID was previously committed with different inputs."""


class AssistantCRMStaleTarget(ValueError):
    """The target changed since the command was frozen."""

class AssistantCRMNoEffect(ValueError):
    """Validation rejected before entering a CRM target transaction."""



def read_effect(db: Session, *, team_id: int, command_id: str, effect_kind: str) -> AssistantCRMEffect | None:
    """Only an exact target-commit receipt establishes attribution."""
    return db.query(AssistantCRMEffect).filter_by(
        team_id=team_id, command_id=command_id, effect_kind=effect_kind,
    ).one_or_none()


def checked_effect(db: Session, command: AssistantCRMCommand, effect_kind: str) -> AssistantCRMEffect | None:
    effects = db.query(AssistantCRMEffect).filter_by(
        team_id=command.team_id, command_id=command.command_id,
    ).all()
    if any(effect.fingerprint != command.fingerprint or effect.actor_id != command.actor_id for effect in effects):
        raise AssistantCRMFingerprintConflict("Assistant CRM command fingerprint or actor conflict")
    allowed_kinds = {"opportunity_stage", "opportunity_auto_won"} if effect_kind in {"opportunity_stage", "opportunity_auto_won"} else {effect_kind}
    if any(effect.effect_kind not in allowed_kinds for effect in effects):
        raise AssistantCRMFingerprintConflict("Assistant CRM command effect kind conflict")
    return next((effect for effect in effects if effect.effect_kind == effect_kind), None)


def record_effect(
    db: Session, command: AssistantCRMCommand, effect_kind: str, *,
    target_public_id: str, approval_id: int | None = None,
    stage_snapshot_id: int | None = None, previous_snapshot_id: int | None = None,
    previous_version: int | None = None, resulting_version: int | None = None,
) -> AssistantCRMEffect:
    effect = AssistantCRMEffect(
        team_id=command.team_id, command_id=command.command_id, effect_kind=effect_kind,
        actor_id=command.actor_id, fingerprint=command.fingerprint,
        target_public_id=target_public_id, approval_id=approval_id,
        stage_snapshot_id=stage_snapshot_id, previous_snapshot_id=previous_snapshot_id,
        previous_version=previous_version, resulting_version=resulting_version,
    )
    db.add(effect)
    db.flush()  # Enforce unique correlation before the target commits.
    return effect
