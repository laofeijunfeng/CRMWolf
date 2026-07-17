"""add actual payer name to payment records

Revision ID: 023_payment_record_actual_payer_name
Revises: 022_contract_owner_id
Create Date: 2026-07-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '023_payment_record_actual_payer_name'
down_revision = '022_contract_owner_id'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    col_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND column_name = 'actual_payer_name'
    """)).scalar()

    if col_exists == 0:
        op.add_column(
            'crm_payment_records',
            sa.Column('actual_payer_name', sa.String(200), nullable=True, comment='实际付款方名称')
        )


def downgrade():
    conn = op.get_bind()
    col_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND column_name = 'actual_payer_name'
    """)).scalar()

    if col_exists > 0:
        op.drop_column('crm_payment_records', 'actual_payer_name')
