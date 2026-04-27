"""
限流服务 - 使用 Redis 滑动窗口算法
"""
import time
import redis
from typing import Optional
from app.core.config import get_settings

settings = get_settings()


class RateLimiter:
    """基于 Redis 的滑动窗口限流"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._connect()

    def _connect(self):
        """建立 Redis 连接"""
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            # 测试连接
            self.redis_client.ping()
        except redis.ConnectionError as e:
            print(f"Redis 连接失败: {e}")
            self.redis_client = None

    def is_allowed(self, key_id: str, rate_limit_tps: int, burst_limit: Optional[int] = None) -> tuple[bool, int, int]:
        """
        检查请求是否被允许（滑动窗口算法）

        Args:
            key_id: API Key ID
            rate_limit_tps: 每秒请求限制
            burst_limit: 突发限制（可选，默认为 rate_limit_tps * 2）

        Returns:
            (是否允许, 当前请求计数, 重试等待秒数)
        """
        if not self.redis_client:
            # Redis 不可用时，默认允许
            return True, 0, 0

        if burst_limit is None:
            burst_limit = min(rate_limit_tps * 2, 200)

        now = time.time()
        window_start = now - 1  # 1秒滑动窗口

        redis_key = f"rate_limit:{key_id}"

        try:
            # 使用 Redis 事务确保原子性
            pipe = self.redis_client.pipeline()

            # 1. 移除窗口外的旧请求
            pipe.zremrangebyscore(redis_key, 0, window_start)

            # 2. 获取当前窗口内的请求计数
            pipe.zcard(redis_key)

            # 3. 添加当前请求时间戳
            pipe.zadd(redis_key, {str(now): now})

            # 4. 设置过期时间（2秒，略大于窗口）
            pipe.expire(redis_key, 2)

            results = pipe.execute()
            current_count = results[1]

            # 检查是否超限
            if current_count >= burst_limit:
                # 计算需要等待的时间（窗口内最早请求的过期时间）
                oldest = self.redis_client.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    wait_time = max(0, 1 - (now - float(oldest[0][1])))
                    return False, current_count, round(wait_time, 3)
                return False, current_count, 1

            if current_count >= rate_limit_tps:
                # 达到限制但未超突发限制
                return True, current_count, 0

            return True, current_count, 0

        except redis.RedisError as e:
            print(f"Redis 限流检查失败: {e}")
            return True, 0, 0

    def get_current_count(self, key_id: str) -> int:
        """获取当前窗口内的请求计数"""
        if not self.redis_client:
            return 0

        redis_key = f"rate_limit:{key_id}"
        now = time.time()
        window_start = now - 1

        try:
            # 清理旧请求并获取计数
            self.redis_client.zremrangebyscore(redis_key, 0, window_start)
            return self.redis_client.zcard(redis_key)
        except redis.RedisError:
            return 0

    def reset(self, key_id: str) -> bool:
        """重置限流计数"""
        if not self.redis_client:
            return False

        redis_key = f"rate_limit:{key_id}"
        try:
            self.redis_client.delete(redis_key)
            return True
        except redis.RedisError:
            return False


# 全局单例
rate_limiter = RateLimiter()