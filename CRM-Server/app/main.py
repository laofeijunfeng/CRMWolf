from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
from app.api import auth, users, roles, permissions, dev, leads, customers, customer_follow_ups, opportunities, filter_options, contracts, approvals, payments, invoices, finance, operation_logs, procurement_methods, procurement_stage_templates, opportunity_stages, customer_procurement, procurement_admin
from app.api.ai_config import router as ai_config_router
from app.api.ai_skills import router as ai_skills_router
from app.api.ai_skill_generator import router as ai_skill_generator_router
from app.api.chat import router as chat_router
from app.api.api_keys import router as api_keys_router
from app.api.openapi import openapi_router
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
    pydantic_validation_exception_handler,
    sqlalchemy_exception_handler,
    generic_exception_handler
)

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
app.include_router(dev.router)
app.include_router(leads.router)
app.include_router(leads.analytics_router)
app.include_router(customers.router)
app.include_router(customer_procurement.router)
app.include_router(customer_follow_ups.router)
app.include_router(opportunities.router)
app.include_router(opportunities.analytics_router)
app.include_router(filter_options.router)
app.include_router(contracts.router)
app.include_router(approvals.router)
app.include_router(payments.router)
app.include_router(invoices.router, prefix="/api/v1")
app.include_router(invoices.invoice_router, prefix="/api/v1")
app.include_router(finance.router, prefix="/api/v1")
app.include_router(operation_logs.router, prefix="/api/v1")
app.include_router(procurement_methods.router)
app.include_router(procurement_stage_templates.router)
app.include_router(opportunity_stages.router)
app.include_router(procurement_admin.router)

# 开放接口路由
app.include_router(openapi_router, prefix="/openapi", tags=["开放接口"])

# ApiKey 管理路由
app.include_router(api_keys_router, prefix="/api/v1")

# AI 配置管理路由
app.include_router(ai_config_router)

# AI Skill 配置管理路由
app.include_router(ai_skills_router)

# AI Skill Generator 路由
app.include_router(ai_skill_generator_router)

# 聊天机器人路由（通用接口，支持飞书/钉钉/企业微信等）
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "CRM API is running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
