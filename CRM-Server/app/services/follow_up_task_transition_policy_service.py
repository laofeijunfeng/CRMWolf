"""Policy gate for automatic follow-up task transitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.crud.system_config import system_config_crud
from app.models.system_config import ConfigType
from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionActionType

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.system_config import SystemConfig


FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY = "follow_up_task_auto_transition_enabled"
FOLLOW_UP_TASK_AUTO_TRANSITION_OWNER_ALLOWLIST_KEY = "follow_up_task_auto_transition_owner_allowlist"
FOLLOW_UP_TASK_AUTO_TRANSITION_ACTION_ALLOWLIST_KEY = "follow_up_task_auto_transition_action_allowlist"

DEFAULT_AUTO_TRANSITION_ACTIONS = (
    FollowUpTaskTransitionActionType.COMPLETE,
    FollowUpTaskTransitionActionType.DELAY,
    FollowUpTaskTransitionActionType.CANCEL,
)


class SystemConfigCrudProtocol(Protocol):
    def get_config(self, db: Session, team_id: int, config_key: str) -> SystemConfig | None: ...


@dataclass(frozen=True)
class FollowUpTaskTransitionPolicyResult:
    """Decision explaining whether an automatic transition may run."""

    allowed: bool
    reason: str
    team_id: int
    action: str | None
    enabled: bool
    owner_allowlist_configured: bool
    allowed_actions: tuple[str, ...]
    config_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "team_id": self.team_id,
            "action": self.action,
            "enabled": self.enabled,
            "owner_allowlist_configured": self.owner_allowlist_configured,
            "allowed_actions": list(self.allowed_actions),
            "config_errors": list(self.config_errors),
        }


class FollowUpTaskTransitionPolicyService:
    """Reads team configuration and fails closed for unsafe automation."""

    supported_actions = frozenset(DEFAULT_AUTO_TRANSITION_ACTIONS)

    def __init__(
        self,
        *,
        config_crud: SystemConfigCrudProtocol = system_config_crud,
    ) -> None:
        self.config_crud = config_crud

    def is_auto_transition_allowed(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        action: str | None,
    ) -> FollowUpTaskTransitionPolicyResult:
        enabled_value, enabled_error, enabled_present = self._read_config(
            db,
            team_id=team_id,
            config_key=FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY,
        )
        if enabled_error:
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=False,
                reason="CONFIG_INVALID",
                errors=(enabled_error,),
            )
        if not enabled_present:
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=False,
                reason="CONFIG_MISSING_DISABLED",
            )
        if not isinstance(enabled_value, bool):
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=False,
                reason="CONFIG_INVALID",
                errors=(f"{FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY}:expected_bool",),
            )
        if not enabled_value:
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=False,
                reason="TEAM_DISABLED",
            )

        owner_allowlist, owner_error, owner_allowlist_configured = self._owner_allowlist(db, team_id=team_id)
        action_allowlist, action_error = self._action_allowlist(db, team_id=team_id)
        config_errors = tuple(error for error in (owner_error, action_error) if error)
        if config_errors:
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=True,
                reason="CONFIG_INVALID",
                owner_allowlist_configured=owner_allowlist_configured,
                allowed_actions=action_allowlist,
                errors=config_errors,
            )

        if owner_allowlist_configured and (not owner_id or owner_id not in owner_allowlist):
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=True,
                reason="OWNER_NOT_ALLOWED",
                owner_allowlist_configured=True,
                allowed_actions=action_allowlist,
            )

        if action and action not in action_allowlist:
            return self._blocked(
                team_id=team_id,
                action=action,
                enabled=True,
                reason="ACTION_NOT_ALLOWED",
                owner_allowlist_configured=owner_allowlist_configured,
                allowed_actions=action_allowlist,
            )

        return FollowUpTaskTransitionPolicyResult(
            allowed=True,
            reason="ALLOWED",
            team_id=team_id,
            action=action,
            enabled=True,
            owner_allowlist_configured=owner_allowlist_configured,
            allowed_actions=action_allowlist,
        )

    def automation_config_type(self) -> str:
        return ConfigType.AUTOMATION.value

    def _owner_allowlist(
        self,
        db: Session,
        *,
        team_id: int,
    ) -> tuple[tuple[str, ...], str | None, bool]:
        value, error, present = self._read_config(
            db,
            team_id=team_id,
            config_key=FOLLOW_UP_TASK_AUTO_TRANSITION_OWNER_ALLOWLIST_KEY,
        )
        if error or not present:
            return (), error, present
        parsed, parse_error = self._parse_string_list(
            value,
            config_key=FOLLOW_UP_TASK_AUTO_TRANSITION_OWNER_ALLOWLIST_KEY,
            allowed_values=None,
        )
        return parsed, parse_error, True

    def _action_allowlist(self, db: Session, *, team_id: int) -> tuple[tuple[str, ...], str | None]:
        value, error, present = self._read_config(
            db,
            team_id=team_id,
            config_key=FOLLOW_UP_TASK_AUTO_TRANSITION_ACTION_ALLOWLIST_KEY,
        )
        if error:
            return (), error
        if not present:
            return DEFAULT_AUTO_TRANSITION_ACTIONS, None
        return self._parse_string_list(
            value,
            config_key=FOLLOW_UP_TASK_AUTO_TRANSITION_ACTION_ALLOWLIST_KEY,
            allowed_values=self.supported_actions,
        )

    def _parse_string_list(
        self,
        value: object,
        *,
        config_key: str,
        allowed_values: frozenset[str] | None,
    ) -> tuple[tuple[str, ...], str | None]:
        if not isinstance(value, list):
            return (), f"{config_key}:expected_string_list"
        if not all(isinstance(item, str) and item for item in value):
            return (), f"{config_key}:expected_string_list"
        deduped = tuple(dict.fromkeys(value))
        if allowed_values is not None:
            unknown = [item for item in deduped if item not in allowed_values]
            if unknown:
                return (), f"{config_key}:unknown_values:{','.join(unknown)}"
        return deduped, None

    def _read_config(
        self,
        db: Session,
        *,
        team_id: int,
        config_key: str,
    ) -> tuple[Any, str | None, bool]:
        config = self.config_crud.get_config(db, team_id, config_key)
        if config is None:
            return None, None, False
        try:
            return json.loads(config.config_value), None, True
        except (TypeError, json.JSONDecodeError):
            return None, f"{config_key}:invalid_json", True

    def _blocked(
        self,
        *,
        team_id: int,
        action: str | None,
        enabled: bool,
        reason: str,
        owner_allowlist_configured: bool = False,
        allowed_actions: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> FollowUpTaskTransitionPolicyResult:
        return FollowUpTaskTransitionPolicyResult(
            allowed=False,
            reason=reason,
            team_id=team_id,
            action=action,
            enabled=enabled,
            owner_allowlist_configured=owner_allowlist_configured,
            allowed_actions=allowed_actions,
            config_errors=errors,
        )


follow_up_task_transition_policy_service = FollowUpTaskTransitionPolicyService()
