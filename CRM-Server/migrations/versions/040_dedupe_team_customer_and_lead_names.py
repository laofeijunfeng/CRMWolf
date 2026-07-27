"""dedupe team-scoped customer and lead names

Revision ID: 040_dedupe_team_customer_and_lead_names
Revises: 039_merge_im_bot_into_oauth_config
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "040_dedupe_team_customer_and_lead_names"
down_revision: Union[str, None] = "039_merge_im_bot_into_oauth_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dedupe_team_names(table_name: str, name_column: str) -> None:
    bind = op.get_bind()
    duplicate_groups = bind.execute(text(
        """
        SELECT team_id, {name_column} AS name
        FROM {table_name}
        GROUP BY team_id, {name_column}
        HAVING COUNT(*) > 1
        """.format(table_name=table_name, name_column=name_column)
    )).fetchall()

    for group in duplicate_groups:
        rows = bind.execute(text(
            """
            SELECT id, {name_column} AS name
            FROM {table_name}
            WHERE team_id = :team_id AND {name_column} = :name
            ORDER BY id
            """.format(table_name=table_name, name_column=name_column)
        ), {"team_id": group.team_id, "name": group.name}).fetchall()

        for row in rows[1:]:
            suffix = f" #{row.id}"
            max_base_len = 255 - len(suffix)
            candidate = f"{str(row.name)[:max_base_len]}{suffix}"
            sequence = 2
            while bind.execute(text(
                """
                SELECT 1 FROM {table_name}
                WHERE team_id = :team_id AND {name_column} = :candidate AND id <> :id
                LIMIT 1
                """.format(table_name=table_name, name_column=name_column)
            ), {"team_id": group.team_id, "candidate": candidate, "id": row.id}).first():
                suffix = f" #{row.id}-{sequence}"
                max_base_len = 255 - len(suffix)
                candidate = f"{str(row.name)[:max_base_len]}{suffix}"
                sequence += 1

            bind.execute(text(
                """
                UPDATE {table_name}
                SET {name_column} = :candidate
                WHERE id = :id
                """.format(table_name=table_name, name_column=name_column)
            ), {"candidate": candidate, "id": row.id})


def upgrade() -> None:
    _dedupe_team_names("crm_customers", "account_name")
    _dedupe_team_names("crm_leads", "lead_name")


def downgrade() -> None:
    pass
