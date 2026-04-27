"""
AI 配置管理接口
"""
import time
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, Generic, TypeVar

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.crud.ai_config import ai_config_crud
from app.schemas.ai_config import AIConfigCreate, AIConfigResponse, AITestRequest, AITestResponse
from app.services.ai_service import ai_service

T = TypeVar("T")


class APIResponse(Generic[T]):
    """简单 API 响应格式"""
    code: int
    message: str
    data: Optional[T]

    def __init__(self, code: int, message: str, data: Optional[T] = None):
        self.code = code
        self.message = message
        self.data = data


router = APIRouter(prefix="/api/v1/ai", tags=["AI 配置管理"])


@router.get("/config")
async def get_ai_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取 AI 配置"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 AI 配置")

    config = ai_config_crud.get_config(db)
    if not config:
        return {
            "code": 0,
            "message": "AI 配置未设置",
            "data": None,
            "timestamp": int(time.time())
        }

    masked_key = config.mask_api_key(ai_config_crud.get_decrypted_api_key(db) or "")

    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": config.id,
            "api_host": config.api_host,
            "api_key_masked": masked_key,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        },
        "timestamp": int(time.time())
    }


@router.post("/config")
async def save_ai_config(
    config_in: AIConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """保存 AI 配置"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限修改 AI 配置")

    config = ai_config_crud.save_or_update(db, config_in, current_user.id)

    masked_key = config.mask_api_key(config_in.api_key)

    return {
        "code": 0,
        "message": "AI 配置保存成功",
        "data": {
            "id": config.id,
            "api_host": config.api_host,
            "api_key_masked": masked_key,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        },
        "timestamp": int(time.time())
    }


@router.post("/test")
async def test_ai_connection(
    test_in: AITestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """测试 AI 连接（返回 SSE 流式响应）"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限测试 AI 连接")

    config = ai_config_crud.get_config(db)
    if not config:
        raise HTTPException(status_code=400, detail="AI 配置未设置")

    api_key = ai_config_crud.get_decrypted_api_key(db)
    if not api_key:
        raise HTTPException(status_code=400, detail="无法获取 API Key")

    async def generate_sse():
        """生成 SSE 流式响应"""
        import httpx

        full_content = ""
        request_body = {
            "model": config.model_name,
            "messages": [{"role": "user", "content": test_in.test_message}],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True
        }

        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{config.api_host}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity"  # 禁用 gzip 压缩
                    },
                    json=request_body
                ) as response:
                    response.raise_for_status()

                    # 发送开始事件
                    yield f"data: {json.dumps({'event': 'start', 'message': '开始接收 AI 响应'})}\n\n"

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
                                            # 发送内容事件
                                            yield f"data: {json.dumps({'event': 'content', 'content': content_piece})}\n\n"
                                except json.JSONDecodeError:
                                    continue

                    # 发送完成事件
                    yield f"data: {json.dumps({'event': 'done', 'success': True, 'message': 'AI 连接测试成功', 'full_content': full_content})}\n\n"

        except httpx.HTTPStatusError as e:
            yield f"data: {json.dumps({'event': 'error', 'success': False, 'message': f'请求失败：{e.response.status_code}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'success': False, 'message': f'连接异常：{str(e)}'})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
    )