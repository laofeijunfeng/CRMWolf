"""主动推送任务

定时检查商机停留提醒，推送消息。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 十、主动推送设计
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 6.1
"""

from typing import List, Dict, Any
from datetime import datetime
import redis.asyncio as redis
import httpx

from app.glue.config import GlueConfig
from app.glue.core.dnd import DNDManager


class PushManager:
    """推送管理器

    定时任务：检查商机停留提醒并推送。
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.config = GlueConfig()
        self.dnd = DNDManager()

    async def check_due_reminders(self) -> List[Dict[str, Any]]:
        """检查待推送的提醒

        Returns:
            List[Dict]: 待推送的提醒列表
        """
        # TODO: 调用 /ai/metadata/due-reminders 或查询只读视图
        # 简化示例：返回空

        # 实际逻辑:
        # 1. 读停留超过 config.OPPORTUNITY_STAY_THRESHOLD 天的商机
        # 2. 对每个 (user, opportunity, reason):
        #    - 去重 key: ai:glue:push:{user}:{opp}:{reason}
        #    - 检查免打扰（DND）
        #    - 拼文本 → ChannelSender.send()

        return []

    async def push_reminder(self, user_id: int, opportunity_id: int, reason: str, text: str) -> bool:
        """推送提醒

        Args:
            user_id: 用户 ID
            opportunity_id: 商机 ID
            reason: 提醒原因
            text: 提醒文本

        Returns:
            bool: 推送是否成功
        """
        # 1. 去重检查
        push_key = f"{self.config.PUSH_KEY_PREFIX}:{user_id}:{opportunity_id}:{reason}"
        if await self.redis.exists(push_key):
            # 已推送过
            return False

        # 2. 免打扰检查
        if self.dnd.is_dnd_active():
            # 当前在免打扰时段，不推送
            return False

        # 3. 推送消息
        # TODO: 获取用户绑定渠道，调用对应 ChannelSender
        # 简化示例：直接记录推送

        await self.redis.set(push_key, "1", ex=self.config.PUSH_TTL)
        return True

    def render_reminder_text(self, opportunity_name: str, stage_name: str, stay_days: int) -> str:
        """渲染提醒文本

        Args:
            opportunity_name: 商机名称
            stage_name: 阶段名称
            stay_days: 停留天数

        Returns:
            str: 提醒文本
        """
        lines = [
            "📢 商机停留提醒",
            f"商机「{opportunity_name}」已在「{stage_name}」阶段停留 {stay_days} 天",
            "建议：跟进客户或推进阶段",
            "",
            "回复「跟进」创建跟进记录",
        ]
        return "\n".join(lines)


__all__ = ["PushManager"]