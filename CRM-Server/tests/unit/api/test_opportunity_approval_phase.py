from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from app.api.opportunities import _resolve_opportunity_approval_phase
from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.models.approval import ApprovalStatus


def test_opportunity_terminal_phase_is_authoritative_over_stale_approval():
    opportunity = SimpleNamespace(
        id=30,
        approval_phase=ApprovalPhase.REJECTED.value,
    )

    stale_approval = SimpleNamespace(status=ApprovalStatus.PENDING)

    with patch("app.crud.approval.approval_crud.get_by_entity", return_value=stale_approval) as get_by_entity:
        phase = _resolve_opportunity_approval_phase(Mock(), opportunity, team_id=2)

    assert phase == ApprovalPhase.REJECTED.value
    get_by_entity.assert_not_called()


def test_opportunity_draft_falls_back_to_existing_latest_approval():
    opportunity = SimpleNamespace(
        id=30,
        approval_phase=ApprovalPhase.DRAFT.value,
    )

    latest_approval = SimpleNamespace(status=ApprovalStatus.PENDING)

    with patch("app.crud.approval.approval_crud.get_by_entity", return_value=latest_approval) as get_by_entity:
        phase = _resolve_opportunity_approval_phase(Mock(), opportunity, team_id=2)

    assert phase == ApprovalPhase.PENDING_REVIEW.value
    get_by_entity.assert_called_once_with(ANY, BusinessType.OPPORTUNITY, 30, 2)


def test_opportunity_legacy_missing_phase_falls_back_to_latest_approval():
    opportunity = SimpleNamespace(
        id=30,
        approval_phase=None,
    )

    latest_approval = SimpleNamespace(status=ApprovalStatus.PENDING)

    with patch("app.crud.approval.approval_crud.get_by_entity", return_value=latest_approval) as get_by_entity:
        phase = _resolve_opportunity_approval_phase(Mock(), opportunity, team_id=2)

    assert phase == ApprovalPhase.PENDING_REVIEW.value
    get_by_entity.assert_called_once_with(ANY, BusinessType.OPPORTUNITY, 30, 2)
