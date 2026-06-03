"""AI OpenAPI 路由聚合"""

from fastapi import APIRouter

from app.api.ai.metadata import router as metadata_router
from app.api.ai.actions import router as actions_router
from app.api.ai.intents import router as intents_router
from app.api.ai.logs import router as logs_router

# 创建主路由
router = APIRouter(prefix="/ai", tags=["AI OpenAPI"])

# 注册子路由
router.include_router(metadata_router, prefix="/metadata", tags=["AI Metadata"])
router.include_router(actions_router, prefix="/actions", tags=["AI Actions"])
router.include_router(intents_router, prefix="/intents", tags=["AI Intents"])
router.include_router(logs_router, prefix="/logs", tags=["AI Logs"])


__all__ = ["router"]