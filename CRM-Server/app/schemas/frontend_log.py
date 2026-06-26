"""
Frontend Log Schema

用于接收前端日志的 Pydantic schema
"""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class FrontendLogEntry(BaseModel):
    """单条前端日志"""
    level: str  # debug, info, warn, error
    context: str  # 如 "[AIAssistant]"
    action: str  # 如 "restore"
    data: Optional[Any] = None
    timestamp: int  # Unix timestamp (ms)
    traceId: Optional[str] = None
    userId: Optional[int] = None
    teamId: Optional[int] = None


class FrontendLogBatchRequest(BaseModel):
    """批量日志请求"""
    logs: list[FrontendLogEntry]
    sessionId: str
    userAgent: Optional[str] = None
    url: Optional[str] = None


class FrontendLogBeaconRequest(BaseModel):
    """Beacon 日志请求（页面关闭时发送）"""
    logs: list[FrontendLogEntry]
    sessionId: str