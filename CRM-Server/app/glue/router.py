"""胶水层路由聚合

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 四、系统架构设计
"""

from fastapi import APIRouter

from app.glue.api.inbound import router as inbound_router
from app.glue.api.admin import router as admin_router


router = APIRouter()

router.include_router(inbound_router)
router.include_router(admin_router)


__all__ = ["router"]