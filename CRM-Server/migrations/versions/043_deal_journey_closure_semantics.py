"""repair deal journey closure semantics

Revision ID: 043_deal_journey_closure_semantics
Revises: 042_customer_deal_journeys
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op


revision: str = "043_deal_journey_closure_semantics"
down_revision: Union[str, None] = "042_customer_deal_journeys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE crm_customer_deal_journeys j
        JOIN crm_opportunities o ON o.id = j.primary_opportunity_id
        SET
            j.status = 'LOST',
            j.closed_at = COALESCE(o.last_modified_time, j.closed_at, CURRENT_TIMESTAMP),
            j.updated_time = CURRENT_TIMESTAMP
        WHERE o.status = 2
    """)

    op.execute("""
        UPDATE crm_customer_deal_journeys j
        JOIN crm_opportunities o ON o.id = j.primary_opportunity_id
        SET
            j.status = 'COMPLETED',
            j.closed_at = COALESCE(
                (
                    SELECT MAX(r.confirmed_time)
                    FROM crm_payment_records r
                    WHERE r.deal_journey_id = j.id
                    AND r.confirmation_status = 'CONFIRMED'
                ),
                (
                    SELECT MAX(r.created_time)
                    FROM crm_payment_records r
                    WHERE r.deal_journey_id = j.id
                    AND r.confirmation_status = 'CONFIRMED'
                ),
                (
                    SELECT MAX(r.payment_date)
                    FROM crm_payment_records r
                    WHERE r.deal_journey_id = j.id
                    AND r.confirmation_status = 'CONFIRMED'
                ),
                j.closed_at,
                CURRENT_TIMESTAMP
            ),
            j.updated_time = CURRENT_TIMESTAMP
        WHERE o.status = 1
        AND EXISTS (
            SELECT 1 FROM crm_contracts c
            WHERE c.deal_journey_id = j.id
            AND c.deleted_at IS NULL
        )
        AND NOT EXISTS (
            SELECT 1 FROM crm_contracts c
            WHERE c.deal_journey_id = j.id
            AND c.deleted_at IS NULL
            AND c.payment_status <> 'COMPLETED'
        )
    """)

    op.execute("""
        UPDATE crm_customer_deal_journeys j
        JOIN crm_opportunities o ON o.id = j.primary_opportunity_id
        SET
            j.status = 'WON',
            j.closed_at = NULL,
            j.updated_time = CURRENT_TIMESTAMP
        WHERE o.status = 1
        AND NOT (
            EXISTS (
                SELECT 1 FROM crm_contracts c
                WHERE c.deal_journey_id = j.id
                AND c.deleted_at IS NULL
            )
            AND NOT EXISTS (
                SELECT 1 FROM crm_contracts c
                WHERE c.deal_journey_id = j.id
                AND c.deleted_at IS NULL
                AND c.payment_status <> 'COMPLETED'
            )
        )
    """)

    op.execute("""
        UPDATE crm_customer_deal_journeys j
        JOIN crm_opportunities o ON o.id = j.primary_opportunity_id
        SET
            j.status = 'ACTIVE',
            j.closed_at = NULL,
            j.updated_time = CURRENT_TIMESTAMP
        WHERE o.status = 0
    """)

    op.execute("""
        UPDATE crm_customer_follow_ups f
        JOIN (
            SELECT team_id, customer_id, MIN(id) AS deal_journey_id, COUNT(*) AS journey_count
            FROM crm_customer_deal_journeys
            WHERE status NOT IN ('LOST', 'COMPLETED')
            GROUP BY team_id, customer_id
        ) j ON j.team_id = f.team_id
            AND j.customer_id = f.customer_id
            AND j.journey_count = 1
        SET f.deal_journey_id = j.deal_journey_id
        WHERE f.deal_journey_id IS NULL
        AND f.customer_id IS NOT NULL
    """)


def downgrade() -> None:
    pass
