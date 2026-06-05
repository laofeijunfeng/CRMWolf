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

            yield {
                "event": "parsed",
                "tool": tool_name,
                "params": params,
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

        # 模糊搜索名称
        table_map = {
            "lead": "leads",
            "customer": "customers",
            "opportunity": "opportunities"
        }
        table = table_map.get(entity_type)
        if not table:
            return None

        result = db.execute(
            text(f"SELECT id FROM {table} WHERE name LIKE :name AND team_id = :team_id LIMIT 1"),
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


ai_tool_service = AIToolService()