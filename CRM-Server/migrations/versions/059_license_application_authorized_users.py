"""move authorized users to license applications

Revision ID: 059_license_application_authorized_users
Revises: 058_customer_intelligence_runs
Create Date: 2026-08-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "059_license_application_authorized_users"
down_revision: str | None = "058_customer_intelligence_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        return conn.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).scalar() > 0

    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return any(row["name"] == column_name for row in rows)

    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def upgrade() -> None:
    conn = op.get_bind()

    if _table_exists("crm_license_applications") and not _column_exists("crm_license_applications", "authorized_users"):
        op.add_column(
            "crm_license_applications",
            sa.Column("authorized_users", sa.Integer(), nullable=True, comment="本次申请使用人数"),
        )

        if conn.dialect.name == "mysql":
            op.execute("""
                UPDATE crm_license_applications la
                LEFT JOIN crm_deployment_infos di ON di.id = la.deployment_info_id
                SET la.authorized_users = COALESCE(di.authorized_users, 1)
            """)
        else:
            op.execute("""
                UPDATE crm_license_applications
                SET authorized_users = COALESCE(
                    (
                        SELECT crm_deployment_infos.authorized_users
                        FROM crm_deployment_infos
                        WHERE crm_deployment_infos.id = crm_license_applications.deployment_info_id
                    ),
                    1
                )
            """)

        if conn.dialect.name != "sqlite":
            op.alter_column(
                "crm_license_applications",
                "authorized_users",
                existing_type=sa.Integer(),
                nullable=False,
                existing_comment="本次申请使用人数",
            )

    if _table_exists("crm_deployment_infos") and _column_exists("crm_deployment_infos", "authorized_users"):
        if conn.dialect.name != "sqlite":
            op.alter_column(
                "crm_deployment_infos",
                "authorized_users",
                existing_type=sa.Integer(),
                nullable=True,
                existing_comment="授权人数",
                comment="历史授权人数（新申请人数记录在 License 申请）",
            )


def downgrade() -> None:
    if _table_exists("crm_deployment_infos") and _column_exists("crm_deployment_infos", "authorized_users"):
        op.execute("UPDATE crm_deployment_infos SET authorized_users = 1 WHERE authorized_users IS NULL")
        if op.get_bind().dialect.name != "sqlite":
            op.alter_column(
                "crm_deployment_infos",
                "authorized_users",
                existing_type=sa.Integer(),
                nullable=False,
                existing_comment="历史授权人数（新申请人数记录在 License 申请）",
                comment="授权人数",
            )

    if _table_exists("crm_license_applications") and _column_exists("crm_license_applications", "authorized_users"):
        op.drop_column("crm_license_applications", "authorized_users")
