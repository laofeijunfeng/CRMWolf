from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.customer import CustomerLicenseSnapshotUpdate, CustomerLifecycleStatusUpdate


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
