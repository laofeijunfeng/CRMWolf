"""One-time deterministic migration of historical CRM Agent messages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import MetaData, Table, select, update

from app.services.agent.migration_inventory import (
    KNOWN_MESSAGE_PAYLOAD_KEY_SETS,
    coerce_agent_message_payload,
)
from app.services.agent.ui.markdown import project_agent_markdown_to_plain_text, validate_agent_markdown
from app.services.agent.ui.schemas import (
    ActionResultBlock,
    AgentUIEnvelope,
    AgentUIMetadata,
    InteractionBlock,
    InteractionField,
    InteractionOption,
    TextBlock,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.engine import Connection, RowMapping


class AgentMessageMigrationError(RuntimeError):
    """Historical message data cannot be mapped to the target contract."""


@dataclass(frozen=True)
class _ProjectedMessageTarget:
    turn_id: str
    content: str
    ui_json: dict[str, JsonValue]
    diagnostics_json: dict[str, JsonValue] | None


class AgentMessageMigrationBatchResult(BaseModel):
    """Content-free evidence for one committed primary-key migration batch."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["crm.agent.message-migration-batch.v1"] = "crm.agent.message-migration-batch.v1"
    after_id: int = Field(ge=0)
    last_id: int | None = Field(default=None, gt=0)
    source_row_count: int = Field(ge=0)
    target_row_count: int = Field(ge=0)
    migrated_row_count: int = Field(ge=0)
    schema_validated_count: int = Field(ge=0)
    source_payload_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_ui_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    has_more: bool


class AgentMessageMigrationService:
    """Migrate one message batch atomically; any invalid row rolls back the batch."""

    _REQUIRED_COLUMNS = frozenset(
        {
            "id",
            "team_id",
            "user_id",
            "session_id",
            "role",
            "event_type",
            "content",
            "payload_json",
            "turn_id",
            "ui_json",
            "diagnostics_json",
        }
    )

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        metadata = MetaData()
        self._messages = Table("crm_agent_messages", metadata, autoload_with=engine)
        self._sessions = Table("crm_agent_sessions", metadata, autoload_with=engine)
        missing_columns = self._REQUIRED_COLUMNS - set(self._messages.c.keys())
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise AgentMessageMigrationError(f"crm_agent_messages is missing migration columns: {missing}")
        required_session_columns = {"id", "team_id", "user_id"}
        missing_session_columns = required_session_columns - set(self._sessions.c.keys())
        if missing_session_columns:
            missing = ", ".join(sorted(missing_session_columns))
            raise AgentMessageMigrationError(f"crm_agent_sessions is missing ownership columns: {missing}")

    def migrate_batch(self, *, after_id: int = 0, batch_size: int = 1000) -> AgentMessageMigrationBatchResult:
        if after_id < 0:
            raise ValueError("after_id must not be negative")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        with self._engine.begin() as connection:
            rows = list(
                connection.execute(
                    select(self._messages)
                    .where(self._messages.c.id > after_id)
                    .order_by(self._messages.c.id)
                    .limit(batch_size)
                ).mappings()
            )
            source_checksum_rows = [{"id": int(row["id"]), "payload_json": row["payload_json"]} for row in rows]
            for row in rows:
                self._validate_message_identity(connection, row)
            inferred_user_message_ids = self._build_inferred_user_message_ids(
                connection,
                rows=rows,
            )
            migrated_count = 0
            expected_targets: dict[int, _ProjectedMessageTarget] = {}
            for row in rows:
                payload = self._validated_payload(row)
                message_id = int(row["id"])
                if row["turn_id"] is not None or row["ui_json"] is not None:
                    expected_targets[message_id] = self._validated_existing_target(
                        connection=connection,
                        row=row,
                        payload=payload,
                        inferred_user_message_ids=inferred_user_message_ids,
                    )
                    continue

                turn_id = self._resolve_turn_id(
                    connection,
                    row=row,
                    payload=payload,
                    inferred_user_message_ids=inferred_user_message_ids,
                )
                content_format = self._content_format(row=row, payload=payload)
                source_content = self._required_content(row)
                ui_text = (
                    _normalize_legacy_markdown(source_content)[0] if content_format == "markdown" else source_content
                )
                target = _project_message_target(
                    message_id=message_id,
                    turn_id=turn_id,
                    role=_target_role(row["role"]),
                    content_format=content_format,
                    ui_text=ui_text,
                    payload=payload,
                )
                expected_targets[message_id] = target
                if (
                    row["turn_id"] != target.turn_id
                    or row["content"] != target.content
                    or row["ui_json"] != target.ui_json
                    or row["diagnostics_json"] != target.diagnostics_json
                ):
                    update_result = connection.execute(
                        update(self._messages)
                        .where(self._messages.c.id == row["id"])
                        .values(
                            turn_id=target.turn_id,
                            content=target.content,
                            ui_json=target.ui_json,
                            diagnostics_json=target.diagnostics_json,
                        )
                    )
                    if update_result.rowcount != 1:
                        raise AgentMessageMigrationError(f"message {row['id']} did not update exactly one row")
                    migrated_count += 1

            source_ids = [int(row["id"]) for row in rows]
            persisted_rows = (
                list(
                    connection.execute(
                        select(self._messages).where(self._messages.c.id.in_(source_ids)).order_by(self._messages.c.id)
                    ).mappings()
                )
                if source_ids
                else []
            )
            if len(persisted_rows) != len(rows):
                raise AgentMessageMigrationError("persisted target row count does not match the source batch")
            validated_target_count = 0
            for persisted_row in persisted_rows:
                self._validate_message_identity(connection, persisted_row)
                persisted_payload = self._validated_payload(persisted_row)
                persisted_target = self._validated_existing_target(
                    connection=connection,
                    row=persisted_row,
                    payload=persisted_payload,
                    inferred_user_message_ids=inferred_user_message_ids,
                )
                if persisted_target != expected_targets[int(persisted_row["id"])]:
                    raise AgentMessageMigrationError(
                        f"message {persisted_row['id']} persisted target differs from the expected projection"
                    )
                validated_target_count += 1

            last_id = int(rows[-1]["id"]) if rows else None
            has_more = False
            if last_id is not None:
                has_more = (
                    connection.scalar(
                        select(self._messages.c.id)
                        .where(self._messages.c.id > last_id)
                        .order_by(self._messages.c.id)
                        .limit(1)
                    )
                    is not None
                )

            return AgentMessageMigrationBatchResult(
                after_id=after_id,
                last_id=last_id,
                source_row_count=len(rows),
                target_row_count=len(persisted_rows),
                migrated_row_count=migrated_count,
                schema_validated_count=validated_target_count,
                source_payload_checksum=_checksum(source_checksum_rows),
                target_ui_checksum=_checksum(
                    [{"id": int(row["id"]), "ui_json": row["ui_json"]} for row in persisted_rows]
                ),
                has_more=has_more,
            )

    def _validate_message_identity(self, connection: Connection, row: RowMapping) -> None:
        session_owner = (
            connection.execute(
                select(
                    self._sessions.c.team_id,
                    self._sessions.c.user_id,
                ).where(self._sessions.c.id == row["session_id"])
            )
            .mappings()
            .first()
        )
        if session_owner is None:
            raise AgentMessageMigrationError(f"message {row['id']} has no owning session")
        if session_owner["team_id"] != row["team_id"] or session_owner["user_id"] != row["user_id"]:
            raise AgentMessageMigrationError(f"message {row['id']} owner does not match its session")

        expected_event_type = {
            "USER": "user_message",
            "ASSISTANT": "assistant_message",
        }.get(row["role"])
        if expected_event_type is None:
            raise AgentMessageMigrationError(f"message {row['id']} has unsupported role")
        if row["event_type"] is not None and row["event_type"] != expected_event_type:
            raise AgentMessageMigrationError(f"message {row['id']} event type does not match role")

    @staticmethod
    def _validated_payload(row: RowMapping) -> dict[str, JsonValue] | None:
        payload, valid = coerce_agent_message_payload(row["payload_json"])
        if not valid or (payload is not None and not isinstance(payload, dict)):
            raise AgentMessageMigrationError(f"message {row['id']} has invalid payload JSON")
        if payload is not None and frozenset(str(key) for key in payload) not in KNOWN_MESSAGE_PAYLOAD_KEY_SETS:
            raise AgentMessageMigrationError(f"message {row['id']} has an unknown payload shape")
        if payload is not None and "trace_events" in payload and not isinstance(payload["trace_events"], list):
            raise AgentMessageMigrationError(f"message {row['id']} has invalid payload data")
        return payload

    def _validated_existing_target(
        self,
        *,
        connection: Connection,
        row: RowMapping,
        payload: dict[str, JsonValue] | None,
        inferred_user_message_ids: dict[int, int],
    ) -> _ProjectedMessageTarget:
        if row["turn_id"] is None or row["ui_json"] is None or row["content"] is None:
            raise AgentMessageMigrationError(f"message {row['id']} has a partial target projection")
        try:
            envelope = AgentUIEnvelope.model_validate(row["ui_json"])
        except ValueError as exc:
            raise AgentMessageMigrationError(f"message {row['id']} has invalid target Agent UI") from exc
        expected_turn_id = self._resolve_turn_id(
            connection,
            row=row,
            payload=payload,
            inferred_user_message_ids=inferred_user_message_ids,
        )
        if (
            row["turn_id"] != expected_turn_id
            or envelope.message_id != int(row["id"])
            or envelope.turn_id != expected_turn_id
            or envelope.role != _target_role(row["role"])
            or envelope.state != "final"
        ):
            raise AgentMessageMigrationError(f"message {row['id']} target identity does not match the source row")
        if row["content"] != envelope.metadata.accessibility_label:
            raise AgentMessageMigrationError(
                f"message {row['id']} target content does not match accessibility metadata"
            )
        if not envelope.blocks or not isinstance(envelope.blocks[0], TextBlock):
            raise AgentMessageMigrationError(f"message {row['id']} target blocks do not match deterministic projection")
        text_block = envelope.blocks[0]
        content_format = self._content_format(row=row, payload=payload)
        if text_block.id != "b_text_1" or text_block.format != content_format:
            raise AgentMessageMigrationError(f"message {row['id']} target blocks do not match deterministic projection")
        expected = _project_message_target(
            message_id=int(row["id"]),
            turn_id=expected_turn_id,
            role=_target_role(row["role"]),
            content_format=content_format,
            ui_text=text_block.text,
            payload=payload,
        )
        expected_envelope = AgentUIEnvelope.model_validate(expected.ui_json)
        actual_blocks = [block.model_dump(mode="json") for block in envelope.blocks]
        expected_blocks = [block.model_dump(mode="json") for block in expected_envelope.blocks]
        if actual_blocks != expected_blocks:
            raise AgentMessageMigrationError(f"message {row['id']} target blocks do not match deterministic projection")
        if row["diagnostics_json"] != expected.diagnostics_json:
            raise AgentMessageMigrationError(f"message {row['id']} target diagnostics do not match the source payload")
        if (
            row["content"] != expected.content
            or row["ui_json"] != expected.ui_json
            or row["turn_id"] != expected.turn_id
        ):
            raise AgentMessageMigrationError(f"message {row['id']} target projection is not deterministic")
        return expected

    def _build_inferred_user_message_ids(
        self,
        connection: Connection,
        *,
        rows: list[RowMapping],
    ) -> dict[int, int]:
        scopes = {(row["team_id"], row["user_id"], row["session_id"]) for row in rows if row["role"] == "ASSISTANT"}
        inferred_user_message_ids: dict[int, int] = {}
        for team_id, user_id, session_id in scopes:
            session_rows = list(
                connection.execute(
                    select(self._messages).where(
                        self._messages.c.team_id == team_id,
                        self._messages.c.user_id == user_id,
                        self._messages.c.session_id == session_id,
                    )
                ).mappings()
            )
            for session_row in session_rows:
                self._validate_message_identity(connection, session_row)
            inferred_user_message_ids.update(self._infer_session_user_message_ids(session_rows))
        return inferred_user_message_ids

    def _infer_session_user_message_ids(
        self,
        rows: list[RowMapping],
    ) -> dict[int, int]:
        ordered_rows = sorted(rows, key=lambda row: int(row["id"]))
        user_ids = {int(row["id"]) for row in ordered_rows if row["role"] == "USER"}
        claimed_user_ids: set[int] = set()
        inferred_user_message_ids: dict[int, int] = {}

        for row in ordered_rows:
            if row["role"] != "ASSISTANT":
                continue
            payload = self._validated_payload(row)
            has_explicit_lineage, linked_user_id = _explicit_user_message_lineage(payload)
            assistant_id = int(row["id"])
            if not has_explicit_lineage:
                if payload is None or frozenset(payload) != {"source"}:
                    raise AgentMessageMigrationError(
                        f"assistant message {row['id']} is missing explicit user-message lineage"
                    )
                preceding_user_ids = [user_id for user_id in user_ids if user_id < assistant_id]
                if not preceding_user_ids:
                    raise AgentMessageMigrationError(
                        f"assistant message {assistant_id} is missing its user-message lineage"
                    )
                linked_user_id = max(preceding_user_ids)
                if linked_user_id in claimed_user_ids:
                    raise AgentMessageMigrationError(
                        f"assistant message {assistant_id} has ambiguous user-message lineage"
                    )
                inferred_user_message_ids[assistant_id] = linked_user_id
            if type(linked_user_id) is not int:
                raise AgentMessageMigrationError(f"assistant message {row['id']} has invalid user-message lineage")
            if linked_user_id not in user_ids or linked_user_id >= assistant_id or linked_user_id in claimed_user_ids:
                raise AgentMessageMigrationError(f"assistant message {row['id']} has invalid user-message lineage")
            claimed_user_ids.add(linked_user_id)

        return inferred_user_message_ids

    def _resolve_turn_id(
        self,
        connection: Connection,
        *,
        row: RowMapping,
        payload: dict[str, JsonValue] | None,
        inferred_user_message_ids: dict[int, int],
    ) -> str:
        if row["role"] == "USER":
            return f"turn_legacy_{row['id']}"
        if row["role"] != "ASSISTANT":
            raise AgentMessageMigrationError(f"message {row['id']} has unsupported role")

        has_explicit_lineage, linked_user_id = _explicit_user_message_lineage(payload)
        if not has_explicit_lineage:
            linked_user_id = inferred_user_message_ids.get(int(row["id"]))
            if linked_user_id is None:
                raise AgentMessageMigrationError(f"assistant message {row['id']} is missing its user-message lineage")
        if type(linked_user_id) is not int:
            raise AgentMessageMigrationError(f"assistant message {row['id']} has invalid user-message lineage")
        user_row = (
            connection.execute(select(self._messages).where(self._messages.c.id == linked_user_id).limit(1))
            .mappings()
            .first()
        )
        if (
            user_row is None
            or user_row["role"] != "USER"
            or int(user_row["id"]) >= int(row["id"])
            or user_row["team_id"] != row["team_id"]
            or user_row["user_id"] != row["user_id"]
            or user_row["session_id"] != row["session_id"]
        ):
            raise AgentMessageMigrationError(f"assistant message {row['id']} has invalid user-message lineage")
        return str(user_row["turn_id"] or f"turn_legacy_{user_row['id']}")

    @staticmethod
    def _content_format(
        *,
        row: RowMapping,
        payload: dict[str, JsonValue] | None,
    ) -> Literal["plain", "markdown"]:
        if row["role"] == "USER":
            return "plain"
        raw_format = payload.get("content_format") if payload is not None else None
        if raw_format in {None, "text"}:
            return "plain"
        if raw_format == "markdown":
            return "markdown"
        raise AgentMessageMigrationError(f"message {row['id']} has an unsupported content format")

    @staticmethod
    def _required_content(row: RowMapping) -> str:
        content = row["content"]
        if not isinstance(content, str):
            raise AgentMessageMigrationError(f"message {row['id']} is missing content")
        return content


def _explicit_user_message_lineage(
    payload: dict[str, JsonValue] | None,
) -> tuple[bool, JsonValue | None]:
    if payload is None:
        return False, None
    if "for_user_message_id" in payload:
        return True, payload["for_user_message_id"]
    if "recovered_for_user_message_id" in payload:
        return True, payload["recovered_for_user_message_id"]
    return False, None


def _target_role(role: object) -> Literal["user", "assistant", "system"]:
    if role == "USER":
        return "user"
    if role == "ASSISTANT":
        return "assistant"
    raise AgentMessageMigrationError("unsupported historical message role")


def _project_message_target(
    *,
    message_id: int,
    turn_id: str,
    role: Literal["user", "assistant", "system"],
    content_format: Literal["plain", "markdown"],
    ui_text: str,
    payload: dict[str, JsonValue] | None,
) -> _ProjectedMessageTarget:
    visible_content = project_agent_markdown_to_plain_text(ui_text) if content_format == "markdown" else ui_text
    projected_content = visible_content
    blocks: list[TextBlock | InteractionBlock | ActionResultBlock] = [
        TextBlock(
            id="b_text_1",
            type="text",
            format=content_format,
            text=ui_text,
        )
    ]
    interaction_projection = _historical_interaction_projection(
        message_id=message_id,
        payload=payload,
    )
    if interaction_projection is not None:
        interaction_block, interaction_content = interaction_projection
        blocks.append(interaction_block)
        projected_content = interaction_content
    action_result_projection = _historical_action_result_projection(
        message_id=message_id,
        payload=payload,
        fallback_message=visible_content,
    )
    if action_result_projection is not None:
        action_result_block, action_result_summary = action_result_projection
        blocks.append(action_result_block)
        projected_content = _append_searchable_summary(projected_content, action_result_summary)
    envelope = AgentUIEnvelope(
        schema_version="crm.agent.ui.v1",
        message_id=message_id,
        turn_id=turn_id,
        role=role,
        state="final",
        blocks=blocks,
        suggested_actions=[],
        metadata=AgentUIMetadata(accessibility_label=projected_content),
    )
    return _ProjectedMessageTarget(
        turn_id=turn_id,
        content=projected_content,
        ui_json=envelope.model_dump(mode="json"),
        diagnostics_json=_diagnostics_from_payload(payload),
    )


def _historical_interaction_projection(
    *,
    message_id: int,
    payload: dict[str, JsonValue] | None,
) -> tuple[InteractionBlock, str] | None:
    if payload is None:
        return None
    trace_events = payload.get("trace_events")
    if not isinstance(trace_events, list):
        return None
    interaction: dict[str, JsonValue] | None = None
    for event in reversed(trace_events):
        if not isinstance(event, dict):
            continue
        candidate = event.get("interaction")
        if isinstance(candidate, dict) and candidate.get("schema_version") == "agent.interaction.v1":
            interaction = candidate
            break
    if interaction is None:
        return None

    prompt = interaction.get("prompt")
    interaction_id = interaction.get("interaction_id")
    if not isinstance(prompt, str) or not prompt.strip():
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
    if interaction_id is not None and (not isinstance(interaction_id, str) or not interaction_id):
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")

    interaction_type = interaction.get("type")
    fields: list[InteractionField] = []
    options: list[InteractionOption] = []
    selection_mode: Literal["single", "multiple"] | None = None
    min_selections: int | None = None
    max_selections: int | None = None
    allow_blank: bool | None = None
    target_type: Literal["choice", "form", "text_input"]

    if interaction_type == "choice":
        target_type = "choice"
        options = _historical_interaction_options(message_id=message_id, raw_choices=interaction.get("choices"))
        raw_selection_mode = interaction.get("selection_mode")
        raw_min_selections = interaction.get("min_selections")
        raw_max_selections = interaction.get("max_selections")
        if (raw_selection_mode, raw_min_selections, raw_max_selections) == (None, None, None):
            selection_mode = "single"
            min_selections = 1
            max_selections = 1
        elif (
            raw_selection_mode not in {"single", "multiple"}
            or type(raw_min_selections) is not int
            or type(raw_max_selections) is not int
        ):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        else:
            selection_mode = "single" if raw_selection_mode == "single" else "multiple"
            min_selections = raw_min_selections
            max_selections = raw_max_selections
    elif interaction_type == "form":
        target_type = "form"
        fields = _historical_interaction_fields(message_id=message_id, raw_fields=interaction.get("fields"))
    elif interaction_type == "text":
        target_type = "text_input"
        raw_allow_blank = interaction.get("allow_free_text", True)
        if not isinstance(raw_allow_blank, bool):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        allow_blank = raw_allow_blank
        placeholder = interaction.get("placeholder")
        if placeholder is not None and not isinstance(placeholder, str):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        fields = [
            InteractionField(
                key="text",
                label="补充内容",
                field_type="textarea",
                required=not allow_blank,
                placeholder=placeholder if placeholder else None,
                min_length=0 if allow_blank else 1,
                max_length=10000,
            )
        ]
    else:
        raise AgentMessageMigrationError(f"message {message_id} has an unsupported historical interaction")

    status = interaction.get("status")
    status_labels = {
        "waiting_user_input": "等待用户输入",
        "waiting_confirmation": "等待确认",
        "submitted": "已提交",
        "completed": "已完成",
        "resolved": "已完成",
        "cancelled": "已取消",
        "expired": "已过期",
    }
    if not isinstance(status, str) or status not in status_labels:
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
    status_label = status_labels[status]
    try:
        block = InteractionBlock(
            id="b_interaction_1",
            type="interaction",
            interaction_id=interaction_id or f"int_legacy_{message_id}",
            interaction_type=target_type,
            state="READ_ONLY",
            prompt=prompt.strip(),
            fields=fields,
            options=options,
            selection_mode=selection_mode,
            min_selections=min_selections,
            max_selections=max_selections,
            allow_blank=allow_blank,
            submit_action_id=None,
        )
    except ValueError as exc:
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction") from exc
    return block, f"{prompt.strip()}\n历史交互状态: {status_label}"


def _historical_interaction_options(
    *,
    message_id: int,
    raw_choices: JsonValue | None,
) -> list[InteractionOption]:
    if not isinstance(raw_choices, list):
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")

    parsed_choices: list[tuple[str, str, str | None, bool, dict[str, JsonValue] | None]] = []
    value_counts: dict[str, int] = {}
    for raw_choice in raw_choices:
        if not isinstance(raw_choice, dict):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        value = raw_choice.get("value")
        label = raw_choice.get("label")
        description = raw_choice.get("description")
        if not isinstance(value, str) or not value or not isinstance(label, str) or not label:
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        if description is not None and not isinstance(description, str):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        disabled = raw_choice.get("disabled", False)
        if not isinstance(disabled, bool):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        metadata = raw_choice.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        parsed_choices.append((value, label, description, disabled, metadata))
        value_counts[value] = value_counts.get(value, 0) + 1

    options: list[InteractionOption] = []
    migrated_values: set[str] = set()
    for value, label, description, disabled, metadata in parsed_choices:
        migrated_value = value
        migrated_description = description
        if value_counts[value] > 1:
            selected_task_id = metadata.get("selected_task_id") if metadata is not None else None
            if type(selected_task_id) is not int or selected_task_id < 1:
                raise AgentMessageMigrationError(f"message {message_id} has an ambiguous historical interaction")
            migrated_value = f"legacy_task_{selected_task_id}"
            task_evidence = f"历史任务 ID: {selected_task_id}"
            migrated_description = (
                task_evidence if migrated_description is None else f"{migrated_description}\n{task_evidence}"
            )
        if migrated_value in migrated_values:
            raise AgentMessageMigrationError(f"message {message_id} has an ambiguous historical interaction")
        migrated_values.add(migrated_value)
        try:
            options.append(
                InteractionOption(
                    value=migrated_value,
                    label=label,
                    description=migrated_description,
                    disabled=disabled,
                )
            )
        except ValueError as exc:
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction") from exc
    return options


def _historical_interaction_fields(
    *,
    message_id: int,
    raw_fields: JsonValue | None,
) -> list[InteractionField]:
    if not isinstance(raw_fields, list):
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
    allowed_types = {"text", "textarea", "number", "date", "datetime", "select", "multi_select", "boolean"}
    fields: list[InteractionField] = []
    for raw_field in raw_fields:
        if not isinstance(raw_field, dict):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        key = raw_field.get("key")
        label = raw_field.get("label")
        field_type = raw_field.get("type", "text")
        placeholder = raw_field.get("placeholder")
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(label, str)
            or not label
            or field_type not in allowed_types
            or (placeholder is not None and not isinstance(placeholder, str))
        ):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        options = (
            _historical_interaction_options(message_id=message_id, raw_choices=raw_field.get("options"))
            if field_type in {"select", "multi_select"}
            else []
        )
        required = raw_field.get("required", False)
        if not isinstance(required, bool):
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction")
        try:
            fields.append(
                InteractionField(
                    key=key,
                    label=label,
                    field_type=field_type,
                    required=required,
                    placeholder=placeholder if placeholder else None,
                    default_value=raw_field.get("default_value"),
                    min_length=0 if field_type in {"text", "textarea"} else None,
                    max_length=10000 if field_type in {"text", "textarea"} else None,
                    minimum=-1_000_000_000 if field_type == "number" else None,
                    maximum=1_000_000_000 if field_type == "number" else None,
                    options=options,
                )
            )
        except ValueError as exc:
            raise AgentMessageMigrationError(f"message {message_id} has an invalid historical interaction") from exc
    return fields


def _historical_action_result_projection(
    *,
    message_id: int,
    payload: dict[str, JsonValue] | None,
    fallback_message: str,
) -> tuple[ActionResultBlock, str] | None:
    if payload is None:
        return None
    trace_events = payload.get("trace_events")
    if not isinstance(trace_events, list):
        return None
    result_event: dict[str, JsonValue] | None = None
    result_event_name: str | None = None
    action_outcomes = {
        "task_completed": ("SUCCESS", "操作已完成"),
        "task_failed": ("FAILED", "操作未完成"),
        "task_cancelled": ("CANCELLED", "操作已取消"),
        "action_completed": ("SUCCESS", "操作已完成"),
        "action_failed": ("FAILED", "操作未完成"),
    }
    for event in reversed(trace_events):
        if not isinstance(event, dict):
            continue
        event_name = event.get("event")
        if isinstance(event_name, str) and event_name in action_outcomes:
            result_event = event
            result_event_name = event_name
            break
    if result_event is None or result_event_name is None:
        return None

    status, title = action_outcomes[result_event_name]
    event_content = result_event.get("content")
    message = fallback_message.strip()
    if result_event_name.startswith("task_") and isinstance(event_content, str) and event_content.strip():
        message = event_content.strip()
    if not message:
        raise AgentMessageMigrationError(f"message {message_id} has an invalid historical action result")
    if len(message) > 10000:
        raise AgentMessageMigrationError(f"message {message_id} historical action result exceeds target limits")
    return (
        ActionResultBlock(
            id="b_action_result_1",
            type="action_result",
            action_id=f"legacy_action_{message_id}",
            status=status,
            title=title,
            message=message,
            entity_ref=None,
        ),
        message,
    )


def _append_searchable_summary(content: str, summary: str) -> str:
    if not summary or summary in content:
        return content
    return f"{content}\n{summary}" if content else summary


def _diagnostics_from_payload(payload: dict[str, JsonValue] | None) -> dict[str, JsonValue] | None:
    if payload is None:
        return None
    diagnostics: dict[str, JsonValue] = {}
    source = payload.get("source")
    if source is not None:
        diagnostics["migration_source"] = source
    trace_events = payload.get("trace_events")
    if trace_events is not None:
        diagnostics["runtime_events"] = trace_events
    turn_observability = payload.get("turn_observability")
    if turn_observability is not None:
        diagnostics["turn_observability"] = turn_observability
    recovery = {
        key: payload[key]
        for key in ("reason", "recovery_status", "related_task_id", "activity_id", "task_id")
        if key in payload
    }
    if recovery:
        diagnostics["recovery"] = recovery
    return diagnostics or None


def _normalize_legacy_markdown(value: str) -> tuple[str, str]:
    """Return target-dialect Markdown plus its searchable plain-text projection."""

    projected = project_agent_markdown_to_plain_text(value)
    try:
        validate_agent_markdown(value)
    except ValueError:
        safe_markdown = projected
        try:
            validate_agent_markdown(safe_markdown)
        except ValueError:
            safe_markdown = re.sub(r"([\\`*_[\]])", r"\\\1", safe_markdown)
            validate_agent_markdown(safe_markdown)
        return safe_markdown, projected
    return value, projected


def _checksum(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
