"""Unified business-journey visibility contract tests."""
from __future__ import annotations

from app.constants.approval_phase import ApprovalPhase
from test_business_journeys_api import api_env, seed_customer_member, seed_journey


def test_sales_member_lists_own_journey_without_dashboard_permission(api_env):
    journey = seed_journey(api_env, customer_owner="1", opportunity_owner="1")
    api_env.permissions = ["customer:view:own", "opportunity:view:own"]

    response = api_env.client.get("/v1/business-journeys")

    assert response.status_code == 200
    assert [item["public_id"] for item in response.json()["items"]] == [journey.public_id]


def test_customer_member_can_see_shared_customer_journey(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    seed_customer_member(api_env, customer_id=journey.customer_id, user_id="1", access_level="VIEW")
    api_env.permissions = []

    response = api_env.client.get("/v1/business-journeys")

    assert response.status_code == 200
    assert journey.public_id in {item["public_id"] for item in response.json()["items"]}



def test_opportunity_owner_can_open_detail_without_customer_view(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="1")
    api_env.permissions = ["opportunity:view:own"]

    response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert response.status_code == 200, response.text
    assert response.json()["journey"]["public_id"] == journey.public_id


def test_customer_owner_can_open_detail_without_opportunity_view(api_env):
    journey = seed_journey(api_env, customer_owner="1", opportunity_owner="2")
    api_env.permissions = ["customer:view:own"]

    response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert response.status_code == 200, response.text
    assert response.json()["journey"]["public_id"] == journey.public_id


def test_customer_member_can_open_detail_without_customer_or_opportunity_permission(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    seed_customer_member(api_env, customer_id=journey.customer_id, user_id="1", access_level="VIEW")
    api_env.permissions = []

    response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert response.status_code == 200, response.text
    assert response.json()["journey"]["public_id"] == journey.public_id


def test_unrelated_detail_returns_404_without_existence_leak(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    visible = seed_journey(api_env, customer_owner="1", opportunity_owner="2")
    api_env.permissions = ["customer:view:own"]

    visible_response = api_env.client.get(f"/v1/business-journeys/{visible.public_id}")
    hidden_response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert visible_response.status_code == 200, visible_response.text
    assert hidden_response.status_code == 404
    assert hidden_response.json()["detail"] == "业务旅程不存在"


def test_detail_no_relevant_permission_or_membership_returns_existing_403(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    api_env.permissions = []

    response = api_env.client.get(f"/v1/business-journeys/{journey.public_id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "缺少业务旅程查看权限"

def test_no_relevant_permission_or_membership_returns_403(api_env):
    seed_journey(api_env, approval_phase=ApprovalPhase.DRAFT.value)
    api_env.permissions = []

    response = api_env.client.get("/v1/business-journeys")

    assert response.status_code == 403
    assert response.json()["detail"] == "缺少业务旅程查看权限"


def test_inactive_or_insufficient_membership_returns_403(api_env):
    journey = seed_journey(api_env, customer_owner="2", opportunity_owner="2")
    seed_customer_member(
        api_env,
        customer_id=journey.customer_id,
        user_id="1",
        access_level="VIEW",
        is_active=False,
    )
    api_env.permissions = []

    response = api_env.client.get("/v1/business-journeys/board")

    assert response.status_code == 403
    assert response.json()["detail"] == "缺少业务旅程查看权限"
