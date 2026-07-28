"""customer deal journeys

Revision ID: 042_customer_deal_journeys
Revises: 041_repair_payment_confirmation_draft
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "042_customer_deal_journeys"
down_revision: Union[str, None] = "041_repair_payment_confirmation_draft"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND index_name = :index_name
    """), {"table_name": table_name, "index_name": index_name}).scalar() > 0


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _add_deal_journey_column(table_name: str, index_name: str) -> None:
    if not _column_exists(table_name, "deal_journey_id"):
        op.add_column(
            table_name,
            sa.Column("deal_journey_id", sa.BigInteger(), nullable=True, comment="成交旅程ID（系统自动关联）"),
        )
    _create_index_if_missing(index_name, table_name, ["deal_journey_id"])


def upgrade() -> None:
    if not _table_exists("crm_customer_deal_journeys"):
        op.create_table(
            "crm_customer_deal_journeys",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("primary_opportunity_id", sa.BigInteger(), nullable=True, comment="主商机ID"),
            sa.Column("name", sa.String(length=255), nullable=False, comment="成交旅程名称"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE", comment="成交旅程状态"),
            sa.Column("started_at", sa.DateTime(), nullable=True, comment="开始时间"),
            sa.Column("closed_at", sa.DateTime(), nullable=True, comment="结束时间"),
            sa.Column("last_event_at", sa.DateTime(), nullable=True, comment="最近事件时间"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["primary_opportunity_id"], ["crm_opportunities.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            comment="客户成交旅程表",
        )
    _create_index_if_missing("idx_deal_journey_team_customer", "crm_customer_deal_journeys", ["team_id", "customer_id"])
    _create_index_if_missing("idx_deal_journey_primary_opportunity", "crm_customer_deal_journeys", ["primary_opportunity_id"], unique=True)
    _create_index_if_missing("idx_deal_journey_status", "crm_customer_deal_journeys", ["status"])
    _create_index_if_missing("idx_deal_journey_last_event_at", "crm_customer_deal_journeys", ["last_event_at"])

    if not _table_exists("crm_customer_deal_journey_events"):
        op.create_table(
            "crm_customer_deal_journey_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
            sa.Column("deal_journey_id", sa.BigInteger(), nullable=False, comment="成交旅程ID"),
            sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
            sa.Column("event_type", sa.String(length=50), nullable=False, comment="事件类型"),
            sa.Column("event_time", sa.DateTime(), nullable=False, comment="事件发生时间"),
            sa.Column("source_type", sa.String(length=50), nullable=False, comment="来源对象类型"),
            sa.Column("source_id", sa.BigInteger(), nullable=True, comment="来源对象ID"),
            sa.Column("actor_id", sa.String(length=100), nullable=True, comment="操作者系统用户ID"),
            sa.Column("summary", sa.Text(), nullable=True, comment="事件摘要"),
            sa.Column("metadata_json", sa.Text(), nullable=True, comment="事件元数据JSON"),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
            sa.ForeignKeyConstraint(["deal_journey_id"], ["crm_customer_deal_journeys.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment="客户成交旅程事件表",
        )
    _create_index_if_missing("idx_deal_journey_event_journey_time", "crm_customer_deal_journey_events", ["deal_journey_id", "event_time"])
    _create_index_if_missing("idx_deal_journey_event_customer_time", "crm_customer_deal_journey_events", ["team_id", "customer_id", "event_time"])
    _create_index_if_missing("idx_deal_journey_event_source", "crm_customer_deal_journey_events", ["source_type", "source_id"])
    _create_index_if_missing("idx_deal_journey_event_type", "crm_customer_deal_journey_events", ["event_type"])

    _add_deal_journey_column("crm_opportunities", "idx_opportunity_deal_journey_id")
    _add_deal_journey_column("crm_contracts", "idx_contract_deal_journey_id")
    _add_deal_journey_column("crm_contract_payment_plans", "idx_payment_plan_deal_journey_id")
    _add_deal_journey_column("crm_payment_records", "idx_payment_record_deal_journey_id")
    _add_deal_journey_column("crm_invoice_applications", "idx_invoice_application_deal_journey_id")
    _add_deal_journey_column("crm_customer_follow_ups", "idx_customer_follow_up_deal_journey_id")

    op.execute("""
        INSERT INTO crm_customer_deal_journeys
            (team_id, customer_id, primary_opportunity_id, name, status, started_at, closed_at, last_event_at, created_time, updated_time)
        SELECT
            o.team_id,
            o.customer_id,
            o.id,
            o.opportunity_name,
            CASE
                WHEN o.status = 2 THEN 'LOST'
                WHEN o.status = 1 AND EXISTS (
                    SELECT 1 FROM crm_contracts c
                    WHERE c.opportunity_id = o.id
                    AND c.deleted_at IS NULL
                ) AND NOT EXISTS (
                    SELECT 1 FROM crm_contracts c
                    WHERE c.opportunity_id = o.id
                    AND c.deleted_at IS NULL
                    AND c.payment_status <> 'COMPLETED'
                ) THEN 'COMPLETED'
                WHEN o.status = 1 THEN 'WON'
                ELSE 'ACTIVE'
            END,
            o.created_time,
            CASE
                WHEN o.status = 1 AND EXISTS (
                    SELECT 1 FROM crm_contracts c
                    WHERE c.opportunity_id = o.id
                    AND c.deleted_at IS NULL
                ) AND NOT EXISTS (
                    SELECT 1 FROM crm_contracts c
                    WHERE c.opportunity_id = o.id
                    AND c.deleted_at IS NULL
                    AND c.payment_status <> 'COMPLETED'
                ) THEN COALESCE(
                    (
                        SELECT MAX(r.confirmed_time)
                        FROM crm_payment_records r
                        JOIN crm_contract_payment_plans p ON p.id = r.payment_plan_id
                        JOIN crm_contracts c ON c.id = p.contract_id
                        WHERE c.opportunity_id = o.id
                        AND c.deleted_at IS NULL
                        AND r.confirmation_status = 'CONFIRMED'
                    ),
                    (
                        SELECT MAX(r.created_time)
                        FROM crm_payment_records r
                        JOIN crm_contract_payment_plans p ON p.id = r.payment_plan_id
                        JOIN crm_contracts c ON c.id = p.contract_id
                        WHERE c.opportunity_id = o.id
                        AND c.deleted_at IS NULL
                        AND r.confirmation_status = 'CONFIRMED'
                    ),
                    (
                        SELECT MAX(r.payment_date)
                        FROM crm_payment_records r
                        JOIN crm_contract_payment_plans p ON p.id = r.payment_plan_id
                        JOIN crm_contracts c ON c.id = p.contract_id
                        WHERE c.opportunity_id = o.id
                        AND c.deleted_at IS NULL
                        AND r.confirmation_status = 'CONFIRMED'
                    ),
                    o.last_modified_time
                )
                WHEN o.status = 2 THEN o.last_modified_time
                ELSE NULL
            END,
            o.created_time,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM crm_opportunities o
        LEFT JOIN crm_customer_deal_journeys j ON j.primary_opportunity_id = o.id
        WHERE j.id IS NULL
    """)

    op.execute("""
        UPDATE crm_opportunities o
        JOIN crm_customer_deal_journeys j ON j.primary_opportunity_id = o.id
        SET o.deal_journey_id = j.id
        WHERE o.deal_journey_id IS NULL
    """)
    op.execute("""
        UPDATE crm_contracts c
        JOIN crm_opportunities o ON o.id = c.opportunity_id
        SET c.deal_journey_id = o.deal_journey_id
        WHERE c.deal_journey_id IS NULL
    """)
    op.execute("""
        UPDATE crm_contract_payment_plans p
        JOIN crm_contracts c ON c.id = p.contract_id
        SET p.deal_journey_id = c.deal_journey_id
        WHERE p.deal_journey_id IS NULL
    """)
    op.execute("""
        UPDATE crm_payment_records r
        JOIN crm_contract_payment_plans p ON p.id = r.payment_plan_id
        SET r.deal_journey_id = p.deal_journey_id
        WHERE r.deal_journey_id IS NULL
    """)
    op.execute("""
        UPDATE crm_invoice_applications i
        JOIN crm_opportunities o ON o.id = i.opportunity_id
        SET i.deal_journey_id = o.deal_journey_id
        WHERE i.deal_journey_id IS NULL
    """)
    op.execute("""
        UPDATE crm_customer_follow_ups f
        JOIN (
            SELECT team_id, customer_id, MIN(id) AS deal_journey_id, COUNT(*) AS journey_count
            FROM crm_customer_deal_journeys
            WHERE status NOT IN ('LOST', 'COMPLETED')
            GROUP BY team_id, customer_id
        ) j ON j.team_id = f.team_id AND j.customer_id = f.customer_id AND j.journey_count = 1
        SET f.deal_journey_id = j.deal_journey_id
        WHERE f.deal_journey_id IS NULL
        AND f.customer_id IS NOT NULL
    """)

    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT o.team_id, o.deal_journey_id, o.customer_id, 'opportunity_created', COALESCE(o.created_time, CURRENT_TIMESTAMP),
               'opportunity', o.id, o.creator_id, CONCAT('创建商机：', o.opportunity_name), CURRENT_TIMESTAMP
        FROM crm_opportunities o
        WHERE o.deal_journey_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, summary, metadata_json, created_time)
        SELECT s.team_id, o.deal_journey_id, o.customer_id, 'opportunity_stage_changed', COALESCE(s.entered_at, CURRENT_TIMESTAMP),
               'opportunity_stage_snapshot', s.id, CONCAT('商机阶段推进到：', s.stage_name),
               CONCAT('{"stage_name":', JSON_QUOTE(s.stage_name), ',"win_probability":', s.win_probability, '}'),
               CURRENT_TIMESTAMP
        FROM crm_opportunity_stage_snapshots s
        JOIN crm_opportunities o ON o.id = s.opportunity_id
        WHERE o.deal_journey_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT o.team_id, o.deal_journey_id, o.customer_id, 'opportunity_won',
               COALESCE(o.actual_closing_date, o.last_modified_time, CURRENT_TIMESTAMP),
               'opportunity', o.id, o.creator_id, CONCAT('商机赢单：', o.opportunity_name), CURRENT_TIMESTAMP
        FROM crm_opportunities o
        WHERE o.deal_journey_id IS NOT NULL AND o.status = 1
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT o.team_id, o.deal_journey_id, o.customer_id, 'opportunity_lost',
               COALESCE(o.last_modified_time, CURRENT_TIMESTAMP),
               'opportunity', o.id, o.creator_id, CONCAT('商机输单：', o.opportunity_name), CURRENT_TIMESTAMP
        FROM crm_opportunities o
        WHERE o.deal_journey_id IS NOT NULL AND o.status = 2
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT c.team_id, c.deal_journey_id, c.customer_id, 'contract_created', COALESCE(c.created_time, CURRENT_TIMESTAMP),
               'contract', c.id, c.creator_id, CONCAT('创建合同：', c.contract_name), CURRENT_TIMESTAMP
        FROM crm_contracts c
        WHERE c.deal_journey_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT c.team_id, c.deal_journey_id, c.customer_id, 'contract_signed',
               COALESCE(c.signing_date, c.last_modified_time, CURRENT_TIMESTAMP),
               'contract', c.id, c.creator_id, CONCAT('合同签署：', c.contract_name), CURRENT_TIMESTAMP
        FROM crm_contracts c
        WHERE c.deal_journey_id IS NOT NULL
        AND c.status IN ('SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED')
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, summary, created_time)
        SELECT p.team_id, p.deal_journey_id, c.customer_id, 'payment_plan_created', COALESCE(p.created_time, CURRENT_TIMESTAMP),
               'payment_plan', p.id, CONCAT('创建回款计划：', p.stage_name), CURRENT_TIMESTAMP
        FROM crm_contract_payment_plans p
        JOIN crm_contracts c ON c.id = p.contract_id
        WHERE p.deal_journey_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT r.team_id, r.deal_journey_id, c.customer_id, 'payment_received', COALESCE(r.created_time, r.payment_date, CURRENT_TIMESTAMP),
               'payment_record', r.id, r.creator_id, CONCAT('登记回款：', r.actual_amount), CURRENT_TIMESTAMP
        FROM crm_payment_records r
        JOIN crm_contract_payment_plans p ON p.id = r.payment_plan_id
        JOIN crm_contracts c ON c.id = p.contract_id
        WHERE r.deal_journey_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT r.team_id, r.deal_journey_id, c.customer_id, 'payment_confirmed',
               COALESCE(r.confirmed_time, r.created_time, r.payment_date, CURRENT_TIMESTAMP),
               'payment_record', r.id, r.creator_id, CONCAT('确认回款：', r.actual_amount), CURRENT_TIMESTAMP
        FROM crm_payment_records r
        JOIN crm_contract_payment_plans p ON p.id = r.payment_plan_id
        JOIN crm_contracts c ON c.id = p.contract_id
        WHERE r.deal_journey_id IS NOT NULL
        AND r.confirmation_status = 'CONFIRMED'
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT i.team_id, i.deal_journey_id, i.customer_id, 'invoice_applied', COALESCE(i.created_time, CURRENT_TIMESTAMP),
               'invoice_application', i.id, i.applicant_id, CONCAT('申请开票：', i.invoice_amount), CURRENT_TIMESTAMP
        FROM crm_invoice_applications i
        WHERE i.deal_journey_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT i.team_id, i.deal_journey_id, i.customer_id, 'invoice_issued', COALESCE(i.issued_time, i.last_modified_time, CURRENT_TIMESTAMP),
               'invoice_application', i.id, i.applicant_id, CONCAT('完成开票：', i.invoice_amount), CURRENT_TIMESTAMP
        FROM crm_invoice_applications i
        WHERE i.deal_journey_id IS NOT NULL
        AND i.status = 'ISSUED'
    """)
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, actor_id, summary, created_time)
        SELECT f.team_id, f.deal_journey_id, f.customer_id, 'follow_up_added', COALESCE(f.created_time, CURRENT_TIMESTAMP),
               'customer_follow_up', f.id, f.creator_id, '新增客户跟进记录', CURRENT_TIMESTAMP
        FROM crm_customer_follow_ups f
        WHERE f.deal_journey_id IS NOT NULL
    """)

    op.execute("""
        UPDATE crm_customer_deal_journeys j
        JOIN (
            SELECT deal_journey_id, MAX(event_time) AS last_event_at
            FROM crm_customer_deal_journey_events
            GROUP BY deal_journey_id
        ) e ON e.deal_journey_id = j.id
        SET j.last_event_at = e.last_event_at
    """)


def downgrade() -> None:
    for table_name, index_name in [
        ("crm_customer_follow_ups", "idx_customer_follow_up_deal_journey_id"),
        ("crm_invoice_applications", "idx_invoice_application_deal_journey_id"),
        ("crm_payment_records", "idx_payment_record_deal_journey_id"),
        ("crm_contract_payment_plans", "idx_payment_plan_deal_journey_id"),
        ("crm_contracts", "idx_contract_deal_journey_id"),
        ("crm_opportunities", "idx_opportunity_deal_journey_id"),
    ]:
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _column_exists(table_name, "deal_journey_id"):
            op.drop_column(table_name, "deal_journey_id")

    if _table_exists("crm_customer_deal_journey_events"):
        op.drop_table("crm_customer_deal_journey_events")
    if _table_exists("crm_customer_deal_journeys"):
        op.drop_table("crm_customer_deal_journeys")
