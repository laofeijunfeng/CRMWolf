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

from app.api import auth, users, roles, permissions, leads, customers, customer_follow_ups, opportunities, filter_options, contracts, approvals, payments, invoices, finance, operation_logs, procurement_methods, procurement_stage_templates, opportunity_stages, customer_procurement, procurement_admin, calendar, teams, industry, lead_ai
from app.api.customer_ai import router as customer_ai_router
from app.api.web_assistant import router as web_assistant_router
from app.api.ai_config import router as ai_config_router
from app.api.ai_skills import router as ai_skills_router
from app.api.ai_skill_generator import router as ai_skill_generator_router
from app.api.chat import router as chat_router
from app.api.ai import router as ai_openapi_router
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

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(permissions.router)
app.include_router(leads.router)
app.include_router(leads.analytics_router)
app.include_router(lead_ai.router)
app.include_router(customers.router)
app.include_router(customer_ai_router)
app.include_router(industry.router)
app.include_router(customer_procurement.router)
app.include_router(customer_follow_ups.router)
app.include_router(opportunities.router)
app.include_router(opportunities.analytics_router)
app.include_router(filter_options.router)
app.include_router(contracts.router)
app.include_router(approvals.router)
app.include_router(payments.router)
app.include_router(invoices.router, prefix="/v1")
app.include_router(invoices.invoice_router, prefix="/v1")
app.include_router(finance.router, prefix="/v1")
app.include_router(operation_logs.router, prefix="/v1")
app.include_router(procurement_methods.router)
app.include_router(procurement_stage_templates.router)
app.include_router(opportunity_stages.router)
app.include_router(procurement_admin.router)
app.include_router(teams.router)

# 日历路由
app.include_router(calendar.router)

# AI 配置管理路由
app.include_router(ai_config_router)

# AI Skill 配置管理路由
app.include_router(ai_skills_router)

# AI Skill Generator 路由
app.include_router(ai_skill_generator_router)

# 聊天机器人路由（通用接口，支持飞书/钉钉/企业微信等）
app.include_router(chat_router)

# Web AI 助手路由
app.include_router(web_assistant_router)

# AI OpenAPI 路由（面向 AI Agent 的标准化接口）
app.include_router(ai_openapi_router)

# AI 对话胶水层路由
from app.glue.router import router as glue_router
app.include_router(glue_router)

# 热力值权重配置路由
from app.api.score_weights import router as score_weights_router
app.include_router(score_weights_router)

# 热力值查询路由
from app.api.scores import router as scores_router
app.include_router(scores_router)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化角色权限和定时任务"""
    logger.info("应用启动，开始初始化角色权限...")
    init_roles_permissions()

    # 启动热力值定时刷新任务
    logger.info("启动热力值定时刷新任务...")
    from app.tasks.score_scheduler import start_score_scheduler
    start_score_scheduler()


@app.get("/")
async def root():
    return {"message": "CRM API is running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
