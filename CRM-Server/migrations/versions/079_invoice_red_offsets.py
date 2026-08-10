"""add invoice red offset records

Revision ID: 079_invoice_red_offsets
Revises: 078_invoice_reissue_permissions
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "079_invoice_red_offsets"
down_revision: str | None = "078_invoice_reissue_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all()
        return bool(rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
            """),
            {"table_name": table_name},
        ).scalar()
        > 0
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:table_name AND name=:index_name"),
            {"table_name": table_name, "index_name": index_name},
        ).all()
        return bool(rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND index_name = :index_name
            """),
            {"table_name": table_name, "index_name": index_name},
        ).scalar()
        > 0
    )


def _create_table_if_needed() -> None:
    table_name = "crm_invoice_red_offsets"
    if _table_exists(table_name):
        return

    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("invoice_application_id", sa.BigInteger(), nullable=False, comment="被冲红的原发票申请ID"),
        sa.Column("source_type", sa.String(length=20), nullable=False, comment="冲红来源：MANUAL/REISSUE"),
        sa.Column("reissue_application_id", sa.BigInteger(), nullable=True, comment="来源重开申请ID"),
        sa.Column("red_invoice_file_path", sa.String(length=500), nullable=False, comment="红字发票文件路径"),
        sa.Column("red_invoice_number", sa.String(length=100), nullable=True, comment="红字发票号码"),
        sa.Column("reason", sa.String(length=500), nullable=True, comment="冲红原因"),
        sa.Column("created_by", sa.String(length=100), nullable=False, comment="操作人系统用户ID"),
        sa.Column("red_offset_time", sa.DateTime(), nullable=False, comment="冲红时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(
            ["invoice_application_id"],
            ["crm_invoice_applications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reissue_application_id"],
            ["crm_invoice_reissue_applications.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_invoice_red_offset_team_id", table_name, ["team_id"])
    op.create_index("idx_invoice_red_offset_invoice", table_name, ["invoice_application_id"])
    op.create_index("idx_invoice_red_offset_reissue", table_name, ["reissue_application_id"])


def _backfill_from_completed_reissues() -> None:
    if not (_table_exists("crm_invoice_red_offsets") and _table_exists("crm_invoice_reissue_applications")):
        return

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO crm_invoice_red_offsets (
                team_id,
                invoice_application_id,
                source_type,
                reissue_application_id,
                red_invoice_file_path,
                red_invoice_number,
                reason,
                created_by,
                red_offset_time,
                created_time,
                last_modified_time
            )
            SELECT
                reissue.team_id,
                reissue.original_invoice_application_id,
                'REISSUE',
                reissue.id,
                reissue.red_invoice_file_path,
                reissue.red_invoice_number,
                reissue.reason,
                reissue.applicant_id,
                COALESCE(reissue.red_issued_time, reissue.completed_time, reissue.last_modified_time, reissue.created_time),
                COALESCE(reissue.red_issued_time, reissue.completed_time, reissue.last_modified_time, reissue.created_time),
                COALESCE(reissue.last_modified_time, reissue.completed_time, reissue.created_time)
            FROM crm_invoice_reissue_applications AS reissue
            WHERE reissue.status = 'COMPLETED'
              AND reissue.red_invoice_file_path IS NOT NULL
              AND reissue.red_invoice_file_path <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM crm_invoice_red_offsets AS red_offset
                  WHERE red_offset.reissue_application_id = reissue.id
              )
        """)
    )


def upgrade() -> None:
    _create_table_if_needed()
    _backfill_from_completed_reissues()


def downgrade() -> None:
    table_name = "crm_invoice_red_offsets"
    if not _table_exists(table_name):
        return
    for index_name in (
        "idx_invoice_red_offset_reissue",
        "idx_invoice_red_offset_invoice",
        "idx_invoice_red_offset_team_id",
    ):
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
    op.drop_table(table_name)
