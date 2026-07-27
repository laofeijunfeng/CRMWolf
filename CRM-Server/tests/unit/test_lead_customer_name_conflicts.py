from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import customers as customer_api
from app.api import leads as lead_api


def test_lead_name_conflict_rejects_same_team_lead(monkeypatch):
    monkeypatch.setattr(
        lead_api.lead_crud,
        "get_by_name",
        lambda db, lead_name, team_id: SimpleNamespace(id=1, lead_name=lead_name),
    )
    monkeypatch.setattr(lead_api.customer_crud, "get_by_name", lambda db, account_name, team_id: None)

    with pytest.raises(HTTPException) as exc_info:
        lead_api._ensure_lead_name_available(object(), "测试科技", 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "线索名称已存在"


def test_lead_name_conflict_rejects_same_team_customer(monkeypatch):
    monkeypatch.setattr(lead_api.lead_crud, "get_by_name", lambda db, lead_name, team_id: None)
    monkeypatch.setattr(
        lead_api.customer_crud,
        "get_by_name",
        lambda db, account_name, team_id: SimpleNamespace(id=1, account_name=account_name),
    )

    with pytest.raises(HTTPException) as exc_info:
        lead_api._ensure_lead_name_available(object(), "测试科技", 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "该名称已存在客户，请直接在客户下跟进"


def test_lead_name_check_does_not_use_contact_phone(monkeypatch):
    monkeypatch.setattr(lead_api.lead_crud, "get_by_name", lambda db, lead_name, team_id: None)
    monkeypatch.setattr(lead_api.customer_crud, "get_by_name", lambda db, account_name, team_id: None)
    monkeypatch.setattr(
        lead_api.lead_crud,
        "get_by_contact_phone",
        lambda *args, **kwargs: pytest.fail("phone duplicate check should not run"),
    )

    lead_api._ensure_lead_name_available(object(), "测试科技", 1)


def test_customer_name_conflict_rejects_same_team_customer(monkeypatch):
    monkeypatch.setattr(
        customer_api.customer_crud,
        "get_by_name",
        lambda db, account_name, team_id: SimpleNamespace(id=1, account_name=account_name),
    )
    monkeypatch.setattr(customer_api.lead_crud, "get_by_name", lambda db, lead_name, team_id: None)
    monkeypatch.setattr(customer_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: None)

    with pytest.raises(HTTPException) as exc_info:
        customer_api._ensure_customer_name_available(object(), "测试科技", 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "客户名称已存在"


def test_customer_name_conflict_rejects_same_team_lead(monkeypatch):
    monkeypatch.setattr(customer_api.customer_crud, "get_by_name", lambda db, account_name, team_id: None)
    monkeypatch.setattr(
        customer_api.lead_crud,
        "get_by_name",
        lambda db, lead_name, team_id: SimpleNamespace(id=2, lead_name=lead_name),
    )
    monkeypatch.setattr(customer_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: None)

    with pytest.raises(HTTPException) as exc_info:
        customer_api._ensure_customer_name_available(object(), "测试科技", 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "该名称已存在线索，请先处理或转化线索"


def test_customer_name_check_allows_source_lead_during_conversion(monkeypatch):
    monkeypatch.setattr(customer_api.customer_crud, "get_by_name", lambda db, account_name, team_id: None)
    monkeypatch.setattr(
        customer_api.lead_crud,
        "get_by_name",
        lambda db, lead_name, team_id: SimpleNamespace(id=2, lead_name=lead_name),
    )
    monkeypatch.setattr(customer_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: None)

    customer_api._ensure_customer_name_available(
        object(),
        "测试科技",
        1,
        allowed_source_lead_id=2,
    )


def test_customer_name_check_uses_team_scope(monkeypatch):
    seen_team_ids = []

    def customer_lookup(db, account_name, team_id):
        seen_team_ids.append(team_id)
        return None

    def lead_lookup(db, lead_name, team_id):
        seen_team_ids.append(team_id)
        return None

    monkeypatch.setattr(customer_api.customer_crud, "get_by_name", customer_lookup)
    monkeypatch.setattr(customer_api.lead_crud, "get_by_name", lead_lookup)
    monkeypatch.setattr(customer_api.customer_crud, "get_by_id", lambda db, customer_id, team_id: None)

    customer_api._ensure_customer_name_available(object(), "测试科技", 99)

    assert seen_team_ids == [99, 99]
