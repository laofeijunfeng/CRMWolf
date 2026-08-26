"""Resolve server-owned entity actions into canonical Root runtime input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.agent.query.result_sets import (
    AgentQueryResultSetRepository,
    ResultSetExpiredError,
    ResultSetNotFoundError,
)
from app.services.customer_activity_access_policy import (
    CustomerActivityAccessDeniedError,
    CustomerActivityAccessPolicy,
    CustomerActivityCustomerNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.agent_persistence import AgentUIActionRecord
    from app.services.agent.query import EntityRef


class EntityActionResolutionError(ValueError):
    """Base error for a server-owned entity action that cannot be resolved."""


class EntityActionInvalidError(EntityActionResolutionError):
    """The persisted action target and immutable result set do not agree."""


class EntityActionResultSetExpiredError(EntityActionResolutionError):
    """The immutable result set referenced by the action is no longer active."""


class EntityActionPermissionDeniedError(EntityActionResolutionError):
    """The current user no longer has permission to perform the requested workflow."""


class _StartCustomerWorkflowTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    workflow: Literal["create_follow_up_task"]
    result_set_id: str = Field(min_length=1, max_length=64)
    ref_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True)
class ResolvedEntityWorkflowAction:
    """Server-authorized text and entity reference for one Workflow start."""

    text: str
    selected_entity_ref: EntityRef


class AgentEntityActionResolver:
    """Validate result-set lineage and current CRM authorization behind one interface."""

    def __init__(
        self,
        *,
        result_set_repository: AgentQueryResultSetRepository | None = None,
        customer_activity_access_policy: CustomerActivityAccessPolicy | None = None,
    ) -> None:
        self._result_set_repository = result_set_repository or AgentQueryResultSetRepository()
        self._customer_activity_access_policy = (
            customer_activity_access_policy or CustomerActivityAccessPolicy()
        )

    def resolve_start_workflow(
        self,
        db: Session,
        *,
        action: AgentUIActionRecord,
        team_id: int,
        user_id: int,
        session_id: int,
        permission_codes: frozenset[str],
    ) -> ResolvedEntityWorkflowAction:
        target = self._target(action)
        try:
            result_set = self._result_set_repository.get_active(
                db,
                public_id=target.result_set_id,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            )
        except ResultSetExpiredError as exc:
            raise EntityActionResultSetExpiredError("result set expired") from exc
        except ResultSetNotFoundError as exc:
            raise EntityActionInvalidError("result set does not belong to the action owner") from exc

        if action.message_id != result_set.source_message_id:
            raise EntityActionInvalidError("action and result set source messages do not match")
        entity_ref = next(
            (ref for ref in result_set.ordered_entity_refs if ref.ref_id == target.ref_id),
            None,
        )
        if (
            entity_ref is None
            or entity_ref.result_set_id != result_set.public_id
            or entity_ref.resource != "customer"
            or result_set.resource != "customer"
        ):
            raise EntityActionInvalidError("action entity reference is not part of the result set")

        try:
            self._customer_activity_access_policy.resolve_customer(
                db,
                customer_identifier=entity_ref.public_id,
                team_id=team_id,
                user_id=user_id,
                permission_codes=permission_codes,
            )
        except CustomerActivityCustomerNotFoundError as exc:
            raise EntityActionInvalidError("referenced customer no longer exists") from exc
        except CustomerActivityAccessDeniedError as exc:
            raise EntityActionPermissionDeniedError(
                "current user cannot create customer follow-up tasks"
            ) from exc

        return ResolvedEntityWorkflowAction(
            text=target.label,
            selected_entity_ref=entity_ref,
        )

    @staticmethod
    def replay_start_workflow(action: AgentUIActionRecord) -> str:
        return AgentEntityActionResolver._target(action).label

    @staticmethod
    def _target(action: AgentUIActionRecord) -> _StartCustomerWorkflowTarget:
        if action.action_type != "start_workflow":
            raise EntityActionInvalidError("action is not a workflow action")
        try:
            return _StartCustomerWorkflowTarget.model_validate(action.target)
        except ValidationError as exc:
            raise EntityActionInvalidError("workflow action target is invalid") from exc
