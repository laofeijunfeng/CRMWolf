"""
审批事务管理器（拒绝妥协设计）

核心职责：
1. 事务原子性保证：业务单据创建 + approval_phase 切换 + Approval 创建在同一事务
2. approval_phase 状态流转统一管理
3. 异常友好处理：保留单据，approval_phase 回退到 DRAFT
4. 原有 status 字段联动：通过 adapter 触发业务状态切换

设计原则：
1. 拒绝"最小改动"妥协 - approval_phase 作为数据库字段，彻底统一状态系统
2. 业务语义分离 - approval_phase 专注审批流程，原有 status 保留业务语义
3. 事务边界明确 - 所有数据库写入在此类中统一 commit
4. 异常分支完整 - 覆盖未匹配、查询失败、通知失败等所有场景
"""

from typing import Any, Dict, Optional, Tuple, Callable
from sqlalchemy.orm import Session
import logging

from app.constants.approval_phase import ApprovalPhase
from app.services.approval_adapter import (
    get_adapter,
    get_approval_card_fields,
    get_approval_customer_name,
    get_approval_type_name,
)
from app.crud.approval import approval_crud, approval_flow_crud
from app.models.approval import Approval

logger = logging.getLogger(__name__)


class ApprovalTransactionManager:
    """审批事务管理器"""

    @staticmethod
    def _approval_phase_value(phase: Any) -> Optional[str]:
        if phase is None:
            return None
        return getattr(phase, "value", phase)

    def create_with_approval(
        self,
        db: Session,
        business_type: str,
        entity_create_func: Callable[[], Any],
        match_flow_kwargs: dict,
        submitter_id: str,
        submitter_name: str,
        team_id: int,
        rollback_on_no_flow: bool = False,
        send_notification: bool = True
    ) -> Tuple[Any, Optional[Approval], Optional[str]]:
        """
        创建业务单据 + 自动提交审批（Contract/Payment 场景）

        流程：
        1. 创建业务单据（approval_phase = DRAFT）
        2. 匹配审批流程（捕获查询异常）
        3. 创建审批实例（create_approval_only，不 commit）
        4. 切换 approval_phase = PENDING_REVIEW
        5. adapter.on_submit() 触发原有 status 联动
        6. 统一 commit
        7. 异步发送通知（失败记录日志，提供补发入口）

        Returns:
            (entity, approval, error_message)
            - entity: 创建的业务单据实例（如果成功）
            - approval: 创建的审批实例（如果审批流程匹配成功）
            - error_message: 错误消息（如果失败）
        """
        try:
            # 1. 创建业务单据（approval_phase = DRAFT）
            entity = entity_create_func()
            db.flush()  # 获取 entity.id

            # 2. 匹配审批流程（捕获查询异常）
            try:
                # A5 修复：使用 match_flow_generic（支持 CONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY）
                # match_flow(contract) 是 CONTRACT 专用 wrapper，不支持 business_type 参数
                flow, err_msg = approval_flow_crud.match_flow_generic(
                    db,
                    business_type,
                    team_id,
                    match_flow_kwargs.get("amount"),
                    match_flow_kwargs.get("license_type")
                )
            except Exception as e:
                logger.error(f"审批流程查询失败: {e}", exc_info=True)
                db.rollback()
                return (None, None, "系统异常：审批流程查询失败，请稍后重试")

            # 3. 审批流程未匹配 → commit 单据，返回提示
            if flow is None:
                if rollback_on_no_flow:
                    db.rollback()
                    logger.info(f"审批流程未匹配，已回滚业务单据创建（business_type={business_type}）")
                    return (None, None, err_msg or "请先配置审批流程")
                entity.approval_phase = ApprovalPhase.DRAFT.value
                db.commit()
                logger.info(f"审批流程未匹配（business_type={business_type}, entity_id={entity.id}）")
                return (entity, None, err_msg or "请先配置审批流程")

            # 4. 创建审批实例（不 commit）
            try:
                approval = approval_crud.create_approval_only(
                    db,
                    business_type=business_type,
                    business_id=entity.id,
                    team_id=team_id,
                    flow=flow,
                    submitter_id=submitter_id,
                    submitter_name=submitter_name
                )
            except Exception as e:
                logger.error(f"审批创建失败: {e}", exc_info=True)
                db.rollback()
                return (None, None, "系统异常：审批创建失败，请稍后重试")

            # 5. 切换 approval_phase = PENDING_REVIEW
            entity.approval_phase = ApprovalPhase.PENDING_REVIEW.value

            # 6. adapter.on_submit() 触发原有 status 联动
            adapter = get_adapter(business_type)
            adapter.on_submit(db, entity)

            # 7. 统一 commit
            db.commit()
            db.refresh(entity)
            db.refresh(approval)

            # 8. 发送通知（失败不阻断）
            if send_notification:
                self._send_notification_sync(db, approval, entity, team_id)

            logger.info(
                f"create_with_approval 成功（business_type={business_type}, "
                f"entity_id={entity.id}, approval_id={approval.id})"
            )

            return (entity, approval, None)

        except Exception as e:
            logger.error(f"create_with_approval 异常: {e}", exc_info=True)
            db.rollback()
            return (None, None, f"系统异常：{str(e)}")

    def submit_for_approval(
        self,
        db: Session,
        business_type: str,
        entity_id: int,
        team_id: int,
        submitter_id: str,
        submitter_name: str,
        send_notification: bool = True
    ) -> Tuple[Optional[Approval], Optional[str]]:
        """
        手动提交审批（Invoice/License 场景）

        流程：
        1. 获取业务单据（approval_phase 必须 = DRAFT 或 REJECTED）
        2. 如果 approval_phase = REJECTED，删除旧 Approval 实例
        3. 匹配审批流程（捕获查询异常）
        4. 创建新审批实例
        5. 切换 approval_phase = PENDING_REVIEW
        6. adapter.on_submit() 触发原有 status 联动
        7. 统一 commit
        8. 异步发送通知

        Returns:
            (approval, error_message)
            - approval: 创建的审批实例（如果成功）
            - error_message: 错误消息（如果失败）
        """
        try:
            # 1. 获取业务单据
            adapter = get_adapter(business_type)
            entity = adapter.get_entity(db, entity_id, team_id)

            if entity is None:
                return (None, "业务单据不存在")

            # 2. 验证 approval_phase 必须 = DRAFT 或 REJECTED
            if hasattr(entity, 'approval_phase'):
                approval_phase = self._approval_phase_value(entity.approval_phase)
                allowed_phases = {
                    ApprovalPhase.DRAFT.value,
                    ApprovalPhase.REJECTED.value,
                }
                if approval_phase not in allowed_phases:
                    return (None, f"单据状态不允许提交审批（当前状态：{approval_phase})")
            else:
                # 兼容旧模型（没有 approval_phase 字段）
                logger.warning(f"业务单据缺少 approval_phase 字段（business_type={business_type}, entity_id={entity_id})")

            # 3. 如果 approval_phase = REJECTED，删除旧 Approval 实例
            if (
                hasattr(entity, 'approval_phase')
                and self._approval_phase_value(entity.approval_phase) == ApprovalPhase.REJECTED.value
            ):
                old_approval = approval_crud.get_by_entity(db, business_type, entity_id, team_id)
                if old_approval:
                    db.delete(old_approval)
                    logger.info(f"删除旧审批实例（approval_id={old_approval.id})")

            # 4. 匹配审批流程
            match_kwargs = adapter.match_kwargs(entity)
            try:
                # A5 修复：使用 match_flow_generic（支持 CONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY）
                # match_flow(contract) 是 CONTRACT 专用 wrapper，不支持 business_type 参数
                flow, err_msg = approval_flow_crud.match_flow_generic(
                    db,
                    business_type,
                    team_id,
                    match_kwargs.get("amount"),
                    match_kwargs.get("license_type")
                )
            except Exception as e:
                logger.error(f"审批流程查询失败: {e}", exc_info=True)
                db.rollback()
                return (None, "系统异常：审批流程查询失败")

            if flow is None:
                # 未匹配审批流程：返回错误提示（err_msg 可能是 None 或具体错误）
                return (None, err_msg or "请先配置审批流程")

            # 5. 创建新审批实例
            approval = approval_crud.create_approval_only(
                db,
                business_type=business_type,
                business_id=entity.id,
                team_id=team_id,
                flow=flow,
                submitter_id=submitter_id,
                submitter_name=submitter_name
            )

            # 6. 切换 approval_phase = PENDING_REVIEW
            if hasattr(entity, 'approval_phase'):
                entity.approval_phase = ApprovalPhase.PENDING_REVIEW.value

            # 7. adapter.on_submit() 触发原有 status 联动
            adapter.on_submit(db, entity)

            # 8. 统一 commit
            db.commit()
            db.refresh(approval)

            # 9. 发送通知（失败不阻断）
            if send_notification:
                self._send_notification_sync(db, approval, entity, team_id)

            logger.info(
                f"submit_for_approval 成功（business_type={business_type}, "
                f"entity_id={entity.id}, approval_id={approval.id})"
            )

            return (approval, None)

        except Exception as e:
            logger.error(f"submit_for_approval 异常: {e}", exc_info=True)
            db.rollback()
            return (None, f"系统异常：{str(e)}")

    def _build_pending_notification_context(
        self,
        db: Session,
        approval: Approval,
        entity: Any,
        team_id: int
    ) -> Optional[Dict[str, Any]]:
        from app.crud.role import role_crud

        adapter = get_adapter(approval.business_type)
        entity_name = adapter.get_name(entity)

        current_node = approval.current_node
        if not current_node or not current_node.approve_role:
            logger.warning(
                "审批通知跳过：当前节点未配置审批角色（approval_id=%s, business_type=%s, business_id=%s）",
                approval.id,
                approval.business_type,
                approval.business_id,
            )
            return None

        role = role_crud.get_by_code(db, current_node.approve_role)
        if not role:
            logger.warning(
                "审批通知跳过：审批角色不存在（approval_id=%s, business_type=%s, business_id=%s, role=%s）",
                approval.id,
                approval.business_type,
                approval.business_id,
                current_node.approve_role,
            )
            return None

        approvers = role_crud.get_role_users(db, role.id, team_id)
        notify_user_ids = current_node.notify_user_ids or []
        if notify_user_ids:
            notify_id_set = {int(user_id) for user_id in notify_user_ids}
            approvers = [user for user in approvers if int(user.id) in notify_id_set]
        if not approvers:
            logger.warning(
                "审批通知跳过：审批角色无可通知成员（approval_id=%s, business_type=%s, business_id=%s, role=%s）",
                approval.id,
                approval.business_type,
                approval.business_id,
                current_node.approve_role,
            )
            return None

        return {
            "team_id": team_id,
            "user_ids": [user.id for user in approvers],
            "entity_type": approval.business_type,
            "entity_name": entity_name,
            "flow_name": approval.flow.flow_name if approval.flow else "",
            "node_name": current_node.node_name,
            "business_id": approval.business_id,
            "submitter_name": approval.submitter_name,
            "approval_type_name": get_approval_type_name(approval.business_type),
            "customer_name": get_approval_customer_name(db, approval.business_type, entity),
            "detail_fields": get_approval_card_fields(db, approval.business_type, entity),
        }

    async def send_notification(self, db: Session, approval: Approval, entity: Any, team_id: int) -> Dict[str, int]:
        """
        发送审批通知（失败不阻断业务流程）

        设计决策：
        1. 通知失败不阻断审批流程（业务数据已 commit）
        2. 失败记录日志（approval.id + entity.id）
        3. 提供手动补发入口（ApprovalService.resend_notification）

        Args:
            db: 数据库会话
            approval: 审批实例
            entity: 业务单据实例
            team_id: 团队ID
        """
        try:
            from app.services.feishu_notification import feishu_notification_service

            context = self._build_pending_notification_context(db, approval, entity, team_id)
            if context is None:
                return {"success": 0, "failed": 0, "skipped": 1}

            result = await feishu_notification_service.notify_approval_pending(
                db=db,
                **context,
            )

            logger.info(
                "审批通知发送完成（approval_id=%s, business_type=%s, business_id=%s, "
                "approver_ids=%s, success=%s, failed=%s, skipped=%s）",
                approval.id,
                approval.business_type,
                approval.business_id,
                context["user_ids"],
                result.get("success", 0),
                result.get("failed", 0),
                result.get("skipped", 0),
            )
            return result

        except Exception as e:
            # 记录日志，不阻断业务流程
            logger.error(
                f"审批通知发送失败（approval_id={approval.id}, "
                f"entity_id={approval.business_id}）: {e}",
                exc_info=True
            )
            return {"success": 0, "failed": 1, "skipped": 0}

    def _send_notification_sync(self, db: Session, approval: Approval, entity: Any, team_id: int) -> Dict[str, int]:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.send_notification(db, approval, entity, team_id))

        logger.error(
            "审批通知发送跳过：同步事务入口运行在异步事件循环中，请在提交后 await send_notification "
            "（approval_id=%s, business_type=%s, business_id=%s）",
            approval.id,
            approval.business_type,
            approval.business_id,
        )
        return {"success": 0, "failed": 0, "skipped": 1}

    def resend_notification(self, db: Session, approval_id: int, team_id: int) -> Tuple[bool, Optional[str]]:
        """
        手动补发审批通知（失败通知的补救入口）

        Args:
            db: 数据库会话
            approval_id: 审批实例ID
            team_id: 团队ID

        Returns:
            (success, error_message)
            - success: 是否成功
            - error_message: 错误消息（如果失败）
        """
        try:
            approval = approval_crud.get_by_id(db, approval_id, team_id)

            if approval is None:
                return (False, "审批实例不存在")

            adapter = get_adapter(approval.business_type)
            entity = adapter.get_entity(db, approval.business_id, team_id)

            if entity is None:
                return (False, "业务单据不存在")

            result = self._send_notification_sync(db, approval, entity, team_id)
            if result.get("success", 0) > 0:
                return (True, None)
            return (False, "通知未发送成功，请检查审批人飞书绑定或通知配置")

        except Exception as e:
            logger.error(f"补发通知失败: {e}", exc_info=True)
            return (False, f"系统异常：{str(e)}")


# 全局单例实例
approval_transaction_manager = ApprovalTransactionManager()
