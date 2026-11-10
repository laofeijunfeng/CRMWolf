"""Create contract amount change request persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence


revision: str = "163_contract_amount_changes"
down_revision: str | None = "162_customer_name_dedupe_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "crm_contract_changes"
_INDEXES = (
    "idx_contract_change_contract",
    "idx_contract_change_phase",
)
_UNIQUE = "uq_contract_change_pending_guard"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
            comment="主键",
        ),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("contract_id", sa.BigInteger(), nullable=False, comment="原合同ID"),
        sa.Column("creator_id", sa.String(length=100), nullable=False, comment="申请人系统用户ID"),
        sa.Column(
            "change_items_json",
            sa.JSON(),
            nullable=False,
            comment="不可变变更项目快照；金额值以字符串保存",
        ),
        sa.Column("reason", sa.Text(), nullable=False, comment="变更原因"),
        sa.Column(
            "approval_phase",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
            comment="审批流程状态：draft/pending_review/approved/rejected",
        ),
        sa.Column(
            "pending_guard",
            sa.String(length=20),
            nullable=True,
            comment="待审批唯一性保护标记；待审批时由服务层设为 pending，终态置空",
        ),
        sa.Column("attachment_path", sa.String(length=500), nullable=True, comment="变更附件路径（相对路径）"),
        sa.Column("attachment_name", sa.String(length=255), nullable=True, comment="变更附件原始文件名"),
        sa.Column("attachment_size", sa.BigInteger(), nullable=True, comment="变更附件大小（字节）"),
        sa.Column("attachment_mime_type", sa.String(length=100), nullable=True, comment="变更附件 MIME 类型"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="删除时间（软删除标记）"),
        sa.ForeignKeyConstraint(["contract_id"], ["crm_contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "contract_id", "pending_guard", name=_UNIQUE),
        comment="合同变更申请表",
    )
    op.create_index(_INDEXES[0], _TABLE, ["team_id", "contract_id"])
    op.create_index(_INDEXES[1], _TABLE, ["team_id", "approval_phase"])


def downgrade() -> None:
    for index_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=_TABLE)
    op.drop_table(_TABLE)
