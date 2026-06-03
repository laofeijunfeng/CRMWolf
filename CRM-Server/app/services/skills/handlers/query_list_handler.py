"""
查询列表 Handler

处理列表查询类型的 Action（如 LeadSkill.list）
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class QueryListHandler(BaseHandler):
    """查询列表 Handler"""

    handler_type = "QueryListHandler"

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
        执行列表查询

        handler_config 结构:
        {
            "crud_mapping": "lead",
            "owner_filter": true,
            "status_exclude": ["CONVERTED"],
            "display_fields": ["id", "lead_name", ...],
            "status_mapping": {"0": "新建", ...},
            "template": "共有 {total} 条线索..."
        }
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从数据库获取 CRUD 映射配置
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud
        crud_mapping = ai_crud_mapping_crud.get_by_name(db, crud_mapping_name)
        if not crud_mapping:
            return self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        # 获取用户信息
        user = user_crud.get_by_id(db, user_id)
        if not user:
            return self.build_result(False, "用户不存在")

        # 获取 CRUD 实例
        crud_instance = self.get_crud_instance(
            crud_mapping.crud_module,
            crud_mapping.crud_instance_name
        )

        # 构建查询参数
        query_params = {
            "skip": 0,
            "limit": 10
        }

        # 应用 owner 过滤
        if handler_config.get("owner_filter"):
            query_params["owner_id"] = str(user.id)

        # 应用状态排除
        if handler_config.get("status_exclude"):
            from app.models.ai_skill import AIEnumMapping
            from app.crud.ai_enum_mapping import ai_enum_mapping_crud

            # 获取 status enum 映射
            enum_name = crud_mapping_name.replace("_follow_up", "") + "_status"
            status_enum_mapping = ai_enum_mapping_crud.get_by_name(db, enum_name)

            if status_enum_mapping:
                model_class = self.get_model_class(crud_mapping.model_class.split(":")[0] if ":" in crud_mapping.model_class else f"app.models.{crud_mapping_name.split('_')[0]}", crud_mapping.model_class.split(":")[-1] if ":" in crud_mapping.model_class else crud_mapping.model_class)
                status_field = getattr(model_class, crud_mapping.status_field or "status", None)

                exclude_values = []
                for exclude_key in handler_config["status_exclude"]:
                    enum_key = status_enum_mapping.values.get(exclude_key)
                    if enum_key:
                        enum_class = self.get_model_class(status_enum_mapping.enum_class)
                        exclude_values.append(getattr(enum_class, enum_key))

                if exclude_values and status_field:
                    query_params["status__ne__in"] = exclude_values

        # 执行查询
        try:
            results, total = crud_instance.get_multi(db, **query_params)
        except Exception as e:
            return self.build_result(False, f"查询失败: {str(e)}")

        if not results:
            empty_msg = handler_config.get("empty_message", "当前没有数据")
            return self.build_result(True, empty_msg)

        # 构建输出
        status_mapping = handler_config.get("status_mapping", {})
        display_fields = handler_config.get("display_fields", [])

        items_text = []
        for i, item in enumerate(results, 1):
            field_values = []
            for field in display_fields:
                value = getattr(item, field, None)

                # 应用状态映射
                if field == "status" or field == crud_mapping.status_field:
                    if status_mapping:
                        str_value = str(value.value) if hasattr(value, 'value') else str(value)
                        value = status_mapping.get(str_value, str(value))

                # 格式化日期
                if isinstance(value, datetime):
                    value = self.format_datetime(value)

                field_values.append(str(value) if value else "-")

            # 根据 display_fields 构建 item 行
            if len(display_fields) >= 4:
                item_line = f"{i}. {field_values[1]}（{field_values[2] or '未知'}，{field_values[3] or '无'}）- 状态：{field_values[-1] if 'status' in display_fields else field_values[-2]}"
            else:
                item_line = f"{i}. {' '.join(field_values)}"

            items_text.append(item_line)

        # 应用模板
        template = handler_config.get("template", "共有 {total} 条数据：\n{items}")
        message = template.format(
            total=total,
            items="\n".join(items_text)
        )

        return self.build_result(True, message, {"total": total, "items": results})