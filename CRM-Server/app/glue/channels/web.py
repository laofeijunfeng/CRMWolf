"""网页渠道适配器

JWT session + 同步返回。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 十一、渠道适配器 11.2
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 5.4
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException

from app.glue.channels.base import ChannelSender


class WebChannelSender(ChannelSender):
    """网页渠道适配器

    特点：
    - 用户 ID 直接从 JWT session 获取
    - 同步返回结果，无需异步推送
    - 无需验签
    """

    channel = "web"

    def __init__(self):
        # 网页渠道的 reply_cache（存储同步返回的结果）
        self._reply_cache: Dict[str, Dict[str, Any]] = {}

    async def send(self, reply_token: str, text: str) -> bool:
        """网页渠道：存储回复到 cache

        网页渠道是同步返回，此方法用于存储结果供后续获取。

        Args:
            reply_token: 请求 message_id 作为 reply_token
            text: 回复文本

        Returns:
            bool: 存储是否成功
        """
        self._reply_cache[reply_token] = {
            "text": text,
            "mode": "reply",
            "timestamp": int(1000),  # TODO: 使用实际时间戳
        }
        return True

    def get_reply(self, reply_token: str) -> Optional[Dict[str, Any]]:
        """获取缓存的回复

        Args:
            reply_token: message_id

        Returns:
            Optional[Dict]: 缓存的回复内容
        """
        return self._reply_cache.get(reply_token)

    async def resolve_user(self, channel_user_id: str) -> Optional[int]:
        """解析 JWT session 用户 ID

        Args:
            channel_user_id: JWT session 中的 user_id

        Returns:
            Optional[int]: CRM 用户 ID
        """
        # 网页渠道：channel_user_id 直接是 crm_user_id
        try:
            return int(channel_user_id)
        except ValueError:
            raise HTTPException(status_code=401, detail="无效的用户 ID")

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """网页渠道：无需验签

        Args:
            body: 请求体
            signature: 签名

        Returns:
            bool: 网页渠道无需验签，直接返回 True
        """
        # 网页渠道通过 JWT 认证，无需验签
        return True


__all__ = ["WebChannelSender"]