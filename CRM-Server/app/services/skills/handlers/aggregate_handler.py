"""
统计汇总 Handler

处理统计汇总类型的 Action（如 PaymentSkill.summary）

注意：
1. 支持名称查找（用户输入名称即可查询，无需 ID）
2. 自动关联父实体信息用于结果展示

硬编码版：不再依赖数据库获取 CRUD/Enum 映射配置
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class AggregateHandler(BaseHandler):
    """统计汇总 Handler"""

    handler_type = "AggregateHandler"

    # 默认排除的状态（已完成状态的实体不应再统计）
    DEFAULT_EXCLUDE_STATUS = []

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
        执行统计汇总操作

        handler_config 结构:
        {
            "crud_mapping": "payment_record",
            "parent_crud_mapping": "contract",
            "aggregate_fields": ["total_amount", "paid_amount", ...],
            "template": "【回款汇总】...",
            // 名称查找配置（可选）
            "name_lookup_field": "contract_name",  // 用户输入的名称参数
            "name_field": "contract_name"          // 父实体的名称字段
        }

        params 可以包含:
            - parent_id 或具体的 id 字段名（如 contract_id）
            - name_lookup_field 值（如 contract_name="某合同"）
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        parent_crud_mapping_name = handler_config.get("parent_crud_mapping")

        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从硬编码配置获取 CRUD 映射配置
        crud_config = self.get_crud_mapping(crud_mapping_name)
        if not crud_config:
            return self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        # 获取用户信息
        user = user_crud.get_by_id(db, user_id)
        if not user:
            return self.build_result(False, "用户不存在")

        # 获取父实体配置
        if not parent_crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 parent_crud_mapping")

        parent_crud_config = self.get_crud_mapping(parent_crud_mapping_name)
        if not parent_crud_config:
            return self.build_result(False, f"父实体 CRUD 映射不存在: {parent_crud_mapping_name}")

        # 尝试通过名称查找父实体
        parent_entity = None
        parent_id = None
        name_lookup_field = handler_config.get("name_lookup_field")
        name_field = handler_config.get("name_field", parent_crud_config.get("name_field"))

        if name_lookup_field and name_field:
            name_lookup_value = params.get(name_lookup_field)
            if name_lookup_value:
                # 从配置直接获取父实体 Model
                parent_model = parent_crud_config["model"]

                # 获取排除状态配置（硬编码版）
                exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)
                exclude_status_values = []
                if exclude_status_keys and parent_crud_config["status_field"]:
                    parent_type = parent_crud_mapping_name.split("_")[0]
                    status_enum_name = f"{parent_type}_status"
                    exclude_status_values = self.get_status_enum_values(status_enum_name, exclude_status_keys)

                # 搜索父实体
                try:
                    _, entities = self.search_active_entities(
                        db,
                        parent_model,
                        name_field,
                        name_lookup_value,
                        exclude_status=exclude_status_values,
                        status_field=parent_crud_config["status_field"]
                    )
                except Exception as e:
                    return self.build_result(False, f"查询父实体失败: {str(e)}")

                if not entities:
                    return self.build_result(False, f"未找到匹配的{parent_crud_mapping_name}: {name_lookup_value}")

                if len(entities) > 1:
                    entity_names = [getattr(e, name_field) for e in entities[:5]]
                    return self.build_result(
                        False,
                        f"找到多个匹配的{parent_crud_mapping_name}，请提供更精确的名称或 ID。匹配结果: {', '.join(entity_names)}"
                    )

                parent_entity = entities[0]
                parent_id = parent_entity.id

        # 如果名称查找失败，尝试从参数获取 ID
        if not parent_id:
            for key in ["parent_id", "id", f"{parent_crud_mapping_name}_id"]:
                if key in params:
                    parent_id = params.get(key)
                    break

        if not parent_id:
            expected_key = f"{parent_crud_mapping_name}_id"
            # 如果支持名称查找，提示用户可以提供名称
            if name_lookup_field:
                return self.build_result(False, f"缺少参数: {expected_key} 或 {name_lookup_field}")
            return self.build_result(False, f"缺少参数: {expected_key}")

        # 如果通过 ID 获取父实体（名称查找已获取则跳过）
        if not parent_entity:
            parent_crud = parent_crud_config["crud"]
            parent_entity = parent_crud.get_by_id(db, parent_id)

            if not parent_entity:
                return self.build_result(False, f"{parent_crud_mapping_name} ID {parent_id} 不存在")

        # 从配置直接获取 Model 类
        model_class = crud_config["model"]

        # 执行聚合查询
        try:
            # 构建查询
            query = db.query(
                func.sum(model_class.amount).label("total_amount")
            )

            # 添加父实体过滤
            parent_field_name = parent_crud_mapping_name.split("_")[0] + "_id"
            if hasattr(model_class, parent_field_name):
                query = query.filter(
                    getattr(model_class, parent_field_name) == parent_id
                )

            result = query.first()

        except Exception as e:
            return self.build_result(False, f"统计查询失败: {str(e)}")

        # 构建结果数据
        aggregate_data = {
            "total_amount": result.total_amount or 0
        }

        # 构建父实体信息
        parent_info = {}
        parent_info["name"] = getattr(parent_entity, parent_crud_config.get("name_field") or "name", "")
        if hasattr(parent_entity, "contract_amount"):
            aggregate_data["contract_amount"] = parent_entity.contract_amount
            aggregate_data["remaining_amount"] = parent_entity.contract_amount - aggregate_data["total_amount"]

        # 构建输出
        result_template = handler_config.get(
            "result_template",
            "【统计汇总】\nID: {id}\n总计: {total_amount}"
        )

        template_data = {
            "id": parent_id,
            "total_amount": aggregate_data.get("total_amount", 0),
            "paid_amount": aggregate_data.get("total_amount", 0),
            "remaining_amount": aggregate_data.get("remaining_amount", 0),
            **parent_info
        }

        message = result_template.format(**template_data)

        return self.build_result(True, message, {"aggregate": aggregate_data, "parent": parent_info})