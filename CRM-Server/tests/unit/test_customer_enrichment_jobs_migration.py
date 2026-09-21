from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


class _RecordingOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record


def _load_migration() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "136_customer_initial_enrichment.py"
    spec = importlib.util.spec_from_file_location("customer_initial_enrichment_136", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_136_creates_enrichment_jobs_and_profile_gate_column():
    migration = _load_migration()
    operations = _RecordingOperations()
    migration.op = operations

    migration.upgrade()

    assert migration.revision == "136_customer_initial_enrichment"
    assert migration.down_revision == "135_deal_journey_public_ids"
    create_table = next(call for call in operations.calls if call[0] == "create_table")
    assert create_table[1][0] == "crm_customer_enrichment_jobs"
    items = create_table[1][1:]
    columns = {item.name for item in items if hasattr(item, "name")}
    assert {
        "public_id", "team_id", "customer_id", "purpose", "plan_version",
        "requested_fields_json", "status", "available_at", "profile_gate_deadline_at",
        "attempt_count", "max_attempts", "next_attempt_at", "lease_token",
        "lease_expires_at", "run_id", "graph_thread_id", "first_attempt_finished_at",
        "profile_gate_timed_out_at", "profile_refresh_request_id", "profile_refresh_enqueued_at",
        "requeue_count", "result_json", "error_message", "started_at", "finished_at",
        "created_time", "updated_time",
    } <= columns
    constraints = {item.name for item in items if getattr(item, "name", None)}
    assert "uq_customer_enrichment_job_plan" in constraints
    assert "ck_customer_enrichment_job_status" in constraints
    assert "ck_customer_enrichment_job_purpose" in constraints
    add_column = next(call for call in operations.calls if call[0] == "add_column")
    assert add_column[1][0] == "crm_customer_intelligence_runs"
    assert add_column[1][1].name == "not_before_at"
