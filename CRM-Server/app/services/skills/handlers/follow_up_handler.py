"""
跟进 Handler

处理添加跟进记录类型的 Action（如 LeadSkill.follow_up）

注意：默认过滤已转化/无效的父实体，避免重复跟进
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class FollowUpHandler(BaseHandler):
    """跟进 Handler"""

    handler_type = "FollowUpHandler"

    # 默认排除的状态（已转化、无效的实体不应再跟进）
    DEFAULT_EXCLUDE_STATUS = ["CONVERTED", "INVALID"]

    async def execute(
        self,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行跟进记录添加

        handler_config 结构:
        {
            "crud_mapping": "lead_follow_up",
            "parent_crud_mapping": "lead",
            "parent_lookup_field": "lead_name",
            "parent_name_field": "lead_name",
            "exclude_status": ["CONVERTED", "INVALID"],  // 可选，默认过滤已转化/无效
            "enum_mappings": {"method": "follow_up_method"},
            "update_parent_status": {"from_status": "NEW", "to_status": "FOLLOWING"},
            "result_template": "跟进记录添加成功..."
        }

        params 必须包含:
            - parent_lookup_field 值（如 lead_name）
            - content: 跟进内容
            - method: 跟进方式
            - next_follow_time: 下次跟进时间（可选）
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        parent_crud_mapping_name = handler_config.get("parent_crud_mapping")

        if not crud_mapping_name or not parent_crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping 或 parent_crud_mapping")

        # 从数据库获取映射配置
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud
        from app.crud.ai_enum_mapping import ai_enum_mapping_crud

        crud_mapping = ai_crud_mapping_crud.get_by_name(db, crud_mapping_name)
        parent_crud_mapping = ai_crud_mapping_crud.get_by_name(db, parent_crud_mapping_name)

        if not crud_mapping or not parent_crud_mapping:
            return self.build_result(False, "CRUD 映射不存在")

        # 获取用户信息
        user = user_crud.get_by_id(db, user_id)
        if not user:
            return self.build_result(False, "用户不存在")

        # 查找父实体
        parent_lookup_field = handler_config.get("parent_lookup_field", "name")
        parent_name_field = handler_config.get("parent_name_field", "name")
        parent_lookup_value = params.get(parent_lookup_field)

        if not parent_lookup_value:
            return self.build_result(False, f"缺少参数: {parent_lookup_field}")

        # 获取父实体 CRUD 和 Model
        parent_crud = self.get_crud_instance(
            parent_crud_mapping.crud_module,
            parent_crud_mapping.crud_instance_name
        )
        parent_model = self.get_model_class(
            f"app.models.{parent_crud_mapping_name.split('_')[0]}",
            parent_crud_mapping.model_class
        )

        # 获取排除状态配置（默认过滤已转化/无效）
        exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)

        # 获取状态枚举值
        if exclude_status_keys and parent_crud_mapping.status_field:
            parent_type = parent_crud_mapping_name.split("_")[0]
            status_enum_name = f"{parent_type}_status"
            exclude_status_values = self.get_status_enum_values(db, status_enum_name, exclude_status_keys)
        else:
            exclude_status_values = []

        # 根据名称模糊查找（过滤已转化/无效状态）
        try:
            name_field_attr, parents = self.search_active_entities(
                db,
                parent_model,
                parent_name_field,
                parent_lookup_value,
                exclude_status=exclude_status_values,
                status_field=parent_crud_mapping.status_field
            )
        except Exception as e:
            return self.build_result(False, f"查询父实体失败: {str(e)}")

        if not parents:
            return self.build_result(False, f"未找到匹配的{parent_crud_mapping_name}: {parent_lookup_value}")

        if len(parents) > 1:
            parent_names = [getattr(p, parent_name_field) for p in parents[:5]]
            return self.build_result(
                False,
                f"找到多个匹配的{parent_crud_mapping_name}，请提供更精确的名称。匹配结果: {', '.join(parent_names)}"
            )

        parent_entity = parents[0]
        parent_name = getattr(parent_entity, parent_name_field)
        parent_id = parent_entity.id

        # 处理跟进方式 enum
        method = params.get("method")
        method_enum = None

        enum_mappings = handler_config.get("enum_mappings", {})
        if "method" in enum_mappings:
            enum_name = enum_mappings["method"]
            enum_mapping = ai_enum_mapping_crud.get_by_name(db, enum_name)

            if enum_mapping:
                enum_key = enum_mapping.values.get(method)
                if enum_key:
                    enum_class = self.get_model_class(enum_mapping.enum_class)
                    method_enum = getattr(enum_class, enum_key)
                else:
                    valid_values = list(enum_mapping.values.keys())
                    return self.build_result(
                        False,
                        f"无效的跟进方式: {method}，请使用: {', '.join(valid_values)}"
                    )

        # 处理下次跟进时间
        next_follow_time = params.get("next_follow_time")
        next_follow_time_dt = self.parse_date(next_follow_time)

        # 构建跟进记录数据
        follow_up_data = {
            "content": params.get("content"),
            "method": method_enum or method,
            "next_follow_time": next_follow_time_dt
        }

        # 获取 Schema 类（使用 crud_mapping_name 推断 schema_module）
        if crud_mapping.schema_create_class:
            schema_module = f"app.schemas.{crud_mapping_name}"
            try:
                SchemaClass = self.get_schema_class(schema_module, crud_mapping.schema_create_class)
                schema_obj = SchemaClass(**follow_up_data)
            except Exception as e:
                return self.build_result(False, f"数据校验失败: {str(e)}")

        # 获取跟进 CRUD 实例
        follow_up_crud = self.get_crud_instance(
            crud_mapping.crud_module,
            crud_mapping.crud_instance_name
        )

        # 执行创建
        try:
            if crud_mapping.schema_create_class:
                follow_up = follow_up_crud.create(
                    db, schema_obj, parent_id, user.feishu_open_id
                )
            else:
                follow_up = follow_up_crud.create(
                    db, follow_up_data, parent_id, user.feishu_open_id
                )
        except Exception as e:
            return self.build_result(False, f"跟进记录添加失败: {str(e)}")

        # 更新父实体状态
        update_parent_status = handler_config.get("update_parent_status")
        if update_parent_status and parent_crud_mapping.status_field:
            from_status = update_parent_status.get("from_status")
            to_status = update_parent_status.get("to_status")

            # 检查当前状态
            current_status = getattr(parent_entity, parent_crud_mapping.status_field)
            current_status_str = current_status.value if hasattr(current_status, 'value') else str(current_status)

            if from_status and current_status_str == from_status:
                # 获取目标状态 enum
                status_enum_name = parent_crud_mapping_name + "_status"
                status_enum_mapping = ai_enum_mapping_crud.get_by_name(db, status_enum_name)

                if status_enum_mapping:
                    to_enum_key = status_enum_mapping.values.get(to_status)
                    if to_enum_key:
                        status_enum_class = self.get_model_class(status_enum_mapping.enum_class)
                        new_status = getattr(status_enum_class, to_enum_key)
                        setattr(parent_entity, parent_crud_mapping.status_field, new_status)
                        db.commit()

        # 构建结果
        result_template = handler_config.get(
            "result_template",
            "跟进记录添加成功\n{parent_type}: {parent_name}\n跟进内容: {content}\n跟进方式: {method}"
        )

        parent_type_name = parent_crud_mapping_name.replace("_follow_up", "")
        message = result_template.format(
            parent_type=parent_type_name,
            parent_name=parent_name,
            content=params.get("content"),
            method=method
        )

        if next_follow_time:
            message += f"\n下次跟进时间: {next_follow_time}"

        return self.build_result(True, message, {"follow_up": follow_up, "parent": parent_entity})