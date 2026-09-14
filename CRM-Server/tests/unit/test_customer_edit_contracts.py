from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.customer import CustomerCreate, CustomerLicenseSnapshotUpdate, CustomerLifecycleStatusUpdate, CustomerUpdate


def test_lifecycle_status_update_requires_a_zero_or_one_target_and_version() -> None:
    payload = CustomerLifecycleStatusUpdate(status=1, expected_version=7)
    assert payload.status == 1
    assert payload.expected_version == 7


def test_lifecycle_status_update_rejects_lost_and_inactive_targets() -> None:
    with pytest.raises(ValidationError):
        CustomerLifecycleStatusUpdate(status=2, expected_version=1)
    with pytest.raises(ValidationError):
        CustomerLifecycleStatusUpdate(status=3, expected_version=1)


def test_license_snapshot_requires_type_when_expiry_exists() -> None:
    with pytest.raises(ValidationError):
        CustomerLicenseSnapshotUpdate(
            expected_version=4,
            license_type=None,
            license_expiry_date=date(2026, 12, 31),
        )


def test_license_snapshot_clears_type_when_expiry_is_empty() -> None:
    payload = CustomerLicenseSnapshotUpdate(
        expected_version=4,
        license_type="TRIAL",
        license_expiry_date=None,
    )
    assert payload.license_type is None
    assert payload.license_expiry_date is None


def test_customer_create_defaults_to_following_and_empty_license_snapshot() -> None:
    payload = CustomerCreate(account_name="客户 A", city="上海")
    assert payload.status == 0
    assert payload.license_type is None
    assert payload.license_expiry_date is None


def test_customer_create_accepts_initial_won_and_complete_license_snapshot() -> None:
    payload = CustomerCreate(
        account_name="客户 A",
        city="上海",
        status=1,
        license_type="TRIAL",
        license_expiry_date=date(2026, 12, 31),
    )
    assert payload.status == 1
    assert payload.license_type == "TRIAL"
    assert payload.license_expiry_date == date(2026, 12, 31)


def test_customer_create_rejects_expiry_without_license_type() -> None:
    with pytest.raises(ValidationError, match="授权到期日期"):
        CustomerCreate(
            account_name="客户 A",
            city="上海",
            license_expiry_date=date(2026, 12, 31),
        )


def test_customer_create_normalizes_type_without_expiry_to_empty_snapshot() -> None:
    payload = CustomerCreate(account_name="客户 A", city="上海", license_type="TRIAL")
    assert payload.license_type is None
    assert payload.license_expiry_date is None


def test_customer_update_accepts_partial_license_fields_for_database_pair_resolution() -> None:
    payload = CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1))
    assert payload.license_expiry_date == date(2027, 1, 1)
    assert "license_expiry_date" in payload.model_fields_set
    assert "license_type" not in payload.model_fields_set


def test_customer_update_rejects_status_two_and_three() -> None:
    with pytest.raises(ValidationError):
        CustomerUpdate(status=2)
    with pytest.raises(ValidationError):
        CustomerUpdate(status=3)
