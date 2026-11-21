"""Approval nodes: 审批人员 (roles + designated members) and CC nodes (CRM-152).

- crm_approval_nodes: add node_type / approver_roles / approver_users / is_archived;
  migrate approve_role + notify_user_ids, then drop approve_role / notify_user_ids / is_required.
  Nodes with notify_user_ids become designated approvers; others approve as the whole role.
- crm_contract_approvals: add nodes_snapshot (frozen at submit).
- crm_approval_participants: per-approval approvers of the current node and CC recipients.
- In-flight PENDING approvals use the same snapshot semantics as new submissions:
  designated legacy notification users are intersected with legacy role membership;
  nodes without designated users use the full role membership.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "167_approval_approvers_cc"
down_revision: str | None = "166_license_permanent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _loads(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _role_member_ids(conn, role_code, team_id) -> list[int]:
    if not role_code or team_id is None:
        return []
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "WHERE r.code = :code AND ur.team_id = :team_id ORDER BY ur.user_id"
        ),
        {"code": role_code, "team_id": team_id},
    ).fetchall()
    return [int(r[0]) for r in rows]


def _legacy_node_user_ids(conn, node, team_id) -> list[int]:
    members = _role_member_ids(conn, node.approve_role, team_id)
    selected = {int(uid) for uid in (_loads(node.notify_user_ids) or []) if uid is not None}
    return [uid for uid in members if uid in selected] if selected else members


def upgrade() -> None:
    op.add_column(
        "crm_approval_nodes",
        sa.Column("node_type", sa.String(20), nullable=False, server_default="APPROVAL", comment="节点类型：APPROVAL 审批 / CC 抄送"),
    )
    op.add_column("crm_approval_nodes", sa.Column("approver_roles", sa.JSON(), nullable=True, comment="整角色选择：角色编码列表"))
    op.add_column("crm_approval_nodes", sa.Column("approver_users", sa.JSON(), nullable=True, comment="指定成员：[{role, user_id}]"))
    op.add_column(
        "crm_approval_nodes",
        sa.Column("is_archived", sa.Integer(), nullable=False, server_default="0", comment="是否已从流程移除（保留给在审单据引用）"),
    )
    op.add_column("crm_contract_approvals", sa.Column("nodes_snapshot", sa.JSON(), nullable=True, comment="提交时的节点配置快照"))
    op.create_table(
        "crm_approval_participants",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column(
            "approval_id",
            sa.BigInteger(),
            sa.ForeignKey("crm_contract_approvals.id", ondelete="CASCADE"),
            nullable=False,
            comment="审批实例ID",
        ),
        sa.Column("node_id", sa.BigInteger(), nullable=False, comment="节点ID"),
        sa.Column("node_name", sa.String(100), nullable=True, comment="节点名称"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("kind", sa.String(20), nullable=False, comment="APPROVER / CC"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="写入时间（抄送时间）"),
        comment="审批参与人表",
    )
    op.create_index("idx_participant_user", "crm_approval_participants", ["team_id", "user_id", "kind"])
    op.create_index("idx_participant_approval", "crm_approval_participants", ["approval_id", "node_id"])

    conn = op.get_bind()
    nodes = conn.execute(
        sa.text("SELECT id, team_id, flow_id, node_name, node_code, approve_role, notify_user_ids FROM crm_approval_nodes")
    ).fetchall()
    nodes_by_id = {}
    for node in nodes:
        notify_ids = [int(uid) for uid in (_loads(node.notify_user_ids) or []) if uid is not None]
        if node.approve_role and notify_ids:
            roles, users = [], [{"role": node.approve_role, "user_id": uid} for uid in notify_ids]
        else:
            roles, users = ([node.approve_role] if node.approve_role else []), []
        conn.execute(
            sa.text("UPDATE crm_approval_nodes SET approver_roles = :roles, approver_users = :users "
                    "WHERE id = :id AND (team_id = :team_id OR (team_id IS NULL AND :team_id IS NULL))"),
            {"roles": json.dumps(roles), "users": json.dumps(users), "id": node.id, "team_id": node.team_id},
        )
        nodes_by_id[node.id] = node

    nodes_by_flow: dict[int, list] = {}
    for row in conn.execute(sa.text("SELECT id, flow_id FROM crm_approval_nodes ORDER BY flow_id, node_order, id")).fetchall():
        nodes_by_flow.setdefault(row.flow_id, []).append(nodes_by_id[row.id])

    pending = conn.execute(
        sa.text(
            "SELECT ap.id, ap.team_id, ap.flow_id, ap.current_node_id, ap.created_time, f.team_id AS flow_team_id "
            "FROM crm_contract_approvals ap LEFT JOIN crm_approval_flows f "
            "ON f.id = ap.flow_id AND (f.team_id = ap.team_id OR f.team_id IS NULL) "
            "WHERE ap.status = 'PENDING' AND f.id IS NOT NULL"
        )
    ).fetchall()
    for ap in pending:
        snapshot = [
            {
                "node_id": n.id,
                "node_name": n.node_name,
                "node_code": n.node_code,
                "node_type": "APPROVAL",
                "user_ids": _legacy_node_user_ids(conn, n, ap.team_id),
            }
            for n in nodes_by_flow.get(ap.flow_id, [])
            if n.team_id is None or n.team_id == ap.team_id
        ]
        conn.execute(
            sa.text("UPDATE crm_contract_approvals SET nodes_snapshot = :snap WHERE id = :id AND team_id = :team_id"),
            {"snap": json.dumps(snapshot, ensure_ascii=False), "id": ap.id, "team_id": ap.team_id},
        )
        current = next((s for s in snapshot if s["node_id"] == ap.current_node_id), None)
        if current is None:
            continue
        for uid in current["user_ids"]:
            conn.execute(
                sa.text(
                    "INSERT INTO crm_approval_participants (team_id, approval_id, node_id, node_name, user_id, kind, created_time) "
                    "VALUES (:team_id, :approval_id, :node_id, :node_name, :user_id, 'APPROVER', :created_time)"
                ),
                {
                    "team_id": ap.team_id,
                    "approval_id": ap.id,
                    "node_id": current["node_id"],
                    "node_name": current["node_name"],
                    "user_id": uid,
                    "created_time": ap.created_time,
                },
            )

    with op.batch_alter_table("crm_approval_nodes") as batch:
        batch.drop_column("approve_role")
        batch.drop_column("notify_user_ids")
        batch.drop_column("is_required")

    _replace_event_type_check(_EVENT_TYPES + ("approval_cc",))


_EVENT_TYPES = (
    "approval_pending", "approval_approved", "approval_rejected",
    "approval_cancelled", "approval_issued", "approval_reminder",
    "account_created", "account_status_won", "account_status_lost",
    "customer_returned", "lead_claimed", "lead_assigned",
    "opportunity_won", "opportunity_lost",
)


def _replace_event_type_check(event_types: tuple[str, ...]) -> None:
    allowed = ", ".join(f"'{value}'" for value in event_types)
    with op.batch_alter_table("crm_outbound_notification_jobs") as batch:
        batch.drop_constraint("ck_outbound_notification_job_event_type", type_="check")
        batch.create_check_constraint("ck_outbound_notification_job_event_type", f"event_type IN ({allowed})")


def downgrade() -> None:
    op.execute("DELETE FROM crm_outbound_notification_jobs WHERE event_type = 'approval_cc'")
    _replace_event_type_check(_EVENT_TYPES)
    with op.batch_alter_table("crm_approval_nodes") as batch:
        batch.add_column(sa.Column("approve_role", sa.String(50), nullable=True, comment="审批角色（TEAM_ADMIN, SALES_DIRECTOR等）"))
        batch.add_column(sa.Column("notify_user_ids", sa.JSON(), nullable=True, comment="通知对象用户ID列表"))
        batch.add_column(sa.Column("is_required", sa.Integer(), nullable=False, server_default="1", comment="是否必须审批：0:否, 1:是"))

    conn = op.get_bind()
    for node in conn.execute(sa.text("SELECT id, approver_roles, approver_users FROM crm_approval_nodes")).fetchall():
        roles = _loads(node.approver_roles) or []
        users = _loads(node.approver_users) or []
        role = roles[0] if roles else (users[0]["role"] if users else None)
        notify = [u["user_id"] for u in users] if not roles and users else None
        conn.execute(
            sa.text("UPDATE crm_approval_nodes SET approve_role = :role, notify_user_ids = :notify WHERE id = :id"),
            {"role": role, "notify": json.dumps(notify) if notify else None, "id": node.id},
        )
    conn.execute(sa.text("DELETE FROM crm_approval_nodes WHERE node_type = 'CC' OR is_archived = 1"))

    op.drop_index("idx_participant_approval", table_name="crm_approval_participants")
    op.drop_index("idx_participant_user", table_name="crm_approval_participants")
    op.drop_table("crm_approval_participants")
    op.drop_column("crm_contract_approvals", "nodes_snapshot")
    with op.batch_alter_table("crm_approval_nodes") as batch:
        batch.drop_column("is_archived")
        batch.drop_column("approver_users")
        batch.drop_column("approver_roles")
        batch.drop_column("node_type")
