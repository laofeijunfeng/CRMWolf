"""审批超时催办定时任务

定时检查审批超时情况，根据超时程度发送不同级别的催办通知：
- 24小时：轻度提醒（审批人）
- 48小时：中度催办（审批人 + 提交人）
- 72小时：强度告警（审批人 + 提交人 + 管理员）

使用 asyncio 实现定时调度，每小时检查一次。
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from app.core.database import SessionLocal
from app.models.approval import Approval, ApprovalStatus, ApprovalNode
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.team import Team
from app.crud.approval import approval_crud
from app.crud.role import role_crud
from app.crud.team import team_crud
from app.crud.system_config import system_config_crud
from app.services.approval_adapter import get_adapter
from app.services.notification import NotificationService

logger = logging.getLogger(__name__)

# 超时阈值（小时）
REMINDER_THRESHOLDS = {
    "light": 24,      # 轻度提醒
    "medium": 48,     # 中度催办
    "strong": 72      # 强度告警
}


class ApprovalReminderScheduler:
    """审批超时催办调度器"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # 记录已发送的通知，避免重复发送
        self._sent_reminders: Dict[str, Dict[int, datetime]] = {}  # {approval_id: {threshold_hours: sent_time}}

    async def check_approval_timeout(self) -> Dict[str, Any]:
        """检查审批超时并发送催办通知

        Returns:
            检查统计信息
        """
        logger.info(f"[{datetime.now()}] 开始执行审批超时检查任务")

        db = SessionLocal()
        stats = {
            "start_time": datetime.now(),
            "pending_approvals": 0,
            "light_reminders": 0,
            "medium_reminders": 0,
            "strong_reminders": 0,
            "errors": []
        }

        try:
            # 查询所有待审批的审批实例
            pending_approvals = db.query(Approval).filter(
                Approval.status == ApprovalStatus.PENDING
            ).all()

            stats["pending_approvals"] = len(pending_approvals)
            logger.info(f"发现 {len(pending_approvals)} 个待审批实例")

            for approval in pending_approvals:
                try:
                    # 计算等待时间（小时）
                    waiting_hours = (datetime.now() - approval.created_time).total_seconds() / 3600

                    # 通过适配器按 business_type/business_id 取业务单据实体
                    # （泛化后回款/发票审批 contract_id=None，不能再按合同查；
                    #  ORPHAN/未知类型/单据被删 → 跳过，对齐原"合同不存在"语义）
                    try:
                        adapter = get_adapter(approval.business_type)
                    except ValueError:
                        logger.warning(
                            f"审批实例 {approval.id} 业务类型 {approval.business_type} 不支持，跳过催办"
                        )
                        continue

                    entity = adapter.get_entity(db, approval.business_id, approval.team_id)
                    if entity is None:
                        logger.warning(
                            f"审批实例 {approval.id} 关联的 {approval.business_type}"
                            f"#{approval.business_id} 不存在，跳过催办"
                        )
                        continue

                    entity_type = approval.business_type
                    entity_name = adapter.get_name(entity)
                    business_id = approval.business_id

                    # 获取当前审批节点
                    current_node = approval.current_node
                    if not current_node:
                        logger.warning(f"审批实例 {approval.id} 当前节点不存在")
                        continue

                    # 获取审批人信息
                    approvers = self._get_node_approvers(db, current_node, approval.team_id)
                    if not approvers:
                        logger.warning(f"审批实例 {approval.id} 当前节点无审批人")
                        continue

                    # 检查各个超时阈值
                    reminder_key = f"{approval.id}"

                    # 24小时轻度提醒
                    if waiting_hours >= REMINDER_THRESHOLDS["light"]:
                        if not self._has_sent_reminder(reminder_key, REMINDER_THRESHOLDS["light"]):
                            await self._send_light_reminder(
                                db, approval, entity_type, entity_name, business_id,
                                current_node, approvers, waiting_hours
                            )
                            self._mark_reminder_sent(reminder_key, REMINDER_THRESHOLDS["light"])
                            stats["light_reminders"] += 1

                    # 48小时中度催办
                    if waiting_hours >= REMINDER_THRESHOLDS["medium"]:
                        if not self._has_sent_reminder(reminder_key, REMINDER_THRESHOLDS["medium"]):
                            await self._send_medium_reminder(
                                db, approval, entity_type, entity_name, business_id,
                                current_node, approvers, waiting_hours
                            )
                            self._mark_reminder_sent(reminder_key, REMINDER_THRESHOLDS["medium"])
                            stats["medium_reminders"] += 1

                    # 72小时强度告警
                    if waiting_hours >= REMINDER_THRESHOLDS["strong"]:
                        if not self._has_sent_reminder(reminder_key, REMINDER_THRESHOLDS["strong"]):
                            await self._send_strong_reminder(
                                db, approval, entity_type, entity_name, business_id,
                                current_node, approvers, waiting_hours
                            )
                            self._mark_reminder_sent(reminder_key, REMINDER_THRESHOLDS["strong"])
                            stats["strong_reminders"] += 1

                except Exception as e:
                    error_msg = f"处理审批实例 {approval.id} 失败: {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)

        except Exception as e:
            logger.error(f"审批超时检查任务执行失败: {str(e)}")
            stats["errors"].append(str(e))

        finally:
            db.close()

        stats["end_time"] = datetime.now()
        stats["duration_seconds"] = (stats["end_time"] - stats["start_time"]).total_seconds()

        logger.info(
            f"[{datetime.now()}] 审批超时检查任务完成: "
            f"待审批={stats['pending_approvals']}, "
            f"轻度提醒={stats['light_reminders']}, "
            f"中度催办={stats['medium_reminders']}, "
            f"强度告警={stats['strong_reminders']}, "
            f"耗时={stats['duration_seconds']:.2f}秒"
        )

        return stats

    def _get_node_approvers(self, db, node: ApprovalNode, team_id: int) -> List[User]:
        """获取审批节点的审批人列表

        Args:
            db: 数据库会话
            node: 审批节点
            team_id: 团队ID

        Returns:
            审批人用户列表
        """
        if not node.approve_role:
            return []

        # 获取角色
        role = role_crud.get_by_code(db, node.approve_role)
        if not role:
            logger.warning(f"角色 {node.approve_role} 不存在")
            return []

        # 获取拥有该角色的用户
        users = role_crud.get_role_users(db, role.id, team_id)
        return users

    def _get_team_admins(self, db, team_id: int) -> List[User]:
        """获取团队管理员列表

        Args:
            db: 数据库会话
            team_id: 团队ID

        Returns:
            管理员用户列表
        """
        # 获取 TEAM_ADMIN 角色
        role = role_crud.get_by_code(db, "TEAM_ADMIN")
        if not role:
            # 如果没有 TEAM_ADMIN 角色，则获取团队创建者
            team = team_crud.get_by_id(db, team_id)
            if team and team.owner_id:
                owner = db.query(User).filter(User.id == team.owner_id).first()
                return [owner] if owner else []
            return []

        # 获取拥有该角色的用户
        users = role_crud.get_role_users(db, role.id, team_id)
        return users

    def _has_sent_reminder(self, approval_key: str, threshold_hours: int) -> bool:
        """检查是否已发送过该级别的提醒

        Args:
            approval_key: 审批实例标识
            threshold_hours: 超时阈值（小时）

        Returns:
            是否已发送
        """
        if approval_key not in self._sent_reminders:
            return False

        reminders = self._sent_reminders[approval_key]
        return threshold_hours in reminders

    def _mark_reminder_sent(self, approval_key: str, threshold_hours: int):
        """标记已发送提醒

        Args:
            approval_key: 审批实例标识
            threshold_hours: 超时阈值（小时）
        """
        if approval_key not in self._sent_reminders:
            self._sent_reminders[approval_key] = {}

        self._sent_reminders[approval_key][threshold_hours] = datetime.now()

    async def _send_light_reminder(
        self,
        db,
        approval: Approval,
        entity_type: str,
        entity_name: str,
        business_id,
        node: ApprovalNode,
        approvers: List[User],
        waiting_hours: float
    ):
        """发送轻度提醒（24小时）- 仅通知审批人

        Args:
            db: 数据库会话
            approval: 审批实例
            entity_type: 业务单据类型（CONTRACT/PAYMENT/INVOICE）
            entity_name: 业务单据展示名
            business_id: 业务单据ID
            node: 当前审批节点
            approvers: 审批人列表
            waiting_hours: 等待时间（小时）
        """
        notification_service = NotificationService(db, approval.team_id)

        for approver in approvers:
            try:
                # 使用 feishu_open_id 发送通知（如果有的话）
                approver_open_id = getattr(approver, 'feishu_open_id', None) or str(approver.id)
                approver_name = approver.name

                await notification_service.notify_approval_reminder(
                    approver_open_id=approver_open_id,
                    approver_name=approver_name,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    waiting_hours=int(waiting_hours),
                    node_name=node.node_name,
                    business_id=business_id,
                    reminder_level="light"
                )

                logger.info(
                    f"发送轻度提醒: approval_id={approval.id}, "
                    f"approver={approver_name}, waiting_hours={int(waiting_hours)}"
                )

            except Exception as e:
                logger.error(f"发送轻度提醒失败: approver={approver.name}, error={str(e)}")

    async def _send_medium_reminder(
        self,
        db,
        approval: Approval,
        entity_type: str,
        entity_name: str,
        business_id,
        node: ApprovalNode,
        approvers: List[User],
        waiting_hours: float
    ):
        """发送中度催办（48小时）- 通知审批人 + 提交人

        Args:
            db: 数据库会话
            approval: 审批实例
            entity_type: 业务单据类型（CONTRACT/PAYMENT/INVOICE）
            entity_name: 业务单据展示名
            business_id: 业务单据ID
            node: 当前审批节点
            approvers: 审批人列表
            waiting_hours: 等待时间（小时）
        """
        notification_service = NotificationService(db, approval.team_id)

        # 通知审批人
        for approver in approvers:
            try:
                approver_open_id = getattr(approver, 'feishu_open_id', None) or str(approver.id)
                approver_name = approver.name

                await notification_service.notify_approval_reminder(
                    approver_open_id=approver_open_id,
                    approver_name=approver_name,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    waiting_hours=int(waiting_hours),
                    node_name=node.node_name,
                    business_id=business_id,
                    reminder_level="medium"
                )

                logger.info(
                    f"发送中度催办给审批人: approval_id={approval.id}, "
                    f"approver={approver_name}, waiting_hours={int(waiting_hours)}"
                )

            except Exception as e:
                logger.error(f"发送中度催办给审批人失败: approver={approver.name}, error={str(e)}")

        # 通知提交人
        try:
            # 获取提交人信息
            submitter = db.query(User).filter(
                User.feishu_open_id == approval.submitter_id
            ).first()

            if not submitter:
                # 如果通过 feishu_open_id 找不到，尝试通过 ID 查找
                try:
                    submitter_id = int(approval.submitter_id)
                    submitter = db.query(User).filter(User.id == submitter_id).first()
                except ValueError:
                    pass

            if submitter:
                submitter_open_id = getattr(submitter, 'feishu_open_id', None) or str(submitter.id)

                # 获取当前审批人姓名（用于通知提交人）
                approver_names = [a.name for a in approvers[:3]]  #最多取3个审批人姓名
                approver_names_str = ", ".join(approver_names) if approver_names else "未知"

                await notification_service.notify_approval_timeout_alert(
                    submitter_open_id=submitter_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    node_name=node.node_name,
                    approver_name=approver_names_str,
                    waiting_hours=int(waiting_hours),
                    business_id=business_id,
                    reminder_level="medium"
                )

                logger.info(
                    f"发送中度催办给提交人: approval_id={approval.id}, "
                    f"submitter={submitter.name}, waiting_hours={int(waiting_hours)}"
                )
            else:
                logger.warning(f"无法找到提交人: submitter_id={approval.submitter_id}")

        except Exception as e:
            logger.error(f"发送中度催办给提交人失败: error={str(e)}")

    async def _send_strong_reminder(
        self,
        db,
        approval: Approval,
        entity_type: str,
        entity_name: str,
        business_id,
        node: ApprovalNode,
        approvers: List[User],
        waiting_hours: float
    ):
        """发送强度告警（72小时）- 通知审批人 + 提交人 + 管理员

        Args:
            db: 数据库会话
            approval: 审批实例
            entity_type: 业务单据类型（CONTRACT/PAYMENT/INVOICE）
            entity_name: 业务单据展示名
            business_id: 业务单据ID
            node: 当前审批节点
            approvers: 审批人列表
            waiting_hours: 等待时间（小时）
        """
        notification_service = NotificationService(db, approval.team_id)

        # 通知审批人
        for approver in approvers:
            try:
                approver_open_id = getattr(approver, 'feishu_open_id', None) or str(approver.id)
                approver_name = approver.name

                await notification_service.notify_approval_reminder(
                    approver_open_id=approver_open_id,
                    approver_name=approver_name,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    waiting_hours=int(waiting_hours),
                    node_name=node.node_name,
                    business_id=business_id,
                    reminder_level="strong"
                )

                logger.info(
                    f"发送强度告警给审批人: approval_id={approval.id}, "
                    f"approver={approver_name}, waiting_hours={int(waiting_hours)}"
                )

            except Exception as e:
                logger.error(f"发送强度告警给审批人失败: approver={approver.name}, error={str(e)}")

        # 通知提交人
        try:
            submitter = db.query(User).filter(
                User.feishu_open_id == approval.submitter_id
            ).first()

            if not submitter:
                try:
                    submitter_id = int(approval.submitter_id)
                    submitter = db.query(User).filter(User.id == submitter_id).first()
                except ValueError:
                    pass

            if submitter:
                submitter_open_id = getattr(submitter, 'feishu_open_id', None) or str(submitter.id)
                approver_names = [a.name for a in approvers[:3]]
                approver_names_str = ", ".join(approver_names) if approver_names else "未知"

                await notification_service.notify_approval_timeout_alert(
                    submitter_open_id=submitter_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    node_name=node.node_name,
                    approver_name=approver_names_str,
                    waiting_hours=int(waiting_hours),
                    business_id=business_id,
                    reminder_level="strong"
                )

                logger.info(
                    f"发送强度告警给提交人: approval_id={approval.id}, "
                    f"submitter={submitter.name}, waiting_hours={int(waiting_hours)}"
                )
            else:
                logger.warning(f"无法找到提交人: submitter_id={approval.submitter_id}")

        except Exception as e:
            logger.error(f"发送强度告警给提交人失败: error={str(e)}")

        # 通知管理员
        try:
            admins = self._get_team_admins(db, approval.team_id)
            for admin in admins:
                admin_open_id = getattr(admin, 'feishu_open_id', None) or str(admin.id)

                await notification_service.notify_approval_timeout_alert(
                    submitter_open_id=admin_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    node_name=node.node_name,
                    approver_name=approver_names_str if approvers else "未知",
                    waiting_hours=int(waiting_hours),
                    business_id=business_id,
                    reminder_level="strong",
                    is_admin=True
                )

                logger.info(
                    f"发送强度告警给管理员: approval_id={approval.id}, "
                    f"admin={admin.name}, waiting_hours={int(waiting_hours)}"
                )

        except Exception as e:
            logger.error(f"发送强度告警给管理员失败: error={str(e)}")

    async def _run_hourly_scheduler(self):
        """每小时定时调度循环"""
        while self._running:
            now = datetime.now()

            # 每小时执行一次检查
            try:
                await self.check_approval_timeout()
            except Exception as e:
                logger.error(f"审批超时检查任务执行异常: {str(e)}")

            # 清理过期提醒记录（超过7天的记录）
            self._cleanup_old_reminders()

            # 每小时等待
            await asyncio.sleep(3600)  # 3600秒 = 1小时

    def _cleanup_old_reminders(self):
        """清理过期的提醒记录（超过7天）"""
        cutoff_time = datetime.now() - timedelta(days=7)
        keys_to_remove = []

        for approval_key, reminders in self._sent_reminders.items():
            # 如果所有提醒都超过7天，移除整个记录
            if all(sent_time < cutoff_time for sent_time in reminders.values()):
                keys_to_remove.append(approval_key)

        for key in keys_to_remove:
            del self._sent_reminders[key]

        if keys_to_remove:
            logger.info(f"清理了 {len(keys_to_remove)} 条过期提醒记录")

    def start(self):
        """启动定时任务"""
        if self._running:
            logger.warning("审批超时催办任务已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_hourly_scheduler())
        logger.info("审批超时催办任务已启动（每小时检查一次）")

    def stop(self):
        """停止定时任务"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                asyncio.get_event_loop().run_until_complete(self._task)
            except asyncio.CancelledError:
                pass

        logger.info("审批超时催办任务已停止")


# 单例实例
approval_reminder_scheduler = ApprovalReminderScheduler()


def start_approval_reminder_scheduler():
    """启动审批超时催办任务

    在应用启动时调用
    """
    approval_reminder_scheduler.start()


def stop_approval_reminder_scheduler():
    """停止审批超时催办任务

    在应用关闭时调用
    """
    approval_reminder_scheduler.stop()