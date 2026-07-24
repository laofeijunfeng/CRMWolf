from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import contracts as contracts_api


class _ContractCrud:
    def __init__(self, contract):
        self.contract = contract

    def get_by_opportunity_id(self, db, opportunity_id, team_id):
        return self.contract


class _OpportunityCrud:
    def __init__(self, opportunity):
        self.opportunity = opportunity

    def get_by_id(self, db, opportunity_id, team_id):
        return self.opportunity


def test_get_contract_by_opportunity_returns_null_when_no_contract(monkeypatch):
    monkeypatch.setattr(contracts_api, "contract_crud", _ContractCrud(None))
    monkeypatch.setattr(
        contracts_api,
        "opportunity_crud",
        _OpportunityCrud(SimpleNamespace(id=12, opportunity_name="测试商机")),
    )

    result = contracts_api.get_contract_by_opportunity(
        opportunity_id=12,
        team_id=1,
        current_user=SimpleNamespace(id="1"),
        db=SimpleNamespace(),
    )

    assert result is None


def test_get_contract_by_opportunity_raises_404_when_opportunity_missing(monkeypatch):
    monkeypatch.setattr(contracts_api, "contract_crud", _ContractCrud(None))
    monkeypatch.setattr(contracts_api, "opportunity_crud", _OpportunityCrud(None))

    with pytest.raises(HTTPException) as exc_info:
        contracts_api.get_contract_by_opportunity(
            opportunity_id=99999,
            team_id=1,
            current_user=SimpleNamespace(id="1"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "商机不存在"
