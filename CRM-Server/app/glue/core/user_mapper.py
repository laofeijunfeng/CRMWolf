"""用户映射服务

渠道用户 ID（open_id/userid）→ CRM 用户 ID 映射。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.7
"""

from typing import Optional
from sqlalchemy.orm import Session

from app.models.user import User


class UserMappingService:
    """用户映射服务

    查询渠道用户与 CRM 用户的映射关系。
    """

    def __init__(self, db: Session):
        self.db = db

    async def resolve(self, channel: str, channel_user_id: str) -> Optional[int]:
        """解析渠道用户 ID → CRM 用户 ID

        Args:
            channel: 渠道类型（feishu/wecom/web）
            channel_user_id: 渠道用户 ID（open_id/userid/JWT user_id）

        Returns:
            crm_user_id 或 None（未绑定）
        """
        # 网页渠道：channel_user_id 直接是 crm_user_id
        if channel == "web":
            try:
                return int(channel_user_id)
            except ValueError:
                return None

        # 测试渠道：同网页
        if channel == "test":
            try:
                return int(channel_user_id)
            except ValueError:
                return None

        # 飞书/企微：查询 UserMapping 表
        # TODO: 实现 UserMapping 表查询
        # 当前返回 None，提示"请先绑定账号"
        return None

    async def resolve_with_tenant(
        self, channel: str, channel_user_id: str
    ) -> tuple[Optional[int], Optional[int]]:
        """解析渠道用户 ID → CRM 用户 ID + tenant_id

        Args:
            channel: 渠道类型（feishu/wecom/web）
            channel_user_id: 渠道用户 ID

        Returns:
            (crm_user_id, tenant_id) 或 (None, None)
        """
        crm_user_id = await self.resolve(channel, channel_user_id)
        if crm_user_id is None:
            return (None, None)

        # 获取用户以查询 tenant_id（team_id）
        user = await self.get_user(crm_user_id)
        if user is None:
            return (None, None)

        tenant_id = user.team_id
        return (crm_user_id, tenant_id)

    async def get_user(self, crm_user_id: int) -> Optional[User]:
        """获取 CRM 用户"""
        return self.db.query(User).filter(User.id == crm_user_id).first()


__all__ = ["UserMappingService"]