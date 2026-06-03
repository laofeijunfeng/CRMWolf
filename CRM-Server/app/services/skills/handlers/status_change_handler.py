"""
状态变更 Handler

处理状态变更类型的 Action（如 OpportunitySkill.win, LeadSkill.convert）

注意：
1. 默认过滤已转化/无效状态的实体，避免重复变更
2. 支持前置状态校验，确保状态变更符合业务流程
3. 支持名称查找实体（类似于 FollowUpHandler）
4. 支持从名称中提取 ID（格式：名称（ID：xxx）或 名称(ID:xxx)）
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import re

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud


class StatusChangeHandler(BaseHandler):
    """状态变更 Handler"""

    handler_type = "StatusChangeHandler"

    # 默认排除的状态（已转化、无效的实体不应再变更状态）
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
        执行状态变更操作

        handler_config 结构:
        {
            "crud_mapping": "opportunity",
            "status_field": "status",
            "target_status": "WON",
            "exclude_status": ["CONVERTED", "INVALID"],  // 可选，过滤已转化/无效
            "pre_check_status": ["NEW", "FOLLOWING"],  // 可选，前置状态校验
            "update_fields": ["actual_amount", "actual_closing_date"],
            "result_template": "商机赢单成功...",
            // 名称查找配置（可选）
            "name_lookup_field": "lead_name",  // 用户输入的名称参数
            "name_field": "lead_name"  // 实体的名称字段
        }

        params 可以包含:
            - entity_id 或具体的 id 字段名（如 opportunity_id）
            - name_lookup_field 值（如 lead_name="广州益晟"）
            - update_fields 中定义的字段值
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从数据库获取映射配置
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

        # 获取 Model 类
        model_class = self.get_model_class(
            f"app.models.{crud_mapping_name.split('_')[0]}",
            crud_mapping.model_class
        )

        # 获取排除状态配置
        exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)
        pre_check_status_keys = handler_config.get("pre_check_status", [])

        # 获取状态枚举值
        module_type = crud_mapping_name.split("_")[0]
        status_enum_name = f"{module_type}_status"
        exclude_status_values = self.get_status_enum_values(db, status_enum_name, exclude_status_keys) if exclude_status_keys else []
        pre_check_status_values = self.get_status_enum_values(db, status_enum_name, pre_check_status_keys) if pre_check_status_keys else []

        # 尝试获取实体
        entity = None
        entity_id = None
        name_lookup_field = handler_config.get("name_lookup_field")
        name_field = handler_config.get("name_field", crud_mapping.name_field)
        # 提前定义 status_field，用于多条匹配时的状态显示
        status_field = handler_config.get("status_field", crud_mapping.status_field)

        # === 第一步：优先使用 AI 提取的 ID 参数 ===
        module_prefix = crud_mapping_name.split("_")[0]
        expected_id_key = f"{module_prefix}_id"
        if expected_id_key in params:
            entity_id = params.get(expected_id_key)
            with open('/Users/eddie/Code/CRMWolf/CRM-Server/skill_debug.log', 'a') as f:
                f.write(f"=== 从 params 获取 ID ===\n")
                f.write(f"expected_id_key: {expected_id_key}\n")
                f.write(f"entity_id: {entity_id}\n")
            # 立刻通过 ID 获取实体
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
                return self.build_result(False, f"{crud_mapping_name} ID {entity_id} 不存在或已完成")

        # === 第二步：尝试从名称中提取 ID 或模糊查找 ===
        if not entity_id and name_lookup_field and name_field:
            name_lookup_value = params.get(name_lookup_field)

            # 写入调试日志文件
            with open('/Users/eddie/Code/CRMWolf/CRM-Server/skill_debug.log', 'a') as f:
                f.write(f"\n=== StatusChangeHandler 调试 ===\n")
                f.write(f"params: {params}\n")
                f.write(f"name_lookup_field: {name_lookup_field}\n")
                f.write(f"name_lookup_value: {name_lookup_value}\n")

            if name_lookup_value:
                # 先尝试从名称中提取 ID
                id_match = self.ID_PATTERN.search(name_lookup_value)
                with open('/Users/eddie/Code/CRMWolf/CRM-Server/skill_debug.log', 'a') as f:
                    f.write(f"ID_PATTERN: {self.ID_PATTERN.pattern}\n")
                    f.write(f"ID匹配结果: {id_match}\n")
                    if id_match:
                        f.write(f"提取的ID: {id_match.group(1)}\n")
                if id_match:
                    entity_id = int(id_match.group(1))
                    # 直接通过 ID 获取实体
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
                        return self.build_result(False, f"{crud_mapping_name} ID {entity_id} 不存在或已完成")
                else:
                    # 没有 ID，使用名称模糊查找（过滤无效状态）
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
                        return self.build_result(False, f"未找到匹配的{crud_mapping_name}: {name_lookup_value}")

                    if len(entities) > 1:
                        # 显示更多信息帮助用户区分：ID、状态、创建时间
                        entity_list = []
                        for e in entities[:5]:
                            entity_name = getattr(e, name_field)
                            entity_status = getattr(e, status_field, None)
                            # 获取状态名称（枚举的 name 属性）
                            if hasattr(entity_status, 'name'):
                                status_str = entity_status.name
                            elif hasattr(entity_status, 'value'):
                                status_str = str(entity_status.value)
                            else:
                                status_str = str(entity_status)
                            created_time = getattr(e, 'created_time', None)
                            time_str = created_time.strftime('%Y-%m-%d') if created_time else '未知'
                            entity_list.append(f"{entity_name}(ID:{e.id}, 状态:{status_str}, 创建:{time_str})")
                        return self.build_result(
                            False,
                            f"找到多个匹配的{crud_mapping_name}，请使用 ID 或更精确的名称指定。匹配结果:\n{chr(10).join(entity_list)}"
                        )

                    entity = entities[0]
                    entity_id = entity.id

        # 如果名称查找失败，尝试从其他 ID 参数获取
        if not entity_id:
            for key in ["entity_id", "id"]:
                if key in params:
                    entity_id = params.get(key)
                    break

        if not entity_id:
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
            # 区分不存在和状态无效的情况
            raw_entity = crud_instance.get_by_id(db, entity_id)
            if raw_entity:
                return self.build_result(False, f"{crud_mapping_name} ID {entity_id} 已完成或无效，无法变更状态")
            else:
                return self.build_result(False, f"{crud_mapping_name} ID {entity_id} 不存在")

        # 前置状态校验
        if pre_check_status_values:
            current_status = getattr(entity, status_field, None)
            if current_status not in pre_check_status_values:
                current_status_str = current_status.value if hasattr(current_status, 'value') else str(current_status)
                allowed_status_str = [s.value if hasattr(s, 'value') else str(s) for s in pre_check_status_values]
                return self.build_result(
                    False,
                    f"当前状态为 {current_status_str}，无法执行此操作。允许的状态: {', '.join(allowed_status_str)}"
                )

        # 获取目标状态
        target_status = handler_config.get("target_status")

        if not target_status:
            return self.build_result(False, "Handler 配置缺少 target_status")

        # 获取状态 enum
        status_enum_name = crud_mapping_name + "_status"
        status_enum_mapping = ai_enum_mapping_crud.get_by_name(db, status_enum_name)

        with open('/Users/eddie/Code/CRMWolf/CRM-Server/skill_debug.log', 'a') as f:
            f.write(f"\n=== 状态枚举处理 ===\n")
            f.write(f"status_enum_name: {status_enum_name}\n")
            f.write(f"status_enum_mapping: {status_enum_mapping}\n")
            f.write(f"target_status: {target_status}\n")
            if status_enum_mapping:
                f.write(f"values: {status_enum_mapping.values}\n")
                f.write(f"values.values(): {list(status_enum_mapping.values.values())}\n")

        if status_enum_mapping:
            enum_class = self.get_model_class(status_enum_mapping.enum_class)

            # values 结构为 {中文: 英文枚举名}，如 {'已转化': 'CONVERTED'}
            # target_status 可能是英文枚举名（如 'CONVERTED'）或中文（如 '已转化'）

            # 先检查 target_status 是否是枚举名（values 的值）
            if target_status in status_enum_mapping.values.values():
                # target_status 就是枚举名，如 'CONVERTED'
                target_status_enum = getattr(enum_class, target_status)
            elif target_status in status_enum_mapping.values:
                # target_status 是中文键，如 '已转化'
                enum_name = status_enum_mapping.values.get(target_status)
                target_status_enum = getattr(enum_class, enum_name)
            else:
                # 尝试直接作为枚举属性名
                try:
                    target_status_enum = getattr(enum_class, target_status)
                except AttributeError:
                    return self.build_result(False, f"无效的目标状态: {target_status}")
        else:
            target_status_enum = target_status

        with open('/Users/eddie/Code/CRMWolf/CRM-Server/skill_debug.log', 'a') as f:
            f.write(f"target_status_enum: {target_status_enum}\n")
            f.write(f"type: {type(target_status_enum)}\n")

        # 更新状态 - 根据字段类型决定使用枚举对象还是整数值
        status_attr = getattr(model_class, status_field, None)
        final_status_value = target_status_enum

        if status_attr is not None:
            from sqlalchemy import Integer
            # 如果字段是 Integer 类型，使用枚举的 value（整数）
            if hasattr(status_attr, 'type') and isinstance(status_attr.type, Integer):
                if hasattr(target_status_enum, 'value'):
                    final_status_value = target_status_enum.value
                else:
                    # 没有枚举映射，直接使用传入的值
                    final_status_value = target_status_enum

        setattr(entity, status_field, final_status_value)

        with open('/Users/eddie/Code/CRMWolf/CRM-Server/skill_debug.log', 'a') as f:
            f.write(f"final_status_value: {final_status_value}\n")
            f.write(f"status_attr.type: {status_attr.type if status_attr else None}\n")

        # 更新其他字段
        update_fields = handler_config.get("update_fields", [])
        for field in update_fields:
            if field in params:
                value = params.get(field)

                # 处理日期字段
                if "date" in field:
                    value = self.parse_date(value)
                elif "amount" in field:
                    try:
                        value = float(value)
                    except ValueError:
                        return self.build_result(False, f"无效的金额: {value}")

                setattr(entity, field, value)

        # 执行更新
        try:
            db.commit()
            db.refresh(entity)
        except Exception as e:
            db.rollback()
            return self.build_result(False, f"更新失败: {str(e)}")

        # 构建结果
        result_template = handler_config.get(
            "result_template",
            "状态变更成功\nID: {id}\n新状态: {status}"
        )

        template_data = {"id": entity_id}
        # 同时添加模块特定的 ID 字段（如 opportunity_id）
        template_data[expected_id_key] = entity_id
        # 添加名称字段到模板数据
        if name_field and hasattr(entity, name_field):
            template_data[name_field] = getattr(entity, name_field)

        for field in update_fields:
            if field in params:
                template_data[field] = params.get(field)

        template_data["status"] = target_status

        message = result_template.format(**template_data)

        return self.build_result(True, message, {"entity": entity})