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
    monkeypatch.setattr(customers_api, "derive_customer_statuses_for_list", lambda _db, _team_id, _customers: {})

    def assign_customer(db, assigned_customer, owner_id, team_id, opportunity_transfer_scope, *, return_details=False):
        assert return_details is True
        assigned_customer.owner_id = owner_id
        return {
            "customer": assigned_customer,
            "previous_owner_id": "1",
            "new_owner_id": owner_id,
            "transferred_opportunities": 2,
            "transferred_contracts": 1,
            "updated_objects": [],
            "skipped_objects": [{"type": "contract", "id": "con_locked"}],
        }

    notifications = []
    monkeypatch.setattr(customers_api.customer_crud, "assign_customer", assign_customer)
    monkeypatch.setattr(
        customers_api, "queue_customer_transfer_notifications", lambda db, **kwargs: notifications.append(kwargs)
    )

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
    assert len(notifications) == 1
    sent = notifications[0]
    assert (sent["previous_owner_id"], sent["new_owner_id"], sent["transfer_scope"]) == ("1", "2", "all")
    assert (sent["transferred_opportunities"], sent["transferred_contracts"], sent["locked_contracts"]) == (2, 1, 1)
    assert sent["customer"] is customer
