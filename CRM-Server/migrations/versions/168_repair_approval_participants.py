"""Repair pending approval participants omitted by revision 167.

Only rows whose current node is still uniquely tied to the same flow and team
are repaired. If the migrated snapshot omitted that node, the node's persisted
approval configuration is used as the legacy migration source; malformed,
cross-team, cross-flow, missing, and CC nodes remain untouched.
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "168_repair_approval_participants"
down_revision: str | None = "167_approval_approvers_cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _loads(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _role_member_ids(conn: sa.engine.Connection, role_codes: list[str] | None, team_id: int | None) -> list[int]:
    codes = [code for code in dict.fromkeys(role_codes or []) if code]
    if not codes or team_id is None:
        return []
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT ur.user_id FROM user_roles ur "
            "JOIN roles r ON r.id = ur.role_id "
            "WHERE r.code IN :codes AND ur.team_id = :team_id ORDER BY ur.user_id"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": codes, "team_id": team_id},
    ).fetchall()
    return [int(row[0]) for row in rows]


def _is_json_null(value: object) -> bool:
    return value is None or (isinstance(value, (str, bytes)) and value.strip() in ("null", b"null"))


def _current_node_user_ids(conn: sa.engine.Connection, node: sa.Row, team_id: int | None) -> list[int] | None:
    # Runtime routing treats SQL NULL and JSON null as an unused side (`or []`);
    # only other non-list values (including invalid JSON) are malformed.
    roles_value = [] if _is_json_null(node.approver_roles) else _loads(node.approver_roles)
    users_value = [] if _is_json_null(node.approver_users) else _loads(node.approver_users)
    if not isinstance(roles_value, list) or not isinstance(users_value, list):
        return None
    if any(not isinstance(role, str) or not role for role in roles_value):
        return None
    if any(
        not isinstance(item, dict)
        or item.get("user_id") is None
        or not isinstance(item.get("role"), str)
        or not item.get("role")
        for item in users_value
    ):
        return None
    try:
        designated = [int(item["user_id"]) for item in users_value]
    except (TypeError, ValueError):
        return None
    user_roles = [item["role"] for item in users_value]
    role_codes = list(dict.fromkeys([*roles_value, *user_roles]))
    role_members = {
        role: set(_role_member_ids(conn, [role], team_id))
        for role in role_codes
    }
    selected = {
        user_id
        for user_id, item in zip(designated, users_value, strict=True)
        if user_id in role_members[item["role"]]
    }
    for role in roles_value:
        selected.update(role_members[role])
    return sorted(selected)


def upgrade() -> None:
    conn = op.get_bind()
    pending = conn.execute(
        sa.text(
            "SELECT ap.id, ap.team_id, ap.flow_id, ap.current_node_id, ap.nodes_snapshot, ap.created_time, "
            "n.id AS node_id, n.flow_id AS node_flow_id, n.team_id AS node_team_id, n.node_name, "
            "n.node_code, n.node_order, n.node_type, n.approver_roles, n.approver_users, "
            "f.id AS flow_row_id, f.team_id AS flow_team_id "
            "FROM crm_contract_approvals ap "
            "LEFT JOIN crm_approval_nodes n ON n.id = ap.current_node_id "
            "LEFT JOIN crm_approval_flows f ON f.id = ap.flow_id "
            "WHERE ap.status = 'PENDING' AND ap.nodes_snapshot IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM crm_approval_participants p "
            "  WHERE p.approval_id = ap.id AND p.team_id = ap.team_id AND p.kind = 'APPROVER'"
            ")"
        )
    ).fetchall()

    for approval in pending:
        if (
            approval.current_node_id is None
            or approval.node_id is None
            or approval.node_flow_id != approval.flow_id
            or approval.flow_row_id is None
            or (approval.flow_team_id is not None and approval.flow_team_id != approval.team_id)
            or (approval.node_team_id is not None and approval.node_team_id != approval.team_id)
        ):
            continue
        snapshot = _loads(approval.nodes_snapshot)
        if not isinstance(snapshot, list) or any(
            not isinstance(entry, dict)
            or not isinstance(entry.get("node_id"), int)
            or isinstance(entry.get("node_id"), bool)
            for entry in snapshot
        ):
            continue
        current = next((entry for entry in snapshot if entry.get("node_id") == approval.current_node_id), None)
        if current is None:
            if approval.node_type != "APPROVAL":
                continue
            user_ids = _current_node_user_ids(conn, approval, approval.team_id)
            if user_ids is None:
                continue
            current = {
                "node_id": approval.node_id,
                "node_name": approval.node_name,
                "node_code": approval.node_code,
                "node_type": "APPROVAL",
                "user_ids": user_ids,
            }
            # Existing snapshot order is historical routing state and runtime advances by
            # position. Insert only when every frozen entry maps to a same-flow node whose
            # persisted order is consistent with the snapshot order; otherwise the
            # historical position is unprovable and the row stays untouched.
            node_orders = {
                int(row.id): row.node_order
                for row in conn.execute(
                    sa.text(
                        "SELECT id, node_order FROM crm_approval_nodes "
                        "WHERE flow_id = :flow_id AND (team_id = :team_id OR team_id IS NULL)"
                    ),
                    {"flow_id": approval.flow_id, "team_id": approval.team_id},
                ).fetchall()
            }
            frozen_orders = [node_orders.get(entry.get("node_id")) for entry in snapshot]
            if (
                approval.node_order is None
                or any(order is None for order in frozen_orders)
                or any(a >= b for a, b in pairwise(frozen_orders))
                or approval.node_order in frozen_orders
            ):
                continue
            position = sum(1 for order in frozen_orders if order < approval.node_order)
            snapshot.insert(position, current)
            conn.execute(
                sa.text(
                    "UPDATE crm_contract_approvals SET nodes_snapshot = :snapshot "
                    "WHERE id = :approval_id AND team_id = :team_id"
                ),
                {
                    "snapshot": json.dumps(snapshot, ensure_ascii=False),
                    "approval_id": approval.id,
                    "team_id": approval.team_id,
                },
            )
        if current.get("node_type") != "APPROVAL":
            continue
        snapshot_user_ids = current.get("user_ids")
        if not isinstance(snapshot_user_ids, list):
            continue
        try:
            user_ids = sorted({int(uid) for uid in snapshot_user_ids if uid is not None})
        except (TypeError, ValueError):
            continue
        for user_id in user_ids:
            conn.execute(
                sa.text(
                    "INSERT INTO crm_approval_participants "
                    "(team_id, approval_id, node_id, node_name, user_id, kind, created_time) "
                    "SELECT :team_id, :approval_id, :node_id, :node_name, :user_id, "
                    "'APPROVER', :created_time WHERE NOT EXISTS ("
                    "SELECT 1 FROM crm_approval_participants WHERE team_id = :team_id "
                    "AND approval_id = :approval_id AND node_id = :node_id "
                    "AND user_id = :user_id AND kind = 'APPROVER')"
                ),
                {
                    "team_id": approval.team_id,
                    "approval_id": approval.id,
                    "node_id": current["node_id"],
                    "node_name": current.get("node_name"),
                    "user_id": user_id,
                    "created_time": approval.created_time,
                },
            )


def downgrade() -> None:
    # Participant rows are owned by revision 167 and cannot be safely distinguished
    # from rows created by normal runtime routing. This repair is intentionally irreversible.
    pass
