from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import case

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import Case, SQLColumnExpression

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

LICENSE_PERMANENT_LABEL = "永久"


def classify_license_status(
    expiry_date: date | None,
    license_type: str | None,
    today: date,
    *,
    is_permanent: bool,
) -> str:
    # Permanent ⇒ OFFICIAL with no expiry date; it never expires.
    if is_permanent:
        return LICENSE_STATUS_OFFICIAL
    if expiry_date is None:
        return LICENSE_STATUS_NONE
    if expiry_date < today:
        return LICENSE_STATUS_EXPIRED
    if license_type == "TRIAL":
        return LICENSE_STATUS_TRIAL
    return LICENSE_STATUS_OFFICIAL


def license_expiry_text(expiry_date: date | None, is_permanent: bool) -> str | None:
    """Export/display text for a License expiry: 'YYYY-MM-DD', '永久', or None."""
    if is_permanent:
        return LICENSE_PERMANENT_LABEL
    if expiry_date is None:
        return None
    return expiry_date.isoformat()


def license_status_expression(
    expiry_column: SQLColumnExpression[date | None],
    type_column: SQLColumnExpression[str | None],
    permanent_column: SQLColumnExpression[bool | None],
    today: date,
) -> Case[str]:
    return case(
        (permanent_column.is_(True), LICENSE_STATUS_OFFICIAL),
        (expiry_column.is_(None), LICENSE_STATUS_NONE),
        (expiry_column < today, LICENSE_STATUS_EXPIRED),
        (type_column == "TRIAL", LICENSE_STATUS_TRIAL),
        else_=LICENSE_STATUS_OFFICIAL,
    )
