"""Merge the activity-submission and payment timestamp migration heads.

Both revisions were created from ``123_payment_record_idempotency`` in the
same release window.  This no-op revision restores a single Alembic head so
future upgrades can use ``upgrade head`` without leaving a split history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "125_merge_activity_and_payment_heads"
down_revision: tuple[str, str] = (
    "124_customer_activity_submission_fingerprint",
    "124_payment_record_updated_time",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
