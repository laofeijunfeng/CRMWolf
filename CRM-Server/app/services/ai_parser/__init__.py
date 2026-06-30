"""
AI 实体解析服务

提供统一的 AI 解析架构，支持线索、客户、商机、合同等实体
"""
from app.services.ai_parser.base_parser import EntityAIParserBase
from app.services.ai_parser.factory import EntityAIParserFactory
from app.services.ai_parser.lead_parser import LeadAIParser
from app.services.ai_parser.customer_parser import CustomerAIParser

__all__ = [
    "EntityAIParserBase",
    "EntityAIParserFactory",
    "LeadAIParser",
    "CustomerAIParser",
]