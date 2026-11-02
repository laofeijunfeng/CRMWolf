"""Record renewal and expansion headcount and amount on one payment.

Revision ID: 160_payment_record_composition
Revises: 159_invoice_application_remark
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "160_payment_record_composition"
down_revision: str | None = "159_invoice_application_remark"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "crm_payment_records"
_CHECK = "ck_payment_record_composition_complete"
_COLUMNS = {
    "renewal_headcount": sa.Column("renewal_headcount", sa.Integer(), nullable=True, comment="续购人数"),
    "renewal_amount": sa.Column("renewal_amount", sa.Numeric(12, 2), nullable=True, comment="续购金额"),
    "expansion_headcount": sa.Column("expansion_headcount", sa.Integer(), nullable=True, comment="增购人数"),
    "expansion_amount": sa.Column("expansion_amount", sa.Numeric(12, 2), nullable=True, comment="增购金额"),
}
_CHECK_SQL = (
    "(renewal_headcount IS NULL AND renewal_amount IS NULL "
    "AND expansion_headcount IS NULL AND expansion_amount IS NULL) "
    "OR (renewal_headcount IS NOT NULL AND renewal_amount IS NOT NULL "
    "AND expansion_headcount IS NOT NULL AND expansion_amount IS NOT NULL)"
)


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _check_exists(table_name: str, name: str) -> bool:
    checks = sa.inspect(op.get_bind()).get_check_constraints(table_name)
    return any(check.get("name") == name for check in checks)


def upgrade() -> None:
    if not _table_exists(_TABLE):
        return
    for name, column in _COLUMNS.items():
        if not _column_exists(_TABLE, name):
            op.add_column(_TABLE, column)
    if not _check_exists(_TABLE, _CHECK):
        op.create_check_constraint(_CHECK, _TABLE, _CHECK_SQL)


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if _check_exists(_TABLE, _CHECK):
        op.drop_constraint(_CHECK, _TABLE, type_="check")
    for name in reversed(tuple(_COLUMNS)):
        if _column_exists(_TABLE, name):
            op.drop_column(_TABLE, name)
