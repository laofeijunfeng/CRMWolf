from dataclasses import dataclass
from typing import Any

from app.services.follow_up_task_transition_plan_service import FollowUpTaskTransitionActionType
from app.services.follow_up_task_transition_policy_service import (
    DEFAULT_AUTO_TRANSITION_ACTIONS,
    FOLLOW_UP_TASK_AUTO_TRANSITION_ACTION_ALLOWLIST_KEY,
    FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY,
    FOLLOW_UP_TASK_AUTO_TRANSITION_OWNER_ALLOWLIST_KEY,
    FollowUpTaskTransitionPolicyService,
)


@dataclass
class _Config:
    config_value: str


class _ConfigCrud:
    def __init__(self, values: dict[str, Any]):
        self.values = values

    def get_config(self, _db, _team_id: int, config_key: str):
        value = self.values.get(config_key)
        if value is None:
            return None
        return _Config(config_value=value)


def _service(values: dict[str, Any]) -> FollowUpTaskTransitionPolicyService:
    return FollowUpTaskTransitionPolicyService(config_crud=_ConfigCrud(values))


def test_auto_transition_policy_is_disabled_when_config_missing():
    result = _service({}).is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )

    assert result.allowed is False
    assert result.reason == "CONFIG_MISSING_DISABLED"
    assert result.enabled is False


def test_auto_transition_policy_allows_team_when_enabled_without_owner_allowlist():
    result = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: "true",
    }).is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )

    assert result.allowed is True
    assert result.reason == "ALLOWED"
    assert result.owner_allowlist_configured is False
    assert result.allowed_actions == DEFAULT_AUTO_TRANSITION_ACTIONS


def test_auto_transition_policy_blocks_when_team_disabled():
    result = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: "false",
    }).is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )

    assert result.allowed is False
    assert result.reason == "TEAM_DISABLED"


def test_auto_transition_policy_respects_owner_allowlist():
    service = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: "true",
        FOLLOW_UP_TASK_AUTO_TRANSITION_OWNER_ALLOWLIST_KEY: '["2"]',
    })

    allowed = service.is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )
    blocked = service.is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="3",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert blocked.reason == "OWNER_NOT_ALLOWED"
    assert blocked.owner_allowlist_configured is True


def test_auto_transition_policy_respects_action_allowlist():
    service = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: "true",
        FOLLOW_UP_TASK_AUTO_TRANSITION_ACTION_ALLOWLIST_KEY: '["COMPLETE"]',
    })

    allowed = service.is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )
    blocked = service.is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.DELAY,
    )

    assert allowed.allowed is True
    assert allowed.allowed_actions == ("COMPLETE",)
    assert blocked.allowed is False
    assert blocked.reason == "ACTION_NOT_ALLOWED"


def test_auto_transition_policy_fails_closed_on_invalid_config_values():
    invalid_enabled = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: '"true"',
    }).is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )
    invalid_owner_allowlist = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: "true",
        FOLLOW_UP_TASK_AUTO_TRANSITION_OWNER_ALLOWLIST_KEY: '"2"',
    }).is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )
    unknown_action = _service({
        FOLLOW_UP_TASK_AUTO_TRANSITION_ENABLED_KEY: "true",
        FOLLOW_UP_TASK_AUTO_TRANSITION_ACTION_ALLOWLIST_KEY: '["ARCHIVE"]',
    }).is_auto_transition_allowed(
        None,
        team_id=1,
        owner_id="2",
        action=FollowUpTaskTransitionActionType.COMPLETE,
    )

    assert invalid_enabled.allowed is False
    assert invalid_enabled.reason == "CONFIG_INVALID"
    assert invalid_enabled.config_errors == ("follow_up_task_auto_transition_enabled:expected_bool",)
    assert invalid_owner_allowlist.allowed is False
    assert invalid_owner_allowlist.reason == "CONFIG_INVALID"
    assert invalid_owner_allowlist.config_errors == (
        "follow_up_task_auto_transition_owner_allowlist:expected_string_list",
    )
    assert unknown_action.allowed is False
    assert unknown_action.reason == "CONFIG_INVALID"
    assert unknown_action.config_errors == (
        "follow_up_task_auto_transition_action_allowlist:unknown_values:ARCHIVE",
    )
