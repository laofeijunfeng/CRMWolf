"""
系统配置 CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import json
from app.models.system_config import SystemConfig, ConfigType
from app.schemas.system_config import NotificationConfigResponse


class SystemConfigCRUD:
    """系统配置 CRUD 操作"""

    def get_config(self, db: Session, team_id: int, config_key: str) -> Optional[SystemConfig]:
        """
        获取单个配置

        Args:
            db: 数据库会话
            team_id: 团队ID
            config_key: 配置键

        Returns:
            SystemConfig 或 None
        """
        return db.query(SystemConfig).filter(
            SystemConfig.team_id == team_id,
            SystemConfig.config_key == config_key
        ).first()

    def get_configs_by_type(self, db: Session, team_id: int, config_type: str) -> List[SystemConfig]:
        """
        按类型获取配置列表

        Args:
            db: 数据库会话
            team_id: 团队ID
            config_type: 配置类型（notification/security/integration）

        Returns:
            配置列表
        """
        return db.query(SystemConfig).filter(
            SystemConfig.team_id == team_id,
            SystemConfig.config_type == config_type
        ).all()

    def get_notification_config(self, db: Session, team_id: int) -> Optional[NotificationConfigResponse]:
        """
        获取通知配置（封装为 NotificationConfigResponse）

        Args:
            db: 数据库会话
            team_id: 团队ID

        Returns:
            NotificationConfigResponse 或 None
        """
        # 获取所有通知类型配置
        configs = self.get_configs_by_type(db, team_id, ConfigType.NOTIFICATION.value)
        if not configs:
            return None

        # 将配置列表转换为字典
        config_dict: Dict[str, Any] = {}
        for config in configs:
            try:
                # 尝试 JSON 反序列化
                value = json.loads(config.config_value)
            except (json.JSONDecodeError, TypeError):
                # 如果不是 JSON，直接使用原值
                value = config.config_value
            config_dict[config.config_key] = value

        # 获取第一个配置的元数据（id, team_id, created_time, updated_time）
        first_config = configs[0]

        return NotificationConfigResponse(
            id=first_config.id,
            team_id=first_config.team_id,
            notification_method=config_dict.get("notification_method", "webhook"),
            feishu_webhook_url=config_dict.get("feishu_webhook_url"),
            feishu_webhook_enabled=config_dict.get("feishu_webhook_enabled", False),
            notification_group_name=config_dict.get("notification_group_name"),
            feishu_app_id=config_dict.get("feishu_app_id"),
            feishu_app_secret=config_dict.get("feishu_app_secret"),
            feishu_api_enabled=config_dict.get("feishu_api_enabled"),
            created_time=first_config.created_time,
            updated_time=first_config.updated_time
        )

    def set_config(
        self,
        db: Session,
        team_id: int,
        config_key: str,
        config_value: Any,
        config_type: str,
        description: Optional[str] = None
    ) -> SystemConfig:
        """
        设置配置（创建或更新）

        Args:
            db: 数据库会话
            team_id: 团队ID
            config_key: 配置键
            config_value: 配置值（自动 JSON 序列化）
            config_type: 配置类型
            description: 配置描述

        Returns:
            SystemConfig
        """
        # JSON 序列化配置值
        if isinstance(config_value, (dict, list, bool)):
            serialized_value = json.dumps(config_value, ensure_ascii=False)
        elif isinstance(config_value, str):
            serialized_value = config_value
        else:
            serialized_value = json.dumps(config_value, ensure_ascii=False)

        # 查找现有配置
        existing = self.get_config(db, team_id, config_key)

        if existing:
            # 更新现有配置
            existing.config_value = serialized_value
            existing.config_type = config_type
            if description is not None:
                existing.description = description
            db.commit()
            db.refresh(existing)
            return existing
        else:
            # 创建新配置
            new_config = SystemConfig(
                team_id=team_id,
                config_key=config_key,
                config_value=serialized_value,
                config_type=config_type,
                description=description
            )
            db.add(new_config)
            db.commit()
            db.refresh(new_config)
            return new_config

    def set_notification_config(self, db: Session, team_id: int, config_data: Dict[str, Any]) -> List[SystemConfig]:
        """
        设置通知配置（批量）

        Args:
            db: 数据库会话
            team_id: 团队ID
            config_data: 通知配置数据字典

        Returns:
            更新的配置列表
        """
        # 定义通知配置键及其默认描述
        notification_keys = {
            "notification_method": "通知方式（webhook/api）",
            "feishu_webhook_url": "飞书Webhook地址",
            "feishu_webhook_enabled": "飞书Webhook是否启用",
            "notification_group_name": "通知群名称",
            "feishu_app_id": "飞书应用ID（预留）",
            "feishu_app_secret": "飞书应用密钥（预留）",
            "feishu_api_enabled": "飞书API是否启用（预留）"
        }

        results = []
        for key, description in notification_keys.items():
            if key in config_data:
                config = self.set_config(
                    db=db,
                    team_id=team_id,
                    config_key=key,
                    config_value=config_data[key],
                    config_type=ConfigType.NOTIFICATION.value,
                    description=description
                )
                results.append(config)

        return results

    def delete_config(self, db: Session, team_id: int, config_key: str) -> bool:
        """
        删除配置

        Args:
            db: 数据库会话
            team_id: 团队ID
            config_key: 配置键

        Returns:
            是否删除成功
        """
        config = self.get_config(db, team_id, config_key)
        if config:
            db.delete(config)
            db.commit()
            return True
        return False


# 单例实例
system_config_crud = SystemConfigCRUD()