"""Opportunity schema and derived field tests."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.crud.opportunity import opportunity_crud
from app.models.customer import Customer
from app.schemas.opportunity import LicenseTypeEnum, OpportunityCreate, OpportunityUpdate, PurchaseTypeEnum

PRODUCT_PUBLIC_ID = "prd_" + "a" * 32
MODULE_PUBLIC_ID = "prm_" + "b" * 32


def _create_payload(**overrides: object) -> OpportunityCreate:
    payload: dict[str, object] = {
        "customer_id": "cus_101",
        "total_amount": 50000,
        "user_count": 100,
        "license_type": LicenseTypeEnum.SUBSCRIPTION,
        "subscription_years": 1,
        "purchase_type": PurchaseTypeEnum.NEW,
        "expected_closing_date": date(2026, 8, 30),
        "product_public_id": PRODUCT_PUBLIC_ID,
        "product_module_public_ids": [MODULE_PUBLIC_ID],
    }
    payload.update(overrides)
    return OpportunityCreate(**payload)


def test_opportunity_create_allows_backend_generated_name():
    payload = _create_payload()

    assert payload.opportunity_name is None
    assert payload.product_public_id == PRODUCT_PUBLIC_ID
    assert payload.product_module_public_ids == [MODULE_PUBLIC_ID]


def test_opportunity_create_requires_product_and_at_least_one_module():
    with pytest.raises(ValidationError):
        _create_payload(product_public_id=None)

    with pytest.raises(ValidationError):
        _create_payload(product_module_public_ids=[])



def test_opportunity_create_splits_comma_separated_module_ids():
    payload = _create_payload(product_module_public_ids="prm_base, prm_pro")

    assert payload.product_module_public_ids == ["prm_base", "prm_pro"]


def test_opportunity_update_requires_modules_when_product_is_set():
    with pytest.raises(ValidationError):
        OpportunityUpdate(product_public_id=PRODUCT_PUBLIC_ID, product_module_public_ids=[])


def test_opportunity_name_generated_from_customer_and_license():
    payload = _create_payload()
    customer = Customer(id=101, account_name="广州睿狐科技有限公司")

    assert opportunity_crud._build_opportunity_name(payload, customer) == "广州睿狐科技有限公司-100人-订阅1年"
