"""Use POSTPONE and persist matcher decisions as a batch contract.

Revision ID: 106_postpone_batch_matcher
Revises: 105_activity_next_action_source
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "106_postpone_batch_matcher"
down_revision: str | None = "105_activity_next_action_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MATCHER_TABLE = "crm_follow_up_task_llm_matcher_runs"
EVALUATION_TABLE = "crm_follow_up_task_reconciliation_evaluation_runs"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _column_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {str(column["name"]) for column in _inspector().get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {str(index["name"]) for index in _inspector().get_indexes(table_name)}


def _rewrite_contract_value(value: Any, *, reverse: bool = False) -> Any:
    replacements = (
        (
            ("POSTPONE", "DELAY"),
            ("postpone", "delay"),
        )
        if reverse
        else (
            ("DELAY", "POSTPONE"),
            ("delay", "postpone"),
        )
    )
    if isinstance(value, dict):
        return {
            _rewrite_contract_value(key, reverse=reverse): _rewrite_contract_value(item, reverse=reverse)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_contract_value(item, reverse=reverse) for item in value]
    if isinstance(value, str):
        updated = value
        for old, new in replacements:
            updated = updated.replace(old, new)
        return updated
    return value


def _rewrite_json_column(table_name: str, column_name: str) -> None:
    columns = _column_names(table_name)
    if "id" not in columns or column_name not in columns:
        return
    table = sa.table(
        table_name,
        sa.column("id", sa.BigInteger()),
        sa.column(column_name, sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(table.c.id, table.c[column_name]).where(table.c[column_name].is_not(None))
    ).mappings()
    for row in rows:
        value = row[column_name]
        rewritten = _rewrite_contract_value(value)
        if rewritten != value:
            connection.execute(
                table.update().where(table.c.id == row["id"]).values({column_name: rewritten})
            )


def _rewrite_scalar_action(table_name: str, column_name: str) -> None:
    if column_name not in _column_names(table_name):
        return
    table = sa.table(table_name, sa.column(column_name, sa.String(length=30)))
    op.get_bind().execute(
        table.update().where(table.c[column_name] == "DELAY").values({column_name: "POSTPONE"})
    )


def _add_batch_matcher_columns() -> None:
    columns = _column_names(MATCHER_TABLE)
    if not columns:
        return
    if "task_decisions_json" not in columns:
        op.add_column(
            MATCHER_TABLE,
            sa.Column("task_decisions_json", sa.JSON(), nullable=True, comment="逐任务语义决策快照"),
        )
    if "empty_outcome_json" not in columns:
        op.add_column(
            MATCHER_TABLE,
            sa.Column("empty_outcome_json", sa.JSON(), nullable=True, comment="无候选任务时的明确结果"),
        )


def _backfill_batch_matcher_rows() -> None:
    required = {
        "id",
        "decision",
        "task_public_id",
        "candidate_public_ids_json",
        "confidence",
        "needs_confirmation",
        "forbid_auto_reasons_json",
        "evidence_terms_json",
        "task_decisions_json",
        "empty_outcome_json",
    }
    if not required.issubset(_column_names(MATCHER_TABLE)):
        return

    matcher = sa.table(
        MATCHER_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("decision", sa.String(length=30)),
        sa.column("task_public_id", sa.String(length=64)),
        sa.column("candidate_public_ids_json", sa.JSON()),
        sa.column("confidence", sa.Float()),
        sa.column("needs_confirmation", sa.Boolean()),
        sa.column("forbid_auto_reasons_json", sa.JSON()),
        sa.column("evidence_terms_json", sa.JSON()),
        sa.column("task_decisions_json", sa.JSON()),
        sa.column("empty_outcome_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(matcher)).mappings()
    for row in rows:
        decision = _rewrite_contract_value(row["decision"])
        task_public_id = row["task_public_id"]
        candidate_ids = row["candidate_public_ids_json"] if isinstance(row["candidate_public_ids_json"], list) else []
        confidence = float(row["confidence"] or 0.0)
        evidence_terms = row["evidence_terms_json"] if isinstance(row["evidence_terms_json"], list) else []
        forbid_reasons = (
            row["forbid_auto_reasons_json"] if isinstance(row["forbid_auto_reasons_json"], list) else []
        )
        task_decisions: list[dict[str, Any]] = []
        empty_outcome: dict[str, Any] | None = None
        if task_public_id and decision:
            task_decisions.append(
                {
                    "decision": decision,
                    "task_public_id": task_public_id,
                    "confidence": confidence,
                    "needs_confirmation": bool(row["needs_confirmation"]),
                    "proposed_due_at": None,
                    "forbid_auto_reasons": _rewrite_contract_value(forbid_reasons),
                    "evidence_terms": _rewrite_contract_value(evidence_terms),
                    "state_mutation_requested": False,
                }
            )
        elif not candidate_ids:
            empty_outcome = {
                "reason": "MIGRATED_MATCHER_RUN_WITHOUT_CANDIDATES",
                "confidence": confidence,
                "evidence_terms": _rewrite_contract_value(evidence_terms),
            }
        connection.execute(
            matcher.update()
            .where(matcher.c.id == row["id"])
            .values(task_decisions_json=task_decisions, empty_outcome_json=empty_outcome)
        )


def _drop_scalar_matcher_contract() -> None:
    if not _table_exists(MATCHER_TABLE):
        return
    existing_indexes = _index_names(MATCHER_TABLE)
    for index_name in (
        "idx_follow_up_llm_matcher_decision",
        "idx_follow_up_llm_matcher_task_public",
        "idx_follow_up_llm_matcher_needs_confirmation",
        "idx_follow_up_llm_matcher_decision_time",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=MATCHER_TABLE)
    columns = _column_names(MATCHER_TABLE)
    removable = [
        name
        for name in (
            "decision",
            "task_public_id",
            "confidence",
            "needs_confirmation",
            "forbid_auto_reasons_json",
            "evidence_terms_json",
        )
        if name in columns
    ]
    if removable:
        with op.batch_alter_table(MATCHER_TABLE) as batch_op:
            for column_name in removable:
                batch_op.drop_column(column_name)


def _rename_evaluation_columns() -> None:
    columns = _column_names(EVALUATION_TABLE)
    if "false_delay_count" in columns and "false_postpone_count" not in columns:
        with op.batch_alter_table(EVALUATION_TABLE) as batch_op:
            batch_op.alter_column(
                "false_delay_count",
                new_column_name="false_postpone_count",
                existing_type=sa.Integer(),
                existing_nullable=False,
            )
    columns = _column_names(EVALUATION_TABLE)
    if "false_delay_rate" in columns and "false_postpone_rate" not in columns:
        with op.batch_alter_table(EVALUATION_TABLE) as batch_op:
            batch_op.alter_column(
                "false_delay_rate",
                new_column_name="false_postpone_rate",
                existing_type=sa.Float(),
                existing_nullable=False,
            )


def upgrade() -> None:
    _add_batch_matcher_columns()
    _backfill_batch_matcher_rows()

    for table_name, column_name in (
        ("crm_follow_up_task_confirmation_cases", "suggested_action"),
        ("crm_follow_up_task_confirmation_cases", "resolved_action"),
        ("crm_follow_up_task_transition_policy_decision_logs", "action"),
    ):
        _rewrite_scalar_action(table_name, column_name)

    for table_name, column_name in (
        ("crm_follow_up_tasks", "evidence_json"),
        ("crm_follow_up_task_events", "payload_json"),
        ("crm_follow_up_task_confirmation_cases", "source_plan_json"),
        ("crm_follow_up_task_confirmation_prompt_deliveries", "payload_json"),
        ("crm_follow_up_task_transition_policy_decision_logs", "allowed_actions_json"),
        ("crm_follow_up_task_transition_policy_decision_logs", "policy_result_json"),
        ("crm_follow_up_task_transition_policy_decision_logs", "context_json"),
        (EVALUATION_TABLE, "metrics_json"),
        (EVALUATION_TABLE, "failure_cases_json"),
        (EVALUATION_TABLE, "case_results_json"),
        (EVALUATION_TABLE, "thresholds_json"),
        ("crm_agent_sessions", "context_json"),
        ("crm_agent_messages", "payload_json"),
        ("crm_agent_workflow_actions", "payload_json"),
        ("crm_agent_async_operation_events", "payload_json"),
    ):
        _rewrite_json_column(table_name, column_name)

    _drop_scalar_matcher_contract()
    _rename_evaluation_columns()


def downgrade() -> None:
    raise RuntimeError(
        "106_postpone_batch_matcher is intentionally irreversible: batch matcher decisions cannot be losslessly "
        "projected back into the removed scalar contract"
    )
