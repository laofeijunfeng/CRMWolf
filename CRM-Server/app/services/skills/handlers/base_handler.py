"""
Handler 基类

所有 Handler 继承此基类，提供统一接口

硬编码版：不再依赖数据库获取 CRUD/Enum 映射配置
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from abc import ABC, abstractmethod
from datetime import datetime

from app.constants.handler_configs import (
    CRUD_MAPPINGS,
    ENUM_MAPPINGS,
    get_crud_config,
    get_enum_config,
    get_status_enum_values,
    get_status_display_name,
)


class BaseHandler(ABC):
    """Handler 基类"""

    handler_type: str = "BaseHandler"

    @abstractmethod
    async def execute(
        self,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行 Handler 操作

        Args:
            db: 数据库 Session
            handler_config: Handler 配置 JSON
            params: 用户传入参数
            user_id: 用户 ID
            user_feishu_open_id: 用户飞书 Open ID
            team_id: 团队 ID

        Returns:
            {"success": bool, "message": str, "data": dict}
        """
        pass

    def format_datetime(self, dt: Optional[datetime]) -> str:
        """格式化日期时间"""
        if not dt:
            return "未知"
        return dt.strftime("%Y-%m-%d %H:%M")

    def format_date(self, dt: Optional[datetime]) -> str:
        """格式化日期"""
        if not dt:
            return "未知"
        return dt.strftime("%Y-%m-%d")

    def parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """解析日期字符串"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

    def get_crud_mapping(self, mapping_name: str) -> Optional[Dict[str, Any]]:
        """
        从硬编码配置获取 CRUD 映射

        Args:
            mapping_name: 映射名称（如 "lead", "lead_follow_up"）

        Returns:
            CRUD 映射配置字典，包含 crud、model、schema_create 等
        """
        return CRUD_MAPPINGS.get(mapping_name)

    def get_enum_mapping(self, enum_name: str) -> Optional[Dict[str, Any]]:
        """
        从硬编码配置获取枚举映射

        Args:
            enum_name: 枚举名称（如 "lead_status", "follow_up_method"）

        Returns:
            枚举映射配置字典，包含 enum_class、values 等
        """
        return ENUM_MAPPINGS.get(enum_name)

    def get_crud_instance(self, crud_module: str, crud_instance_name: str) -> Any:
        """
        动态获取 CRUD 实例

        Args:
            crud_module: CRUD 模块路径（如 app.crud.lead）
            crud_instance_name: CRUD 实例名（如 lead_crud）

        Returns:
            CRUD 实例对象
        """
        import importlib

        module = importlib.import_module(crud_module)
        crud_instance = getattr(module, crud_instance_name)
        return crud_instance

    def get_model_class(self, model_module: str, model_class_name: Optional[str] = None) -> Any:
        """
        动态获取 Model 类

        Args:
            model_module: 模块路径（如 app.models.lead）或完整路径（如 app.models.lead:Lead）
            model_class_name: 类名（可选，如果 model_module 包含冒号则不需要）

        Returns:
            Model 类对象
        """
        import importlib

        # 处理完整路径格式（如 app.models.lead:Lead）
        if ":" in model_module:
            module_path, class_name = model_module.split(":")
            module = importlib.import_module(module_path)
            return getattr(module, class_name)

        # 如果只传了一个参数且没有冒号，尝试从路径中提取类名
        if model_class_name is None:
            parts = model_module.split(".")
            class_name = parts[-1]
            module_path = ".".join(parts[:-1])
            module = importlib.import_module(module_path)
            return getattr(module, class_name)

        # 双参数模式
        module = importlib.import_module(model_module)
        return getattr(module, model_class_name)

    def get_schema_class(self, schema_module: str, schema_class_name: str) -> Any:
        """动态获取 Schema 类"""
        import importlib

        module = importlib.import_module(schema_module)
        return getattr(module, schema_class_name)

    def convert_enum_value(
        self,
        enum_mapping: Dict[str, str],
        user_value: str,
        enum_class: Any
    ) -> Any:
        """
        将用户输入值转换为 Enum 成员

        Args:
            enum_mapping: 值映射 {"电话": "PHONE"}
            user_value: 用户输入值（如 "电话"）
            enum_class: Enum 类

        Returns:
            Enum 成员
        """
        enum_key = enum_mapping.get(user_value)
        if not enum_key:
            return None
        return getattr(enum_class, enum_key)

    def build_result(self, success: bool, message: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """构建执行结果"""
        return {
            "success": success,
            "message": message,
            "data": data
        }

    def search_active_entities(
        self,
        db: Session,
        model_class: Any,
        name_field: str,
        search_value: str,
        exclude_status: Optional[List[str]] = None,
        status_field: Optional[str] = None
    ) -> tuple[Any, List[Any]]:
        """
        搜索有效状态的实体（过滤已转化/无效等状态）

        Args:
            db: 数据库 Session
            model_class: Model 类
            name_field: 名称字段名
            search_value: 搜索值
            exclude_status: 需排除的状态值列表（如 ["CONVERTED", "INVALID"]）
            status_field: 状态字段名

        Returns:
            (name_field_attr, matching_entities)
        """
        name_field_attr = getattr(model_class, name_field)
        query = db.query(model_class).filter(
            name_field_attr.like(f"%{search_value}%")
        )

        if exclude_status and status_field:
            status_attr = getattr(model_class, status_field)
            query = query.filter(status_attr.notin_(exclude_status))

        return name_field_attr, query.all()

    def get_active_entity_by_id(
        self,
        db: Session,
        model_class: Any,
        entity_id: int,
        exclude_status: Optional[List[str]] = None,
        status_field: Optional[str] = None
    ) -> Optional[Any]:
        """
        根据 ID 获取有效状态的实体

        Args:
            db: 数据库 Session
            model_class: Model 类
            entity_id: 实体 ID
            exclude_status: 需排除的状态值列表
            status_field: 状态字段名

        Returns:
            实体对象或 None
        """
        query = db.query(model_class).filter(model_class.id == entity_id)

        if exclude_status and status_field:
            status_attr = getattr(model_class, status_field)
            query = query.filter(status_attr.notin_(exclude_status))

        return query.first()

    def get_status_enum_values(
        self,
        enum_mapping_name: str,
        status_keys: List[str]
    ) -> List[Any]:
        """
        获取状态枚举值列表（硬编码版）

        Args:
            enum_mapping_name: Enum 映射名称（如 "lead_status"）
            status_keys: 状态键列表（如 ["NEW", "FOLLOWING"]）

        Returns:
            Enum 值列表（返回 .value 属性，兼容数据库 INTEGER 类型）
        """
        enum_config = self.get_enum_mapping(enum_mapping_name)
        if not enum_config:
            return []

        enum_class = enum_config.get("enum_class")
        return get_status_enum_values(enum_class, status_keys)

    def _get_status_display_name(
        self,
        entity_type: str,
        status_value: Any
    ) -> str:
        """
        获取状态的中文显示名称（硬编码版）

        Args:
            entity_type: 实体类型（如 lead, customer, opportunity）
            status_value: 状态值（整数）

        Returns:
            状态的中文显示名称
        """
        enum_mapping_name = f"{entity_type}_status"
        enum_config = self.get_enum_mapping(enum_mapping_name)

        if not enum_config:
            return str(status_value)

        return get_status_display_name(enum_config, status_value)