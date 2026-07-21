"""normalize opportunity names

Revision ID: 028_normalize_opportunity_names
Revises: 027_follow_up_effectiveness_fields
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "028_normalize_opportunity_names"
down_revision: Union[str, None] = "027_follow_up_effectiveness_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE crm_opportunities o
        LEFT JOIN crm_customers c ON c.id = o.customer_id
        SET o.opportunity_name = CONCAT(
            LEFT(
                COALESCE(NULLIF(TRIM(c.account_name), ''), CONCAT('客户 #', o.customer_id)),
                GREATEST(
                    1,
                    255 - CHAR_LENGTH(
                        CASE
                            WHEN o.license_type = 'SUBSCRIPTION' THEN CONCAT(
                                COALESCE(NULLIF(o.user_count, 0), 1),
                                '人-订阅',
                                COALESCE(NULLIF(o.subscription_years, 0), 1),
                                '年'
                            )
                            ELSE CONCAT(COALESCE(NULLIF(o.user_count, 0), 1), '人-买断')
                        END
                    ) - 1
                )
            ),
            '-',
            CASE
                WHEN o.license_type = 'SUBSCRIPTION' THEN CONCAT(
                    COALESCE(NULLIF(o.user_count, 0), 1),
                    '人-订阅',
                    COALESCE(NULLIF(o.subscription_years, 0), 1),
                    '年'
                )
                ELSE CONCAT(COALESCE(NULLIF(o.user_count, 0), 1), '人-买断')
            END
        )
    """))


def downgrade() -> None:
    # Data migration only. Previous custom opportunity names were not persisted separately.
    pass
