"""Allow owner-transfer Feishu notification events (CRM-162).

- customer_transferred / customer_transferred_previous: 客户移交通知新/原负责人
- lead_assigned_previous: 线索重新分配通知原负责人 (新负责人沿用 lead_assigned)

Revision ID: 170_owner_transfer_notifications
Revises: 169_follow_up_week_suppression
"""

from collections.abc import Sequence

from alembic import op

revision: str = "170_owner_transfer_notifications"
down_revision: str | None = "169_follow_up_week_suppression"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_TYPES = (
    "approval_pending",
    "approval_approved",
    "approval_rejected",
    "approval_cancelled",
    "approval_issued",
    "approval_reminder",
    "approval_cc",
    "account_created",
    "account_status_won",
    "account_status_lost",
    "customer_returned",
    "lead_claimed",
    "lead_assigned",
    "opportunity_won",
    "opportunity_lost",
)
_NEW_EVENT_TYPES = (
    "lead_assigned_previous",
    "customer_transferred",
    "customer_transferred_previous",
)


def _replace_event_type_check(event_types: tuple[str, ...]) -> None:
    allowed = ", ".join(f"'{value}'" for value in event_types)
    with op.batch_alter_table("crm_outbound_notification_jobs") as batch:
        batch.drop_constraint("ck_outbound_notification_job_event_type", type_="check")
        batch.create_check_constraint("ck_outbound_notification_job_event_type", f"event_type IN ({allowed})")


def upgrade() -> None:
    _replace_event_type_check(_EVENT_TYPES + _NEW_EVENT_TYPES)


def downgrade() -> None:
    removed = ", ".join(f"'{value}'" for value in _NEW_EVENT_TYPES)
    op.execute(f"DELETE FROM crm_outbound_notification_jobs WHERE event_type IN ({removed})")
    _replace_event_type_check(_EVENT_TYPES)
