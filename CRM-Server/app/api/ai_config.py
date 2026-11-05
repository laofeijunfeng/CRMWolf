"""AI 配置管理接口。"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_user_team
from app.crud.ai_config import ai_config_crud
from app.models.ai_config import AIConfig
from app.models.user import User
from app.schemas.ai_config import (
    AIConfigCreate,
    AITestRequest,
    AssistantCapabilityEnvelope,
    AssistantCapabilityResponse,
)
from app.services.ai_http_client import ai_httpx_client_kwargs, ai_httpx_timeout
from app.services.assistant.model_capabilities import (
    assistant_model_capabilities,
    assistant_verification_is_current,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.models.permission import Permission

router = APIRouter(prefix="/v1/ai", tags=["AI 配置管理"])


def _permissions(db: Session, user: User) -> list[Permission]:
    from app.services.permission_service import permission_service

    return permission_service.get_user_permissions_from_db(db, user.id)


def _require_read(db: Session, user: User) -> None:
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in _permissions(db, user)):
        raise HTTPException(status_code=403, detail="无权限访问 AI 配置")


def _require_manage(db: Session, user: User) -> None:
    if not any(p.code in ["system:config", "ai:manage"] for p in _permissions(db, user)):
        raise HTTPException(status_code=403, detail="无权限修改 AI 配置")


def _config_data(config: AIConfig, api_key: str) -> dict[str, object]:
    mode = config.structured_output_mode or "json_object"
    verified = assistant_verification_is_current(config, api_key)
    return {
        "id": config.id,
        "api_host": config.api_host,
        "api_key_masked": config.mask_api_key(api_key),
        "model_name": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        "structured_output_mode": mode,
        "assistant_verification_state": "VERIFIED" if verified else "UNVERIFIED",
        "assistant_verified_at": config.assistant_verified_at.isoformat() if verified else None,
    }


@router.get("/config")
async def get_ai_config(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_read(db, current_user)
    config = ai_config_crud.get_config(db, team_id)
    if not config:
        return {"code": 0, "message": "AI 配置未设置", "data": None, "timestamp": int(time.time())}
    api_key = ai_config_crud.get_decrypted_api_key(db, team_id) or ""
    return {"code": 0, "message": "success", "data": _config_data(config, api_key), "timestamp": int(time.time())}


@router.post("/config")
async def save_ai_config(
    config_in: AIConfigCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(db, current_user)
    try:
        config = ai_config_crud.save_or_update(db, config_in, current_user.id, team_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="首次配置必须提供 API Key") from exc
    return {
        "code": 0,
        "message": "AI 配置保存成功",
        "data": _config_data(config, AIConfig.decrypt_api_key(config.api_key_encrypted)),
        "timestamp": int(time.time()),
    }


@router.post("/test-assistant", response_model=AssistantCapabilityEnvelope)
async def test_assistant_capability(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    _require_manage(db, current_user)
    result: AssistantCapabilityResponse = await assistant_model_capabilities.verify(db, team_id=team_id)
    return {
        "code": 0 if result.success else 1,
        "message": result.message,
        "data": result.model_dump(mode="json"),
        "timestamp": int(time.time()),
    }


@router.post("/test")
async def test_ai_connection(
    test_in: AITestRequest,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """测试普通 AI 连接；该测试不代表销售助手结构化能力已就绪。"""
    _require_manage(db, current_user)
    config = ai_config_crud.get_config(db, team_id)
    if not config:
        raise HTTPException(status_code=400, detail="AI 配置未设置")
    api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    if not api_key:
        raise HTTPException(status_code=400, detail="无法获取 API Key")

    async def generate_sse() -> AsyncIterator[str]:
        import httpx

        full_content = ""
        request_body = {
            "model": config.model_name,
            "messages": [{"role": "user", "content": test_in.test_message}],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=ai_httpx_timeout(), **ai_httpx_client_kwargs()) as client:
                async with client.stream(
                    "POST", f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    json=request_body,
                ) as response:
                    response.raise_for_status()
                    yield f"data: {json.dumps({'event': 'start', 'message': '开始接收 AI 响应'})}\n\n"
                    buffer = ""
                    async for text_chunk in response.aiter_text():
                        buffer += text_chunk
                        lines = buffer.split("\n")
                        buffer = lines[-1] if lines else ""
                        for line in lines[:-1]:
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if choices:
                                    piece = choices[0].get("delta", {}).get("content", "")
                                    if piece:
                                        full_content += piece
                                        yield f"data: {json.dumps({'event': 'content', 'content': piece})}\n\n"
                            except json.JSONDecodeError:
                                continue
                    done_event = {
                        "event": "done", "success": True, "message": "AI 连接测试成功", "full_content": full_content,
                    }
                    yield f"data: {json.dumps(done_event)}\n\n"
        except httpx.HTTPStatusError as exc:
            error_event = {"event": "error", "success": False, "message": f"请求失败：{exc.response.status_code}"}
            yield f"data: {json.dumps(error_event)}\n\n"
        except Exception:
            error_event = {"event": "error", "success": False, "message": "连接异常，请检查配置或服务状态"}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        generate_sse(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
