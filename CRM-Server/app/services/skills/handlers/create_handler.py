"""
创建 Handler

处理创建记录类型的 Action（如 LeadSkill.create）

注意：唯一性检查时默认过滤已转化/无效状态的实体
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class CreateHandler(BaseHandler):
    """创建 Handler"""

    handler_type = "CreateHandler"

    # 默认排除的状态（已转化、无效的实体不应影响新创建）
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
        执行创建操作

        handler_config 结构:
        {
            "crud_mapping": "lead",
            "schema_class": "LeadCreate",
            "enum_mappings": {"source": "lead_source", ...},
            "unique_check": {
                "field": "contact_phone",
                "message": "电话已存在",
                "exclude_status": ["CONVERTED", "INVALID"]  // 可选，过滤已转化/无效
            },
            "auto_fields": {"owner_id": "user_feishu_open_id"},
            "result_template": "线索创建成功..."
        }
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从数据库获取 CRUD 映射配置
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud
        from app.crud.ai_enum_mapping import ai_enum_mapping_crud

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

        # 处理唯一性检查（支持状态过滤）
        unique_check = handler_config.get("unique_check")
        if unique_check:
            check_field = unique_check.get("field")
            check_value = params.get(check_field)

            if check_field and check_value:
                # 获取排除状态配置
                exclude_status_keys = unique_check.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)

                # 获取 Model 类和状态字段
                model_class = self.get_model_class(
                    f"app.models.{crud_mapping_name.split('_')[0]}",
                    crud_mapping.model_class
                )

                # 获取状态枚举值进行过滤
                if exclude_status_keys and crud_mapping.status_field:
                    module_type = crud_mapping_name.split("_")[0]
                    status_enum_name = f"{module_type}_status"
                    exclude_status_values = self.get_status_enum_values(db, status_enum_name, exclude_status_keys)

                    # 使用带状态过滤的查询
                    status_attr = getattr(model_class, crud_mapping.status_field)
                    check_field_attr = getattr(model_class, check_field)
                    existing = db.query(model_class).filter(
                        check_field_attr == check_value,
                        status_attr.notin_(exclude_status_values)
                    ).first()
                else:
                    # 使用 CRUD 方法的旧逻辑（无状态过滤）
                    check_method = f"get_by_{check_field}"
                    if hasattr(crud_instance, check_method):
                        existing = getattr(crud_instance, check_method)(db, check_value)
                    else:
                        existing = None

                if existing:
                    error_msg = unique_check.get("message", f"{check_field} 已存在")
                    return self.build_result(False, f"{error_msg}: {check_value}")

        # 构建 Schema 数据
        schema_data = {}

        # 处理 enum 映射
        enum_mappings = handler_config.get("enum_mappings", {})
        for param_key, enum_name in enum_mappings.items():
            if param_key in params:
                enum_mapping = ai_enum_mapping_crud.get_by_name(db, enum_name)
                if enum_mapping:
                    user_value = params.get(param_key)
                    enum_key = enum_mapping.values.get(user_value)

                    if enum_key:
                        # 获取 Enum 类
                        enum_class = self.get_model_class(enum_mapping.enum_class)
                        schema_data[param_key] = getattr(enum_class, enum_key)
                    else:
                        valid_values = list(enum_mapping.values.keys())
                        return self.build_result(
                            False,
                            f"无效的 {enum_mapping.display_name}: {user_value}，请使用: {', '.join(valid_values)}"
                        )

        # 处理普通字段
        for key, value in params.items():
            if key not in enum_mappings:
                # 处理日期字段
                if "date" in key or "time" in key:
                    value = self.parse_date(value)
                schema_data[key] = value

        # 处理自动字段
        auto_fields = handler_config.get("auto_fields", {})
        for field_name, source in auto_fields.items():
            if source == "user_feishu_open_id":
                schema_data[field_name] = user.feishu_open_id
            elif source == "user_id":
                schema_data[field_name] = user_id
            elif source in params:
                schema_data[field_name] = params[source]

        # 获取 Schema 类并创建
        if crud_mapping.schema_create_class:
            schema_module = f"app.schemas.{crud_mapping_name.split('_')[0]}"
            try:
                SchemaClass = self.get_schema_class(schema_module, crud_mapping.schema_create_class)
                schema_obj = SchemaClass(**schema_data)
            except Exception as e:
                return self.build_result(False, f"数据校验失败: {str(e)}")

        # 执行创建
        try:
            if hasattr(crud_instance, "create"):
                if crud_mapping.schema_create_class:
                    entity = crud_instance.create(db, schema_obj, user.feishu_open_id)
                else:
                    entity = crud_instance.create(db, schema_data, user.feishu_open_id)
            else:
                return self.build_result(False, "CRUD 实例不支持 create 方法")
        except Exception as e:
            return self.build_result(False, f"创建失败: {str(e)}")

        # 构建结果
        result_template = handler_config.get("result_template", "创建成功，ID: {id}")

        # 获取字段值用于模板
        template_data = {"id": entity.id}
        for field in ["name", "lead_name", "account_name", "opportunity_name", "contract_name"]:
            if hasattr(entity, field):
                template_data["name"] = getattr(entity, field)
                template_data[field] = getattr(entity, field)

        for key, value in schema_data.items():
            if hasattr(entity, key):
                attr_value = getattr(entity, key)
                if hasattr(attr_value, 'value'):
                    template_data[key] = attr_value.value
                else:
                    template_data[key] = attr_value

        message = result_template.format(**template_data)

        return self.build_result(True, message, {"entity": entity})