"""Give Assistant tasks a kind and an optional parent (CRM-165).

- crm_assistant_tasks.task_kind: customer_activity (existing rows) or one direct-create
  entity kind; one task owns exactly one CRM record.
- crm_assistant_tasks.parent_task_id: the activity task a profile proposal came from.
- Pending-draft listing index (team, user, status, kind, last modified).

Revision ID: 172_assistant_task_kind
Revises: 171_customer_child_dedupe_keys
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "172_assistant_task_kind"
down_revision: str | None = "171_customer_child_dedupe_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_assistant_tasks",
        sa.Column(
            "task_kind",
            sa.String(32),
            nullable=False,
            server_default="customer_activity",
            comment="任务类型 customer_activity 或直接新建的实体类型",
        ),
    )
    op.add_column(
        "crm_assistant_tasks",
        sa.Column("parent_task_id", sa.BigInteger(), nullable=True, comment="来源活动任务ID"),
    )
    op.create_index(
        "idx_assistant_task_owner_kind",
        "crm_assistant_tasks",
        ["team_id", "user_id", "status", "task_kind", "last_modified_time"],
    )


def downgrade() -> None:
    op.drop_index("idx_assistant_task_owner_kind", table_name="crm_assistant_tasks")
    op.drop_column("crm_assistant_tasks", "parent_task_id")
    op.drop_column("crm_assistant_tasks", "task_kind")
