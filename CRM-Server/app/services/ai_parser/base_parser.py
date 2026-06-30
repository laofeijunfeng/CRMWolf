"""
AI 实体解析基类

提供通用的 AI 解析逻辑,子类继承后只需实现定制化部分
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, Optional
from sqlalchemy.orm import Session
import httpx
import json

from app.crud.ai_config import ai_config_crud


class EntityAIParserBase(ABC):
    """实体 AI 解析基类"""

    # 子类必须定义的属性
    entity_type: str = ""  # 实体类型：lead, customer, opportunity, contract

    # ==================== 抽象方法（子类必须实现） ====================

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取系统提示词（各实体定义自己的提示词）"""
        pass

    @abstractmethod
    def get_enum_maps(self) -> Dict[str, Dict[str, Any]]:
        """
        获取枚举映射配置

        Returns:
            {"source": {"线上注册": "ONLINE_REGISTER", ...}, "scale": {...}}
        """
        pass

    @abstractmethod
    def parse_ai_response(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 AI 响应，转换为结构化数据

        Args:
            parsed: AI 返回的 JSON 数据

        Returns:
            结构化的解析结果（各实体定义自己的结构）
        """
        pass

    @abstractmethod
    async def create_entity(
        self,
        db: Session,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> Any:
        """
        创建实体（各实体定义自己的创建逻辑）

        Args:
            db: 数据库 Session
            parsed_data: 解析后的数据
            user_id: 用户 ID
            team_id: 团队 ID

        Returns:
            创建的实体对象
        """
        pass

    @abstractmethod
    async def post_create_actions(
        self,
        db: Session,
        entity: Any,
        parsed_data: Dict[str, Any],
        user_id: str,
        team_id: int
    ) -> None:
        """
        创建后的额外操作（可选）

        例如：
        - 线索：创建跟进记录
        - 客户：触发档案生成
        """
        pass

    # ==================== 通用方法（基类提供） ====================

    def _clean_json_response(self, content: str) -> str:
        """清理 JSON 响应中的 markdown 代码块标记"""
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        return clean_content.strip()

    def convert_enum_value(
        self,
        enum_map_name: str,
        user_value: str
    ) -> Optional[str]:
        """
        转换枚举值（通用方法）

        Args:
            enum_map_name: 枚举映射名称（如 "source", "scale"）
            user_value: 用户输入值（如 "线上注册", "20人"）

        Returns:
            枚举值（如 "ONLINE_REGISTER", "1-50人"）
        """
        enum_maps = self.get_enum_maps()
        enum_map = enum_maps.get(enum_map_name)

        if not enum_map:
            return None

        return enum_map.get(user_value)

    async def parse_stream(
        self,
        db: Session,
        user_message: str,
        team_id: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式解析（通用 SSE 流式响应逻辑）

        Args:
            db: 数据库 Session
            user_message: 用户输入的自然语言
            team_id: 团队 ID

        Yields:
            SSE 事件字典
        """
        # 获取 AI 配置
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            yield {"event": "error", "message": "AI 配置未设置"}
            return

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            yield {"event": "error", "message": "无法获取 API Key"}
            return

        # 发送状态事件
        yield {"event": "status", "message": f"正在解析{self.entity_type}信息..."}

        # 构建请求
        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
            "stream": True,
            "response_format": {"type": "json_object"}
        }

        full_content = ""

        try:
            # 流式调用 AI API
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_body
                ) as response:
                    response.raise_for_status()

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
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content_piece = delta.get("content", "")
                                    if content_piece:
                                        full_content += content_piece
                                        yield {"event": "content", "content": content_piece}
                            except json.JSONDecodeError:
                                continue

                    # 解析完整响应
                    clean_content = self._clean_json_response(full_content)
                    parsed = json.loads(clean_content)

                    # 调用子类的解析方法
                    result = self.parse_ai_response(parsed)

                    yield {
                        "event": "parsed",
                        **result  # 展开子类返回的结构化数据
                    }

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}