"""
Handler 工厂

根据 handler_type 创建对应的 Handler 实例
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.services.skills.handlers.base_handler import BaseHandler
from app.services.skills.handlers.query_list_handler import QueryListHandler
from app.services.skills.handlers.query_detail_handler import QueryDetailHandler
from app.services.skills.handlers.create_handler import CreateHandler
from app.services.skills.handlers.follow_up_handler import FollowUpHandler
from app.services.skills.handlers.status_change_handler import StatusChangeHandler
from app.services.skills.handlers.lead_convert_handler import LeadConvertHandler
from app.services.skills.handlers.aggregate_handler import AggregateHandler


class HandlerFactory:
    """Handler 工厂"""

    # Handler 类型映射
    HANDLER_MAP = {
        "QueryListHandler": QueryListHandler,
        "QueryDetailHandler": QueryDetailHandler,
        "CreateHandler": CreateHandler,
        "FollowUpHandler": FollowUpHandler,
        "StatusChangeHandler": StatusChangeHandler,
        "LeadConvertHandler": LeadConvertHandler,
        "AggregateHandler": AggregateHandler,
    }

    @classmethod
    def get_handler(cls, handler_type: str) -> Optional[BaseHandler]:
        """
        根据类型获取 Handler 实例

        Args:
            handler_type: Handler 类型名称

        Returns:
            Handler 实例
        """
        handler_class = cls.HANDLER_MAP.get(handler_type)
        if handler_class:
            return handler_class()
        return None

    @classmethod
    def register_handler(cls, handler_type: str, handler_class: type) -> None:
        """
        注册新的 Handler 类型

        Args:
            handler_type: Handler 类型名称
            handler_class: Handler 类
        """
        cls.HANDLER_MAP[handler_type] = handler_class

    @classmethod
    async def execute_handler(
        cls,
        handler_type: str,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行指定类型的 Handler

        Args:
            handler_type: Handler 类型
            db: 数据库 Session
            handler_config: Handler 配置
            params: 用户参数
            user_id: 用户 ID
            user_feishu_open_id: 用户飞书 Open ID

        Returns:
            执行结果
        """
        handler = cls.get_handler(handler_type)
        if not handler:
            return {
                "success": False,
                "message": f"不支持的 Handler 类型: {handler_type}",
                "data": None
            }

        return await handler.execute(
            db, handler_config, params, user_id, user_feishu_open_id
        )

    @classmethod
    def get_supported_handlers(cls) -> list:
        """获取支持的 Handler 类型列表"""
        return list(cls.HANDLER_MAP.keys())