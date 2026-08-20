from __future__ import annotations

from datetime import date

from sqlalchemy import case

LICENSE_STATUS_NONE = "none"
LICENSE_STATUS_EXPIRED = "expired"
LICENSE_STATUS_TRIAL = "trial"
LICENSE_STATUS_OFFICIAL = "official"

LICENSE_STATUS_VALUES = (
    LICENSE_STATUS_NONE,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_TRIAL,
    LICENSE_STATUS_OFFICIAL,
)


def classify_license_status(
    expiry_date: date | None,
    license_type: str | None,
    today: date,
) -> str:
    if expiry_date is None:
        return LICENSE_STATUS_NONE
    if expiry_date < today:
        return LICENSE_STATUS_EXPIRED
    if license_type == "TRIAL":
        return LICENSE_STATUS_TRIAL
    return LICENSE_STATUS_OFFICIAL


def license_status_expression(expiry_column, type_column, today: date):
    return case(
        (expiry_column.is_(None), LICENSE_STATUS_NONE),
        (expiry_column < today, LICENSE_STATUS_EXPIRED),
        (type_column == "TRIAL", LICENSE_STATUS_TRIAL),
        else_=LICENSE_STATUS_OFFICIAL,
    )
