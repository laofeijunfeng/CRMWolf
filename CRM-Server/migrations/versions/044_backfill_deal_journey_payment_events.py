"""backfill deal journey payment events

Revision ID: 044_backfill_deal_journey_payment_events
Revises: 043_deal_journey_closure_semantics
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op


revision: str = "044_backfill_deal_journey_payment_events"
down_revision: Union[str, None] = "043_deal_journey_closure_semantics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO crm_customer_deal_journey_events
            (team_id, deal_journey_id, customer_id, event_type, event_time, source_type, source_id, summary, created_time)
        SELECT p.team_id, p.deal_journey_id, c.customer_id, 'payment_plan_created',
               COALESCE(p.created_time, CURRENT_TIMESTAMP),
               'payment_plan', p.id, CONCAT('创建回款计划：', p.stage_name), CURRENT_TIMESTAMP
        FROM crm_contract_payment_plans p
        JOIN crm_contracts c ON c.id = p.contract_id
        LEFT JOIN crm_customer_deal_journey_events e
            ON e.deal_journey_id = p.deal_journey_id
            AND e.event_type = 'payment_plan_created'
            AND e.source_type = 'payment_plan'
            AND e.source_id = p.id
        WHERE p.deal_journey_id IS NOT NULL
        AND e.id IS NULL
    """)

    op.execute("""
        UPDATE crm_customer_deal_journey_events e
        JOIN crm_payment_records r ON r.id = e.source_id
        SET e.event_time = COALESCE(r.created_time, r.payment_date, e.event_time)
        WHERE e.event_type = 'payment_received'
        AND e.source_type = 'payment_record'
        AND r.deal_journey_id = e.deal_journey_id
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
        LEFT JOIN crm_customer_deal_journey_events e
            ON e.deal_journey_id = r.deal_journey_id
            AND e.event_type = 'payment_confirmed'
            AND e.source_type = 'payment_record'
            AND e.source_id = r.id
        WHERE r.deal_journey_id IS NOT NULL
        AND r.confirmation_status = 'CONFIRMED'
        AND e.id IS NULL
    """)

    op.execute("""
        UPDATE crm_customer_deal_journey_events e
        JOIN crm_payment_records r ON r.id = e.source_id
        SET e.event_time = COALESCE(r.confirmed_time, r.created_time, r.payment_date, e.event_time)
        WHERE e.event_type = 'payment_confirmed'
        AND e.source_type = 'payment_record'
        AND r.deal_journey_id = e.deal_journey_id
        AND r.confirmation_status = 'CONFIRMED'
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

    op.execute("""
        UPDATE crm_customer_deal_journeys j
        JOIN (
            SELECT deal_journey_id, MAX(event_time) AS closed_at
            FROM crm_customer_deal_journey_events
            WHERE event_type = 'payment_confirmed'
            GROUP BY deal_journey_id
        ) e ON e.deal_journey_id = j.id
        SET j.closed_at = e.closed_at
        WHERE j.status = 'COMPLETED'
    """)


def downgrade() -> None:
    # Data repair migration. Existing payment_plan_created/payment_confirmed events may
    # have been produced by normal business flows, so do not delete timeline facts.
    pass
