"""
AI 工具服务

使用 Function Calling 处理用户消息，执行对应工具
"""
import json
from typing import Dict, Any, Optional, AsyncGenerator, List
from sqlalchemy.orm import Session
import httpx

from app.crud.ai_config import ai_config_crud
from app.crud.conversation_log import conversation_log_crud
from app.crud.user import user_crud
from app.constants.tools import get_tools_schema, get_tool_handler_config
from app.services.skills.handlers.handler_factory import HandlerFactory
from app.services.permission_service import permission_service


class AIToolService:
    """AI 工具服务 - 使用 Function Calling"""

    # 参数字段中文标签映射
    PARAM_LABEL_MAP: Dict[str, str] = {
        # 线索相关
        "lead_name": "线索名称",
        "lead_id": "线索ID",
        "contact_name": "联系人姓名",
        "contact_phone": "联系电话",
        "source": "线索来源",
        "city": "所在城市",
        "company_scale": "公司规模",
        # 客户相关
        "customer_name": "客户名称",
        "customer_id": "客户ID",
        "industry": "所属行业",
        "address": "地址",
        "remarks": "备注",
        # 商机相关
        "opportunity_name": "商机名称",
        "opportunity_id": "商机ID",
        "total_amount": "预计总金额",
        "user_count": "采购用户数",
        "license_type": "授权模式",
        "subscription_years": "订阅年限",
        "purchase_type": "采购类型",
        "expected_amount": "预期金额",
        "expected_closing_date": "预期成交日期",
        "actual_amount": "实际成交金额",
        "actual_closing_date": "实际成交日期",
        "reason": "原因",
        # 跟进相关
        "content": "跟进内容",
        "method": "跟进方式",
        "next_action": "下一步动作",
        "next_follow_time": "下次跟进时间",
        # 通用
        "owner_name": "负责人",
        "owner_id": "负责人ID",
        "keyword": "搜索关键词",
        "status": "状态",
        "stage": "阶段",
        "limit": "数量限制",
        "entity_type": "实体类型",
        "entity_id": "实体ID",
        "entity_name": "实体名称",
        "procurement_method_name": "采购方式",
    }

    async def handle_message_stream(
        self,
        db: Session,
        user_id: int,
        user: Any,
        content: str,
        team_id: int,
        confirmed_tool: Optional[str] = None,
        confirmed_params: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户消息（SSE 流式响应）

        Args:
            db: 数据库 session
            user_id: 用户 ID
            user: 用户对象
            content: 用户输入内容
            team_id: 团队 ID
            confirmed_tool: 用户确认执行时指定的工具名
            confirmed_params: 用户确认执行时的参数

        Yields:
            SSE 事件字典
        """
        # 如果是确认执行请求，直接执行
        if confirmed_tool and confirmed_params:
            yield {"event": "status", "message": "正在执行操作..."}
            async for event in self._execute_tool_and_yield(
                db, user, confirmed_tool, confirmed_params, team_id
            ):
                yield event
            return

        # 否则进行解析流程
        yield {"event": "status", "message": "正在解析您的请求..."}

        # 获取 AI 配置
        config, api_key = self._get_config(db, team_id)
        if not config or not api_key:
            yield {"event": "error", "message": "AI 配置未设置，请联系管理员先配置 AI 服务"}
            return

        # 创建会话日志
        log = conversation_log_crud.create_log(
            db,
            user_id=user_id,
            channel_user_id=str(user_id),
            channel_type="web_assistant",
            request_text=content,
            status="PENDING",
            team_id=team_id
        )

        # 调用 AI（使用 Function Calling）
        try:
            tool_calls = None
            ai_content = ""

            async for event in self._stream_chat_with_tools(
                config, api_key, content, get_tools_schema()
            ):
                if event["type"] == "content":
                    ai_content += event.get("content", "")
                    yield {"event": "content", "content": event.get("content", "")}
                elif event["type"] == "tool_call":
                    tool_calls = event.get("calls", [])
                elif event["type"] == "error":
                    yield {"event": "error", "message": event.get("message", "AI 调用失败")}
                    conversation_log_crud.update_result(db, log.id, status="FAILED")
                    return

            # 检查是否有工具调用
            if not tool_calls:
                # AI 直接回复（没有工具调用）
                if ai_content:
                    yield {"event": "result", "message": ai_content}
                    conversation_log_crud.update_result(db, log.id, execution_result=ai_content, status="SUCCESS")
                else:
                    yield {"event": "result", "message": "我无法理解您的请求，请描述具体的业务操作"}
                    conversation_log_crud.update_result(db, log.id, status="PARAM_MISSING")
                return

            # 有工具调用
            first_call = tool_calls[0]
            tool_name = first_call["name"]
            params = json.loads(first_call["arguments"])

            # 在 parsed 阶段就继承父实体的字段默认值（如采购方式）
            params = self._inherit_parent_fields_in_parsed(tool_name, params, db, team_id)

            # 获取参数定义（传入 db 和 team_id 以获取动态选项）
            param_definitions = self._get_tool_param_definitions(tool_name, db, team_id)
            # 检测缺失的必填参数
            missing_params = self._get_missing_params(tool_name, params)

            yield {
                "event": "parsed",
                "tool": tool_name,
                "params": params,
                "param_definitions": param_definitions,
                "missing_params": missing_params,
                "reply_text": self._get_tool_description(tool_name, params)
            }

            conversation_log_crud.update_result(db, log.id, ai_skill=tool_name, status="PARSED")

        except Exception as e:
            yield {"event": "error", "message": f"解析失败：{str(e)}"}
            conversation_log_crud.update_result(db, log.id, execution_result=str(e), status="FAILED")

    async def execute_confirmed_tool(
        self,
        db: Session,
        user: Any,
        tool_name: str,
        params: Dict[str, Any],
        team_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行用户确认的工具
        """
        async for event in self._execute_tool_and_yield(db, user, tool_name, params, team_id):
            yield event

    async def _execute_tool_and_yield(
        self,
        db: Session,
        user: Any,
        tool_name: str,
        params: Dict[str, Any],
        team_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行工具并返回结果"""
        yield {"event": "status", "message": "正在执行操作..."}

        # 获取 Handler 配置
        handler_config = get_tool_handler_config(tool_name)
        if not handler_config:
            yield {"event": "error", "message": f"未知工具：{tool_name}"}
            return

        # 检查权限
        permission_code = handler_config.get("config", {}).get("permission_code")
        if permission_code:
            permissions = permission_service.get_user_permissions_from_db(db, user.id)
            if not any(p.code == permission_code for p in permissions):
                yield {"event": "error", "message": "您没有执行此操作的权限"}
                return

        # 预处理参数（名称查找 ID）
        processed_params = await self._preprocess_params(db, params, team_id)

        # 执行 Handler
        try:
            handler_type = handler_config.get("handler")
            handler = HandlerFactory.get_handler(handler_type)

            if not handler:
                yield {"event": "error", "message": f"Handler 不存在：{handler_type}"}
                return

            # 合并配置
            full_config = {**handler_config.get("config", {}), **processed_params}

            result = await handler.execute(
                db=db,
                handler_config=full_config,
                params=processed_params,
                user_id=user.id,
                team_id=team_id
            )

            if result.get("success"):
                yield {"event": "result", "message": result.get("message", "操作成功"), "data": result.get("data")}
            else:
                yield {"event": "error", "message": result.get("message", "操作失败")}

        except Exception as e:
            yield {"event": "error", "message": f"执行失败：{str(e)}"}

    async def _preprocess_params(
        self,
        db: Session,
        params: Dict[str, Any],
        team_id: int
    ) -> Dict[str, Any]:
        """
        预处理参数：
        - 根据名称查找 ID（如 lead_name → lead_id）
        - 根据负责人姓名查找 owner_id
        """
        processed = params.copy()

        # 实体名称查找 ID
        entity_types = ["lead", "customer", "opportunity"]
        for entity_type in entity_types:
            name_field = f"{entity_type}_name"
            id_field = f"{entity_type}_id"

            if name_field in params and id_field not in params:
                entity_id = await self._find_entity_id(db, entity_type, params[name_field], team_id)
                if entity_id:
                    processed[id_field] = entity_id

        # 负责人姓名查找 ID
        if "owner_name" in params and "owner_id" not in params:
            from sqlalchemy import text
            result = db.execute(
                text("SELECT id FROM users WHERE name = :name"),
                {"name": params["owner_name"]}
            ).fetchone()
            if result:
                processed["owner_id"] = str(result[0])

        return processed

    async def _find_entity_id(
        self,
        db: Session,
        entity_type: str,
        name: str,
        team_id: int
    ) -> Optional[int]:
        """根据名称查找实体 ID"""
        from sqlalchemy import text

        # 从名称中提取 ID（格式：名称（ID：xxx））
        import re
        id_pattern = re.compile(r'[（(]\s*ID[：:]\s*(\d+)\s*[）)]')
        match = id_pattern.search(name)
        if match:
            return int(match.group(1))

        # 模糊搜索名称（不同表用不同的名称字段）
        table_map = {
            "lead": ("crm_leads", "name"),
            "customer": ("crm_customers", "account_name"),
            "opportunity": ("crm_opportunities", "opportunity_name")
        }
        table_info = table_map.get(entity_type)
        if not table_info:
            return None

        table, name_field = table_info

        result = db.execute(
            text(f"SELECT id FROM {table} WHERE {name_field} LIKE :name AND team_id = :team_id LIMIT 1"),
            {"name": f"%{name}%", "team_id": team_id}
        ).fetchone()

        return result[0] if result else None

    def _get_config(self, db: Session, team_id: int):
        """获取 AI 配置和 API Key"""
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            return None, None
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        return config, api_key

    def _get_tool_description(self, tool_name: str, params: Dict[str, Any]) -> str:
        """获取工具操作的描述文本"""
        from app.constants.tools import TOOLS

        for tool in TOOLS:
            if tool["function"]["name"] == tool_name:
                desc = tool["function"]["description"]
                # 构建参数摘要
                param_summary = ", ".join(f"{k}={v}" for k, v in params.items() if v)
                return f"将执行：{desc}（参数：{param_summary}）"

        return f"将执行：{tool_name}"

    async def _stream_chat_with_tools(
        self,
        config: Any,
        api_key: str,
        user_message: str,
        tools: List[Dict[str, Any]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        使用 Function Calling 调用 AI API（流式响应）

        支持 OpenAI 格式，兼容 Anthropic、DeepSeek 等
        """
        request_body = {
            "model": config.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {"role": "user", "content": user_message}
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
            "tools": tools,
            "tool_choice": "auto"
        }

        full_content = ""
        tool_calls_buffer = []

        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity"
                    },
                    json=request_body
                ) as response:
                    response.raise_for_status()

                    yield {"type": "start"}

                    buffer = ""
                    async for text_chunk in response.aiter_text():
                        buffer += text_chunk
                        lines = buffer.split('\n')
                        buffer = lines[-1] if lines else ""

                        for line in lines[:-1]:
                            if not line or not line.startswith("data: "):
                                continue

                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue

                                delta = choices[0].get("delta", {})

                                # 内容输出
                                content_piece = delta.get("content", "")
                                if content_piece:
                                    full_content += content_piece
                                    yield {"type": "content", "content": content_piece}

                                # 工具调用（流式格式）
                                if "tool_calls" in delta:
                                    for tc in delta["tool_calls"]:
                                        idx = tc.get("index", 0)
                                        # 缓存工具调用片段
                                        if idx >= len(tool_calls_buffer):
                                            tool_calls_buffer.append({
                                                "id": "",
                                                "name": "",
                                                "arguments": ""
                                            })
                                        if tc.get("id"):
                                            tool_calls_buffer[idx]["id"] = tc["id"]
                                        if tc.get("function", {}).get("name"):
                                            tool_calls_buffer[idx]["name"] = tc["function"]["name"]
                                        if tc.get("function", {}).get("arguments"):
                                            tool_calls_buffer[idx]["arguments"] += tc["function"]["arguments"]

                            except json.JSONDecodeError:
                                continue

                    # 处理完整的工具调用
                    if tool_calls_buffer:
                        calls = []
                        for tc in tool_calls_buffer:
                            if tc["name"]:
                                calls.append({
                                    "id": tc["id"],
                                    "name": tc["name"],
                                    "arguments": tc["arguments"]
                                })
                        if calls:
                            yield {"type": "tool_call", "calls": calls}

        except httpx.HTTPStatusError as e:
            yield {"type": "error", "message": f"AI 服务错误：{e.response.status_code}"}
        except Exception as e:
            yield {"type": "error", "message": f"连接失败：{str(e)}"}

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是 CRMWolf 系统的 AI 助手，帮助用户管理销售线索、客户和商机。

你可以通过调用工具来执行业务操作：
- 创建、查询、分配线索
- 创建、查询客户，添加跟进记录
- 创建、查询商机，推进阶段，标记成交/失败

当用户描述业务需求时，判断需要执行什么操作，调用对应的工具。
如果信息不完整，先向用户询问必要信息。

重要提示：
1. 实体名称可能包含 ID，格式如"张三的公司（ID: 123）"，请提取 ID
2. 如果用户提到"我的"、"自己的"，表示当前用户的资源
3. 今天是 """ + self._get_current_date() + """

请根据用户输入，选择合适的工具并填写参数。"""


    def _get_current_date(self) -> str:
        """获取当前日期"""
        from datetime import datetime
        now = datetime.now()
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[now.weekday()]
        return f"{now.strftime('%Y-%m-%d')}（{weekday}）"

    def _map_param_type(self, json_type: str, has_enum: bool, param_name: str) -> str:
        """
        将 JSON Schema 类型映射为前端表单类型

        Args:
            json_type: JSON Schema 类型 (string, integer, number)
            has_enum: 是否有枚举值
            param_name: 参数名（用于特殊字段判断）

        Returns:
            前端表单类型: text, number, date, select, textarea
        """
        # 有枚举值 -> 下拉选择
        if has_enum:
            return "select"

        # 特殊字段：日期类型
        date_fields = [
            "next_follow_time", "expected_closing_date", "actual_closing_date",
            "next_follow_up_time", "expected_amount_date"
        ]
        if param_name in date_fields:
            return "date"

        # 特殊字段：多行文本
        textarea_fields = ["content", "remarks", "reason", "description", "note"]
        if param_name in textarea_fields:
            return "textarea"

        # 默认映射
        TYPE_MAP = {
            "string": "text",
            "integer": "number",
            "number": "number",
        }
        return TYPE_MAP.get(json_type, "text")

    def _get_tool_param_definitions(self, tool_name: str, db: Session = None, team_id: int = None) -> Dict[str, Any]:
        """
        从 TOOLS 定义中提取参数定义，转换为前端表单格式

        对于需要动态选项的字段（如采购方式），从数据库获取

        返回格式:
        {
            "param_name": {
                "label": "中文标签",
                "type": "text|number|date|select|textarea",
                "required": true/false,
                "placeholder": "提示文本",
                "options": [{"value": "x", "label": "x"}]  # 仅 select 类型
            }
        }
        """
        from app.constants.tools import TOOLS

        for tool in TOOLS:
            if tool["function"]["name"] == tool_name:
                params_schema = tool["function"].get("parameters", {})
                properties = params_schema.get("properties", {})
                required = params_schema.get("required", [])

                param_definitions = {}
                for param_name, param_def in properties.items():
                    has_enum = "enum" in param_def
                    json_type = param_def.get("type", "string")
                    param_type = self._map_param_type(json_type, has_enum, param_name)

                    definition = {
                        "label": self.PARAM_LABEL_MAP.get(param_name, param_name),
                        "type": param_type,
                        "required": param_name in required,
                        "placeholder": param_def.get("description", "")
                    }

                    # 添加选项
                    if has_enum:
                        # 使用工具定义中的枚举值
                        enum_values = param_def.get("enum", [])
                        definition["options"] = [
                            {"value": v, "label": v} for v in enum_values
                        ]
                    elif param_name == "procurement_method_name" and db and team_id:
                        # 动态获取采购方式列表
                        options = self._get_procurement_method_options(db, team_id)
                        if options:
                            definition["type"] = "select"
                            definition["options"] = options

                    param_definitions[param_name] = definition

                return param_definitions

        return {}

    def _get_procurement_method_options(self, db: Session, team_id: int) -> List[Dict[str, str]]:
        """
        从数据库获取采购方式选项列表

        Args:
            db: 数据库 session
            team_id: 团队 ID

        Returns:
            [{"value": "采购方式名称", "label": "采购方式名称"}, ...]
        """
        from sqlalchemy import text

        try:
            result = db.execute(
                text("""
                    SELECT name FROM crm_procurement_methods
                    WHERE (team_id = :team_id OR team_id IS NULL)
                    AND is_active = 1
                    ORDER BY sort_order
                """),
                {"team_id": team_id}
            )
            rows = result.fetchall()
            return [{"value": row[0], "label": row[0]} for row in rows]
        except Exception:
            return []

    def _inherit_parent_fields_in_parsed(self, tool_name: str, params: Dict[str, Any], db: Session, team_id: int) -> Dict[str, Any]:
        """
        在 parsed 阶段继承父实体的字段默认值

        例如：创建商机时，如果用户没有指定采购方式，从客户的默认采购方式继承

        Args:
            tool_name: 工具名称
            params: AI 返回的参数
            db: 数据库 session
            team_id: 团队 ID

        Returns:
            处理后的参数（包含继承的默认值）
        """
        from app.constants.tools import get_tool_handler_config

        handler_config = get_tool_handler_config(tool_name)
        if not handler_config:
            return params

        config = handler_config.get("config", {})
        parent_lookup = config.get("parent_lookup")
        if not parent_lookup:
            return params

        # 获取继承字段配置
        inherit_fields = parent_lookup.get("inherit_fields", {})
        if not inherit_fields:
            return params

        # 获取父实体名称（如 customer_name）
        parent_lookup_field = parent_lookup.get("parent_lookup_field")
        if not parent_lookup_field:
            return params

        parent_name = params.get(parent_lookup_field)
        if not parent_name:
            return params

        # 查找父实体
        parent_crud_mapping = parent_lookup.get("parent_crud_mapping")
        if not parent_crud_mapping:
            return params

        parent_entity = self._find_parent_entity(db, parent_crud_mapping, parent_name, team_id)
        if not parent_entity:
            return params

        # 继承字段值
        result_params = params.copy()
        for child_field, parent_field in inherit_fields.items():
            # 检查相关的参数字段（如 procurement_method_name）是否存在
            related_param_field = child_field.replace("_id", "_name") if child_field.endswith("_id") else child_field

            # 只有当用户没有提供相关参数时才继承
            if related_param_field not in result_params or result_params[related_param_field] is None:
                parent_value = getattr(parent_entity, parent_field, None)
                if parent_value is not None:
                    # 如果是 ID 字段，需要转换为名称显示给用户
                    if child_field.endswith("_id") and parent_field.endswith("_id"):
                        # 查询对应的名称
                        name_value = self._get_entity_name_by_id(db, child_field, parent_value, team_id)
                        if name_value:
                            result_params[related_param_field] = name_value
                    else:
                        if hasattr(parent_value, 'value'):
                            result_params[child_field] = parent_value.value
                        else:
                            result_params[child_field] = parent_value

        return result_params

    def _find_parent_entity(self, db: Session, crud_mapping: str, name: str, team_id: int) -> Any:
        """
        根据名称查找父实体

        Args:
            db: 数据库 session
            crud_mapping: CRUD 映射名称（如 "customer"）
            name: 实体名称
            team_id: 团队 ID

        Returns:
            父实体对象或 None
        """
        from sqlalchemy import text

        table_field_map = {
            "customer": ("crm_customers", "account_name"),
            "lead": ("crm_leads", "name"),
            "opportunity": ("crm_opportunities", "opportunity_name"),
        }

        table_info = table_field_map.get(crud_mapping)
        if not table_info:
            return None

        table, name_field = table_info

        result = db.execute(
            text(f"SELECT * FROM {table} WHERE {name_field} LIKE :name AND team_id = :team_id LIMIT 1"),
            {"name": f"%{name}%", "team_id": team_id}
        ).fetchone()

        return result

    def _get_entity_name_by_id(self, db: Session, id_field: str, entity_id: int, team_id: int) -> Optional[str]:
        """
        根据 ID 获取实体的名称

        Args:
            db: 数据库 session
            id_field: ID 字段名（如 "procurement_method_id"）
            entity_id: 实体 ID
            team_id: 团队 ID

        Returns:
            实体名称或 None
        """
        from sqlalchemy import text

        # 映射 ID 字段到表和名称字段
        id_to_table_map = {
            "procurement_method_id": ("crm_procurement_methods", "name"),
        }

        table_info = id_to_table_map.get(id_field)
        if not table_info:
            return None

        table, name_field = table_info

        result = db.execute(
            text(f"SELECT {name_field} FROM {table} WHERE id = :id"),
            {"id": entity_id}
        ).fetchone()

        return result[0] if result else None

    def _get_missing_params(self, tool_name: str, params: Dict[str, Any]) -> List[str]:
        """
        检测所有缺失的字段（包括必填和可选）

        只要字段在参数定义中存在但在 params 中为空，就视为缺失，
        让用户可以在表单中补充。

        Args:
            tool_name: 工具名称
            params: AI 返回的参数

        Returns:
            缺失的参数名列表
        """
        from app.constants.tools import TOOLS

        for tool in TOOLS:
            if tool["function"]["name"] == tool_name:
                properties = tool["function"].get("parameters", {}).get("properties", {})
                missing = []
                for field in properties.keys():
                    value = params.get(field)
                    if value is None or value == "" or value == []:
                        missing.append(field)
                return missing

        return []


ai_tool_service = AIToolService()