"""
通知服务统一入口

根据系统配置选择通知方式（Webhook 或 API），统一调用 feishu_service 的对应方法。
通知失败时记录日志但不阻塞审批流程。
"""
import logging
import warnings
from typing import Optional
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.crud.system_config import system_config_crud
from app.schemas.system_config import NotificationConfigResponse
from app.services.feishu import feishu_service

logger = logging.getLogger(__name__)


# 单据类型展示名（Webhook 标题里 fallback 用，避免硬编码"合同"）
_ENTITY_TYPE_LABEL = {
    BusinessType.CONTRACT: "合同",
    BusinessType.PAYMENT: "回款登记",
    BusinessType.INVOICE: "发票申请",
}


def _resolve_entity_fields(
    entity_type: Optional[str],
    entity_name: Optional[str],
    business_id: Optional[int],
    contract_name: Optional[str],
    contract_id: Optional[int],
) -> tuple[str, Optional[str], Optional[int]]:
    """把旧合同别名（contract_name / contract_id）映射到泛化签名。

    new 签名优先；旧调用方仍传 contract_name / contract_id 时回退，并触发
    DeprecationWarning。entity_type 缺省视为 CONTRACT（旧合同端点沿用语义）。
    """
    if entity_name is None and contract_name is not None:
        entity_name = contract_name
        warnings.warn(
            "notify_approval_*: contract_name 已弃用，请改用 entity_name",
            DeprecationWarning,
            stacklevel=3,
        )
    if business_id is None and contract_id is not None:
        business_id = contract_id
        warnings.warn(
            "notify_approval_*: contract_id 已弃用，请改用 business_id",
            DeprecationWarning,
            stacklevel=3,
        )
    if entity_type is None:
        entity_type = BusinessType.CONTRACT
    return entity_type, entity_name, business_id


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
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        flow_name: str = "",
        node_name: str = "",
        approver_open_id: str = "",
        approver_name: str = "",
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """发送审批待处理通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代旧的
        contract_name / contract_id。旧合同调用方传 contract_name / contract_id
        仍可工作（内部回退映射，并触发 DeprecationWarning）。

        Args:
            entity_type: 业务单据类型（CONTRACT / PAYMENT / INVOICE），缺省 CONTRACT
            entity_name: 业务单据展示名（如 "合同A" / "回款登记#9"）
            flow_name: 审批流程名称
            node_name: 当前审批节点名称
            approver_open_id: 审批人 Open ID（API 方式使用）
            approver_name: 审批人姓名（Webhook 方式使用）
            business_id: 业务单据ID
            contract_name: (已弃用) 旧合同别名，映射到 entity_name
            contract_id: (已弃用) 旧合同别名，映射到 business_id

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity_fields(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批待处理通知: "
                f"team_id={self.team_id}, entity_type={entity_type}, entity_name={entity_name}"
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
                    entity_type=entity_type,
                    entity_name=entity_name,
                    flow_name=flow_name,
                    node_name=node_name,
                    approver_name=approver_name,
                    business_id=business_id,
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_pending(
                    user_id=approver_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    flow_name=flow_name,
                    node_name=node_name,
                    business_id=business_id,
                )
        except Exception as e:
            logger.error(
                f"发送审批待处理通知失败: entity_type={entity_type}, "
                f"entity_name={entity_name}, error={str(e)}"
            )
            return False

    async def notify_approval_approved(
        self,
        submitter_open_id: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """发送审批通过通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            submitter_open_id: 提交人 Open ID（API 方式使用）
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            business_id: 业务单据ID
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity_fields(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批通过通知: "
                f"team_id={self.team_id}, entity_type={entity_type}, entity_name={entity_name}"
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
                    entity_type=entity_type,
                    entity_name=entity_name,
                    business_id=business_id,
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_approved(
                    user_id=submitter_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    business_id=business_id,
                )
        except Exception as e:
            logger.error(
                f"发送审批通过通知失败: entity_type={entity_type}, "
                f"entity_name={entity_name}, error={str(e)}"
            )
            return False

    async def notify_approval_rejected(
        self,
        submitter_open_id: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        reject_reason: str = "",
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """发送审批拒绝通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            submitter_open_id: 提交人 Open ID（API 方式使用）
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            reject_reason: 拒绝原因
            business_id: 业务单据ID
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity_fields(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批拒绝通知: "
                f"team_id={self.team_id}, entity_type={entity_type}, entity_name={entity_name}"
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
                    entity_type=entity_type,
                    entity_name=entity_name,
                    reject_reason=reject_reason,
                    business_id=business_id,
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_rejected(
                    user_id=submitter_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    reject_reason=reject_reason,
                    business_id=business_id,
                )
        except Exception as e:
            logger.error(
                f"发送审批拒绝通知失败: entity_type={entity_type}, "
                f"entity_name={entity_name}, error={str(e)}"
            )
            return False

    async def notify_approval_cancelled(
        self,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        submitter_name: str = "",
        business_id: Optional[int] = None,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """发送审批撤回通知

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            submitter_name: 撤回人姓名
            business_id: 业务单据ID
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity_fields(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批撤回通知: "
                f"team_id={self.team_id}, entity_type={entity_type}, entity_name={entity_name}"
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
                    entity_type=entity_type,
                    entity_name=entity_name,
                    submitter_name=submitter_name,
                    business_id=business_id,
                )
            else:
                # API 方式暂未实现撤回通知（feishu_service 中无对应方法）
                logger.warning(
                    f"API 方式暂不支持审批撤回通知: team_id={self.team_id}"
                )
                return False
        except Exception as e:
            logger.error(
                f"发送审批撤回通知失败: entity_type={entity_type}, "
                f"entity_name={entity_name}, error={str(e)}"
            )
            return False

    async def notify_approval_reminder(
        self,
        approver_open_id: str,
        approver_name: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        waiting_hours: int = 0,
        node_name: str = "",
        business_id: Optional[int] = None,
        reminder_level: str = "light",
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """发送审批催办通知给审批人

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            approver_open_id: 审批人 Open ID（API 方式使用）
            approver_name: 审批人姓名（Webhook 方式使用）
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            waiting_hours: 已等待小时数
            node_name: 当前审批节点名称
            business_id: 业务单据ID
            reminder_level: 提醒级别（light/medium/strong）
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity_fields(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批催办通知: "
                f"team_id={self.team_id}, entity_type={entity_type}, entity_name={entity_name}"
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
                    entity_type=entity_type,
                    entity_name=entity_name,
                    waiting_hours=waiting_hours,
                    node_name=node_name,
                    approver_name=approver_name,
                    business_id=business_id,
                    reminder_level=reminder_level
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_reminder(
                    user_id=approver_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    waiting_hours=waiting_hours,
                    node_name=node_name,
                    reminder_level=reminder_level
                )
        except Exception as e:
            logger.error(
                f"发送审批催办通知失败: entity_type={entity_type}, "
                f"entity_name={entity_name}, error={str(e)}"
            )
            return False

    async def notify_approval_timeout_alert(
        self,
        submitter_open_id: str,
        entity_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        node_name: str = "",
        approver_name: str = "",
        waiting_hours: int = 0,
        business_id: Optional[int] = None,
        reminder_level: str = "medium",
        is_admin: bool = False,
        *,
        contract_name: Optional[str] = None,
        contract_id: Optional[int] = None,
    ) -> bool:
        """发送审批超时告警给提交人或管理员

        泛化签名（A8）：entity_type / entity_name / business_id 替代
        contract_name / contract_id（旧合同别名仍兼容）。

        Args:
            submitter_open_id: 提交人/管理员 Open ID（API 方式使用）
            entity_type: 业务单据类型，缺省 CONTRACT
            entity_name: 业务单据展示名
            node_name: 当前审批节点名称
            approver_name: 当前审批人姓名
            waiting_hours: 已等待小时数
            business_id: 业务单据ID
            reminder_level: 提醒级别（medium/strong）
            is_admin: 是否通知管理员
            contract_name: (已弃用) 旧合同别名
            contract_id: (已弃用) 旧合同别名

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        entity_type, entity_name, business_id = _resolve_entity_fields(
            entity_type, entity_name, business_id, contract_name, contract_id
        )
        config = self.get_config()
        if not config:
            logger.warning(
                f"通知配置未设置，跳过发送审批超时告警: "
                f"team_id={self.team_id}, entity_type={entity_type}, entity_name={entity_name}"
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
                    entity_type=entity_type,
                    entity_name=entity_name,
                    node_name=node_name,
                    approver_name=approver_name,
                    waiting_hours=waiting_hours,
                    business_id=business_id,
                    reminder_level=reminder_level,
                    is_admin=is_admin
                )
            else:
                # API 方式
                return await feishu_service.notify_approval_timeout_alert(
                    user_id=submitter_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    node_name=node_name,
                    approver_name=approver_name,
                    waiting_hours=waiting_hours,
                    reminder_level=reminder_level,
                    is_admin=is_admin
                )
        except Exception as e:
            logger.error(
                f"发送审批超时告警失败: entity_type={entity_type}, "
                f"entity_name={entity_name}, error={str(e)}"
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