"""
Frontend Log Schema

用于接收前端日志的 Pydantic schema
"""
from typing import Any

from pydantic import BaseModel


class FrontendLogEntry(BaseModel):
    """单条前端日志"""
    level: str  # debug, info, warn, error
    context: str  # 如 "[AIAssistant]"
    action: str  # 如 "restore"
    data: Any | None = None
    timestamp: int  # Unix timestamp (ms)
    traceId: str | None = None
    userId: int | None = None
    teamId: int | None = None


class FrontendLogBatchRequest(BaseModel):
    """批量日志请求"""
    logs: list[FrontendLogEntry]
    sessionId: str
    userAgent: str | None = None
    url: str | None = None


class FrontendLogBeaconRequest(BaseModel):
    """Beacon 日志请求（页面关闭时发送）"""
    logs: list[FrontendLogEntry]
    sessionId: str