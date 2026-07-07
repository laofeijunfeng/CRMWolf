"""AI OpenAPI 路由聚合"""

from fastapi import APIRouter

from app.api.ai.actions import router as actions_router

# 创建主路由
router = APIRouter(prefix="/ai", tags=["AI OpenAPI"])

# 注册子路由
router.include_router(actions_router, prefix="/actions", tags=["AI Actions"])


__all__ = ["router"]