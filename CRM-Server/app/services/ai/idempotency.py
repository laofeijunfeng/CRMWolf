"""AI OpenAPI 幂等性管理器

基于 Redis 实现 action_id 的幂等性检查，防止重复执行。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

import json
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.redis import get_redis_client


class IdempotencyManager:
    """幂等性管理器

    功能：
    1. 检查 action_id 是否已执行
    2. 锁定 action_id 防止并发重复执行
    3. 记录执行结果供查询

    TTL: 1 小时（可根据业务调整）
    """

    KEY_PREFIX = "ai:action"
    TTL_SECONDS = 3600  # 1 小时

    def __init__(self):
        self.redis = get_redis_client()

    def check_or_lock(self, action_id: str) -> bool:
        """检查是否已执行，未执行则锁定

        Args:
            action_id: 动作唯一标识

        Returns:
            True: 可执行（已锁定）
            False: 已执行或已被锁定
        """
        key = f"{self.KEY_PREFIX}:{action_id}"

        # 使用 SETNX 实现原子性检查+锁定
        result = self.redis.setnx(key, "locked")
        if result:
            # 设置过期时间
            self.redis.expire(key, self.TTL_SECONDS)
            return True

        return False

    def unlock(self, action_id: str) -> bool:
        """解除锁定（用于执行失败时）

        Args:
            action_id: 动作唯一标识

        Returns:
            True: 解锁成功
            False: 键不存在
        """
        key = f"{self.KEY_PREFIX}:{action_id}"
        return self.redis.delete(key) > 0

    def record_result(self, action_id: str, result: Dict[str, Any]) -> bool:
        """记录执行结果

        Args:
            action_id: 动作唯一标识
            result: 执行结果（包含 status、data、error 等）

        Returns:
            True: 记录成功
        """
        key = f"{self.KEY_PREFIX}:{action_id}:result"

        result_data = {
            "action_id": action_id,
            "status": result.get("status"),
            "data": result.get("data"),
            "error": result.get("error"),
            "message": result.get("message"),
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.redis.setex(key, self.TTL_SECONDS, json.dumps(result_data, ensure_ascii=False))
        return True

    def get_result(self, action_id: str) -> Optional[Dict[str, Any]]:
        """获取执行结果

        Args:
            action_id: 动作唯一标识

        Returns:
            执行结果字典，若不存在返回 None
        """
        key = f"{self.KEY_PREFIX}:{action_id}:result"
        data = self.redis.get(key)

        if data:
            return json.loads(data)
        return None

    def is_executed(self, action_id: str) -> bool:
        """检查是否已执行

        Args:
            action_id: 动作唯一标识

        Returns:
            True: 已执行
            False: 未执行
        """
        key = f"{self.KEY_PREFIX}:{action_id}"
        return self.redis.exists(key) > 0

    def clear_all(self) -> int:
        """清除所有 AI action 相关键（慎用）

        Returns:
            清除的键数量
        """
        pattern = f"{self.KEY_PREFIX}:*"
        keys = self.redis.keys(pattern)
        if keys:
            return self.redis.delete(*keys)
        return 0


# 全局实例
idempotency_manager = IdempotencyManager()


__all__ = ["IdempotencyManager", "idempotency_manager"]