"""backfill deal journey opportunity stage events

Revision ID: 045_backfill_deal_journey_stage_events
Revises: 044_backfill_deal_journey_payment_events
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op


revision: str = "045_backfill_deal_journey_stage_events"
down_revision: Union[str, None] = "044_backfill_deal_journey_payment_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, summary, metadata_json, created_time)
        SELECT
            s.team_id,
            o.deal_journey_id,
            o.customer_id,
            'opportunity_stage_changed',
            COALESCE(s.entered_at, CURRENT_TIMESTAMP),
            'opportunity_stage_snapshot',
            s.id,
            CONCAT('商机阶段推进到：', s.stage_name),
            CONCAT('{"stage_name":', JSON_QUOTE(s.stage_name), ',"win_probability":', s.win_probability, '}'),
            CURRENT_TIMESTAMP
        FROM crm_opportunity_stage_snapshots s
        JOIN crm_opportunities o ON o.id = s.opportunity_id
        LEFT JOIN crm_customer_deal_journey_events e
            ON e.deal_journey_id = o.deal_journey_id
            AND e.event_type = 'opportunity_stage_changed'
            AND e.source_type = 'opportunity_stage_snapshot'
            AND e.source_id = s.id
        WHERE o.deal_journey_id IS NOT NULL
        AND e.id IS NULL
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
    # Data repair migration. Do not delete timeline facts that may have been
    # produced by normal business flows.
    pass
