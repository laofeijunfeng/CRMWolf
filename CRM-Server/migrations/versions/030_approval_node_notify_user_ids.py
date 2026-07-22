"""add approval node notify user ids

Revision ID: 030_approval_node_notify_user_ids
Revises: 029_oauth_login_tables
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "030_approval_node_notify_user_ids"
down_revision: Union[str, None] = "029_oauth_login_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crm_approval_nodes",
        sa.Column("notify_user_ids", mysql.JSON(), nullable=True, comment="通知对象用户ID列表"),
    )


def downgrade() -> None:
    op.drop_column("crm_approval_nodes", "notify_user_ids")
