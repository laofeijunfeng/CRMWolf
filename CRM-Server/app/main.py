import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

# 初始化日志系统（开发环境开启 DEBUG）
from app.core.logging import get_logger, setup_logging

debug_mode = os.getenv("CRM_DEBUG", "true").lower() == "true"
setup_logging(debug=debug_mode)
logger = get_logger(__name__)

from app.api import (
    approval_ai,
    approvals,
    auth,
    business_journey_board,
    contracts,
    customer_activities,
    customer_procurement,
    customers,
    filter_options,
    finance,
    industry,
    invoices,
    leads,
    oauth,
    operation_logs,
    opportunities,
    opportunity_stages,
    payments,
    permissions,
    procurement_admin,
    procurement_ai,
    procurement_methods,
    procurement_stage_templates,
    roles,
    sales_dashboard,
    system_configs,
    teams,
    users,
    view_preferences,
)
from app.api.agent import router as agent_router
from app.api.ai_config import router as ai_config_router
from app.api.customer_ai import router as customer_ai_router
from app.api.deployment import router as deployment_router  # 新增

# Frontend Logs 路由
from app.api.frontend_logs import router as frontend_logs_router
from app.api.im_bots import router as im_bots_router
from app.api.license_application import router as license_application_router  # 新增
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    pydantic_validation_exception_handler,
    sqlalchemy_exception_handler,
    validation_exception_handler,
)
from app.core.database import SessionLocal
from app.services.customer_intelligence_health_service import customer_intelligence_health_service

# 导入初始化服务
from app.services.init_service import init_roles_permissions

app = FastAPI(
    title="CRM API",
    description="Customer Relationship Management API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# ========================================
# 路由注册（统一 /api 前缀）
# ========================================
from fastapi import APIRouter

# 创建主 API 路由
api_router = APIRouter()

# === 认证相关（模块内部无 /v1，main.py 添加 /v1）===
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(users.router, prefix="/v1")
api_router.include_router(roles.router, prefix="/v1")
api_router.include_router(permissions.router, prefix="/v1")

# === 业务路由（模块内部已有 /v1）===
api_router.include_router(leads.router)
api_router.include_router(leads.analytics_router)
api_router.include_router(procurement_ai.router)
api_router.include_router(approval_ai.router)
api_router.include_router(customers.router)
api_router.include_router(customer_ai_router)
api_router.include_router(industry.router)
api_router.include_router(customer_procurement.router)
api_router.include_router(customer_activities.router)
api_router.include_router(opportunities.router)
api_router.include_router(opportunities.analytics_router)
api_router.include_router(filter_options.router)
api_router.include_router(contracts.router)
api_router.include_router(approvals.router)
api_router.include_router(sales_dashboard.router)
api_router.include_router(business_journey_board.router)
api_router.include_router(system_configs.router)
api_router.include_router(view_preferences.router)
api_router.include_router(payments.router)
api_router.include_router(invoices.router, prefix="/v1")
api_router.include_router(invoices.invoice_router, prefix="/v1")
api_router.include_router(finance.router, prefix="/v1")
api_router.include_router(operation_logs.router, prefix="/v1")
api_router.include_router(procurement_methods.router)
api_router.include_router(procurement_stage_templates.router)
api_router.include_router(opportunity_stages.router)
api_router.include_router(procurement_admin.router)
api_router.include_router(teams.router)
api_router.include_router(oauth.router)
api_router.include_router(deployment_router)  # 新增：部署信息管理
api_router.include_router(license_application_router)  # 新增：License申请管理

# === AI 相关路由 ===
api_router.include_router(ai_config_router)
api_router.include_router(agent_router)
api_router.include_router(im_bots_router)
api_router.include_router(frontend_logs_router)

# 注册主 API 路由到 app（添加统一的 /api 前缀）
app.include_router(api_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化角色权限和定时任务"""
    logger.info("应用启动，开始初始化角色权限...")
    init_roles_permissions()

    logger.info("恢复未完成客户活动 AI workflow...")
    from app.services.customer_activity_processing_service import customer_activity_processing_service
    recovered_count = await customer_activity_processing_service.recover_unfinished()
    logger.info("已重新派发 %s 个未完成客户活动 AI workflow", recovered_count)

    logger.info("启动客户证据向量同步任务...")
    from app.tasks.customer_evidence_sync import start_customer_evidence_sync_scheduler
    start_customer_evidence_sync_scheduler()

    logger.info("启动客户智能档案刷新重试任务...")
    from app.tasks.customer_intelligence_refresh_retry import start_customer_intelligence_refresh_retry_scheduler
    start_customer_intelligence_refresh_retry_scheduler()

    logger.info("启动客户智能历史补档任务...")
    from app.tasks.customer_intelligence_backfill import start_customer_intelligence_backfill_scheduler
    start_customer_intelligence_backfill_scheduler()

    logger.info("审批超时自动催办任务已停用，催办改为审批中心手动触发")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止后台调度任务"""
    from app.tasks.customer_evidence_sync import stop_customer_evidence_sync_scheduler
    from app.tasks.customer_intelligence_backfill import stop_customer_intelligence_backfill_scheduler
    from app.tasks.customer_intelligence_refresh_retry import stop_customer_intelligence_refresh_retry_scheduler

    stop_customer_intelligence_backfill_scheduler()
    stop_customer_intelligence_refresh_retry_scheduler()
    stop_customer_evidence_sync_scheduler()


@app.get("/")
async def root():
    return {"message": "CRM API is running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/health/customer-intelligence")
async def customer_intelligence_health_check():
    db = SessionLocal()
    try:
        return customer_intelligence_health_service.check(db)
    finally:
        db.close()
