"""Opportunity approval snapshot backfill tests."""
import importlib.util
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


def _load_backfill_module():
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(
        here, "migrations", "versions", "035_backfill_opportunity_approval_snapshots.py",
    )
    spec = importlib.util.spec_from_file_location("_m035_opportunity_backfill", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_backfill_mod = _load_backfill_module()


def _load_cleanup_module():
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(
        here, "migrations", "versions", "036_remove_extra_opportunity_backfill_records.py",
    )
    spec = importlib.util.spec_from_file_location("_m036_opportunity_cleanup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cleanup_mod = _load_cleanup_module()


@pytest.fixture(scope="function")
def conn():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE crm_opportunities (
                id INTEGER PRIMARY KEY,
                team_id INTEGER NOT NULL,
                opportunity_name VARCHAR(255) NOT NULL,
                approval_phase VARCHAR(20) NOT NULL,
                creator_id VARCHAR(100) NOT NULL,
                created_time DATETIME NOT NULL,
                last_modified_time DATETIME
            )
            """
        ))
        connection.execute(text(
            """
            CREATE TABLE crm_contract_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                contract_id INTEGER,
                business_type VARCHAR(20) NOT NULL,
                business_id INTEGER,
                flow_id INTEGER,
                current_node_id INTEGER,
                status VARCHAR(20) NOT NULL,
                submitter_id VARCHAR(100) NOT NULL,
                submitter_name VARCHAR(100),
                created_time DATETIME NOT NULL,
                updated_time DATETIME NOT NULL
            )
            """
        ))
        connection.execute(text(
            """
            CREATE TABLE crm_contract_approval_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                approval_id INTEGER NOT NULL,
                node_id INTEGER,
                approver_id VARCHAR(100) NOT NULL,
                approver_name VARCHAR(100),
                action VARCHAR(20) NOT NULL,
                comment TEXT,
                created_time DATETIME NOT NULL
            )
            """
        ))
    with engine.begin() as connection:
        yield connection


def _insert_opportunity(conn, opportunity_id: int, approval_phase: str) -> None:
    conn.execute(text(
        """
        INSERT INTO crm_opportunities
            (id, team_id, opportunity_name, approval_phase, creator_id,
             created_time, last_modified_time)
        VALUES
            (:id, 1, :name, :approval_phase, '1',
             '2026-07-01 10:00:00', '2026-07-02 10:00:00')
        """
    ), {
        "id": opportunity_id,
        "name": f"商机{opportunity_id}",
        "approval_phase": approval_phase,
    })


def test_backfills_approved_opportunity_missing_approval(conn):
    _insert_opportunity(conn, 1, "approved")

    _backfill_mod.run_opportunity_approval_snapshot_backfill(conn)

    approval = conn.execute(text(
        """
        SELECT * FROM crm_contract_approvals
        WHERE business_type = 'OPPORTUNITY' AND business_id = 1
        """
    )).mappings().one()
    assert approval["status"] == "APPROVED"
    assert approval["contract_id"] is None
    assert approval["submitter_id"] == "1"
    assert approval["submitter_name"] == _backfill_mod.BACKFILL_SUBMITTER_NAME

    record = conn.execute(text(
        "SELECT * FROM crm_contract_approval_records WHERE approval_id = :id"
    ), {"id": approval["id"]}).mappings().one()
    assert record["action"] == "APPROVE"
    assert record["comment"] == _backfill_mod.BACKFILL_COMMENT


def test_backfill_is_idempotent_and_preserves_existing_approval(conn):
    _insert_opportunity(conn, 1, "approved")
    conn.execute(text(
        """
        INSERT INTO crm_contract_approvals
            (id, team_id, business_type, business_id, status, submitter_id,
             created_time, updated_time)
        VALUES
            (101, 1, 'OPPORTUNITY', 1, 'APPROVED', '9',
             '2026-07-01 10:00:00', '2026-07-02 10:00:00')
        """
    ))

    _backfill_mod.run_opportunity_approval_snapshot_backfill(conn)
    _backfill_mod.run_opportunity_approval_snapshot_backfill(conn)

    approvals = conn.execute(text(
        """
        SELECT id FROM crm_contract_approvals
        WHERE business_type = 'OPPORTUNITY' AND business_id = 1
        """
    )).mappings().all()
    assert [approval["id"] for approval in approvals] == [101]

    records = conn.execute(text(
        "SELECT * FROM crm_contract_approval_records WHERE approval_id = 101"
    )).mappings().all()
    assert len(records) == 0


def test_backfill_skips_non_approved_opportunities(conn):
    _insert_opportunity(conn, 1, "pending_review")

    _backfill_mod.run_opportunity_approval_snapshot_backfill(conn)

    total = conn.execute(text("SELECT COUNT(*) FROM crm_contract_approvals")).scalar()
    assert total == 0


def test_cleanup_removes_backfill_record_when_real_records_exist(conn):
    conn.execute(text(
        """
        INSERT INTO crm_contract_approvals
            (id, team_id, business_type, business_id, status, submitter_id,
             created_time, updated_time)
        VALUES
            (101, 1, 'OPPORTUNITY', 1, 'APPROVED', '9',
             '2026-07-01 10:00:00', '2026-07-02 10:00:00')
        """
    ))
    conn.execute(text(
        """
        INSERT INTO crm_contract_approval_records
            (id, team_id, approval_id, approver_id, action, comment, created_time)
        VALUES
            (201, 1, 101, '9', 'SUBMIT', NULL, '2026-07-01 10:00:00'),
            (202, 1, 101, '9', 'APPROVE', :comment, '2026-07-02 10:00:00')
        """
    ), {"comment": _backfill_mod.BACKFILL_COMMENT})

    _cleanup_mod.remove_extra_opportunity_backfill_records(conn)

    rows = conn.execute(text(
        """
        SELECT id, action, comment
        FROM crm_contract_approval_records
        WHERE approval_id = 101
        ORDER BY id
        """
    )).mappings().all()
    assert [dict(row) for row in rows] == [
        {"id": 201, "action": "SUBMIT", "comment": None},
    ]
