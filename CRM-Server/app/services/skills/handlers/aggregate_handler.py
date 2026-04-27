"""
统计汇总 Handler

处理统计汇总类型的 Action（如 PaymentSkill.summary）
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class AggregateHandler(BaseHandler):
    """统计汇总 Handler"""

    handler_type = "AggregateHandler"

    async def execute(
        self,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
       执行统计汇总操作

        handler_config 结构:
        {
            "crud_mapping": "payment_record",
            "parent_crud_mapping": "contract",
            "aggregate_fields": ["total_amount", "paid_amount", ...],
            "template": "【回款汇总】..."
        }

        params 必须包含:
            - parent_id 或具体的 id 字段名（如 contract_id）
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        parent_crud_mapping_name = handler_config.get("parent_crud_mapping")

        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从数据库获取映射配置
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud

        crud_mapping = ai_crud_mapping_crud.get_by_name(db, crud_mapping_name)
        if not crud_mapping:
            return self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        # 获取用户信息
        user = user_crud.get_by_id(db, user_id)
        if not user:
            return self.build_result(False, "用户不存在")

        # 从参数获取父实体 ID
        parent_id = None
        for key in ["parent_id", "id", f"{parent_crud_mapping_name}_id" if parent_crud_mapping_name else None]:
            if key and key in params:
                parent_id = params.get(key)
                break

        if not parent_id:
            if parent_crud_mapping_name:
                expected_key = f"{parent_crud_mapping_name}_id"
            else:
                expected_key = "id"
            return self.build_result(False, f"缺少参数: {expected_key}")

        # 获取 Model 类
        model_class = self.get_model_class(
            f"app.models.{crud_mapping_name.split('_')[0]}",
            crud_mapping.model_class
        )

        # 执行聚合查询
        try:
            # 构建查询
            query = db.query(
                func.sum(model_class.amount).label("total_amount")
            )

            # 添加父实体过滤
            if parent_crud_mapping_name:
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

        # 如果有父实体，查询父实体信息
        parent_info = {}
        if parent_crud_mapping_name:
            parent_crud_mapping = ai_crud_mapping_crud.get_by_name(db, parent_crud_mapping_name)
            if parent_crud_mapping:
                parent_crud = self.get_crud_instance(
                    parent_crud_mapping.crud_module,
                    parent_crud_mapping.crud_instance_name
                )
                parent_entity = parent_crud.get_by_id(db, parent_id)
                if parent_entity:
                    parent_info["name"] = getattr(parent_entity, parent_crud_mapping.name_field or "name", "")
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