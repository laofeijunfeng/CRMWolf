"""
通知服务统一入口

根据系统配置选择通知方式（Webhook 或 API），统一调用 feishu_service 的对应方法。
通知失败时记录日志但不阻塞审批流程。
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.crud.system_config import system_config_crud
from app.schemas.system_config import NotificationConfigResponse
from app.services.feishu import feishu_service

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务统一入口"""

    def __init__(self, db: Session, team_id: int):
        """初始化通知服务

        Args:
            db: 数据库会话
            team_id: 团队ID
        """
        self.db = db
        self.team_id = team_id
        self._config: Optional[NotificationConfigResponse] = None

    def get_config(self) -> Optional[NotificationConfigResponse]:
        """获取通知配置

        Returns:
            NotificationConfigResponse 或 None
        """
        if self._config is None:
            try:
                self._config = system_config_crud.get_notification_config(
                    self.db, self.team_id
                )
            except Exception as e:
                logger.error(f"获取通知配置失败: team_id={self.team_id}, error={str(e)}")
                return None
        return self._config

    async def notify_approval_pending(
        self,
        contract_name: str,
        flow_name: str,
        node_name: str,
        approver_open_id: str,
        approver_name: str,
        contract_id: int
    ) -> bool:
        """发送审批待处理通知

        Args:
            contract_name: 合同名称
            flow_name: 审批流程名称
            node_name: 当前审批节点名称
            approver_open_id: 审批人 Open ID（API 方式使用）
            approver_name: 审批人姓名（Webhook 方式使用）
            contract_id: 合同ID

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批待处理通知: "
                f"team_id={self.team_id}, contract_name={contract_name}"
            )
            return False

        try:
            if config.notification_method == "webhook":
                # Webhook 方式
                if not config.feishu_webhook_url:
                    logger.warning(
                        f"Webhook URL 未配置，跳过发送: team_id={self.team_id}"
                    )
                    return False

                if not config.feishu_webhook_enabled:
                    logger.warning(
                        f"Webhook 通知已禁用，跳过发送: team_id={self.team_id}"
                    )
                    return False

                return await feishu_service.notify_approval_webhook(
                    webhook_url=config.feishu_webhook_url,
                    contract_name=contract_name,
                    flow_name=flow_name,
                    node_name=node_name,
                    approver_name=approver_name,
                    contract_id=contract_id
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_pending(
                    user_id=approver_open_id,
                    contract_name=contract_name,
                    flow_name=flow_name,
                    node_name=node_name
                )
        except Exception as e:
            logger.error(
                f"发送审批待处理通知失败: contract_name={contract_name}, "
                f"error={str(e)}"
            )
            return False

    async def notify_approval_approved(
        self,
        submitter_open_id: str,
        contract_name: str,
        contract_id: int
    ) -> bool:
        """发送审批通过通知

        Args:
            submitter_open_id: 提交人 Open ID（API 方式使用）
            contract_name: 合同名称
            contract_id: 合同ID

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批通过通知: "
                f"team_id={self.team_id}, contract_name={contract_name}"
            )
            return False

        try:
            if config.notification_method == "webhook":
                # Webhook 方式
                if not config.feishu_webhook_url:
                    logger.warning(
                        f"Webhook URL 未配置，跳过发送: team_id={self.team_id}"
                    )
                    return False

                if not config.feishu_webhook_enabled:
                    logger.warning(
                        f"Webhook 通知已禁用，跳过发送: team_id={self.team_id}"
                    )
                    return False

                return await feishu_service.notify_approval_approved_webhook(
                    webhook_url=config.feishu_webhook_url,
                    contract_name=contract_name,
                    contract_id=contract_id
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_approved(
                    user_id=submitter_open_id,
                    contract_name=contract_name
                )
        except Exception as e:
            logger.error(
                f"发送审批通过通知失败: contract_name={contract_name}, "
                f"error={str(e)}"
            )
            return False

    async def notify_approval_rejected(
        self,
        submitter_open_id: str,
        contract_name: str,
        reject_reason: str,
        contract_id: int
    ) -> bool:
        """发送审批拒绝通知

        Args:
            submitter_open_id: 提交人 Open ID（API 方式使用）
            contract_name: 合同名称
            reject_reason: 拒绝原因
            contract_id: 合同ID

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批拒绝通知: "
                f"team_id={self.team_id}, contract_name={contract_name}"
            )
            return False

        try:
            if config.notification_method == "webhook":
                # Webhook 方式
                if not config.feishu_webhook_url:
                    logger.warning(
                        f"Webhook URL 未配置，跳过发送: team_id={self.team_id}"
                    )
                    return False

                if not config.feishu_webhook_enabled:
                    logger.warning(
                        f"Webhook 通知已禁用，跳过发送: team_id={self.team_id}"
                    )
                    return False

                return await feishu_service.notify_approval_rejected_webhook(
                    webhook_url=config.feishu_webhook_url,
                    contract_name=contract_name,
                    reject_reason=reject_reason,
                    contract_id=contract_id
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_rejected(
                    user_id=submitter_open_id,
                    contract_name=contract_name,
                    reject_reason=reject_reason
                )
        except Exception as e:
            logger.error(
                f"发送审批拒绝通知失败: contract_name={contract_name}, "
                f"error={str(e)}"
            )
            return False

    async def notify_approval_cancelled(
        self,
        contract_name: str,
        submitter_name: str,
        contract_id: int
    ) -> bool:
        """发送审批撤回通知

        Args:
            contract_name: 合同名称
            submitter_name: 撤回人姓名
            contract_id: 合同ID

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批撤回通知: "
                f"team_id={self.team_id}, contract_name={contract_name}"
            )
            return False

        try:
            if config.notification_method == "webhook":
                # Webhook 方式
                if not config.feishu_webhook_url:
                    logger.warning(
                        f"Webhook URL 未配置，跳过发送: team_id={self.team_id}"
                    )
                    return False

                if not config.feishu_webhook_enabled:
                    logger.warning(
                        f"Webhook 通知已禁用，跳过发送: team_id={self.team_id}"
                    )
                    return False

                return await feishu_service.notify_approval_cancelled_webhook(
                    webhook_url=config.feishu_webhook_url,
                    contract_name=contract_name,
                    submitter_name=submitter_name,
                    contract_id=contract_id
                )
            else:
                # API 方式暂未实现撤回通知（feishu_service 中无对应方法）
                logger.warning(
                    f"API 方式暂不支持审批撤回通知: team_id={self.team_id}"
                )
                return False
        except Exception as e:
            logger.error(
                f"发送审批撤回通知失败: contract_name={contract_name}, "
                f"error={str(e)}"
            )
            return False

    async def notify_approval_reminder(
        self,
        approver_open_id: str,
        approver_name: str,
        contract_name: str,
        waiting_hours: int,
        node_name: str,
        contract_id: int,
        reminder_level: str = "light"
    ) -> bool:
        """发送审批催办通知给审批人

        Args:
            approver_open_id: 审批人 Open ID（API 方式使用）
            approver_name: 审批人姓名（Webhook 方式使用）
            contract_name: 合同名称
            waiting_hours: 已等待小时数
            node_name: 当前审批节点名称
            contract_id: 合同ID
            reminder_level: 提醒级别（light/medium/strong）

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批催办通知: "
                f"team_id={self.team_id}, contract_name={contract_name}"
            )
            return False

        try:
            if config.notification_method == "webhook":
                # Webhook 方式
                if not config.feishu_webhook_url:
                    logger.warning(
                        f"Webhook URL 未配置，跳过发送: team_id={self.team_id}"
                    )
                    return False

                if not config.feishu_webhook_enabled:
                    logger.warning(
                        f"Webhook 通知已禁用，跳过发送: team_id={self.team_id}"
                    )
                    return False

                return await feishu_service.notify_approval_reminder_webhook(
                    webhook_url=config.feishu_webhook_url,
                    contract_name=contract_name,
                    waiting_hours=waiting_hours,
                    node_name=node_name,
                    approver_name=approver_name,
                    contract_id=contract_id,
                    reminder_level=reminder_level
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_reminder(
                    user_id=approver_open_id,
                    contract_name=contract_name,
                    waiting_hours=waiting_hours,
                    node_name=node_name,
                    reminder_level=reminder_level
                )
        except Exception as e:
            logger.error(
                f"发送审批催办通知失败: contract_name={contract_name}, "
                f"error={str(e)}"
            )
            return False

    async def notify_approval_timeout_alert(
        self,
        submitter_open_id: str,
        contract_name: str,
        node_name: str,
        approver_name: str,
        waiting_hours: int,
        contract_id: int,
        reminder_level: str = "medium",
        is_admin: bool = False
    ) -> bool:
        """发送审批超时告警给提交人或管理员

        Args:
            submitter_open_id: 提交人/管理员 Open ID（API 方式使用）
            contract_name: 合同名称
            node_name: 当前审批节点名称
            approver_name: 当前审批人姓名
            waiting_hours: 已等待小时数
            contract_id: 合同ID
            reminder_level: 提醒级别（medium/strong）
            is_admin: 是否通知管理员

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批超时告警: "
                f"team_id={self.team_id}, contract_name={contract_name}"
            )
            return False

        try:
            if config.notification_method == "webhook":
                # Webhook 方式
                if not config.feishu_webhook_url:
                    logger.warning(
                        f"Webhook URL 未配置，跳过发送: team_id={self.team_id}"
                    )
                    return False

                if not config.feishu_webhook_enabled:
                    logger.warning(
                        f"Webhook 通知已禁用，跳过发送: team_id={self.team_id}"
                    )
                    return False

                return await feishu_service.notify_approval_timeout_webhook(
                    webhook_url=config.feishu_webhook_url,
                    contract_name=contract_name,
                    node_name=node_name,
                    approver_name=approver_name,
                    waiting_hours=waiting_hours,
                    contract_id=contract_id,
                    reminder_level=reminder_level,
                    is_admin=is_admin
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_timeout_alert(
                    user_id=submitter_open_id,
                    contract_name=contract_name,
                    node_name=node_name,
                    approver_name=approver_name,
                    waiting_hours=waiting_hours,
                    reminder_level=reminder_level,
                    is_admin=is_admin
                )
        except Exception as e:
            logger.error(
                f"发送审批超时告警失败: contract_name={contract_name}, "
                f"error={str(e)}"
            )
            return False


# 缓存实例
_notification_service_cache: dict = {}


def notification_service_factory(db: Session, team_id: int) -> NotificationService:
    """获取通知服务单例实例

    Args:
        db: 数据库会话
        team_id: 团队ID

    Returns:
        NotificationService 实例
    """
    cache_key = f"{id(db)}_{team_id}"
    if cache_key not in _notification_service_cache:
        _notification_service_cache[cache_key] = NotificationService(db, team_id)
    return _notification_service_cache[cache_key]