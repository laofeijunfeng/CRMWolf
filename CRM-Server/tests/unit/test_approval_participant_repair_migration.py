"""Regression coverage for repairing pending approvals after revision 167."""

import importlib.util
import json
from pathlib import Path

import sqlalchemy as sa

REVISION = Path(__file__).resolve().parents[2] / "migrations/versions/168_repair_approval_participants.py"


def _load_revision():
    spec = importlib.util.spec_from_file_location("migration_168", REVISION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, operation):
    with engine.begin() as connection:

        class _Op:
            @staticmethod
            def get_bind():
                return connection

        module = _load_revision()
        module.op = _Op()
        operation = getattr(module, operation.__name__)
        operation()


def _node(
    node_id: int,
    team_id: int,
    flow_id: int,
    name: str,
    code: str,
    node_order: int,
    node_type: str,
    roles: str | None,
    users: str,
) -> dict:
    return {
        "id": node_id,
        "team_id": team_id,
        "flow_id": flow_id,
        "name": name,
        "code": code,
        "node_order": node_order,
        "node_type": node_type,
        "roles": roles,
        "users": users,
    }


def _entry(node_id: int, name: str, code: str, user_ids: list) -> dict:
    return {"node_id": node_id, "node_name": name, "node_code": code, "node_type": "APPROVAL", "user_ids": user_ids}


def _approval(approval_id: int, flow_id: int, current_node_id: int, snapshot: list[dict]) -> dict:
    return {
        "id": approval_id,
        "flow_id": flow_id,
        "current_node_id": current_node_id,
        "snapshot": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
    }


def test_upgrade_repairs_current_snapshot_gap_without_cross_team_backfill():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE roles (id INTEGER PRIMARY KEY, code VARCHAR(50) NOT NULL)")
        conn.exec_driver_sql(
            "CREATE TABLE user_roles (user_id INTEGER NOT NULL, role_id INTEGER NOT NULL, team_id INTEGER NOT NULL)"
        )
        conn.exec_driver_sql("CREATE TABLE crm_approval_flows (id INTEGER PRIMARY KEY, team_id INTEGER)")
        conn.exec_driver_sql(
            """CREATE TABLE crm_approval_nodes (
                id INTEGER PRIMARY KEY, team_id INTEGER, flow_id INTEGER NOT NULL,
                node_name VARCHAR(100), node_code VARCHAR(100), node_order INTEGER NOT NULL,
                node_type VARCHAR(20) NOT NULL, approver_roles JSON, approver_users JSON,
                is_archived INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.exec_driver_sql(
            """CREATE TABLE crm_contract_approvals (
                id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, flow_id INTEGER NOT NULL,
                current_node_id INTEGER, nodes_snapshot JSON, status VARCHAR(30) NOT NULL,
                created_time DATETIME NOT NULL
            )"""
        )
        conn.exec_driver_sql(
            """CREATE TABLE crm_approval_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT, team_id INTEGER NOT NULL,
                approval_id INTEGER NOT NULL, node_id INTEGER NOT NULL, node_name VARCHAR(100),
                user_id INTEGER NOT NULL, kind VARCHAR(20) NOT NULL, created_time DATETIME NOT NULL
            )"""
        )
        conn.exec_driver_sql("INSERT INTO roles VALUES (1, 'SALES')")
        conn.exec_driver_sql("INSERT INTO user_roles VALUES (101, 1, 10), (201, 1, 20)")
        conn.exec_driver_sql("INSERT INTO crm_approval_flows VALUES (1, 10), (2, 20)")
        sales = '["SALES"]'
        designated = '[{"user_id":101,"role":"SALES"}]'
        bad_designated = '[{"user_id":"bad","role":"SALES"}]'
        conn.execute(
            sa.text(
                "INSERT INTO crm_approval_nodes VALUES "
                "(:id, :team_id, :flow_id, :name, :code, :node_order, :node_type, :roles, :users, 0)"
            ),
            [
                _node(1, 10, 1, "销售", "SALES", 1, "APPROVAL", sales, "[]"),
                _node(2, 10, 1, "财务", "FINANCE", 2, "APPROVAL", sales, "[]"),
                _node(3, 20, 1, "跨团队", "OTHER", 2, "APPROVAL", sales, "[]"),
                _node(4, 10, 1, "已冻结审批", "FROZEN", 3, "CC", "[]", "[]"),
                _node(5, 10, 1, "指定成员", "DESIGNATED", 4, "APPROVAL", "[]", designated),
                _node(6, 10, 1, "坏配置", "MALFORMED", 5, "APPROVAL", "[]", bad_designated),
                _node(7, 10, 1, "法务", "LEGAL", 6, "APPROVAL", sales, "[]"),
                _node(8, 10, 2, "跨团队流程", "FOREIGN_FLOW", 1, "APPROVAL", sales, "[]"),
                _node(9, 10, 1, "仅指定成员", "DESIGNATED_NULL_ROLES", 7, "APPROVAL", None, designated),
                _node(10, 10, 1, "指定成员JSON空", "DESIGNATED_JSON_NULL", 8, "APPROVAL", "null", designated),
            ],
        )
        sales_entry = _entry(1, "销售", "SALES", [101])
        conn.execute(
            sa.text(
                "INSERT INTO crm_contract_approvals VALUES "
                "(:id, 10, :flow_id, :current_node_id, :snapshot, 'PENDING', '2026-01-01 12:00:00')"
            ),
            [
                _approval(1, 1, 2, [sales_entry]),
                _approval(2, 1, 1, [sales_entry]),
                _approval(3, 1, 3, [sales_entry]),
                _approval(4, 1, 999, [sales_entry]),
                _approval(5, 1, 5, [sales_entry]),
                _approval(6, 1, 6, [sales_entry]),
                _approval(7, 1, 4, [_entry(4, "已冻结审批", "FROZEN", [101])]),
                _approval(8, 1, 5, [_entry(2, "财务", "FINANCE", [101]), sales_entry]),
                _approval(9, 1, 1, [_entry(1, "销售", "SALES", ["bad"])]),
                _approval(10, 1, 2, [sales_entry, _entry(7, "法务", "LEGAL", [101])]),
                _approval(11, 2, 8, [_entry(8, "跨团队流程", "FOREIGN_FLOW", [101])]),
                _approval(12, 1, 9, [sales_entry]),
                _approval(13, 1, 2, [{"node_id": [1], "node_type": "APPROVAL", "user_ids": [101]}]),
                _approval(14, 1, 10, [sales_entry]),
            ],
        )

    revision = _load_revision()
    _run(engine, revision.upgrade)
    _run(engine, revision.upgrade)

    with engine.connect() as conn:
        snapshot = json.loads(
            conn.execute(sa.text("SELECT nodes_snapshot FROM crm_contract_approvals WHERE id=1")).scalar_one()
        )
        assert [entry["node_id"] for entry in snapshot] == [1, 2]
        assert snapshot[1]["user_ids"] == [101]
        repaired = conn.execute(
            sa.text(
                "SELECT team_id, approval_id, node_id, user_id, kind FROM crm_approval_participants "
                "ORDER BY approval_id, node_id"
            )
        ).fetchall()
        assert repaired == [
            (10, 1, 2, 101, "APPROVER"),
            (10, 2, 1, 101, "APPROVER"),
            (10, 5, 5, 101, "APPROVER"),
            (10, 7, 4, 101, "APPROVER"),
            (10, 10, 2, 101, "APPROVER"),
            (10, 12, 9, 101, "APPROVER"),
            (10, 14, 10, 101, "APPROVER"),
        ]
        malformed_snapshot = conn.execute(
            sa.text("SELECT nodes_snapshot FROM crm_contract_approvals WHERE id=6")
        ).scalar_one()
        assert json.loads(malformed_snapshot) == json.loads(
            '[{"node_id":1,"node_name":"销售","node_code":"SALES","node_type":"APPROVAL","user_ids":[101]}]'
        )
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM crm_approval_participants WHERE approval_id=3")).scalar_one()
            == 0
        )
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM crm_approval_participants WHERE approval_id=4")).scalar_one()
            == 0
        )
        future = json.loads(
            conn.execute(sa.text("SELECT nodes_snapshot FROM crm_contract_approvals WHERE id=10")).scalar_one()
        )
        assert [entry["node_id"] for entry in future] == [1, 2, 7]
        reordered = json.loads(
            conn.execute(sa.text("SELECT nodes_snapshot FROM crm_contract_approvals WHERE id=8")).scalar_one()
        )
        assert [entry["node_id"] for entry in reordered] == [2, 1]
        designated_only = json.loads(
            conn.execute(sa.text("SELECT nodes_snapshot FROM crm_contract_approvals WHERE id=12")).scalar_one()
        )
        assert [entry["node_id"] for entry in designated_only] == [1, 9]
        unhashable = json.loads(
            conn.execute(sa.text("SELECT nodes_snapshot FROM crm_contract_approvals WHERE id=13")).scalar_one()
        )
        assert unhashable == [{"node_id": [1], "node_type": "APPROVAL", "user_ids": [101]}]

    engine.dispose()
