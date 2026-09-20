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
