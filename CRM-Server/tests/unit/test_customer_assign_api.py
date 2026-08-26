from datetime import datetime
from types import SimpleNamespace

from app.api import customers as customers_api
from app.models.customer import Customer
from app.schemas.customer import CustomerAssignRequest


def test_assign_customer_projects_source_lead_public_id(monkeypatch):
    customer = Customer(
        id=23,
        public_id="cus_test",
        team_id=1,
        account_name="测试客户",
        city="上海",
        status=0,
        owner_id="1",
        source_lead_id=67,
        creator_id="1",
        created_time=datetime(2026, 8, 26, 9, 0, 0),
        last_modified_time=datetime(2026, 8, 26, 9, 0, 0),
        version=1,
    )
    source_lead = SimpleNamespace(id=67, public_id="lead_test", team_id=1)

    monkeypatch.setattr(customers_api.user_crud, "get_by_id", lambda db, user_id: SimpleNamespace(id=user_id))
    monkeypatch.setattr(customers_api.team_crud, "is_member", lambda db, team_id, user_id: True)
    monkeypatch.setattr(customers_api, "_get_customer_or_404", lambda db, customer_id, team_id: customer)
    monkeypatch.setattr(customers_api.lead_crud, "get_by_id", lambda db, lead_id, team_id: source_lead)

    def assign_customer(db, assigned_customer, owner_id, team_id, opportunity_transfer_scope):
        assigned_customer.owner_id = owner_id
        return assigned_customer, 2, 1

    monkeypatch.setattr(customers_api.customer_crud, "assign_customer", assign_customer)

    response = customers_api.assign_customer(
        customer_id="cus_test",
        assign_data=CustomerAssignRequest(owner_id="2", opportunity_transfer_scope="all"),
        team_id=1,
        _current_user=SimpleNamespace(id=1),
        db=SimpleNamespace(),
    )

    assert response.customer.id == "cus_test"
    assert response.customer.owner_id == "2"
    assert response.customer.source_lead_id == "lead_test"
    assert response.transferred_opportunities == 2
    assert response.transferred_contracts == 1
