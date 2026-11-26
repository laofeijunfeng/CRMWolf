"""Let Assistant input, activity text and its evidence text hold a 100k-character transcript (CRM-167).

MySQL TEXT stops at 64 KB, about 21k Chinese characters; MEDIUMTEXT holds 16 MB.

Revision ID: 173_long_transcript_text
Revises: 172_assistant_task_kind
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "173_long_transcript_text"
down_revision: str | None = "172_assistant_task_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, str, bool, str | None], ...] = (
    ("crm_assistant_conversation_entries", "user_text", False, None),
    ("crm_assistant_tasks", "goal", False, "任务目标"),
    ("crm_customer_activities", "source_content", False, "原始输入内容"),
    ("crm_customer_activities", "content_json", True, "结构化活动内容JSON"),
    ("crm_customer_vector_documents", "text", False, "可检索证据文本"),
)


def upgrade() -> None:
    for table, column, nullable, comment in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            type_=mysql.MEDIUMTEXT,
            existing_nullable=nullable,
            existing_comment=comment,
        )


def downgrade() -> None:
    for table, column, nullable, comment in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=mysql.MEDIUMTEXT,
            type_=sa.Text(),
            existing_nullable=nullable,
            existing_comment=comment,
        )
