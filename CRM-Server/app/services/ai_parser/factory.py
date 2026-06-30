"""
AI 实体解析工厂

根据实体类型返回对应的 Parser 实例，提供统一调用接口
"""
from typing import Optional

from app.services.ai_parser.base_parser import EntityAIParserBase
from app.services.ai_parser.lead_parser import LeadAIParser
from app.services.ai_parser.customer_parser import CustomerAIParser


class EntityAIParserFactory:
    """实体 AI 解析工厂"""

    # Parser 类型映射
    PARSER_MAP = {
        "lead": LeadAIParser,
        "customer": CustomerAIParser,
        # 未来扩展：
        # "opportunity": OpportunityAIParser,
        # "contract": ContractAIParser,
    }

    @classmethod
    def get_parser(cls, entity_type: str) -> Optional[EntityAIParserBase]:
        """
        根据实体类型获取 Parser 实例

        Args:
            entity_type: 实体类型（lead, customer, opportunity, contract）

        Returns:
            Parser 实例
        """
        parser_class = cls.PARSER_MAP.get(entity_type)
        if parser_class:
            return parser_class()
        return None

    @classmethod
    def register_parser(cls, entity_type: str, parser_class: type) -> None:
        """
        注册新的 Parser 类型

        Args:
            entity_type: 实体类型
            parser_class: Parser 类
        """
        cls.PARSER_MAP[entity_type] = parser_class

    @classmethod
    def get_supported_entity_types(cls) -> list:
        """获取支持的实体类型列表"""
        return list(cls.PARSER_MAP.keys())