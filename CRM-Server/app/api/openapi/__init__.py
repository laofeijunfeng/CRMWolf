"""
开放接口路由模块
"""
from fastapi import APIRouter

from app.api.openapi.leads import router as leads_router
from app.api.openapi.customers import router as customers_router
from app.api.openapi.opportunities import router as opportunities_router
from app.api.openapi.contracts import router as contracts_router
from app.api.openapi.payments import router as payments_router
from app.api.openapi.invoices import router as invoices_router

openapi_router = APIRouter(prefix="/v1")

# 注册各模块路由
openapi_router.include_router(leads_router, prefix="/leads", tags=["线索开放接口"])
openapi_router.include_router(customers_router, prefix="/customers", tags=["客户开放接口"])
openapi_router.include_router(opportunities_router, prefix="/opportunities", tags=["商机开放接口"])
openapi_router.include_router(contracts_router, prefix="/contracts", tags=["合同开放接口"])
openapi_router.include_router(payments_router, prefix="/payments", tags=["回款开放接口"])
openapi_router.include_router(invoices_router, prefix="/invoices", tags=["发票开放接口"])