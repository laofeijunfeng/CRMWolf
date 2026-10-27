"""Backfill durable conversation messages from historical assistant state."""

from collections.abc import Mapping, Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "156_assistant_historical_messages"
down_revision: str | None = "155_assistant_message_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREFIX = "ams_m156_"


def _require_table_columns(
    connection: sa.Connection,
    requirements: dict[str, tuple[str, ...]],
) -> None:
    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())
    missing_tables = sorted(set(requirements) - table_names)
    if missing_tables:
        raise RuntimeError(
            "assistant historical migration requires missing tables: "
            + ", ".join(missing_tables)
        )
    missing_columns: list[str] = []
    for table_name, required_columns in requirements.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name in required_columns:
            if column_name not in actual_columns:
                missing_columns.append(f"{table_name}.{column_name}")
    if missing_columns:
        raise RuntimeError(
            "assistant historical migration requires missing columns: "
            + ", ".join(missing_columns)
        )


def _text(
    payload: object,
    keys: tuple[str, ...] = ("text", "message", "prompt", "content"),
) -> str | None:
    if isinstance(payload, str):
        value = payload.strip()
        return value or None
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("payload", "data", "result", "response"):
        nested = _text(payload.get(key), keys)
        if nested:
            return nested
    return None


def _turn_user_text(payload: object) -> str | None:
    return _text(payload, ("text", "user_text", "message", "content"))


def _waiting_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    text = _text(payload, ("message", "text", "content"))
    if text:
        return text
    snapshot = payload.get("task")
    if isinstance(snapshot, dict):
        waiting = snapshot.get("waiting")
        text = _text(waiting, ("message", "prompt", "text", "content"))
        if text:
            return text
        text = _text(snapshot, ("message", "prompt", "text", "content"))
        if text:
            return text
    return _text(payload, ("prompt", "text", "content"))


def _latest_waiting_message(
    connection: sa.Connection,
    turn_id: int,
) -> tuple[str, datetime] | None:
    events = sa.table(
        "crm_assistant_turn_events",
        sa.column("turn_id", sa.BigInteger()),
        sa.column("seq", sa.Integer()),
        sa.column("event", sa.String(32)),
        sa.column("data_json", sa.JSON()),
        sa.column("created_time", sa.DateTime()),
    )
    row = connection.execute(
        sa.select(events.c.event, events.c.data_json, events.c.created_time)
        .where(events.c.turn_id == turn_id)
        .order_by(events.c.seq.desc())
        .limit(1)
    ).first()
    if row is None or row.event != "waiting":
        return None
    text = _waiting_text(row.data_json)
    return (text, row.created_time) if text else None


def _action_text(action: Mapping[str, object]) -> str | None:
    result = action["result_json"]
    if isinstance(result, dict):
        text = _text(result, ("message", "prompt", "text", "label")) or _text(
            result.get("confirmation"), ("prompt",)
        )
        if text:
            return text
    source = action["input_json"]
    return _text(source, ("message", "prompt", "text", "label"))


def _existing_message(
    connection: sa.Connection,
    messages: sa.TableClause,
    *,
    public_id: str,
    team_id: int,
    user_id: int,
    conversation_id: int,
    turn_id: int | None,
    role: str,
) -> bool:
    query = sa.select(messages.c.id).where(
        messages.c.team_id == team_id,
        messages.c.user_id == user_id,
        messages.c.conversation_id == conversation_id,
        messages.c.role == role,
    )
    if turn_id is None:
        query = query.where(messages.c.turn_id.is_(None), messages.c.public_id == public_id)
    else:
        query = query.where(messages.c.turn_id == turn_id)
    return connection.execute(query.limit(1)).first() is not None


def _append(
    connection: sa.Connection,
    conversations: sa.TableClause,
    messages: sa.TableClause,
    *,
    conversation_id: int,
    team_id: int,
    user_id: int,
    role: str,
    text: str,
    task_id: int,
    turn_id: int | None,
    created_time: datetime,
    public_id: str,
) -> None:
    row = connection.execute(
        sa.select(conversations.c.next_message_seq)
        .where(
            conversations.c.id == conversation_id,
            conversations.c.team_id == team_id,
            conversations.c.user_id == user_id,
        )
        .with_for_update()
    ).first()
    if row is None:
        return
    max_seq = connection.execute(
        sa.select(sa.func.coalesce(sa.func.max(messages.c.seq), 0)).where(
            messages.c.conversation_id == conversation_id,
            messages.c.team_id == team_id,
            messages.c.user_id == user_id,
        )
    ).scalar_one()
    next_seq = max(int(row.next_message_seq), int(max_seq) + 1)
    if _existing_message(
        connection,
        messages,
        public_id=public_id,
        team_id=team_id,
        user_id=user_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        role=role,
    ):
        if int(row.next_message_seq) < next_seq:
            connection.execute(
                conversations.update()
                .where(
                    conversations.c.id == conversation_id,
                    conversations.c.team_id == team_id,
                    conversations.c.user_id == user_id,
                )
                .values(next_message_seq=next_seq)
            )
        return
    message_values = {
        "public_id": public_id,
        "team_id": team_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "role": role,
        "text": text,
        "task_id": task_id,
        "input_fingerprint": None,
        "reference_id": None,
        "turn_id": turn_id,
        "seq": next_seq,
        "created_time": created_time,
        "last_modified_time": created_time,
    }
    if connection.dialect.name == "sqlite":
        message_values["id"] = int(
            connection.execute(
                sa.select(sa.func.coalesce(sa.func.max(messages.c.id), 0) + 1)
            ).scalar_one()
        )
    connection.execute(messages.insert().values(**message_values))
    connection.execute(
        conversations.update()
        .where(
            conversations.c.id == conversation_id,
            conversations.c.team_id == team_id,
            conversations.c.user_id == user_id,
        )
        .values(next_message_seq=next_seq + 1)
    )


def upgrade() -> None:
    connection = op.get_bind()
    _require_table_columns(
        connection,
        {
            "crm_assistant_tasks": (
                "id", "team_id", "user_id", "conversation_id", "goal", "created_time"
            ),
            "crm_assistant_turns": (
                "id", "team_id", "user_id", "task_id", "input_json", "created_time"
            ),
            "crm_assistant_actions": (
                "id", "task_id", "team_id", "input_json", "result_json", "created_time"
            ),
            "crm_assistant_turn_events": (
                "turn_id", "seq", "event", "data_json", "created_time"
            ),
            "crm_assistant_conversations": (
                "id", "team_id", "user_id", "next_message_seq"
            ),
            "crm_assistant_messages": (
                "id", "public_id", "team_id", "user_id", "conversation_id", "role", "text",
                "task_id", "client_request_id", "input_fingerprint", "reference_id", "turn_id",
                "seq", "created_time", "last_modified_time"
            ),
        },
    )
    tasks = sa.table(
        "crm_assistant_tasks",
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("goal", sa.Text()),
        sa.column("created_time", sa.DateTime()),
    )
    turns = sa.table(
        "crm_assistant_turns",
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("task_id", sa.BigInteger()),
        sa.column("input_json", sa.JSON()),
        sa.column("created_time", sa.DateTime()),
    )
    actions = sa.table(
        "crm_assistant_actions",
        sa.column("id", sa.BigInteger()),
        sa.column("task_id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("input_json", sa.JSON()),
        sa.column("result_json", sa.JSON()),
        sa.column("created_time", sa.DateTime()),
    )
    conversations = sa.table(
        "crm_assistant_conversations",
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("next_message_seq", sa.Integer()),
    )
    messages = sa.table(
        "crm_assistant_messages",
        sa.column("id", sa.BigInteger()),
        sa.column("public_id", sa.String(64)),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("conversation_id", sa.BigInteger()),
        sa.column("role", sa.String(20)),
        sa.column("text", sa.Text()),
        sa.column("task_id", sa.BigInteger()),
        sa.column("client_request_id", sa.String(128)),
        sa.column("input_fingerprint", sa.String(64)),
        sa.column("reference_id", sa.BigInteger()),
        sa.column("turn_id", sa.BigInteger()),
        sa.column("seq", sa.Integer()),
        sa.column("created_time", sa.DateTime()),
        sa.column("last_modified_time", sa.DateTime()),
    )

    candidates: list[tuple[datetime, int, int, int, str, str, int, int | None]] = []
    task_rows = connection.execute(sa.select(tasks)).mappings().all()
    for task in task_rows:
        task_id = int(task["id"])
        team_id, user_id = int(task["team_id"]), int(task["user_id"])
        conversation_id = task["conversation_id"]
        if conversation_id is None:
            continue
        owner_exists = connection.execute(
            sa.select(conversations.c.id).where(
                conversations.c.id == conversation_id,
                conversations.c.team_id == team_id,
                conversations.c.user_id == user_id,
            )
        ).first()
        if owner_exists is None:
            raise RuntimeError(
                "assistant historical migration found task "
                f"{task_id} with an unrecognized conversation owner "
                f"({conversation_id}, {team_id}, {user_id})"
            )
        turn_rows = connection.execute(
            sa.select(turns)
            .where(
                turns.c.task_id == task_id,
                turns.c.team_id == team_id,
                turns.c.user_id == user_id,
            )
            .order_by(turns.c.created_time, turns.c.id)
        ).mappings().all()
        if not turn_rows:
            goal = _text(task["goal"], ("text",))
            if goal:
                candidates.append(
                    (
                        task["created_time"],
                        0,
                        team_id,
                        user_id,
                        "USER",
                        goal,
                        task_id,
                        None,
                    )
                )
            action_rows = connection.execute(
                sa.select(actions)
                .where(
                    actions.c.task_id == task_id,
                    actions.c.team_id == team_id,
                )
                .order_by(actions.c.id.desc())
            ).mappings()
            for action in action_rows:
                text = _action_text(action)
                if text:
                    candidates.append(
                        (
                            action["created_time"],
                            1,
                            team_id,
                            user_id,
                            "ASSISTANT",
                            text,
                            task_id,
                            None,
                        )
                    )
                    break
            continue
        for turn in turn_rows:
            turn_id = int(turn["id"])
            user_text = _turn_user_text(turn["input_json"])
            if user_text:
                candidates.append(
                    (
                        turn["created_time"],
                        0,
                        team_id,
                        user_id,
                        "USER",
                        user_text,
                        task_id,
                        turn_id,
                    )
                )
            waiting = _latest_waiting_message(connection, turn_id)
            if waiting:
                candidates.append(
                    (
                        waiting[1],
                        1,
                        team_id,
                        user_id,
                        "ASSISTANT",
                        waiting[0],
                        task_id,
                        turn_id,
                    )
                )

    for source_time, role_order, team_id, user_id, role, text, task_id, turn_id in sorted(
        candidates,
        key=lambda item: (item[2], item[3], item[0], item[1], item[6], item[7] or -1),
    ):
        del role_order
        conversation_id = connection.execute(
            sa.select(tasks.c.conversation_id).where(
                tasks.c.id == task_id,
                tasks.c.team_id == team_id,
                tasks.c.user_id == user_id,
            )
        ).scalar_one_or_none()
        if conversation_id is None:
            continue
        public_id = (
            f"{_PREFIX}{role.lower()}_"
            f"{'turn' if turn_id is not None else 'task'}_{turn_id or task_id}"
        )
        _append(
            connection,
            conversations,
            messages,
            conversation_id=int(conversation_id),
            team_id=team_id,
            user_id=user_id,
            role=role,
            text=text,
            task_id=task_id,
            turn_id=turn_id,
            created_time=source_time,
            public_id=public_id,
        )

    max_rows = connection.execute(
        sa.select(
            messages.c.conversation_id,
            messages.c.team_id,
            messages.c.user_id,
            sa.func.coalesce(sa.func.max(messages.c.seq), 0).label("max_seq"),
        ).group_by(
            messages.c.conversation_id,
            messages.c.team_id,
            messages.c.user_id,
        )
    ).mappings()
    for row in max_rows:
        connection.execute(
            conversations.update()
            .where(
                conversations.c.id == row["conversation_id"],
                conversations.c.team_id == row["team_id"],
                conversations.c.user_id == row["user_id"],
                conversations.c.next_message_seq < int(row["max_seq"]) + 1,
            )
            .values(next_message_seq=int(row["max_seq"]) + 1)
        )


def downgrade() -> None:
    connection = op.get_bind()
    messages = sa.table(
        "crm_assistant_messages",
        sa.column("id", sa.BigInteger()),
        sa.column("public_id", sa.String(64)),
        sa.column("role", sa.String(20)),
        sa.column("turn_id", sa.BigInteger()),
        sa.column("task_id", sa.BigInteger()),
    )
    for row in connection.execute(sa.select(messages)).mappings().all():
        if row["role"] not in {"USER", "ASSISTANT"} or row["task_id"] is None:
            continue
        source_kind = "turn" if row["turn_id"] is not None else "task"
        source_id = row["turn_id"] if row["turn_id"] is not None else row["task_id"]
        expected = f"{_PREFIX}{row['role'].lower()}_{source_kind}_{source_id}"
        if row["public_id"] == expected:
            connection.execute(
                messages.delete().where(
                    messages.c.id == row["id"],
                    messages.c.public_id == expected,
                )
            )
