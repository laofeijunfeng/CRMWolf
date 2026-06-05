"""
跟进 Handler

处理添加跟进记录类型的 Action（如 LeadSkill.follow_up）

注意：
1. 默认过滤已转化/无效的父实体，避免重复跟进
2. 支持从名称中提取 ID（格式：名称（ID：xxx）或 名称(ID:xxx)）
3. 支持相对时间解析（如"后天"、"三天后"、"下周"）
4. 默认下次跟进时间为 3 天后

硬编码版：不再依赖数据库获取 CRUD/Enum 映射配置
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.services.skills.handlers.base_handler import BaseHandler
from app.crud.user import user_crud
from app.services.follow_up_parser import follow_up_parser_service
from app.constants.handler_configs import (
    CRUD_MAPPINGS,
    ENUM_MAPPINGS,
    get_enum_value,
)


class FollowUpHandler(BaseHandler):
    """跟进 Handler"""

    handler_type = "FollowUpHandler"

    # 默认排除的状态（已转化、无效的实体不应再跟进）
    DEFAULT_EXCLUDE_STATUS = ["CONVERTED", "INVALID"]

    # 从名称中提取 ID 的正则表达式（复用共享服务）
    ID_PATTERN = follow_up_parser_service.ID_PATTERN

    # 默认下次跟进间隔（天数）
    DEFAULT_NEXT_FOLLOW_DAYS = 3

    def parse_relative_time(self, time_text: Optional[str], base_date: datetime = None) -> Optional[datetime]:
        """
        解析相对时间表达（复用共享服务）

        支持：
        - 具体日期：2024-05-25, 5月25日
        - 相对天数：后天、三天后、3天后、一周后、下周三
        - 今天/明天

        Args:
            time_text: 时间文本
            base_date: 基准日期（默认今天）

        Returns:
            datetime 对象或 None
        """
        return follow_up_parser_service.parse_relative_time(time_text, base_date)

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

        # 从硬编码配置获取映射
        crud_config = self.get_crud_mapping(crud_mapping_name)
        parent_crud_config = self.get_crud_mapping(parent_crud_mapping_name)

        if not crud_config or not parent_crud_config:
            return self.build_result(False, "CRUD 映射不存在")

        # 获取用户信息
        user = user_crud.get_by_id(db, user_id)
        if not user:
            return self.build_result(False, "用户不存在")

        # 从配置直接获取 CRUD 和 Model
        parent_crud = parent_crud_config["crud"]
        parent_model = parent_crud_config["model"]

        # 查找父实体
        parent_lookup_field = handler_config.get("parent_lookup_field", "name")
        parent_name_field = handler_config.get("parent_name_field", "name")
        parent_lookup_value = params.get(parent_lookup_field)

        # 尝试从参数中直接获取 ID（如 lead_id, customer_id）
        parent_type_prefix = parent_crud_mapping_name.split("_")[0]  # lead, customer, opportunity
        direct_id_field = f"{parent_type_prefix}_id"
        direct_id = params.get(direct_id_field)

        # 如果没有 lookup_value 也没有 direct_id，报错
        if not parent_lookup_value and not direct_id:
            return self.build_result(False, f"缺少参数: {parent_lookup_field} 或 {direct_id_field}")

        # 获取排除状态配置（默认过滤已转化/无效）
        exclude_status_keys = handler_config.get("exclude_status", self.DEFAULT_EXCLUDE_STATUS)

        # 获取状态枚举值（硬编码版，不需要 db）
        if exclude_status_keys and parent_crud_config["status_field"]:
            parent_type = parent_crud_mapping_name.split("_")[0]
            status_enum_name = f"{parent_type}_status"
            exclude_status_values = self.get_status_enum_values(status_enum_name, exclude_status_keys)
        else:
            exclude_status_values = []

        # 根据名称模糊查找（过滤已转化/无效状态）
        parent_entity = None
        parent_id = None

        # 优先使用直接传入的 ID
        if direct_id:
            parent_id = int(direct_id)
            # 先检查实体是否存在（不过滤状态）
            raw_entity = parent_crud.get_by_id(db, parent_id)

            if not raw_entity:
                return self.build_result(False, f"{parent_crud_mapping_name} ID {parent_id} 不存在")

            # 检查实体状态是否被排除
            if exclude_status_values and parent_crud_config["status_field"]:
                current_status = getattr(raw_entity, parent_crud_config["status_field"])
                if current_status in exclude_status_values:
                    # 获取状态显示名称（硬编码版，不需要 db）
                    status_display = self._get_status_display_name(parent_type_prefix, current_status)
                    return self.build_result(
                        False,
                        f"{parent_crud_mapping_name}「{getattr(raw_entity, parent_name_field)}」当前状态为「{status_display}」，无法添加跟进记录"
                    )

            parent_entity = raw_entity
        # 尝试从名称中提取 ID 或使用名称查找
        elif parent_lookup_value:
            id_match = self.ID_PATTERN.search(parent_lookup_value)
            if id_match:
                parent_id = int(id_match.group(1))
                # 先检查实体是否存在（不过滤状态）
                raw_entity = parent_crud.get_by_id(db, parent_id)

                if not raw_entity:
                    return self.build_result(False, f"{parent_crud_mapping_name} ID {parent_id} 不存在")

                # 检查实体状态是否被排除
                if exclude_status_values and parent_crud_config["status_field"]:
                    current_status = getattr(raw_entity, parent_crud_config["status_field"])
                    if current_status in exclude_status_values:
                        status_display = self._get_status_display_name(parent_type_prefix, current_status)
                        return self.build_result(
                            False,
                            f"{parent_crud_mapping_name}「{getattr(raw_entity, parent_name_field)}」当前状态为「{status_display}」，无法添加跟进记录"
                        )

                parent_entity = raw_entity
            else:
                # 没有 ID，使用名称模糊查找
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

        # 获取 team_id（从父实体）
        team_id = getattr(parent_entity, 'team_id', None)
        if team_id is None:
            # 尝试从关联实体获取（如 Contract 通过 Opportunity 获取）
            if hasattr(parent_entity, 'opportunity_id') and parent_entity.opportunity_id:
                from app.crud.opportunity import opportunity_crud
                opp = opportunity_crud.get_by_id(db, parent_entity.opportunity_id)
                if opp:
                    team_id = opp.team_id

        # 处理跟进方式 enum（硬编码版）
        method = params.get("method")
        method_enum = None

        enum_mappings = handler_config.get("enum_mappings", {})
        if "method" in enum_mappings and method:
            enum_name = enum_mappings["method"]
            enum_config = self.get_enum_mapping(enum_name)

            if enum_config:
                enum_class = enum_config["enum_class"]
                method_enum = get_enum_value(enum_class, method, enum_config)
                if not method_enum:
                    valid_values = list(enum_config.get("values", {}).keys())
                    return self.build_result(
                        False,
                        f"无效的跟进方式: {method}，请使用: {', '.join(valid_values)}"
                    )

        # 如果没有传入 method，使用默认值 "其他"
        if not method and not method_enum:
            method = "其他"

        # 处理下次跟进时间
        next_follow_time = params.get("next_follow_time")
        if next_follow_time:
            # 用户提供了时间，解析相对时间表达
            next_follow_time_dt = self.parse_relative_time(next_follow_time)
        else:
            # 用户未提供时间，使用默认值（3天后）
            next_follow_time_dt = datetime.now() + timedelta(days=self.DEFAULT_NEXT_FOLLOW_DAYS)

        # 获取下一步动作
        next_action = params.get("next_action")

        # 构建跟进记录数据
        follow_up_data = {
            "content": params.get("content"),
            "method": method_enum or method,
            "next_follow_time": next_follow_time_dt,
            "next_action": next_action
        }

        # 获取 Schema 类（从硬编码配置）
        schema_create = crud_config.get("schema_create")
        if schema_create:
            try:
                schema_obj = schema_create(**follow_up_data)
            except Exception as e:
                return self.build_result(False, f"数据校验失败: {str(e)}")

        # 获取跟进 CRUD 实例（从硬编码配置）
        follow_up_crud = crud_config["crud"]

        # 执行创建
        try:
            if schema_create:
                follow_up = follow_up_crud.create(
                    db, schema_obj, parent_id, str(user.id), team_id,
                    operator_name=user.name
                )
            else:
                follow_up = follow_up_crud.create(
                    db, follow_up_data, parent_id, str(user.id), team_id,
                    operator_name=user.name
                )
        except Exception as e:
            return self.build_result(False, f"跟进记录添加失败: {str(e)}")

        # 更新父实体状态（硬编码版）
        update_parent_status = handler_config.get("update_parent_status")
        if update_parent_status and parent_crud_config["status_field"]:
            from_status = update_parent_status.get("from_status")
            to_status = update_parent_status.get("to_status")

            # 检查当前状态
            current_status = getattr(parent_entity, parent_crud_config["status_field"])
            current_status_str = current_status.value if hasattr(current_status, 'value') else str(current_status)

            if from_status and current_status_str == from_status:
                # 获取目标状态 enum（硬编码版）
                status_enum_name = parent_crud_mapping_name + "_status"
                status_enum_config = self.get_enum_mapping(status_enum_name)

                if status_enum_config:
                    enum_class = status_enum_config["enum_class"]
                    to_enum_key = status_enum_config.get("values", {}).get(to_status)
                    if to_enum_key:
                        new_status = getattr(enum_class, to_enum_key)
                        setattr(parent_entity, parent_crud_config["status_field"], new_status)
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

        if next_action:
            message += f"\n下一步动作: {next_action}"

        return self.build_result(True, message, {
            "follow_up_id": follow_up.id,
            "parent_id": parent_id,
            "parent_name": parent_name
        })