"""
查询详情 Handler

处理详情查询类型的 Action（如 LeadSkill.detail）

注意：
1. 默认过滤已转化/无效状态的实体，避免查询已完成业务的数据
2. 支持名称查找（用户输入名称即可查询，无需 ID）
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler


class QueryDetailHandler(BaseHandler):
    """查询详情 Handler"""

    handler_type = "QueryDetailHandler"

    # 默认排除的状态（已转化、无效的实体不应查询详情）
    DEFAULT_EXCLUDE_STATUS = ["CONVERTED", "INVALID"]

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
        执行详情查询

        handler_config 结构:
        {
            "crud_mapping": "lead",
            "display_fields": ["id", "lead_name", ...],
            "status_mapping": {"0": "新建", ...},
            "exclude_status": ["CONVERTED", "INVALID"],  // 可选，过滤已转化/无效
            "template": "【线索详情】...",
            // 名称查找配置（可选）
            "name_lookup_field": "lead_name",  // 用户输入的名称参数
            "name_field": "lead_name"          // 实体的名称字段
        }

        params 可以包含:
            - entity_id 或具体的 id 字段名（如 lead_id）
            - name_lookup_field 值（如 lead_name="广州益晟"）
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从数据库获取 CRUD 映射配置
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud
        crud_mapping = ai_crud_mapping_crud.get_by_name(db, crud_mapping_name)
        if not crud_mapping:
            return self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        # 获取 CRUD 实例
        crud_instance = self.get_crud_instance(
            crud_mapping.crud_module,
            crud_mapping.crud_instance_name
        )

        # 获取 Model 类
        model_class = self.get_model_class(
            f"app.models.{crud_mapping_name.split('_')[0]}",
            crud_mapping.model_class
        )

        # 获取排除状态配置
        exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)

        # 获取状态枚举值进行过滤
        if exclude_status_keys and crud_mapping.status_field:
            module_type = crud_mapping_name.split("_")[0]
            status_enum_name = f"{module_type}_status"
            exclude_status_values = self.get_status_enum_values(db, status_enum_name, exclude_status_keys)
        else:
            exclude_status_values = []

        # 尝试通过名称查找实体
        entity = None
        entity_id = None
        name_lookup_field = handler_config.get("name_lookup_field")
        name_field = handler_config.get("name_field", crud_mapping.name_field)

        if name_lookup_field and name_field:
            name_lookup_value = params.get(name_lookup_field)
            if name_lookup_value:
                # 根据名称模糊查找（过滤无效状态）
                try:
                    _, entities = self.search_active_entities(
                        db,
                        model_class,
                        name_field,
                        name_lookup_value,
                        exclude_status=exclude_status_values,
                        status_field=crud_mapping.status_field
                    )
                except Exception as e:
                    return self.build_result(False, f"查询失败: {str(e)}")

                if not entities:
                    module_name = crud_mapping_name.replace("_follow_up", "")
                    return self.build_result(False, f"未找到匹配的{module_name}: {name_lookup_value}")

                if len(entities) > 1:
                    # 显示更多信息帮助用户区分
                    entity_list = []
                    for e in entities[:5]:
                        entity_name = getattr(e, name_field)
                        entity_status = getattr(e, crud_mapping.status_field, None)
                        status_str = entity_status.name if hasattr(entity_status, 'name') else str(entity_status)
                        created_time = getattr(e, 'created_time', None)
                        time_str = created_time.strftime('%Y-%m-%d') if created_time else '未知'
                        entity_list.append(f"{entity_name}(ID:{e.id}, 状态:{status_str}, 创建:{time_str})")
                    return self.build_result(
                        False,
                        f"找到多个匹配的{crud_mapping_name.replace('_follow_up', '')}，请使用 ID 或更精确的名称指定。匹配结果:\n{chr(10).join(entity_list)}"
                    )

                entity = entities[0]
                entity_id = entity.id

        # 如果名称查找失败，尝试从参数获取 ID
        if not entity_id:
            for key in ["entity_id", "id", f"{crud_mapping_name}_id"]:
                if key in params:
                    entity_id = params.get(key)
                    break

        if not entity_id:
            module_prefix = crud_mapping_name.split("_")[0]
            expected_id_key = f"{module_prefix}_id"
            # 如果支持名称查找，提示用户可以提供名称
            if name_lookup_field:
                return self.build_result(False, f"缺少参数: {expected_id_key} 或 {name_lookup_field}")
            return self.build_result(False, f"缺少参数: {expected_id_key}")

        # 如果通过 ID 获取实体（名称查找已获取则跳过）
        if not entity:
            try:
                entity = self.get_active_entity_by_id(
                    db,
                    model_class,
                    entity_id,
                    exclude_status=exclude_status_values,
                    status_field=crud_mapping.status_field
                )
            except Exception as e:
                return self.build_result(False, f"查询失败: {str(e)}")

        if not entity:
            module_name = crud_mapping_name.replace("_follow_up", "")
            # 区分不存在和状态无效的情况
            raw_entity = crud_instance.get_by_id(db, entity_id)
            if raw_entity:
                return self.build_result(False, f"{module_name} ID {entity_id} 已完成或无效，无法查看详情")
            else:
                return self.build_result(False, f"{module_name} ID {entity_id} 不存在")

        # 构建输出
        status_mapping = handler_config.get("status_mapping", {})
        display_fields = handler_config.get("display_fields", [])

        field_values = {}
        for field in display_fields:
            value = getattr(entity, field, None)

            # 应用状态映射
            if field == "status" or field == crud_mapping.status_field:
                if status_mapping:
                    str_value = str(value.value) if hasattr(value, 'value') else str(value)
                    field_values[f"{field}_text"] = status_mapping.get(str_value, str(value))
                    field_values[field] = str_value
                else:
                    field_values[field] = str(value) if value else "未设置"

            # 格式化日期
            elif isinstance(value, datetime):
                field_values[field] = self.format_datetime(value)
            else:
                field_values[field] = str(value) if value else "未设置"

        # 应用模板
        template = handler_config.get("template", "")
        if template:
            # 处理模板中的特殊字段
            for key, value in field_values.items():
                if f"{key}_text" in field_values:
                    continue
                template = template.replace(f"{{{key}}}", value)

            # 处理 status_text
            if "status_text" in template and "status_text" in field_values:
                template = template.replace("{status_text}", field_values["status_text"])
            elif "status_text" in template:
                template = template.replace("{status_text}", field_values.get("status", "未知"))

        else:
            # 默认模板
            module_name = crud_mapping_name.replace("_follow_up", "")
            template = f"【{module_name}详情】\n"
            for field in display_fields:
                template += f"{field}: {field_values.get(field, '未知')}\n"

        return self.build_result(True, template.strip(), {"entity": entity})