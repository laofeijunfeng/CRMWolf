"""ChannelSender 抽象

渠道适配器的抽象接口定义。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 十一、渠道适配器
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 5.1
"""

from abc import ABC, abstractmethod
from typing import Optional


class ChannelSender(ABC):
    """渠道发送器抽象

    定义各渠道适配器的统一接口。
    """

    channel: str  # 渠道标识

    @abstractmethod
    async def send(self, reply_token: str, text: str) -> bool:
        """发送文本回复

        Args:
            reply_token: 回复 token
            text: 回复文本

        Returns:
            bool: 发送是否成功
        """
        pass

    @abstractmethod
    async def resolve_user(self, channel_user_id: str) -> Optional[int]:
        """解析渠道用户 ID → CRM 用户 ID

        Args:
            channel_user_id: 渠道用户 ID（open_id/userid）

        Returns:
            Optional[int]: CRM 用户 ID 或 None（未绑定）
        """
        pass

    @abstractmethod
    def verify_signature(self, body: bytes, signature: str) -> bool:
        """验证请求签名

        Args:
            body: 请求体
            signature: 签名

        Returns:
            bool: 签名是否有效
        """
        pass


__all__ = ["ChannelSender"]