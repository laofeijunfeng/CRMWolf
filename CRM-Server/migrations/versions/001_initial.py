"""Initial migration - create all tables

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration relies on SQLAlchemy's metadata.create_all()
    # The actual table creation happens via Base.metadata.create_all() in init_db.py
    # This is a marker migration to establish the baseline
    pass


def downgrade() -> None:
    # For initial migration, we don't support downgrade
    # Production databases should never be downgraded to empty state
    pass