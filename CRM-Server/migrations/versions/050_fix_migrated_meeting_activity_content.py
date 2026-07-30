"""fix migrated meeting activity content

Revision ID: 050_fix_migrated_meeting_activity_content
Revises: 049_langgraph_customer_activity_checkpoints
Create Date: 2026-07-30

"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text


revision: str = "050_fix_migrated_meeting_activity_content"
down_revision: str | None = "049_langgraph_customer_activity_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def upgrade() -> None:
    if not _table_exists("crm_customer_activities"):
        return

    conn = op.get_bind()
    conn.execute(text("""
        UPDATE crm_customer_activities
        SET content_json = JSON_OBJECT(
                'meeting_subject', '',
                'meeting_background', '',
                'communication_context', '',
                'participants', JSON_OBJECT('internal', JSON_ARRAY(), 'customer', JSON_ARRAY()),
                'key_minutes', JSON_ARRAY(source_content),
                'qa_items', JSON_ARRAY(),
                'requirements', JSON_ARRAY(),
                'concerns_or_objections', JSON_ARRAY(),
                'risks', JSON_ARRAY(),
                'decisions_or_commitments', JSON_ARRAY(),
                'action_items', JSON_ARRAY(),
                'next_step_summary', COALESCE(next_action, '')
            ),
            processing_status = 'PENDING',
            processing_error = NULL,
            processed_at = NULL
        WHERE activity_kind IN ('ONLINE_MEETING', 'OFFLINE_MEETING')
          AND JSON_VALID(content_json)
          AND JSON_EXTRACT(content_json, '$.meeting_subject') IS NULL
    """))


def downgrade() -> None:
    pass
