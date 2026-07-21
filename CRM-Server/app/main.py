from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
import os

# 初始化日志系统（开发环境开启 DEBUG）
from app.core.logging import setup_logging, get_logger
debug_mode = os.getenv("CRM_DEBUG", "true").lower() == "true"
setup_logging(debug=debug_mode)
logger = get_logger(__name__)

from app.api import auth, users, roles, permissions, leads, customers, customer_follow_ups, opportunities, filter_options, contracts, approvals, payments, invoices, finance, operation_logs, procurement_methods, procurement_stage_templates, opportunity_stages, customer_procurement, procurement_admin, teams, industry, lead_ai, procurement_ai, approval_ai, system_configs, sales_dashboard, oauth
from app.api.deployment import router as deployment_router  # 新增
from app.api.license_application import router as license_application_router  # 新增
from app.api.customer_ai import router as customer_ai_router
# from app.api.web_assistant import router as web_assistant_router  # 暂时禁用（依赖旧的 LangGraph）
from app.api.ai_config import router as ai_config_router
# from app.api.chat import router as chat_router  # 暂时禁用（依赖旧的 LangGraph）
from app.api.ai import router as ai_openapi_router
from app.api.workflow_undo import router as workflow_undo_router
# Frontend Logs 路由
from app.api.frontend_logs import router as frontend_logs_router
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
    pydantic_validation_exception_handler,
    sqlalchemy_exception_handler,
    generic_exception_handler
)

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
from app.api.score_weights import router as score_weights_router
from app.api.scores import router as scores_router

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
api_router.include_router(lead_ai.router)
api_router.include_router(procurement_ai.router)
api_router.include_router(approval_ai.router)
api_router.include_router(customers.router)
api_router.include_router(customer_ai_router)
api_router.include_router(industry.router)
api_router.include_router(customer_procurement.router)
api_router.include_router(customer_follow_ups.router)
api_router.include_router(opportunities.router)
api_router.include_router(opportunities.analytics_router)
api_router.include_router(filter_options.router)
api_router.include_router(contracts.router)
api_router.include_router(approvals.router)
api_router.include_router(sales_dashboard.router)
api_router.include_router(system_configs.router)
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
api_router.include_router(frontend_logs_router)
api_router.include_router(score_weights_router)
api_router.include_router(scores_router)

# === AI OpenAPI 路由（无 /v1 前缀）===
api_router.include_router(ai_openapi_router)

# === Workflow Undo 路由 ===
api_router.include_router(workflow_undo_router)

# 注册主 API 路由到 app（添加统一的 /api 前缀）
app.include_router(api_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化角色权限和定时任务"""
    logger.info("应用启动，开始初始化角色权限...")
    init_roles_permissions()

    # 启动热力值定时刷新任务
    logger.info("启动热力值定时刷新任务...")
    from app.tasks.score_scheduler import start_score_scheduler
    start_score_scheduler()

    # 启动审批超时催办任务
    logger.info("启动审批超时催办任务...")
    from app.tasks.approval_reminder import start_approval_reminder_scheduler
    start_approval_reminder_scheduler()


@app.get("/")
async def root():
    return {"message": "CRM API is running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
