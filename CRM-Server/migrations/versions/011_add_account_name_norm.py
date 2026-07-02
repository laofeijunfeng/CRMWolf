"""Add account_name_norm column and pg_trgm extension

Revision ID: 011_add_account_name_norm
Revises: 010_contract_soft_delete_approval_no_cascade
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = '011_add_account_name_norm'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add account_name_norm column and pg_trgm extension for fuzzy search"""

    # 1. Enable pg_trgm extension (required for GIN trigram index)
    # This extension must be installed at database level
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Add account_name_norm column to crm_customers
    op.add_column(
        'crm_customers',
        sa.Column(
            'account_name_norm',
            sa.String(255),
            nullable=True,
            comment='归一化客户名称（去后缀/括号）'
        )
    )

    # 3. Populate existing rows with normalized names
    # Using SQL to perform basic normalization (similar to normalize_corp_name)
    # Note: Full normalization happens via ORM hook on future updates

    # Step 3a: Remove content in parentheses (e.g., "张三（北京）科技" → "张三科技")
    op.execute("""
        UPDATE crm_customers
        SET account_name_norm = REGEXP_REPLACE(
            REPLACE(REPLACE(account_name, '（', '('), '）', ')'),
            '\([^)]*\)',
            '',
            'g'
        )
        WHERE account_name_norm IS NULL
    """)

    # Step 3b: Remove common suffixes (股份有限公司, 有限公司, etc.)
    # Order matters: remove longer suffixes first
    op.execute("""
        UPDATE crm_customers
        SET account_name_norm = REGEXP_REPLACE(
            account_name_norm,
            '(股份有限公司|有限责任公司|有限公司|股份公司|集团|分公司|营业部|办事处)$',
            '',
            'g'
        )
        WHERE account_name_norm IS NOT NULL
    """)

    # Step 3c: Trim whitespace
    op.execute("""
        UPDATE crm_customers
        SET account_name_norm = TRIM(account_name_norm)
        WHERE account_name_norm IS NOT NULL
    """)

    # 4. Create GIN index for fuzzy search (pg_trgm)
    # This enables fast similarity search on account_name_norm
    op.execute("""
        CREATE INDEX idx_account_name_norm_gin
        ON crm_customers
        USING gin (account_name_norm gin_trgm_ops)
    """)

    print("✅ Migration complete: account_name_norm column + pg_trgm extension added")


def downgrade() -> None:
    """Remove account_name_norm column and GIN index"""

    # 1. Drop the GIN index
    op.execute("DROP INDEX IF EXISTS idx_account_name_norm_gin")

    # 2. Drop the column
    op.drop_column('crm_customers', 'account_name_norm')

    # 3. Note: We keep pg_trgm extension as it may be used by other tables
    # To remove it completely, you would need to check dependencies first
    # op.execute("DROP EXTENSION IF EXISTS pg_trgm")

    print("✅ Downgrade complete: account_name_norm column + GIN index removed")