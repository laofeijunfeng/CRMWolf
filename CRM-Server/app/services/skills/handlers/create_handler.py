"""
创建 Handler

处理创建记录类型的 Action（如 LeadSkill.create, OpportunitySkill.create）

注意：
1. 唯一性检查时默认过滤已转化/无效状态的实体
2. 支持 parent_lookup，可根据父实体名称查找 ID（如根据客户名称找 customer_id）
3. 支持 name_auto_generate，当用户未提供名称时自动生成标准化名称
4. 支持从名称中提取 ID（格式：名称（ID：xxx）或 名称(ID:xxx)）

硬编码版：不再依赖数据库获取 CRUD/Enum 映射配置
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import re

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud
from app.constants.handler_configs import get_enum_value


class CreateHandler(BaseHandler):
    """创建 Handler"""

    handler_type = "CreateHandler"

    # 默认排除的状态（已转化、无效的实体不应影响新创建）
    DEFAULT_EXCLUDE_STATUS = ["CONVERTED", "INVALID"]

    # 从名称中提取 ID 的正则表达式
    ID_PATTERN = re.compile(r'[（(]\s*ID[：:]\s*(\d+)\s*[）)]')

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
        执行创建操作

        handler_config 结构:
        {
            "crud_mapping": "opportunity",
            "schema_class": "OpportunityCreate",
            "parent_lookup": {  // 可选，根据父实体名称查找 ID
                "parent_crud_mapping": "customer",
                "parent_lookup_field": "customer_name",  // 用户传入的参数名
                "parent_name_field": "account_name",     // 父实体中的名称字段
                "parent_result_field": "customer_id",    // 要填充的字段名
                "exclude_status": ["LOST", "INACTIVE"]   // 可选，过滤无效状态的父实体
            },
            "name_auto_generate": {  // 可选，自动生成名称
                "name_field": "opportunity_name",  // 名称字段
                "template": "{parent_name}-{purchase_type}-{license_type}-{user_count}人-{year}",
                "field_mappings": {  // 字段映射到模板变量
                    "parent_name": "customer_name",  // 从 parent_lookup 获取
                    "purchase_type": "purchase_type",  // 从 params 获取（enum 会转中文）
                    "license_type": "license_type",
                    "user_count": "user_count",
                    "year": "auto:year"  // 自动值：year/month/day
                }
            },
            "enum_mappings": {"purchase_type": "purchase_type", ...},
            "auto_fields": {"owner_id": "user_feishu_open_id"},
            "result_template": "商机创建成功..."
        }
        """
        crud_mapping_name = handler_config.get("crud_mapping")
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

        # 初始化 team_id（后续可能从 parent_entity 获取）
        team_id = None

        # 处理 parent_lookup（根据父实体名称查找 ID）
        parent_lookup = handler_config.get("parent_lookup")
        if parent_lookup:
            parent_crud_mapping_name = parent_lookup.get("parent_crud_mapping")
            parent_lookup_field = parent_lookup.get("parent_lookup_field", "name")
            parent_name_field = parent_lookup.get("parent_name_field", "name")
            parent_result_field = parent_lookup.get("parent_result_field", "parent_id")
            exclude_status_keys = parent_lookup.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)

            if parent_crud_mapping_name:
                parent_crud_config = self.get_crud_mapping(parent_crud_mapping_name)
                if not parent_crud_config:
                    return self.build_result(False, f"父实体 CRUD 映射不存在: {parent_crud_mapping_name}")

                # 获取用户传入的父实体名称
                parent_lookup_value = params.get(parent_lookup_field)
                if not parent_lookup_value:
                    return self.build_result(False, f"缺少参数: {parent_lookup_field}")

                # 从配置直接获取父实体 Model
                parent_model = parent_crud_config["model"]

                # 获取排除状态枚举值（硬编码版）
                if exclude_status_keys and parent_crud_config["status_field"]:
                    parent_type = parent_crud_mapping_name.split("_")[0]
                    status_enum_name = f"{parent_type}_status"
                    exclude_status_values = self.get_status_enum_values(status_enum_name, exclude_status_keys)
                else:
                    exclude_status_values = []

                parent_entity = None
                parent_id = None

                # 先尝试从名称中提取 ID
                id_match = self.ID_PATTERN.search(parent_lookup_value)
                if id_match:
                    parent_id = int(id_match.group(1))
                    parent_entity = self.get_active_entity_by_id(
                        db,
                        parent_model,
                        parent_id,
                        exclude_status=exclude_status_values,
                        status_field=parent_crud_config["status_field"]
                    )
                    if not parent_entity:
                        return self.build_result(False, f"{parent_crud_mapping_name} ID {parent_id} 不存在或已完成")
                else:
                    # 没有 ID，使用名称模糊搜索
                    try:
                        name_field_attr, parents = self.search_active_entities(
                            db,
                            parent_model,
                            parent_name_field,
                            parent_lookup_value,
                            exclude_status=exclude_status_values,
                            status_field=parent_crud_config["status_field"]
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
                    parent_id = parent_entity.id

                parent_name = getattr(parent_entity, parent_name_field)

                # 将 parent_id 填充到 params（后续会复制到 schema_data）
                params[parent_result_field] = parent_id
                params[parent_lookup_field] = parent_name  # 保存名称用于结果模板

                # 获取 team_id（从父实体）
                team_id = getattr(parent_entity, 'team_id', None)

                # 处理 inherit_fields（从父实体继承字段值）
                inherit_fields = parent_lookup.get("inherit_fields", {})
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[inherit] inherit_fields={inherit_fields}")
                for child_field, parent_field in inherit_fields.items():
                    # 检查相关的参数字段是否存在
                    # 例如：procurement_method_id 对应的参数是 procurement_method_name
                    related_param_field = child_field.replace("_id", "_name") if child_field.endswith("_id") else child_field

                    logger.info(f"[inherit] child={child_field}, parent={parent_field}, related={related_param_field}, in_params={related_param_field in params}")

                    # 只有当用户没有提供相关参数时才继承
                    if related_param_field not in params or params[related_param_field] is None:
                        parent_value = getattr(parent_entity, parent_field, None)
                        logger.info(f"[inherit] parent_value from {parent_field} = {parent_value}")
                        if parent_value is not None:
                            # 如果是枚举类型，获取枚举值
                            if hasattr(parent_value, 'value'):
                                params[child_field] = parent_value.value
                            else:
                                params[child_field] = parent_value
                            logger.info(f"[inherit] set params[{child_field}] = {params.get(child_field)}")

        # 处理 name_auto_generate（自动生成标准化名称）
        name_auto_generate = handler_config.get("name_auto_generate")
        enum_mappings = handler_config.get("enum_mappings", {})  # 获取 enum_mappings 配置

        if name_auto_generate:
            name_field = name_auto_generate.get("name_field", "name")
            template = name_auto_generate.get("template", "{parent_name}-{year}")
            field_mappings = name_auto_generate.get("field_mappings", {})
            default_values = name_auto_generate.get("default_values", {})  # 默认值配置

            # 检查用户是否已提供名称
            if not params.get(name_field):
                # 构建模板变量
                template_vars = {}
                now = datetime.now()

                for var_name, field_source in field_mappings.items():
                    if field_source.startswith("auto:"):
                        # 自动值
                        auto_type = field_source.split(":")[1]
                        if auto_type == "year":
                            template_vars[var_name] = str(now.year)
                        elif auto_type == "month":
                            template_vars[var_name] = str(now.month)
                        elif auto_type == "day":
                            template_vars[var_name] = str(now.day)
                    else:
                        # 从 params 获取
                        value = params.get(field_source)
                        if not value and default_values.get(field_source):
                            # 使用默认值
                            value = default_values.get(field_source)
                            params[field_source] = value  # 同时填充到 params，后续 enum 处理会用

                        if value:
                            # 如果该字段有 enum_mapping，尝试转换为中文显示值（硬编码版）
                            if field_source in enum_mappings:
                                enum_name = enum_mappings[field_source]
                                enum_config = self.get_enum_mapping(enum_name)
                                if enum_config:
                                    # 检查 value 是否是枚举 key（英文），找到对应的中文值
                                    for chinese_val, eng_key in enum_config.get("values", {}).items():
                                        if value == eng_key:
                                            value = chinese_val
                                            break
                                    # 如果 value 本身就是中文，保持不变

                            template_vars[var_name] = value

                # 生成名称
                try:
                    generated_name = template.format(**template_vars)
                    params[name_field] = generated_name
                except KeyError as e:
                    return self.build_result(False, f"名称自动生成失败，缺少字段: {e}")

        # 从配置直接获取 CRUD 实例
        crud_instance = crud_config["crud"]

        # 处理唯一性检查（支持状态过滤）
        unique_check = handler_config.get("unique_check")
        if unique_check:
            check_field = unique_check.get("field")
            check_value = params.get(check_field)

            if check_field and check_value:
                # 获取排除状态配置
                exclude_status_keys = unique_check.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)

                # 从配置直接获取 Model 类
                model_class = crud_config["model"]

                # 获取状态枚举值进行过滤（硬编码版）
                if exclude_status_keys and crud_config["status_field"]:
                    module_type = crud_mapping_name.split("_")[0]
                    status_enum_name = f"{module_type}_status"
                    exclude_status_values = self.get_status_enum_values(status_enum_name, exclude_status_keys)

                    # 使用带状态过滤的查询
                    status_attr = getattr(model_class, crud_config["status_field"])
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

        # 处理 enum 映射（硬编码版）
        enum_mappings = handler_config.get("enum_mappings", {})
        for param_key, enum_name in enum_mappings.items():
            if param_key in params:
                enum_config = self.get_enum_mapping(enum_name)
                if enum_config:
                    user_value = params.get(param_key)
                    enum_class = enum_config["enum_class"]
                    values = enum_config.get("values", {})

                    # 先尝试用中文值查找（标准方式）
                    enum_key = values.get(user_value)

                    # 如果找不到，尝试用英文值反向查找（兼容 AI 返回英文值的情况）
                    if not enum_key:
                        # 检查 user_value 是否直接是枚举 key（如 SUBSCRIPTION）
                        for chinese_key, eng_key in values.items():
                            if user_value == eng_key:
                                enum_key = eng_key
                                break

                    if enum_key:
                        schema_data[param_key] = getattr(enum_class, enum_key)
                    else:
                        valid_values = list(values.keys())
                        return self.build_result(
                            False,
                            f"无效的 {enum_config.get('display_name', enum_name)}: {user_value}，请使用: {', '.join(valid_values)}"
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
                schema_data[field_name] = str(user.id)
            elif source == "user_id":
                schema_data[field_name] = user_id
            elif source in params:
                schema_data[field_name] = params[source]

        # 获取 Schema 类并创建（从硬编码配置）
        schema_create = crud_config.get("schema_create")
        if schema_create:
            try:
                schema_obj = schema_create(**schema_data)
            except Exception as e:
                return self.build_result(False, f"数据校验失败: {str(e)}")

        # 执行创建
        try:
            if hasattr(crud_instance, "create"):
                # 检查 create 方法是否需要 team_id 参数
                import inspect
                create_sig = inspect.signature(crud_instance.create)
                needs_team_id = 'team_id' in create_sig.parameters

                if schema_create:
                    if needs_team_id and team_id is not None:
                        entity = crud_instance.create(db, schema_obj, str(user.id), team_id)
                    else:
                        entity = crud_instance.create(db, schema_obj, str(user.id))
                else:
                    if needs_team_id and team_id is not None:
                        entity = crud_instance.create(db, schema_data, str(user.id), team_id)
                    else:
                        entity = crud_instance.create(db, schema_data, str(user.id))
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

        # 补充 parent_lookup 相关字段（如 customer_name）
        if parent_lookup:
            parent_lookup_field = parent_lookup.get("parent_lookup_field")
            if parent_lookup_field and parent_lookup_field not in template_data:
                template_data[parent_lookup_field] = params.get(parent_lookup_field)

        message = result_template.format(**template_data)

        return self.build_result(True, message, {"entity": entity})