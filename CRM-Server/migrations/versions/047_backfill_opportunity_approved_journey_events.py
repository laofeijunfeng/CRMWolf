"""backfill opportunity approved journey events

Revision ID: 047_backfill_opportunity_approved_journey_events
Revises: 046_im_inbound_agent_reply_binding
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "047_backfill_opportunity_approved_journey_events"
down_revision: Union[str, None] = "046_im_inbound_agent_reply_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, summary, created_time)
        SELECT
            o.team_id,
            o.deal_journey_id,
            o.customer_id,
            'opportunity_approved',
            COALESCE(a.approved_time, o.last_modified_time, o.created_time, CURRENT_TIMESTAMP),
            'opportunity',
            o.id,
            CONCAT('商机审批通过：', o.opportunity_name),
            CURRENT_TIMESTAMP
        FROM crm_opportunities o
        JOIN crm_customer_deal_journeys j
            ON j.id = o.deal_journey_id
            AND j.team_id = o.team_id
        LEFT JOIN (
            SELECT team_id, business_id, MAX(updated_time) AS approved_time
            FROM crm_contract_approvals
            WHERE business_type = 'OPPORTUNITY'
                AND status = 'APPROVED'
            GROUP BY team_id, business_id
        ) a
            ON a.business_id = o.id
            AND a.team_id = o.team_id
        WHERE o.deal_journey_id IS NOT NULL
            AND o.approval_phase = 'approved'
            AND NOT EXISTS (
                SELECT 1
                FROM crm_customer_deal_journey_events e
                WHERE e.deal_journey_id = o.deal_journey_id
                    AND e.event_type = 'opportunity_approved'
                    AND e.source_type = 'opportunity'
                    AND e.source_id = o.id
            )
    """))

    conn.execute(text("""
        UPDATE crm_customer_deal_journeys j
        JOIN (
            SELECT deal_journey_id, MAX(event_time) AS last_event_at
            FROM crm_customer_deal_journey_events
            GROUP BY deal_journey_id
        ) e ON e.deal_journey_id = j.id
        SET j.last_event_at = e.last_event_at
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DELETE FROM crm_customer_deal_journey_events
        WHERE event_type = 'opportunity_approved'
            AND source_type = 'opportunity'
    """))

    conn.execute(text("""
        UPDATE crm_customer_deal_journeys j
        LEFT JOIN (
            SELECT deal_journey_id, MAX(event_time) AS last_event_at
            FROM crm_customer_deal_journey_events
            GROUP BY deal_journey_id
        ) e ON e.deal_journey_id = j.id
        SET j.last_event_at = e.last_event_at
    """))
