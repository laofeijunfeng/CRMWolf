"""Opportunity schema and derived field tests."""
from datetime import date

from app.crud.opportunity import opportunity_crud
from app.models.customer import Customer
from app.schemas.opportunity import LicenseTypeEnum, OpportunityCreate, PurchaseTypeEnum


def test_opportunity_create_allows_backend_generated_name():
    payload = OpportunityCreate(
        customer_id=101,
        total_amount=50000,
        user_count=100,
        license_type=LicenseTypeEnum.SUBSCRIPTION,
        subscription_years=1,
        purchase_type=PurchaseTypeEnum.NEW,
        expected_closing_date=date(2026, 8, 30),
    )

    assert payload.opportunity_name is None


def test_opportunity_name_generated_from_customer_and_license():
    payload = OpportunityCreate(
        customer_id=101,
        total_amount=50000,
        user_count=100,
        license_type=LicenseTypeEnum.SUBSCRIPTION,
        subscription_years=1,
        purchase_type=PurchaseTypeEnum.NEW,
        expected_closing_date=date(2026, 8, 30),
    )
    customer = Customer(id=101, account_name="广州睿狐科技有限公司")

    assert opportunity_crud._build_opportunity_name(payload, customer) == "广州睿狐科技有限公司-100人-订阅1年"
