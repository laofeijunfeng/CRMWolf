from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import deps


class _ContractCrud:
    def __init__(self, contract):
        self.contract = contract

    def get_by_id(self, db, contract_id, team_id):
        return self.contract


def _patch_contract_crud(monkeypatch, contract):
    import app.crud.contract as contract_module

    monkeypatch.setattr(contract_module, "contract_crud", _ContractCrud(contract))


def _patch_permissions(monkeypatch, codes):
    permissions = [SimpleNamespace(code=code) for code in codes]
    monkeypatch.setattr(
        deps.permission_crud,
        "get_user_permissions",
        lambda db, user_id, team_id: permissions,
    )


def test_contract_delete_own_uses_owner_id(monkeypatch):
    contract = SimpleNamespace(id=28, owner_id="2", creator_id="4")
    current_user = SimpleNamespace(id=2)
    _patch_contract_crud(monkeypatch, contract)
    _patch_permissions(monkeypatch, ["contract:delete:own"])

    result = deps.check_contract_delete_permission(
        contract_id=28,
        team_id=1,
        current_user=current_user,
        db=object(),
    )

    assert result is contract


def test_contract_edit_own_uses_owner_id(monkeypatch):
    contract = SimpleNamespace(id=28, owner_id="2", creator_id="4")
    current_user = SimpleNamespace(id=2)
    _patch_contract_crud(monkeypatch, contract)
    _patch_permissions(monkeypatch, ["contract:edit:own"])

    result = deps.check_contract_edit_permission(
        contract_id=28,
        team_id=1,
        current_user=current_user,
        db=object(),
    )

    assert result is contract


def test_contract_delete_own_rejects_other_owner(monkeypatch):
    contract = SimpleNamespace(id=28, owner_id="1", creator_id="2")
    current_user = SimpleNamespace(id=2)
    _patch_contract_crud(monkeypatch, contract)
    _patch_permissions(monkeypatch, ["contract:delete:own"])

    with pytest.raises(HTTPException) as exc_info:
        deps.check_contract_delete_permission(
            contract_id=28,
            team_id=1,
            current_user=current_user,
            db=object(),
        )

    assert exc_info.value.status_code == 403
