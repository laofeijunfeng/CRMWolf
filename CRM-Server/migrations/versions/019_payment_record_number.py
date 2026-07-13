"""add record_number to payment_records with backfill

Revision ID: 019_payment_record_number
Revises: 018_add_approval_phase_field
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '019_payment_record_number'
down_revision = '018_add_approval_phase_field'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Step 1: Check if column exists, add if not (idempotent)
    col_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND column_name = 'record_number'
    """)).scalar()

    if col_exists == 0:
        op.add_column(
            'crm_payment_records',
            sa.Column('record_number', sa.String(50), nullable=True, comment='回款记录编号（系统自动生成）')
        )

    # Step 2: Add index if not exists (idempotent)
    idx_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND index_name = 'idx_payment_record_number'
    """)).scalar()

    if idx_exists == 0:
        op.create_index('idx_payment_record_number', 'crm_payment_records', ['record_number'])

    # Step 3: Backfill existing records that don't have record_number
    records = conn.execute(text("""
        SELECT id, created_time
        FROM crm_payment_records
        WHERE record_number IS NULL
        ORDER BY created_time, id
    """)).fetchall()

    if records:
        # 按日期分组生成编号
        date_groups = {}
        for record in records:
            record_id = record[0]
            created_time = record[1]
            date_str = created_time.strftime('%Y%m%d') if created_time else datetime.now().strftime('%Y%m%d')

            if date_str not in date_groups:
                date_groups[date_str] = []
            date_groups[date_str].append(record_id)

        # 为每组分配序号并更新
        for date_str, record_ids in date_groups.items():
            for idx, record_id in enumerate(record_ids, start=1):
                record_number = f"PAY{date_str}{idx:04d}"
                conn.execute(text("""
                    UPDATE crm_payment_records
                    SET record_number = :record_number
                    WHERE id = :id
                """), {"record_number": record_number, "id": record_id})

    # Step 4: Set NOT NULL constraint if not already set
    col_info = conn.execute(text("""
        SELECT IS_NULLABLE FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND column_name = 'record_number'
    """)).scalar()

    if col_info == 'YES':
        op.alter_column('crm_payment_records', 'record_number',
                        existing_type=sa.String(50), nullable=False)

    # Step 5: Add unique constraint if not exists (idempotent)
    uc_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND constraint_name = 'uq_payment_record_number'
    """)).scalar()

    if uc_exists == 0:
        op.create_unique_constraint('uq_payment_record_number', 'crm_payment_records', ['record_number'])


def downgrade():
    # Remove unique constraint
    try:
        op.drop_constraint('uq_payment_record_number', 'crm_payment_records', type_='unique')
    except Exception:
        pass

    # Remove index
    try:
        op.drop_index('idx_payment_record_number', 'crm_payment_records')
    except Exception:
        pass

    # Remove column
    op.drop_column('crm_payment_records', 'record_number')