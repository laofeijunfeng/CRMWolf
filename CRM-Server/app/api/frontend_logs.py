"""
Frontend Logs API

接收前端日志的 API 端点
- POST /v1/logs/batch: 批量接收日志
- POST /v1/logs/beacon: sendBeacon 专用端点
"""
from fastapi import APIRouter, Request
from fastapi.responses import Response
from app.schemas.frontend_log import FrontendLogBatchRequest, FrontendLogBeaconRequest
from app.services.frontend_log_service import FrontendLogService
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/logs", tags=["frontend-logs"])

# 服务实例（单例）
log_service = FrontendLogService()


@router.post("/batch")
async def receive_log_batch(request: FrontendLogBatchRequest):
    """
    批量接收前端日志

    - 不阻塞响应（快速返回 200）
    - 写入文件存储
    """
    try:
        # 写入日志文件
        await log_service.write_logs(
            logs=request.logs,
            session_id=request.sessionId,
            user_agent=request.userAgent,
            url=request.url
        )

        logger.debug(f"Received {len(request.logs)} frontend logs from session {request.sessionId}")

        return {"received": len(request.logs)}

    except Exception as e:
        logger.error(f"Failed to write frontend logs: {e}")
        # 即使失败也返回 200，避免前端重试导致雪崩
        return {"received": 0, "error": str(e)}


@router.post("/beacon")
async def receive_beacon_logs(request: Request):
    """
    接收 sendBeacon 发送的日志（页面关闭时）

    - 使用 Request 直接接收 JSON（sendBeacon 无法发送标准 HTTP body）
    - 直接写入文件（不经过队列）
    """
    try:
        # 解析 JSON body
        body = await request.json()
        log_request = FrontendLogBeaconRequest(**body)

        # 直接写入文件
        await log_service.write_logs_direct(
            logs=log_request.logs,
            session_id=log_request.sessionId
        )

        logger.debug(f"Received beacon logs: {len(log_request.logs)} entries")

        # 返回 204 No Content（sendBeacon 不关心响应）
        return Response(status_code=204)

    except Exception as e:
        logger.error(f"Failed to write beacon logs: {e}")
        return Response(status_code=204)  # 始终返回 204