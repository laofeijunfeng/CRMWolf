from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.crud import opportunity as opportunity_module
from app.models.opportunity import OpportunityStatus
from app.schemas.opportunity import OpportunityLose


def _won_opportunity() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        team_id=7,
        status=OpportunityStatus.WON.value,
        actual_amount=1000,
        actual_closing_date=SimpleNamespace(isoformat=lambda: "2026-07-09"),
        loss_reason=None,
        win_probability=100,
        version=3,
        customer_id=21,
        opportunity_name="赢单商机",
        total_amount=1000,
    )

def _db() -> Mock:
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(account_name="客户甲")
    return db

def _patch_loss_dependencies(monkeypatch: pytest.MonkeyPatch, opportunity: SimpleNamespace) -> Mock:
    monkeypatch.setattr(opportunity_module, "_lock_opportunity", lambda db, opportunity_id, team_id=None: opportunity)
    monkeypatch.setattr(
        "app.crud.user.user_crud.get_by_id",
        lambda db, operator_id: SimpleNamespace(name="销售一号"),
    )
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service.mark_lost", Mock())
    monkeypatch.setattr("app.services.operation_log_service.operation_log_service.log", Mock())
    from app.crud.contract import contract_crud
    return contract_crud


def test_won_opportunity_without_active_contract_can_be_marked_lost(monkeypatch: pytest.MonkeyPatch):
    opportunity = _won_opportunity()
    contract_crud = _patch_loss_dependencies(monkeypatch, opportunity)
    monkeypatch.setattr(contract_crud, "has_active_contract_for_opportunity", lambda db, opportunity_id, team_id: False)

    result = opportunity_module.opportunity_crud.mark_as_lost(
        _db(), opportunity, OpportunityLose(loss_reason="客户预算调整"), "9"
    )

    assert result.status == OpportunityStatus.LOST.value
    assert result.loss_reason == "客户预算调整"
    assert result.win_probability == 0
    assert result.actual_amount is None
    assert result.actual_closing_date is None
    assert result.version == 4


def test_won_opportunity_with_any_active_contract_is_rejected(monkeypatch: pytest.MonkeyPatch):
    opportunity = _won_opportunity()
    contract_crud = _patch_loss_dependencies(monkeypatch, opportunity)
    monkeypatch.setattr(contract_crud, "has_active_contract_for_opportunity", lambda db, opportunity_id, team_id: True)

    with pytest.raises(ValueError, match="已有合同"):
        opportunity_module.opportunity_crud.mark_as_lost(
            _db(), opportunity, OpportunityLose(loss_reason="客户预算调整"), "9"
        )

    assert opportunity.status == OpportunityStatus.WON.value
    assert opportunity.loss_reason is None
    assert opportunity.version == 3


def test_following_opportunity_can_be_marked_lost(monkeypatch: pytest.MonkeyPatch):
    opportunity = _won_opportunity()
    opportunity.status = OpportunityStatus.FOLLOWING.value
    contract_crud = _patch_loss_dependencies(monkeypatch, opportunity)
    monkeypatch.setattr(contract_crud, "has_active_contract_for_opportunity", lambda db, opportunity_id, team_id: True)

    result = opportunity_module.opportunity_crud.mark_as_lost(
        _db(), opportunity, OpportunityLose(loss_reason="客户预算调整"), "9"
    )

    assert result.status == OpportunityStatus.LOST.value
    assert result.loss_reason == "客户预算调整"
    assert result.version == 4


def test_lost_opportunity_cannot_be_marked_lost_again(monkeypatch: pytest.MonkeyPatch):
    opportunity = _won_opportunity()
    opportunity.status = OpportunityStatus.LOST.value
    contract_crud = _patch_loss_dependencies(monkeypatch, opportunity)
    monkeypatch.setattr(contract_crud, "has_active_contract_for_opportunity", lambda db, opportunity_id, team_id: False)

    with pytest.raises(ValueError, match="已经是输单状态"):
        opportunity_module.opportunity_crud.mark_as_lost(
            _db(), opportunity, OpportunityLose(loss_reason="重复操作"), "9"
        )

    assert opportunity.loss_reason is None
    assert opportunity.version == 3
