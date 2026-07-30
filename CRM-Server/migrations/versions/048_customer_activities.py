"""customer activities

Revision ID: 048_customer_activities
Revises: 047_backfill_opportunity_approved_journey_events
Create Date: 2026-07-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "048_customer_activities"
down_revision: str | None = "047_backfill_opportunity_approved_journey_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND index_name = :index_name
    """), {"table_name": table_name, "index_name": index_name}).scalar() > 0


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        INSERT INTO permissions (name, code, resource, action, created_at, updated_at)
        SELECT permission_name, permission_code, 'customer_activity', permission_action, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM (
            SELECT '创建客户活动' AS permission_name, 'customer:activity:create' AS permission_code, 'create' AS permission_action
            UNION ALL SELECT '编辑客户活动', 'customer:activity:edit', 'edit'
            UNION ALL SELECT '删除客户活动', 'customer:activity:delete', 'delete'
        ) p
        WHERE NOT EXISTS (
            SELECT 1 FROM permissions existing WHERE existing.code = p.permission_code
        )
    """))

    conn.execute(text("""
        INSERT INTO role_permissions (role_id, permission_id, created_at)
        SELECT r.id, p.id, CURRENT_TIMESTAMP
        FROM roles r
        JOIN permissions p
            ON p.code IN ('customer:activity:create', 'customer:activity:edit', 'customer:activity:delete')
        LEFT JOIN role_permissions rp
            ON rp.role_id = r.id
            AND rp.permission_id = p.id
        WHERE r.code IN ('TEAM_ADMIN', 'SALES_DIRECTOR', 'SALES_MEMBER')
            AND rp.id IS NULL
    """))

    if not _table_exists("crm_customer_activities"):
        op.create_table(
            "crm_customer_activities",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="关联客户ID"),
            sa.Column("deal_journey_id", sa.BigInteger(), nullable=True, comment="成交旅程ID"),
            sa.Column("original_lead_id", sa.BigInteger(), nullable=True, comment="原始线索ID"),
            sa.Column("activity_kind", sa.String(length=50), nullable=False, comment="活动分类"),
            sa.Column("title", sa.String(length=255), nullable=True, comment="活动标题"),
            sa.Column("source_content", sa.Text(), nullable=False, comment="原始输入内容"),
            sa.Column("content_json", sa.Text(), nullable=True, comment="结构化活动内容JSON"),
            sa.Column("summary", sa.Text(), nullable=True, comment="列表摘要缓存"),
            sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="COMPLETED", comment="整理状态"),
            sa.Column("processing_error", sa.Text(), nullable=True, comment="整理失败原因"),
            sa.Column("processed_at", sa.DateTime(), nullable=True, comment="整理完成时间"),
            sa.Column("next_follow_time", sa.DateTime(), nullable=True, comment="计划下次跟进时间"),
            sa.Column("next_follow_time_source", sa.String(length=30), nullable=True, comment="下次跟进时间来源"),
            sa.Column("next_action", sa.Text(), nullable=True, comment="下一步动作内容"),
            sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="活动发生时间"),
            sa.Column("creator_id", sa.String(length=100), nullable=False, comment="记录创建人"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="记录创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
            sa.Column("effectiveness_score", sa.Integer(), nullable=True, comment="AI评估活动有效性得分，满分100"),
            sa.Column("effectiveness_is_valid", sa.Boolean(), nullable=True, comment="AI评估是否有效"),
            sa.Column("effectiveness_reason", sa.Text(), nullable=True, comment="AI评估原因摘要"),
            sa.Column("effectiveness_detail_json", sa.Text(), nullable=True, comment="AI评估分项明细JSON"),
            sa.Column("effectiveness_status", sa.String(length=20), nullable=True, server_default="PENDING", comment="AI评估状态"),
            sa.Column("effectiveness_evaluated_time", sa.DateTime(), nullable=True, comment="AI评估完成时间"),
            sa.Column("effectiveness_error_message", sa.Text(), nullable=True, comment="AI评估失败原因"),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["deal_journey_id"], ["crm_customer_deal_journeys.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["original_lead_id"], ["crm_leads.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            comment="客户活动表",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )

    conn.execute(text("""
        ALTER TABLE crm_customer_activities
        CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """))

    _create_index_if_missing("idx_customer_activity_customer", "crm_customer_activities", ["customer_id"])
    _create_index_if_missing("idx_customer_activity_deal_journey", "crm_customer_activities", ["deal_journey_id"])
    _create_index_if_missing("idx_customer_activity_original_lead", "crm_customer_activities", ["original_lead_id"])
    _create_index_if_missing("idx_customer_activity_creator", "crm_customer_activities", ["creator_id"])
    _create_index_if_missing("idx_customer_activity_kind", "crm_customer_activities", ["activity_kind"])
    _create_index_if_missing("idx_customer_activity_next_time", "crm_customer_activities", ["next_follow_time"])
    _create_index_if_missing("idx_customer_activity_occurred_at", "crm_customer_activities", ["occurred_at"])
    _create_index_if_missing("idx_customer_activity_created_time", "crm_customer_activities", ["created_time"])
    _create_index_if_missing("idx_customer_activity_team", "crm_customer_activities", ["team_id"])

    conn.execute(text("""
        INSERT INTO crm_customer_activities
            (team_id, customer_id, deal_journey_id, original_lead_id, activity_kind, title,
             source_content, content_json, summary, processing_status, processed_at,
             next_follow_time, next_follow_time_source, next_action, occurred_at, creator_id, created_time, updated_time,
             effectiveness_score, effectiveness_is_valid, effectiveness_reason, effectiveness_detail_json,
             effectiveness_status, effectiveness_evaluated_time, effectiveness_error_message)
        SELECT
            f.team_id,
            f.customer_id,
            f.deal_journey_id,
            f.original_lead_id,
            CASE
                WHEN f.method = '电话' THEN 'PHONE_FOLLOW_UP'
                WHEN f.method = '微信' THEN 'WECHAT_FOLLOW_UP'
                WHEN f.method = '邮件' THEN 'EMAIL_FOLLOW_UP'
                WHEN f.method IN ('拜访', '面谈') THEN 'VISIT_FOLLOW_UP'
                WHEN f.method = '会议' THEN 'ONLINE_MEETING'
                ELSE 'OTHER_FOLLOW_UP'
            END,
            CASE
                WHEN f.method = '电话' THEN '电话跟进'
                WHEN f.method = '微信' THEN '微信跟进'
                WHEN f.method = '邮件' THEN '邮件跟进'
                WHEN f.method IN ('拜访', '面谈') THEN '拜访跟进'
                WHEN f.method = '会议' THEN '线上会议'
                ELSE '其他跟进'
            END,
            f.content,
            CASE
                WHEN f.method = '会议' THEN JSON_OBJECT(
                    'meeting_subject', '',
                    'meeting_background', '',
                    'communication_context', '',
                    'participants', JSON_OBJECT('internal', JSON_ARRAY(), 'customer', JSON_ARRAY()),
                    'key_minutes', JSON_ARRAY(f.content),
                    'qa_items', JSON_ARRAY(),
                    'requirements', JSON_ARRAY(),
                    'concerns_or_objections', JSON_ARRAY(),
                    'risks', JSON_ARRAY(),
                    'decisions_or_commitments', JSON_ARRAY(),
                    'action_items', JSON_ARRAY(),
                    'next_step_summary', COALESCE(f.next_action, '')
                )
                ELSE JSON_OBJECT(
                    'content', f.content,
                    'customer_feedback', '',
                    'current_progress', '',
                    'risks', JSON_ARRAY(),
                    'next_action', COALESCE(f.next_action, ''),
                    'next_follow_time_text', ''
                )
            END,
            LEFT(f.content, 300),
            'COMPLETED',
            f.created_time,
            f.next_follow_time,
            CASE WHEN f.next_follow_time IS NOT NULL THEN 'MIGRATED' ELSE NULL END,
            f.next_action,
            COALESCE(f.created_time, CURRENT_TIMESTAMP),
            f.creator_id,
            COALESCE(f.created_time, CURRENT_TIMESTAMP),
            CURRENT_TIMESTAMP,
            f.effectiveness_score,
            f.effectiveness_is_valid,
            f.effectiveness_reason,
            f.effectiveness_detail_json,
            f.effectiveness_status,
            f.effectiveness_evaluated_time,
            f.effectiveness_error_message
        FROM crm_customer_follow_ups f
        LEFT JOIN crm_customer_activities a
            ON a.team_id = f.team_id
            AND a.customer_id <=> f.customer_id
            AND a.source_content COLLATE utf8mb4_unicode_ci = f.content COLLATE utf8mb4_unicode_ci
            AND a.created_time = f.created_time
        WHERE a.id IS NULL
    """))

    conn.execute(text("""
        UPDATE crm_customer_deal_journey_events e
        JOIN crm_customer_follow_ups f
            ON e.source_type = 'customer_follow_up'
            AND e.source_id = f.id
        JOIN crm_customer_activities a
            ON a.team_id = f.team_id
            AND a.customer_id <=> f.customer_id
            AND a.source_content COLLATE utf8mb4_unicode_ci = f.content COLLATE utf8mb4_unicode_ci
            AND a.created_time = f.created_time
        SET e.source_type = 'customer_activity',
            e.source_id = a.id,
            e.event_type = 'activity_added',
            e.summary = REPLACE(COALESCE(e.summary, '新增客户跟进记录'), '客户跟进记录', '客户活动')
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE crm_customer_deal_journey_events e
        JOIN crm_customer_activities a
            ON e.source_type = 'customer_activity'
            AND e.source_id = a.id
        JOIN crm_customer_follow_ups f
            ON f.team_id = a.team_id
            AND f.customer_id <=> a.customer_id
            AND f.content COLLATE utf8mb4_unicode_ci = a.source_content COLLATE utf8mb4_unicode_ci
            AND f.created_time = a.created_time
        SET e.source_type = 'customer_follow_up',
            e.source_id = f.id,
            e.event_type = 'follow_up_added'
    """))
    if _table_exists("crm_customer_activities"):
        op.drop_table("crm_customer_activities")
