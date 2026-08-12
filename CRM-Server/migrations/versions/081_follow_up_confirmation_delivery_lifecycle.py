"""add follow up confirmation delivery lifecycle

Revision ID: 081_follow_up_confirmation_delivery_lifecycle
Revises: 080_agent_workflow_actions
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "081_follow_up_confirmation_delivery_lifecycle"
down_revision: str | None = "080_agent_workflow_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_follow_up_task_confirmation_prompt_deliveries"


def _column_names() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _index_names() -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}


def repair_duplicate_prompt_keys(connection: sa.engine.Connection, *, table_name: str = TABLE) -> int:
    """Preserve historical audit rows while making legacy prompt keys unique."""

    duplicate_groups = connection.execute(
        sa.text(
            f"""
            SELECT team_id, prompt_key
            FROM {table_name}
            GROUP BY team_id, prompt_key
            HAVING COUNT(*) > 1
            ORDER BY team_id, prompt_key
            """
        )
    ).mappings()
    repaired = 0
    for group in duplicate_groups:
        rows = connection.execute(
            sa.text(
                f"""
                SELECT id
                FROM {table_name}
                WHERE team_id = :team_id AND prompt_key = :prompt_key
                ORDER BY id ASC
                """
            ),
            {"team_id": group["team_id"], "prompt_key": group["prompt_key"]},
        ).scalars().all()
        for row_id in rows[1:]:
            attempt = 1
            while True:
                suffix = f":legacy:{row_id}" if attempt == 1 else f":legacy:{row_id}:{attempt}"
                repaired_key = f"{str(group['prompt_key'])[: 128 - len(suffix)]}{suffix}"
                collision = connection.execute(
                    sa.text(
                        f"""
                        SELECT 1
                        FROM {table_name}
                        WHERE team_id = :team_id
                          AND prompt_key = :repaired_key
                          AND id <> :row_id
                        LIMIT 1
                        """
                    ),
                    {
                        "team_id": group["team_id"],
                        "repaired_key": repaired_key,
                        "row_id": row_id,
                    },
                ).first()
                if collision is None:
                    break
                attempt += 1
            connection.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET prompt_key = :repaired_key
                    WHERE id = :row_id AND team_id = :team_id
                    """
                ),
                {
                    "repaired_key": repaired_key,
                    "row_id": row_id,
                    "team_id": group["team_id"],
                },
            )
            repaired += 1
    return repaired


def upgrade() -> None:
    columns = _column_names()
    additions = (
        ("reason_code", sa.Column("reason_code", sa.String(length=80), nullable=True, comment="投递状态原因码")),
        ("error_message", sa.Column("error_message", sa.Text(), nullable=True, comment="投递失败信息")),
        ("thread_id", sa.Column("thread_id", sa.String(length=160), nullable=True, comment="Agent线程ID")),
        ("run_id", sa.Column("run_id", sa.String(length=100), nullable=True, comment="运行ID")),
        ("attempted_at", sa.Column("attempted_at", sa.DateTime(), nullable=True, comment="投递尝试时间")),
        ("delivered_at", sa.Column("delivered_at", sa.DateTime(), nullable=True, comment="确认送达时间")),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column(TABLE, column)

    op.execute(sa.text(f"UPDATE {TABLE} SET attempted_at = prompted_at WHERE attempted_at IS NULL"))
    op.execute(sa.text(f"UPDATE {TABLE} SET delivered_at = prompted_at WHERE status = 'SENT' AND delivered_at IS NULL"))
    op.alter_column(TABLE, "attempted_at", existing_type=sa.DateTime(), nullable=False)

    indexes = _index_names()
    for index_name, columns in (
        ("idx_follow_up_confirmation_prompt_reason", ["reason_code"]),
        ("idx_follow_up_confirmation_prompt_thread", ["thread_id"]),
        ("idx_follow_up_confirmation_prompt_run", ["run_id"]),
        ("idx_follow_up_confirmation_prompt_attempted", ["attempted_at"]),
        ("idx_follow_up_confirmation_prompt_delivered", ["delivered_at"]),
    ):
        if index_name not in indexes:
            op.create_index(index_name, TABLE, columns)
    if "uq_follow_up_confirmation_prompt_key" not in indexes:
        repair_duplicate_prompt_keys(op.get_bind())
        op.create_index("uq_follow_up_confirmation_prompt_key", TABLE, ["team_id", "prompt_key"], unique=True)


def downgrade() -> None:
    indexes = _index_names()
    for index_name in (
        "uq_follow_up_confirmation_prompt_key",
        "idx_follow_up_confirmation_prompt_delivered",
        "idx_follow_up_confirmation_prompt_attempted",
        "idx_follow_up_confirmation_prompt_run",
        "idx_follow_up_confirmation_prompt_thread",
        "idx_follow_up_confirmation_prompt_reason",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name=TABLE)
    columns = _column_names()
    for column_name in ("delivered_at", "attempted_at", "run_id", "thread_id", "error_message", "reason_code"):
        if column_name in columns:
            op.drop_column(TABLE, column_name)
