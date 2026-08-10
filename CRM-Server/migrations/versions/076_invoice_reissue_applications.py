"""add invoice reissue applications

Revision ID: 076_invoice_reissue_applications
Revises: 075_customer_vector_document_metadata_json
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "076_invoice_reissue_applications"
down_revision: str | None = "075_customer_vector_document_metadata_json"
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


def upgrade() -> None:
    table_name = "crm_invoice_reissue_applications"
    if _table_exists(table_name):
        return

    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("application_number", sa.String(length=50), nullable=False, comment="重开申请单号"),
        sa.Column("original_invoice_application_id", sa.BigInteger(), nullable=False, comment="原发票申请ID"),
        sa.Column("applicant_id", sa.String(length=100), nullable=False, comment="申请人系统用户ID"),
        sa.Column("reason", sa.String(length=500), nullable=False, comment="重开原因"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="重开申请状态"),
        sa.Column("approval_phase", sa.String(length=20), nullable=False, comment="审批流程状态"),
        sa.Column("invoice_title_type", sa.String(length=10), nullable=False, comment="新发票抬头类型快照"),
        sa.Column("invoice_title_text", sa.String(length=255), nullable=False, comment="新发票开票抬头快照"),
        sa.Column("invoice_taxpayer_id", sa.String(length=100), nullable=False, comment="新发票纳税人识别号快照"),
        sa.Column("invoice_bank_name", sa.String(length=255), nullable=True, comment="新发票开户行快照"),
        sa.Column("invoice_bank_account", sa.String(length=100), nullable=True, comment="新发票开户账号快照"),
        sa.Column("invoice_address", sa.String(length=500), nullable=True, comment="新发票开票地址快照"),
        sa.Column("invoice_phone", sa.String(length=50), nullable=True, comment="新发票电话快照"),
        sa.Column("invoice_amount", sa.Numeric(12, 2), nullable=False, comment="新发票金额"),
        sa.Column("invoice_type", sa.String(length=20), nullable=False, comment="新发票类型"),
        sa.Column("red_invoice_file_path", sa.String(length=500), nullable=True, comment="红字发票文件路径"),
        sa.Column("red_invoice_number", sa.String(length=100), nullable=True, comment="红字发票号码"),
        sa.Column("red_issued_time", sa.DateTime(), nullable=True, comment="红字发票开具时间"),
        sa.Column("new_invoice_file_path", sa.String(length=500), nullable=True, comment="新蓝字发票文件路径"),
        sa.Column("new_invoice_number", sa.String(length=100), nullable=True, comment="新蓝字发票号码"),
        sa.Column("new_issued_time", sa.DateTime(), nullable=True, comment="新蓝字发票开具时间"),
        sa.Column("completed_time", sa.DateTime(), nullable=True, comment="重开完成时间"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(
            ["original_invoice_application_id"],
            ["crm_invoice_applications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_number"),
    )
    op.create_index("idx_invoice_reissue_team_id", table_name, ["team_id"])
    op.create_index("idx_invoice_reissue_original_invoice", table_name, ["original_invoice_application_id"])
    op.create_index("idx_invoice_reissue_status", table_name, ["status"])


def downgrade() -> None:
    table_name = "crm_invoice_reissue_applications"
    if not _table_exists(table_name):
        return
    op.drop_index("idx_invoice_reissue_status", table_name=table_name)
    op.drop_index("idx_invoice_reissue_original_invoice", table_name=table_name)
    op.drop_index("idx_invoice_reissue_team_id", table_name=table_name)
    op.drop_table(table_name)
