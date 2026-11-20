"""CRM-148 permanent OFFICIAL License: application term rules and export text."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.core.list_query.license_status import license_expiry_text
from app.schemas.license_application import LicenseApplicationCreate

TOMORROW = date.today() + timedelta(days=1)


def _create(**overrides: object) -> LicenseApplicationCreate:
    values: dict[str, object] = {
        "customer_id": "cus-1",
        "license_type": "OFFICIAL",
        "authorized_users": 10,
        "contract_id": 1,
    }
    values.update(overrides)
    return LicenseApplicationCreate(**values)


def test_permanent_official_drops_submitted_expiry_date() -> None:
    application = _create(is_permanent=True, expiry_date=TOMORROW)

    assert application.is_permanent is True
    assert application.expiry_date is None


def test_permanent_trial_is_rejected() -> None:
    with pytest.raises(ValidationError, match="试用 License 不能设为永久"):
        _create(license_type="TRIAL", contract_id=None, is_permanent=True)


@pytest.mark.parametrize("expiry_date", [None, date.today()])
def test_trial_requires_future_expiry_date(expiry_date: date | None) -> None:
    with pytest.raises(ValidationError, match="试用 License 必须填到期日期，且要晚于今天。"):
        _create(license_type="TRIAL", contract_id=None, expiry_date=expiry_date)


@pytest.mark.parametrize("expiry_date", [None, date.today()])
def test_non_permanent_official_requires_future_expiry_date(expiry_date: date | None) -> None:
    with pytest.raises(ValidationError, match="到期时间必须晚于今天"):
        _create(expiry_date=expiry_date)


def test_permanent_official_still_requires_contract() -> None:
    with pytest.raises(ValidationError, match="正式版 License 必须关联合同"):
        _create(contract_id=None, is_permanent=True)


def test_license_expiry_text_shows_permanent_date_or_empty() -> None:
    assert license_expiry_text(None, True) == "永久"
    assert license_expiry_text(date(2027, 3, 4), False) == "2027-03-04"
    assert license_expiry_text(None, False) is None
