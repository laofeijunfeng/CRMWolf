"""
AI 调用服务（SSE 流式请求）
"""
import httpx
import json
import logging
from typing import Optional, AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session
from app.crud.ai_config import ai_config_crud

logger = logging.getLogger(__name__)


class AIService:
    """AI 调用服务（兼容 OpenAI 格式，使用 SSE 流式请求）"""

    async def _stream_chat_collect(
        self,
        api_host: str,
        api_key: str,
        model: str,
        messages: list,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        response_format: Optional[dict] = None,
        timeout: float = 120.0  # 增加默认超时时间
    ) -> str:
        """
        使用 SSE 流式请求调用 AI API，收集完整响应

        Args:
            api_host: API 基础地址
            api_key: API Key
            model: 模型名称
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 tokens
            response_format: 响应格式（可选）
            timeout: 超时时间（秒），默认120秒

        Returns:
            完整的响应内容字符串
        """
        request_body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        if response_format:
            request_body["response_format"] = response_format

        full_content = ""

        logger.info(f"AI 调用开始: model={model}, timeout={timeout}s")

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{api_host}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity"  # 禁用 gzip 压缩
                },
                json=request_body
            ) as response:
                response.raise_for_status()

                # 使用 aiter_text() 正确处理流式响应
                buffer = ""
                async for text_chunk in response.aiter_text():
                    buffer += text_chunk
                    lines = buffer.split('\n')
                    buffer = lines[-1] if lines else ""

                    for line in lines[:-1]:
                        if not line:
                            continue

                        if line.startswith("data: "):
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
                            except json.JSONDecodeError:
                                continue

        logger.info(f"AI 调用完成: 响应长度={len(full_content)}")
        return full_content

    async def _stream_chat_generator(
        self,
        api_host: str,
        api_key: str,
        model: str,
        messages: list,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        response_format: Optional[dict] = None,
        timeout: float = 60.0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        使用 SSE 流式请求调用 AI API，生成 SSE 事件

        Yields:
            SSE 事件字典: {"event": "start/content/done/error", ...}
        """
        request_body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        if response_format:
            request_body["response_format"] = response_format

        full_content = ""

        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity"  # 禁用 gzip 压缩
                    },
                    json=request_body
                ) as response:
                    response.raise_for_status()

                    # 发送开始事件
                    yield {"event": "start", "message": "开始接收 AI 响应"}

                    # 使用 aiter_text() 正确处理流式响应
                    buffer = ""
                    async for text_chunk in response.aiter_text():
                        buffer += text_chunk
                        lines = buffer.split('\n')
                        buffer = lines[-1] if lines else ""

                        for line in lines[:-1]:
                            if not line:
                                continue

                            if line.startswith("data: "):
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

                    # 处理剩余 buffer
                    if buffer.startswith("data: ") and buffer[6:] != "[DONE]":
                        try:
                            chunk = json.loads(buffer[6:])
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content_piece = delta.get("content", "")
                                if content_piece:
                                    full_content += content_piece
                                    yield {"event": "content", "content": content_piece}
                        except json.JSONDecodeError:
                            pass

                    # 发送完成事件
                    yield {"event": "done", "full_content": full_content}

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}

    def get_config_and_key(self, db: Session, team_id: int = 1) -> tuple[Optional[Any], Optional[str]]:
        """获取 AI 配置和 API Key"""
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            return None, None
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        return config, api_key

    async def stream_intent_parse(
        self,
        db: Session,
        config: Any,
        api_key: str,
        user_message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式解析用户意图，生成 SSE 事件

        Yields:
            SSE 事件字典
        """
        # 使用动态提示词服务
        system_prompt = self._get_system_prompt(db)

        request_body = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
            "response_format": {"type": "json_object"}
        }

        full_content = ""

        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity"  # 禁用 gzip 压缩，避免流式解码问题
                    },
                    json=request_body
                ) as response:
                    response.raise_for_status()

                    # 发送开始事件
                    yield {"event": "start", "message": "开始接收 AI 响应"}

                    # 使用 aiter_text() 替代 aiter_lines() 以正确处理可能的压缩响应
                    buffer = ""
                    async for text_chunk in response.aiter_text():
                        buffer += text_chunk
                        # 按行分割处理 SSE
                        lines = buffer.split('\n')
                        buffer = lines[-1] if lines else ""  # 保留不完整的行

                        for line in lines[:-1]:  # 处理完整的行
                            if not line:
                                continue

                            if line.startswith("data: "):
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

                    # 发送解析完成事件
                    # 清理 markdown 代码块标记
                    clean_content = full_content.strip()
                    if clean_content.startswith("```json"):
                        clean_content = clean_content[7:]
                    if clean_content.startswith("```"):
                        clean_content = clean_content[3:]
                    if clean_content.endswith("```"):
                        clean_content = clean_content[:-3]
                    clean_content = clean_content.strip()

                    try:
                        parsed = json.loads(clean_content)
                        yield {
                            "event": "parsed",
                            "skill": parsed.get("skill"),
                            "action": parsed.get("action"),
                            "params": parsed.get("params", {}),
                            "reply_text": parsed.get("reply_text", "正在为你执行操作，请稍候...")
                        }
                    except json.JSONDecodeError:
                        yield {"event": "error", "message": f"AI 返回格式异常: {clean_content[:200]}"}

        except httpx.HTTPStatusError as e:
            yield {"event": "error", "message": f"AI 服务请求失败：{e.response.status_code}"}
        except Exception as e:
            yield {"event": "error", "message": f"AI 服务异常：{str(e)}"}

    async def test_connection(self, db: Session, test_message: str, team_id: int = 1) -> tuple[bool, str, Optional[str]]:
        """
        测试 AI 连接（使用 SSE 流式请求）
        """
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            return False, "AI 配置未设置", None

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return False, "无法获取 API Key", None

        try:
            full_content = await self._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[{"role": "user", "content": test_message}],
                temperature=config.temperature,
                max_tokens=config.max_tokens
            )

            return True, "AI 连接测试成功", full_content

        except httpx.HTTPStatusError as e:
            return False, f"请求失败：{e.response.status_code}", None
        except Exception as e:
            return False, f"连接异常：{str(e)}", None


ai_service = AIService()