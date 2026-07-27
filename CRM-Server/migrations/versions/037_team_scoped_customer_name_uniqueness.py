"""team scoped customer name uniqueness

Revision ID: 037_team_scoped_customer_name_uniqueness
Revises: 036_remove_extra_opportunity_backfill_records
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text


revision: str = "037_team_scoped_customer_name_uniqueness"
down_revision: Union[str, None] = "036_remove_extra_opportunity_backfill_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "crm_customers"
LEAD_TABLE_NAME = "crm_leads"
TEAM_UNIQUE_INDEX = "uq_customer_team_account_name"
LEAD_TEAM_UNIQUE_INDEX = "uq_lead_team_lead_name"


def _has_duplicate_team_names(bind) -> bool:
    row = bind.execute(text(
        """
        SELECT team_id, account_name, COUNT(*) AS count
        FROM crm_customers
        GROUP BY team_id, account_name
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).first()
    return row is not None


def _has_duplicate_global_names(bind) -> bool:
    row = bind.execute(text(
        """
        SELECT account_name, COUNT(*) AS count
        FROM crm_customers
        GROUP BY account_name
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).first()
    return row is not None


def _has_duplicate_team_lead_names(bind) -> bool:
    row = bind.execute(text(
        """
        SELECT team_id, lead_name, COUNT(*) AS count
        FROM crm_leads
        GROUP BY team_id, lead_name
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).first()
    return row is not None


def _drop_global_account_name_unique(bind) -> None:
    inspector = inspect(bind)

    for constraint in inspector.get_unique_constraints(TABLE_NAME):
        if constraint.get("column_names") == ["account_name"] and constraint.get("name"):
            try:
                op.drop_constraint(constraint["name"], TABLE_NAME, type_="unique")
            except Exception:
                pass

    for index in inspector.get_indexes(TABLE_NAME):
        if index.get("unique") and index.get("column_names") == ["account_name"] and index.get("name"):
            try:
                op.drop_index(index["name"], table_name=TABLE_NAME)
            except Exception:
                pass

    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TABLE crm_customers DROP CONSTRAINT IF EXISTS crm_customers_account_name_key")
        op.execute("DROP INDEX IF EXISTS account_name")
    elif dialect in {"mysql", "mariadb"}:
        for index_name in ("account_name", "crm_customers_account_name_key"):
            try:
                op.execute(f"ALTER TABLE crm_customers DROP INDEX {index_name}")
            except Exception:
                pass


def _has_index(bind, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if _has_duplicate_team_names(bind):
        raise RuntimeError("crm_customers 存在同一团队内重复客户名称，请先清理后再执行迁移")
    if _has_duplicate_team_lead_names(bind):
        raise RuntimeError("crm_leads 存在同一团队内重复线索名称，请先清理后再执行迁移")

    _drop_global_account_name_unique(bind)

    if not _has_index(bind, TABLE_NAME, TEAM_UNIQUE_INDEX):
        op.create_index(TEAM_UNIQUE_INDEX, TABLE_NAME, ["team_id", "account_name"], unique=True)
    if not _has_index(bind, LEAD_TABLE_NAME, LEAD_TEAM_UNIQUE_INDEX):
        op.create_index(LEAD_TEAM_UNIQUE_INDEX, LEAD_TABLE_NAME, ["team_id", "lead_name"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, LEAD_TABLE_NAME, LEAD_TEAM_UNIQUE_INDEX):
        op.drop_index(LEAD_TEAM_UNIQUE_INDEX, table_name=LEAD_TABLE_NAME)

    if _has_index(bind, TABLE_NAME, TEAM_UNIQUE_INDEX):
        op.drop_index(TEAM_UNIQUE_INDEX, table_name=TABLE_NAME)

    if _has_duplicate_global_names(bind):
        raise RuntimeError("crm_customers 存在跨团队重复客户名称，无法恢复全局唯一约束")

    op.create_index("account_name", TABLE_NAME, ["account_name"], unique=True)
