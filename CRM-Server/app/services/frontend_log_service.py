"""
Frontend Log Service

负责前端日志的文件存储、轮转、清理
"""
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from app.core.logging import get_logger
from app.schemas.frontend_log import FrontendLogEntry

logger = get_logger(__name__)

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志保留天数
LOG_RETENTION_DAYS = 30


class FrontendLogService:
    """前端日志服务"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._last_cleanup_time = 0.0
        self._cleanup_interval = 3600  # 1 hour

    async def write_logs(
        self,
        logs: list[FrontendLogEntry],
        session_id: str,
        user_agent: Optional[str] = None,
        url: Optional[str] = None
    ):
        """
        异步写入日志

        Args:
            logs: 日志条目列表
            session_id: 会话 ID
            user_agent: 用户代理
            url: 页面 URL
        """
        async with self._lock:
            try:
                # 获取当日日志文件
                log_file = self._get_log_file()

                # 准备日志条目
                entries = []
                for log in logs:
                    # 构建完整日志结构
                    log_entry = {
                        "timestamp": log.timestamp,
                        "level": log.level,
                        "context": log.context,
                        "action": log.action,
                        "data": log.data,
                        "sessionId": session_id,
                        "userId": log.userId,
                        "teamId": log.teamId,
                        "traceId": log.traceId,
                        "userAgent": user_agent,
                        "url": url
                    }

                    # 每行一个 JSON
                    entries.append(json.dumps(log_entry, ensure_ascii=False) + "\n")

                # 异步写入文件
                await asyncio.to_thread(self._write_log_entries, log_file, entries)

                logger.debug(f"Written {len(logs)} logs to {log_file}")

                # 清理过期日志
                await self._cleanup_old_logs()

            except Exception as e:
                logger.error(f"Failed to write logs: {e}")
                raise

    async def write_logs_direct(
        self,
        logs: list[FrontendLogEntry],
        session_id: str
    ):
        """
        直接写入日志（不经过队列，用于 beacon）

        Args:
            logs: 日志条目列表
            session_id: 会话 ID
        """
        async with self._lock:
            try:
                log_file = self._get_log_file()

                entries = []
                for log in logs:
                    log_entry = {
                        "timestamp": log.timestamp,
                        "level": log.level,
                        "context": log.context,
                        "action": log.action,
                        "data": log.data,
                        "sessionId": session_id,
                        "userId": log.userId,
                        "teamId": log.teamId,
                        "traceId": log.traceId
                    }

                    entries.append(json.dumps(log_entry, ensure_ascii=False) + "\n")

                # 异步写入文件
                await asyncio.to_thread(self._write_log_entries, log_file, entries)

            except Exception as e:
                logger.error(f"Failed to write direct logs: {e}")

    def _write_log_entries(self, file_path: Path, entries: list[str]):
        """同步写入日志条目（在线程中执行）"""
        with open(file_path, "a", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry)

    def _get_log_file(self) -> Path:
        """获取当日日志文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return LOG_DIR / f"frontend-{today}.log"

    async def _cleanup_old_logs(self):
        """清理超过保留天数的日志"""
        now = time.time()
        if now - self._last_cleanup_time < self._cleanup_interval:
            return  # Skip if cleanup ran recently

        self._last_cleanup_time = now

        try:
            retention_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)

            for log_file in LOG_DIR.glob("frontend-*.log"):
                # 解析日期
                date_str = log_file.stem.replace("frontend-", "")
                try:
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")

                    if file_date < retention_date:
                        log_file.unlink()
                        logger.info(f"Deleted old log file: {log_file}")

                except ValueError:
                    # 无法解析日期的文件跳过
                    continue

        except Exception as e:
            logger.error(f"Failed to cleanup logs: {e}")