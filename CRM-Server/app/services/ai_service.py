"""
AI 调用服务（SSE 流式请求）
"""
import httpx
import json
import logging
import asyncio
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

        logger.info(f"AI 调用开始: model={model}, timeout={timeout}s")

        last_status_error: Optional[httpx.HTTPStatusError] = None
        for attempt in range(3):
            full_content = ""

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
                    if response.status_code >= 400:
                        error_body = (await response.aread()).decode("utf-8", "replace")
                        retry_after = response.headers.get("retry-after")
                        logger.warning(
                            "AI 调用失败: status=%s, retry_after=%s, body=%s",
                            response.status_code,
                            retry_after,
                            error_body[:1000],
                        )
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError as exc:
                            last_status_error = exc
                            if response.status_code == 429 and attempt < 2:
                                delay = self._get_retry_delay(retry_after, attempt)
                                logger.info("AI 调用触发限流，%s 秒后重试: attempt=%s", delay, attempt + 1)
                                await asyncio.sleep(delay)
                                continue
                            raise

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

        if last_status_error:
            raise last_status_error
        return ""

    def _get_retry_delay(self, retry_after: Optional[str], attempt: int) -> float:
        if retry_after:
            try:
                return max(1.0, min(float(retry_after), 10.0))
            except ValueError:
                pass
        return float(2 ** attempt)

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
