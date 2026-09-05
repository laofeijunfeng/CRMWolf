"""Persistence and state transitions for durable user command outcomes."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.models.command_execution import CommandExecution, CommandExecutionStatus
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.command import CommandEffect, CommandNextAction, CommandResource


class CommandIdempotencyConflict(ValueError):
    """The same idempotency key was reused with a different request."""


class CommandAlreadyInProgress(ValueError):
    """A second request arrived while the first command is still pending."""


class CommandOperationConflict(ValueError):
    """The supplied operation id is already owned by another command."""


def request_fingerprint(payload: object) -> str:
    """Create a deterministic hash without persisting the raw request body."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


class CommandExecutionService:
    def new_operation_id(self) -> str:
        return f"op_{uuid4().hex}"

    def begin(
        self,
        db: Session,
        *,
        team_id: int,
        actor_id: str,
        command_type: str,
        resource_type: str | None = None,
        resource_public_id: str | None = None,
        operation_id: str | None = None,
        idempotency_key: str | None = None,
        fingerprint: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[CommandExecution, bool]:
        """Return ``(execution, is_replay)`` while keeping the caller's transaction.

        The idempotency key is scoped to a team.  A terminal execution is a
        replay; a pending execution is explicitly rejected so the client never
        creates a duplicate fact while the original result is unresolved.
        """
        normalized_operation_id = (operation_id or self.new_operation_id()).strip()
        normalized_key = idempotency_key.strip() if idempotency_key else None
        existing = None
        if normalized_key:
            existing = (
                db.query(CommandExecution)
                .filter(
                    CommandExecution.team_id == team_id,
                    CommandExecution.idempotency_key == normalized_key,
                )
                .first()
            )
        if existing is None and operation_id:
            existing = (
                db.query(CommandExecution)
                .filter(
                    CommandExecution.team_id == team_id,
                    CommandExecution.operation_id == normalized_operation_id,
                )
                .first()
            )
        if existing is not None:
            if fingerprint and existing.request_fingerprint and fingerprint != existing.request_fingerprint:
                raise CommandIdempotencyConflict("幂等键已用于其他请求")
            if existing.status == CommandExecutionStatus.PENDING:
                raise CommandAlreadyInProgress(existing.operation_id)
            return existing, True

        execution = CommandExecution(
            operation_id=normalized_operation_id,
            team_id=team_id,
            actor_id=actor_id,
            command_type=command_type,
            resource_type=resource_type,
            resource_public_id=resource_public_id,
            idempotency_key=normalized_key,
            request_fingerprint=fingerprint,
            status=CommandExecutionStatus.PENDING,
            correlation_id=correlation_id,
        )
        db.add(execution)
        try:
            db.flush()
        except IntegrityError:
            # Two requests can pass the read-before-write check at the same
            # time. The database uniqueness constraints are the final arbiter;
            # recover the committed winner instead of leaking a 500 or creating
            # a second business fact.
            db.rollback()
            winner = None
            if normalized_key:
                winner = (
                    db.query(CommandExecution)
                    .filter(
                        CommandExecution.team_id == team_id,
                        CommandExecution.idempotency_key == normalized_key,
                    )
                    .first()
                )
            if winner is None:
                winner = (
                    db.query(CommandExecution)
                    .filter(CommandExecution.operation_id == normalized_operation_id)
                    .first()
                )
            if winner is None:
                raise
            if winner.team_id != team_id:
                raise CommandOperationConflict("操作ID已被其他团队使用") from None
            if fingerprint and winner.request_fingerprint and fingerprint != winner.request_fingerprint:
                raise CommandIdempotencyConflict("幂等键已用于其他请求") from None
            if winner.status == CommandExecutionStatus.PENDING:
                raise CommandAlreadyInProgress(winner.operation_id) from None
            return winner, True
        return execution, False

    def succeed(
        self,
        db: Session,
        execution: CommandExecution,
        *,
        data: object = None,
        resource: CommandResource | None = None,
        effects: list[CommandEffect] | None = None,
        next_actions: list[CommandNextAction] | None = None,
        correlation_id: str | None = None,
    ) -> CommandExecution:
        execution.status = CommandExecutionStatus.SUCCEEDED
        execution.result_json = {
            "data": data,
            "resource": resource.model_dump() if resource else None,
            "effects": [effect.model_dump() for effect in effects or []],
            "next_actions": [action.model_dump() for action in next_actions or []],
        }
        execution.error_code = None
        execution.error_message = None
        execution.retryable = False
        execution.correlation_id = correlation_id or execution.correlation_id
        execution.completed_time = business_now()
        db.flush()
        return execution

    def fail(
        self,
        db: Session,
        execution: CommandExecution,
        *,
        status: str = CommandExecutionStatus.FAILED,
        error_code: str = "COMMAND_FAILED",
        error_message: str = "操作失败",
        retryable: bool = False,
    ) -> CommandExecution:
        # A late cleanup/refresh failure must never overwrite a terminal
        # outcome that was already committed.  In particular, if the business
        # transaction committed and a post-commit operation raised, the
        # recovery path may call ``fail`` with UNKNOWN; preserving the
        # terminal record keeps the operation query truthful and idempotent.
        if execution.status in CommandExecutionStatus.TERMINAL:
            return execution

        execution.status = status
        execution.result_json = None
        execution.error_code = error_code
        execution.error_message = error_message
        execution.retryable = retryable
        execution.completed_time = business_now()
        db.flush()
        return execution

    def to_response_payload(self, execution: CommandExecution) -> dict[str, object]:
        result = execution.result_json if isinstance(execution.result_json, dict) else {}
        error = None
        if execution.error_code:
            error = {
                "code": execution.error_code,
                "message": execution.error_message or "操作失败",
            }
        return {
            "operation_id": execution.operation_id,
            "status": execution.status,
            "command_type": execution.command_type,
            "resource": result.get("resource"),
            "data": result.get("data"),
            "effects": result.get("effects", []),
            "next_actions": result.get("next_actions", []),
            "retryable": bool(execution.retryable),
            "queryable": True,
            "error": error,
            "correlation_id": execution.correlation_id,
            "created_time": execution.created_time,
            "updated_time": execution.updated_time,
            "completed_time": execution.completed_time,
        }


command_execution_service = CommandExecutionService()
