"""Activity writes remain valid without a customer-profile receipt."""

from __future__ import annotations

import pytest

from app.services.agent.durable_work_contracts import CustomerActivityDurableWorkReceipt
from app.services.agent.tools.service import CRMAgentToolService


def test_activity_receipt_accepts_missing_profile_request() -> None:
    receipt = CustomerActivityDurableWorkReceipt(
        activity_id=241,
        post_commit_job_public_id="pcj_async_001",
        customer_intelligence_request_id=None,
    )

    assert receipt.activity_id == 241
    assert receipt.post_commit_job_public_id == "pcj_async_001"
    assert receipt.customer_intelligence_request_id is None


def test_activity_response_without_profile_request_is_valid() -> None:
    receipt = CRMAgentToolService._customer_activity_durable_work_receipt(
        {
            "id": 241,
            "durable_work": {
                "activity_revision": 1,
                "post_commit_job_public_id": "pcj_async_001",
                "customer_intelligence_request_id": None,
            },
        }
    )

    assert receipt.customer_intelligence_request_id is None


def test_activity_response_still_requires_task_reconciliation_receipt() -> None:
    with pytest.raises(ValueError, match="跟进任务对账回执"):
        CRMAgentToolService._customer_activity_durable_work_receipt(
            {
                "id": 241,
                "durable_work": {
                    "activity_revision": 1,
                    "customer_intelligence_request_id": None,
                },
            }
        )
