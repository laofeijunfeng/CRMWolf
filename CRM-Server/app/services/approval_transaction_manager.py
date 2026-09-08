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
from app.services.approval_adapter import get_adapter
from app.crud.approval import approval_crud, approval_flow_crud
from app.models.approval import Approval
from app.services.outbound_notification_job_service import outbound_notification_job_service

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

            # 7. 通知意图写入同一事务；失败不阻断财务/审批事实。
            notify_request = None
            if send_notification:
                try:
                    notify_request = outbound_notification_job_service.enqueue_pending_for_approval(
                        db,
                        approval=approval,
                        team_id=team_id,
                        actor_id=submitter_id,
                    )
                except Exception as notify_error:
                    logger.error(
                        "审批通知入队失败（approval_id=%s, entity_id=%s）: %s",
                        approval.id,
                        entity.id,
                        notify_error,
                        exc_info=True,
                    )

            # 8. 统一 commit，再 kick 出站通知 worker
            db.commit()
            db.refresh(entity)
            db.refresh(approval)
            outbound_notification_job_service.kick(notify_request)

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

            # 锁住业务单据行，串行化“检查状态 -> 创建审批”的关键区段。
            # 这样两个并发提交不会都在 DRAFT 状态下创建审批实例。
            entity_model = type(entity)
            if hasattr(entity_model, "__table__") and hasattr(entity_model, "id"):
                entity_query = db.query(entity_model).filter(entity_model.id == entity_id)
                if hasattr(entity_model, "team_id"):
                    entity_query = entity_query.filter(entity_model.team_id == team_id)
                locked_entity = entity_query.with_for_update().first()
                if locked_entity is not None:
                    entity = locked_entity

            # 2. 已在审批中的单据：幂等返回现有实例。
            #    这条路径用于网络重试/用户重复点击，不改变正常用户路径，
            #    也不会重复创建审批或重复发送通知。
            if hasattr(entity, 'approval_phase'):
                approval_phase = self._approval_phase_value(entity.approval_phase)
                if approval_phase == ApprovalPhase.PENDING_REVIEW.value:
                    pending_approval = approval_crud.get_pending_by_entity(
                        db, business_type, entity_id, team_id
                    )
                    if pending_approval is not None:
                        return (pending_approval, "审批已在处理中")
                    return (None, "单据正在审批中，但未找到审批实例，请刷新后确认结果")

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

            # 8. 通知意图写入同一事务；失败不阻断审批事实。
            notify_request = None
            if send_notification:
                try:
                    notify_request = outbound_notification_job_service.enqueue_pending_for_approval(
                        db,
                        approval=approval,
                        team_id=team_id,
                        actor_id=submitter_id,
                    )
                except Exception as notify_error:
                    logger.error(
                        "审批通知入队失败（approval_id=%s, entity_id=%s）: %s",
                        approval.id,
                        entity.id,
                        notify_error,
                        exc_info=True,
                    )

            # 9. 统一 commit，再 kick 出站通知 worker
            db.commit()
            db.refresh(approval)
            outbound_notification_job_service.kick(notify_request)

            logger.info(
                f"submit_for_approval 成功（business_type={business_type}, "
                f"entity_id={entity.id}, approval_id={approval.id})"
            )

            return (approval, None)

        except Exception as e:
            logger.error(f"submit_for_approval 异常: {e}", exc_info=True)
            db.rollback()
            return (None, f"系统异常：{str(e)}")

    async def send_notification(self, db: Session, approval: Approval, entity: Any, team_id: int) -> Dict[str, int]:
        """Enqueue a pending approval notification after the source transaction already committed."""
        try:
            request = outbound_notification_job_service.enqueue_pending_for_approval(
                db,
                approval=approval,
                team_id=team_id,
            )
            if request is None:
                return {"success": 0, "failed": 0, "skipped": 1, "queued": 0}
            db.commit()
            outbound_notification_job_service.kick(request)
            logger.info(
                "审批通知已入队（approval_id=%s, business_type=%s, business_id=%s, job=%s）",
                approval.id,
                approval.business_type,
                approval.business_id,
                request.job_public_id,
            )
            return {"success": 0, "failed": 0, "skipped": 0, "queued": 1}
        except Exception as e:
            logger.error(
                f"审批通知入队失败（approval_id={approval.id}, "
                f"entity_id={approval.business_id}）: {e}",
                exc_info=True
            )
            return {"success": 0, "failed": 1, "skipped": 0, "queued": 0}

    def resend_notification(self, db: Session, approval_id: int, team_id: int) -> Tuple[bool, Optional[str]]:
        """Requeue a pending approval notification. Delivery stays on the outbox worker."""
        try:
            approval = approval_crud.get_by_id(db, approval_id, team_id)

            if approval is None:
                return (False, "审批实例不存在")

            adapter = get_adapter(approval.business_type)
            entity = adapter.get_entity(db, approval.business_id, team_id)

            if entity is None:
                return (False, "业务单据不存在")

            request = outbound_notification_job_service.requeue_pending(
                db,
                approval=approval,
                team_id=team_id,
            )
            if request is None:
                return (False, "通知未发送成功，请检查审批人飞书绑定或通知配置")
            db.commit()
            outbound_notification_job_service.kick(request)
            return (True, None)

        except Exception as e:
            logger.error(f"补发通知失败: {e}", exc_info=True)
            return (False, f"系统异常：{str(e)}")


# 全局单例实例
approval_transaction_manager = ApprovalTransactionManager()
