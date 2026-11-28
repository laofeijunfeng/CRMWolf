# ruff: noqa: RUF001
"""Multimodal vision extraction for assistant image attachments (zero LangChain imports)."""

from __future__ import annotations

import asyncio
import base64
from time import monotonic
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from app.services import file_storage as file_storage_module
from app.services.assistant.failure_contract import AssistantFailureCode, attempt_budget_remaining
from app.services.assistant.model_transport import (
    AssistantLLMError,
    _status_failure,
    team_model_credentials,
)
from app.services.file_storage import (
    ASSISTANT_ATTACHMENT_ROOT,
    FileStorageError,
    FileStorageService,
    detect_image_mime,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.assistant_conversation import ConversationAttachmentRef

_VISION_TIMEOUT_SECONDS = 45.0
_MAX_EXTRACT_CHARS = 4000

VISION_UNSUPPORTED_MESSAGE = "当前配置的模型暂不支持图片识别，请切换支持视觉理解的模型，或改用文字描述。"

VISION_SYSTEM_PROMPT = """你是 CRM 销售助手的图片信息提取器。
请准确、忠实地提取用户上传图片中的业务信息，输出简洁清晰的中文纯文本。
要求：
1. 如果是微信/IM 聊天截图：按对话顺序列出发送方、关键沟通内容、明确提到的时间、金额、客户诉求、承诺与待办。
2. 如果是名片/联系人信息：提取姓名、公司名称、职位、手机号、微信号、邮箱、地址等可见字段。
3. 如果是会议记录/报价单/合同/文档截图：提取标题、客户方、核心条款、金额、日期与关键事项。
4. 只写图片中明确可见的信息，严禁编造或猜测看不清的内容；如果有多张图片，按「图1」「图2」分段整理。
5. 直接输出整理后的纯文本事实，不要输出 Markdown 代码块或多余寒暄。"""


class VisionUnsupportedError(AssistantLLMError):
    """Raised when the configured team model rejects multimodal image input."""


class AttachmentVisionExtractor(Protocol):
    async def extract(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        attachments: list[ConversationAttachmentRef],
        user_text: str,
    ) -> str: ...


def compose_multimodal_text(user_text: str, vision_extract: object) -> str:
    """Combine user-typed text with extracted image facts for downstream LLM stages."""

    extracted = vision_extract.strip() if isinstance(vision_extract, str) else ""
    typed = user_text.strip()
    if not extracted:
        return user_text
    if not typed:
        return f"[用户上传了图片]\n{extracted}"
    return f"{user_text}\n\n[图片内容]\n{extracted}"


def load_owned_attachment_data_uri(
    attachment: ConversationAttachmentRef,
    *,
    team_id: int,
    user_id: int,
    storage: FileStorageService | None = None,
) -> tuple[str, str]:
    """Fail-closed read of one user-owned image attachment as a base64 data URI."""

    prefix = f"{ASSISTANT_ATTACHMENT_ROOT}/{team_id}/{user_id}/"
    stored_name = attachment.file_url.removeprefix(prefix)
    if (
        stored_name == attachment.file_url
        or stored_name in {"", ".", ".."}
        or "/" in stored_name
        or "\\" in stored_name
    ):
        raise AssistantLLMError("图片识别：附件无权访问", code=AssistantFailureCode.INTERNAL_ERROR)
    active_storage = file_storage_module.file_storage_service if storage is None else storage
    try:
        full_path = active_storage.get_full_path(attachment.file_url)
        with open(full_path, "rb") as fp:
            raw = fp.read()
    except (FileStorageError, OSError) as exc:
        raise AssistantLLMError(
            "图片识别：附件不存在或无法读取",
            code=AssistantFailureCode.INTERNAL_ERROR,
            cause=exc,
        ) from exc
    mime = detect_image_mime(raw)
    if mime is None:
        raise AssistantLLMError("图片识别：附件不是有效图片", code=AssistantFailureCode.INTERNAL_ERROR)
    encoded = base64.b64encode(raw).decode("ascii")
    return attachment.file_name, f"data:{mime};base64,{encoded}"


def _extract_message_text(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("refusal"):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            item.get("text", "").strip()
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
        ]
        return "\n".join(part for part in parts if part).strip()
    return ""


class OpenAIAttachmentVisionExtractor:
    """Parse uploaded images via the team's OpenAI-compatible chat completions endpoint."""

    def __init__(self, *, storage: FileStorageService | None = None) -> None:
        self._storage = storage

    async def extract(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        attachments: list[ConversationAttachmentRef],
        user_text: str,
    ) -> str:
        if not attachments:
            return ""
        content_parts: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"用户附言：{user_text.strip()}\n请结合附言重点提取以下图片中的业务事实。"
                    if user_text.strip()
                    else "请提取以下图片中的全部关键业务信息。"
                ),
            }
        ]
        for attachment in attachments:
            _name, data_uri = load_owned_attachment_data_uri(
                attachment, team_id=team_id, user_id=user_id, storage=self._storage
            )
            content_parts.append({"type": "image_url", "image_url": {"url": data_uri}})

        api_host, api_key, model_name = team_model_credentials(db, team_id)
        remaining = attempt_budget_remaining()
        timeout_seconds = _VISION_TIMEOUT_SECONDS if remaining is None else min(_VISION_TIMEOUT_SECONDS, remaining)
        if timeout_seconds <= 0:
            raise AssistantLLMError("图片识别：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)
        payload: dict[str, Any] = {
            "model": model_name,
            "temperature": 0.0,
            "stream": False,
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": content_parts},
            ],
        }
        started = monotonic()
        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
                    response = await client.post(
                        f"{api_host.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise AssistantLLMError(
                "图片识别：AI 请求超时",
                code=AssistantFailureCode.UPSTREAM_TIMEOUT,
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise AssistantLLMError(
                "图片识别：AI 请求失败",
                code=AssistantFailureCode.UPSTREAM_UNAVAILABLE,
                cause=exc,
            ) from exc

        if monotonic() - started >= timeout_seconds:
            raise AssistantLLMError("图片识别：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)

        failure = _status_failure(response, "图片识别", api_key)
        if failure is not None:
            if failure.code is AssistantFailureCode.REQUEST_PROTOCOL_ERROR:
                raise VisionUnsupportedError(
                    VISION_UNSUPPORTED_MESSAGE,
                    code=failure.code,
                    provider_status=failure.provider_status,
                    provider_request_id=failure.provider_request_id,
                    provider_error_type=failure.provider_error_type,
                    provider_error_param=failure.provider_error_param,
                ) from failure
            raise failure

        try:
            extracted = _extract_message_text(response.json())
        except ValueError as exc:
            raise AssistantLLMError(
                "图片识别：返回格式无效",
                code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
                cause=exc,
            ) from exc
        if not extracted:
            raise AssistantLLMError("图片识别：未返回有效图片内容", code=AssistantFailureCode.MODEL_OUTPUT_INVALID)
        return extracted[:_MAX_EXTRACT_CHARS]
