"""
Agent Executor Pool - 资源隔离

Agent 专用线程池 + 并发限制 + 超时机制。

Phase E 核心功能：
1. 独立线程池：与 CRM 核心业务隔离
2. Semaphore 并发限制：防止 Agent 满载拖垮系统
3. 超时机制：防止死循环或长时间阻塞
4. 速率限制：防止恶意高频调用

用于 AI Agent 执行资源隔离，避免影响核心 CRM 请求线程。
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from app.core.config import get_settings


class AgentExecutorPool:
    """Agent 执行线程池

    设计原则：
    - 资源隔离：Agent 执行线程与核心 CRM 业务线程池隔离
    - 并发限制：防止 Agent 高频调用拖垮整个 CRM 系统
    - 超时保护：防止 Agent 死循环或长时间阻塞

    配置项：
    - AGENT_THREAD_POOL_SIZE: 线程池大小（默认 4）
    - AGENT_MAX_CONCURRENT: 最大并发数（默认 10）
    - AGENT_TIMEOUT: 单次执行超时（默认 120 秒）
    - AGENT_USER_RATE_LIMIT: 用户速率限制（默认 10/分钟）
    - AGENT_GLOBAL_RATE_LIMIT: 全局速率限制（默认 100/分钟）
    """

    def __init__(self):
        self.settings = get_settings()

        # Agent 专用线程池
        self.pool = ThreadPoolExecutor(
            max_workers=self.settings.AGENT_THREAD_POOL_SIZE,
            thread_name_prefix="agent_worker"
        )

        # 并发限制 Semaphore
        self.semaphore = asyncio.Semaphore(self.settings.AGENT_MAX_CONCURRENT)

        # 统计信息
        self.stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "timeout_executions": 0,
            "rejected_executions": 0,  # 因并发限制被拒绝
            "current_concurrent": 0,
        }

    async def execute(
        self,
        workflow_id: str,
        session: Dict[str, Any],
        executor_func: Callable,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """在隔离线程池中执行 Workflow

        Args:
            workflow_id: 流程 ID
            session: Session 状态
            executor_func: 执行函数（同步函数）
            timeout: 超时时间（秒），默认使用配置

        Returns:
            执行结果
        """
        timeout = timeout or self.settings.AGENT_TIMEOUT
        start_time = time.time()

        # 检查并发限制
        if self.semaphore.locked() and self.stats["current_concurrent"] >= self.settings.AGENT_MAX_CONCURRENT:
            self.stats["rejected_executions"] += 1
            return {
                "success": False,
                "error": "Agent 并发数已达上限，请稍后重试",
                "rejected": True,
                "current_concurrent": self.stats["current_concurrent"],
            }

        async with self.semaphore:
            self.stats["current_concurrent"] += 1
            self.stats["total_executions"] += 1

            try:
                # 在线程池中执行（带超时）
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self.pool,
                        executor_func,
                        workflow_id,
                        session
                    ),
                    timeout=timeout
                )

                self.stats["successful_executions"] += 1

                return {
                    "success": True,
                    "result": result,
                    "duration_ms": (time.time() - start_time) * 1000,
                }

            except asyncio.TimeoutError:
                self.stats["timeout_executions"] += 1
                self.stats["failed_executions"] += 1

                return {
                    "success": False,
                    "error": f"Agent 执行超时（{timeout}秒）",
                    "timeout": True,
                    "duration_ms": (time.time() - start_time) * 1000,
                }

            except Exception as e:
                self.stats["failed_executions"] += 1

                return {
                    "success": False,
                    "error": str(e),
                    "duration_ms": (time.time() - start_time) * 1000,
                }

            finally:
                self.stats["current_concurrent"] -= 1

    async def execute_streaming(
        self,
        workflow_id: str,
        session: Dict[str, Any],
        executor_func: Callable,
        timeout: Optional[int] = None
    ):
        """流式执行（用于 SSE）

        Args:
            workflow_id: 流程 ID
            session: Session 状态
            executor_func: 执行函数（返回 AsyncGenerator）
            timeout: 超时时间

        Yields:
            SSE 事件
        """
        timeout = timeout or self.settings.AGENT_TIMEOUT

        # 检查并发限制
        if self.semaphore.locked() and self.stats["current_concurrent"] >= self.settings.AGENT_MAX_CONCURRENT:
            self.stats["rejected_executions"] += 1
            yield {
                "event": "agent_rejected",
                "data": {
                    "message": "Agent 并发数已达上限，请稍后重试",
                    "current_concurrent": self.stats["current_concurrent"],
                    "max_concurrent": self.settings.AGENT_MAX_CONCURRENT,
                }
            }
            return

        async with self.semaphore:
            self.stats["current_concurrent"] += 1
            self.stats["total_executions"] += 1

            start_time = time.time()

            try:
                # 流式执行（带超时保护）
                async for event in executor_func(workflow_id, session):
                    # 检查超时
                    if (time.time() - start_time) > timeout:
                        self.stats["timeout_executions"] += 1
                        yield {
                            "event": "agent_timeout",
                            "data": {
                                "message": f"Agent 执行超时（{timeout}秒）",
                                "duration_ms": (time.time() - start_time) * 1000,
                            }
                        }
                        return

                    yield event

                self.stats["successful_executions"] += 1

            except Exception as e:
                self.stats["failed_executions"] += 1
                yield {
                    "event": "agent_error",
                    "data": {
                        "message": str(e),
                        "duration_ms": (time.time() - start_time) * 1000,
                    }
                }

            finally:
                self.stats["current_concurrent"] -= 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "thread_pool_size": self.settings.AGENT_THREAD_POOL_SIZE,
            "max_concurrent": self.settings.AGENT_MAX_CONCURRENT,
            "timeout": self.settings.AGENT_TIMEOUT,
            "pool_active_threads": len([t for t in self.pool._threads if t.is_alive()]),
        }

    def shutdown(self):
        """关闭线程池"""
        self.pool.shutdown(wait=True)


class AgentRateLimiter:
    """Agent 请求速率限制器

    防止 Agent 被恶意高频调用。

    Features:
    - 用户级别速率限制
    - 全局速率限制
    - 突发流量控制
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        self.settings = get_settings()

    def _user_key(self, user_id: int) -> str:
        """用户速率限制 key"""
        return f"agent_rate:user:{user_id}"

    def _global_key(self) -> str:
        """全局速率限制 key"""
        return f"agent_rate:global"

    async def check_rate_limit(self, user_id: int) -> tuple[bool, str]:
        """检查速率限制

        Args:
            user_id: 用户 ID

        Returns:
            (是否允许, 原因)
        """
        # 检查用户级别限制
        user_key = self._user_key(user_id)
        user_count = await self.redis.get(user_key)

        if user_count and int(user_count) >= self.settings.AGENT_USER_RATE_LIMIT:
            return False, f"用户速率限制已达上限（{self.settings.AGENT_USER_RATE_LIMIT}/分钟）"

        # 检查全局限制
        global_key = self._global_key()
        global_count = await self.redis.get(global_key)

        if global_count and int(global_count) >= self.settings.AGENT_GLOBAL_RATE_LIMIT:
            return False, f"全局速率限制已达上限（{self.settings.AGENT_GLOBAL_RATE_LIMIT}/分钟）"

        return True, "允许"

    async def increment_rate(self, user_id: int) -> None:
        """增加速率计数"""
        user_key = self._user_key(user_id)
        global_key = self._global_key()

        # 用户计数（60 秒过期）
        await self.redis.incr(user_key)
        await self.redis.expire(user_key, 60)

        # 全局计数
        await self.redis.incr(global_key)
        await self.redis.expire(global_key, 60)


# 全局单例
_agent_pool: Optional[AgentExecutorPool] = None


def get_agent_pool() -> AgentExecutorPool:
    """获取 Agent Pool 单例"""
    global _agent_pool

    if _agent_pool is None:
        _agent_pool = AgentExecutorPool()

    return _agent_pool


def shutdown_agent_pool():
    """关闭 Agent Pool"""
    global _agent_pool

    if _agent_pool:
        _agent_pool.shutdown()
        _agent_pool = None


__all__ = [
    "AgentExecutorPool",
    "AgentRateLimiter",
    "get_agent_pool",
    "shutdown_agent_pool",
]
