"""审批人员解析与节点流转\uff08CRM-152\uff09。

提交时把流程节点冻结为快照 ``Approval.nodes_snapshot``\uff1a
``[{node_id, node_name, node_code, node_type, user_ids}]``。之后的流转、权限、待我审批、
通知都只读快照与 ``crm_approval_participants``\uff0c不再受流程或角色后续变更影响。
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models.approval import Approval, ApprovalNode, ApprovalParticipant, ApprovalParticipantKind
from app.models.role import Role
from app.models.user_role import UserRole

NODE_TYPE_APPROVAL = "APPROVAL"
NODE_TYPE_CC = "CC"


def _role_members(db: Session, role_codes: Iterable[str], team_id: int) -> dict[str, set[int]]:
    codes = [code for code in dict.fromkeys(role_codes) if code]
    if not codes:
        return {}
    rows = (
        db.query(Role.code, UserRole.user_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(Role.code.in_(codes), UserRole.team_id == team_id)
        .all()
    )
    members: dict[str, set[int]] = {code: set() for code in codes}
    for code, user_id in rows:
        members[code].add(int(user_id))
    return members


def resolve_node_user_ids(db: Session, node: ApprovalNode, team_id: int) -> list[int]:
    """整角色成员 \u222a 仍持有所选角色的指定成员\uff08Q3\uff1a离开角色的指定成员不再有效\uff09。"""
    roles = list(node.approver_roles or [])
    users = list(node.approver_users or [])
    members = _role_members(db, roles + [u.get("role") for u in users], team_id)
    result: set[int] = set()
    for code in roles:
        result |= members.get(code, set())
    for item in users:
        uid = item.get("user_id")
        if uid is not None and int(uid) in members.get(item.get("role"), set()):
            result.add(int(uid))
    return sorted(result)


def build_snapshot(db: Session, nodes: list[ApprovalNode], team_id: int) -> list[dict[str, Any]]:
    """冻结节点与审批人\uff1b任何审批节点无人可批时拒绝提交。"""
    snapshot: list[dict[str, Any]] = []
    for index, node in enumerate(sorted(nodes, key=lambda n: n.node_order), start=1):
        node_type = node.node_type or NODE_TYPE_APPROVAL
        user_ids = resolve_node_user_ids(db, node, team_id)
        if node_type == NODE_TYPE_APPROVAL and not user_ids:
            raise ValueError(f"第 {index} 个节点没有审批人\uff0c请联系管理员")
        snapshot.append({
            "node_id": node.id,
            "node_name": node.node_name,
            "node_code": node.node_code,
            "node_type": node_type,
            "user_ids": user_ids,
        })
    if not any(item["node_type"] == NODE_TYPE_APPROVAL for item in snapshot):
        raise ValueError("审批流程未配置审批节点\uff0c请联系管理员")
    return snapshot


def first_blocked_node_message(db: Session, nodes: list[ApprovalNode], team_id: int) -> str | None:
    try:
        build_snapshot(db, nodes, team_id)
    except ValueError as exc:
        return str(exc)
    return None


@dataclass
class EnterResult:
    finished: bool
    cc_entries: list[dict[str, Any]] = field(default_factory=list)


def _snapshot(approval: Approval) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", approval.nodes_snapshot or [])


def _snapshot_index(approval: Approval) -> int:
    snapshot = _snapshot(approval)
    for index, item in enumerate(snapshot):
        if item["node_id"] == approval.current_node_id:
            return index
    return -1


def current_snapshot_entry(approval: Approval) -> dict[str, Any] | None:
    index = _snapshot_index(approval)
    return _snapshot(approval)[index] if index >= 0 else None


def snapshot_entry_for_node(approval: Approval, node_id: int | None) -> dict[str, Any] | None:
    if node_id is None:
        return None
    return next((item for item in _snapshot(approval) if item.get("node_id") == node_id), None)


def clear_approvers(db: Session, approval: Approval) -> None:
    db.query(ApprovalParticipant).filter(
        ApprovalParticipant.approval_id == approval.id,
        ApprovalParticipant.team_id == approval.team_id,
        ApprovalParticipant.kind == ApprovalParticipantKind.APPROVER,
    ).delete(synchronize_session=False)


def enter_next(db: Session, approval: Approval, start_index: int | None = None) -> EnterResult:
    """从 start_index\uff08默认当前节点之后\uff09向后流转\uff1a抄送节点写入抄送人后直接跳过\uff0c
    停在下一个审批节点并替换 APPROVER 参与人\uff1b没有后续审批节点则返回 finished。"""
    snapshot = _snapshot(approval)
    index = _snapshot_index(approval) + 1 if start_index is None else start_index
    clear_approvers(db, approval)
    result = EnterResult(finished=True)
    while index < len(snapshot):
        entry = snapshot[index]
        if entry["node_type"] == NODE_TYPE_CC:
            for uid in entry["user_ids"]:
                db.add(ApprovalParticipant(
                    team_id=approval.team_id,
                    approval_id=approval.id,
                    node_id=entry["node_id"],
                    node_name=entry["node_name"],
                    user_id=uid,
                    kind=ApprovalParticipantKind.CC,
                ))
            if entry["user_ids"]:
                result.cc_entries.append(entry)
            approval.current_node_id = entry["node_id"]
            index += 1
            continue
        approval.current_node_id = entry["node_id"]
        for uid in entry["user_ids"]:
            db.add(ApprovalParticipant(
                team_id=approval.team_id,
                approval_id=approval.id,
                node_id=entry["node_id"],
                node_name=entry["node_name"],
                user_id=uid,
                kind=ApprovalParticipantKind.APPROVER,
            ))
        result.finished = False
        break
    db.flush()
    return result


def current_approver_ids(db: Session, approval: Approval) -> list[int]:
    rows = db.query(ApprovalParticipant.user_id).filter(
        ApprovalParticipant.approval_id == approval.id,
        ApprovalParticipant.team_id == approval.team_id,
        ApprovalParticipant.kind == ApprovalParticipantKind.APPROVER,
    ).all()
    return sorted({int(r[0]) for r in rows})


def is_participant(db: Session, approval: Approval, user_id: int, kind: str) -> bool:
    return db.query(ApprovalParticipant.id).filter(
        ApprovalParticipant.approval_id == approval.id,
        ApprovalParticipant.team_id == approval.team_id,
        ApprovalParticipant.user_id == int(user_id),
        ApprovalParticipant.kind == kind,
    ).first() is not None
