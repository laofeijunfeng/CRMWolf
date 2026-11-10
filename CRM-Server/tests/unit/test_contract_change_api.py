"""Contract change API boundary: typed payloads and safe errors."""
import asyncio
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import contracts as api
from app.services.contract_change import ContractChangeError, ContractNotFoundError


def test_invalid_change_payload_does_not_reach_service(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("invalid request reached service")

    monkeypatch.setattr(api.contract_change_service, "create_request", unexpected)
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.create_contract_change(1, '{"new_amount":"0","reason":"扩容"}', None, 1, SimpleNamespace(id=7), SimpleNamespace()))
    assert error.value.status_code == 400


@pytest.mark.parametrize("exception,status", [(ContractNotFoundError("合同不存在"), 404), (ContractChangeError("已有一条变更在审批中"), 400)])
def test_change_errors_preserve_http_boundary(monkeypatch, exception, status):
    def reject(*args, **kwargs):
        raise exception

    monkeypatch.setattr(api.contract_change_service, "create_request", reject)
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.create_contract_change(1, '{"new_amount":"125.00","reason":"扩容"}', None, 1, SimpleNamespace(id=7), SimpleNamespace()))
    assert error.value.status_code == status
    assert error.value.detail == str(exception)


def test_create_response_exposes_immutable_change_not_storage_path(monkeypatch):
    def create(db, **kwargs):
        assert kwargs["new_amount"] == Decimal("125.00")
        return SimpleNamespace(
            id=3, contract_id=1, creator_id="7", reason="扩容",
            change_items_json=[{"key":"contract_amount", "old_value":"100.00", "new_value":"125.00"}],
            approval_phase="pending_review", attachment_name=None, attachment_size=None,
            attachment_mime_type=None, attachment_path="private/path", created_time=datetime(2026,11,10), updated_time=datetime(2026,11,10),
        )

    monkeypatch.setattr(api.contract_change_service, "create_request", create)
    result = asyncio.run(api.create_contract_change(1, '{"new_amount":"125.00","reason":"扩容"}', None, 1, SimpleNamespace(id=7), SimpleNamespace()))
    assert result.change_items[0].new_value == "125.00"
    assert "attachment_path" not in result.model_dump()


def test_history_permission_denial_stops_lookup(monkeypatch):
    def deny(*args):
        raise HTTPException(status_code=404, detail="合同不存在")

    def unexpected(*args):
        raise AssertionError("history queried without permission")

    monkeypatch.setattr(api, "check_contract_view_permission", deny)
    monkeypatch.setattr(api.contract_change_service, "list_history", unexpected)
    with pytest.raises(HTTPException) as error:
        api.list_contract_changes(1, 2, SimpleNamespace(id=7), SimpleNamespace())
    assert error.value.status_code == 404
