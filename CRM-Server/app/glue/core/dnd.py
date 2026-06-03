"""免打扰策略

判断当前是否在免打扰时段。

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 6.2
"""

from datetime import datetime, time
from typing import Optional

from app.glue.config import GlueConfig


class DNDManager:
    """免打扰管理器

    判断当前时间是否在免打扰时段。
    """

    def __init__(self):
        self.config = GlueConfig()

    def is_dnd_active(self, custom_start: Optional[int] = None, custom_end: Optional[int] = None) -> bool:
        """判断当前是否在免打扰时段

        Args:
            custom_start: 自定义开始时间（小时）
            custom_end: 自定义结束时间（小时）

        Returns:
            bool: 是否在免打扰时段
        """
        now = datetime.now()
        current_hour = now.hour

        # 使用配置或自定义时间
        start_hour = custom_start if custom_start is not None else self.config.DND_HOURS_START
        end_hour = custom_end if custom_end is not None else self.config.DND_HOURS_END

        # 判断是否在免打扰时段
        if start_hour > end_hour:
            # 跨天的情况（如 22:00 - 08:00）
            return current_hour >= start_hour or current_hour < end_hour
        else:
            # 同一天的情况（如 13:00 - 14:00）
            return start_hour <= current_hour < end_hour

    def get_next_available_time(self) -> datetime:
        """获取下一个可推送时间

        Returns:
            datetime: 下一个可推送时间
        """
        now = datetime.now()
        end_hour = self.config.DND_HOURS_END

        if now.hour < end_hour:
            # 当前在免打扰时段，返回今天结束时间
            return datetime(now.year, now.month, now.day, end_hour, 0, 0)
        else:
            # 当前不在免打扰时段，返回明天结束时间
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = tomorrow.replace(day=now.day + 1)
            return tomorrow.replace(hour=end_hour)


__all__ = ["DNDManager"]