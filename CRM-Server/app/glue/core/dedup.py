"""消息去重管理器

防止 IM webhook 重投导致的重复处理。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 七、Session 数据契约 7.4
"""

import redis.asyncio as redis
from app.glue.config import GlueConfig


class DedupManager:
    """消息去重管理器

    使用 Redis SETNX 检查 message_id 是否已处理。
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.config = GlueConfig()

    async def check(self, message_id: str) -> bool:
        """检查消息是否可处理

        Args:
            message_id: 消息唯一标识

        Returns:
            True: 可处理（首次）
            False: 已处理（重复）
        """
        key = f"{self.config.MESSAGE_KEY_PREFIX}:{message_id}"
        result = await self.redis.setnx(key, "1")

        if result:
            # 设置 TTL
            await self.redis.expire(key, self.config.MESSAGE_TTL)
            return True

        # 已存在，重复消息
        return False


__all__ = ["DedupManager"]