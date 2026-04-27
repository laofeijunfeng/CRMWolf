"""
开放接口认证依赖
"""
import time
import hashlib
from typing import Optional
from fastapi import Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.crud.api_key import api_key_crud
from app.models.api_key import ApiKey, ApiKeyStatus
from app.services.rate_limiter import rate_limiter
from app.services.api_call_logger import api_call_logger


async def verify_api_key(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key", description="API Key"),
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    验证 API Key 并返回 ApiKey 对象

    Args:
        request: FastAPI Request 对象
        x_api_key: 请求头中的 API Key
        db: 数据库会话

    Returns:
        ApiKey: 验证通过的 ApiKey 对象

    Raises:
        HTTPException: 401 - API Key 无效
        HTTPException: 403 - API Key 被禁用或无权限
        HTTPException: 429 - 请求限流
    """
    # 1. 计算 API Key 哈希
    api_key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    # 2. 获取客户端 IP
    client_ip = get_client_ip(request)

    # 3. 校验 API Key
    is_valid, key_record, error_msg = api_key_crud.is_valid(db, api_key_hash, client_ip)

    if not is_valid:
        if error_msg == "API Key 不存在":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 无效"
            )
        elif error_msg.startswith("API Key 状态为"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg
            )
        elif error_msg == "API Key 已过期":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API Key 已过期"
            )
        elif error_msg.startswith("IP"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg
            )

    # 4. 限流检查
    if key_record:
        allowed, current_count, wait_time = rate_limiter.is_allowed(
            key_record.key_id,
            key_record.rate_limit_tps
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求限流，请等待 {wait_time} 秒后重试",
                headers={"Retry-After": str(wait_time)}
            )

    # 5. 更新最后使用时间
    if key_record:
        api_key_crud.update_last_used(db, key_record.id)

    return key_record


def get_client_ip(request: Request) -> Optional[str]:
    """获取客户端真实 IP"""
    # 优先从代理头获取
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # 直接连接的 IP
    if request.client:
        return request.client.host

    return None


def require_api_permission(permission_code: str):
    """
    API Key 权限校验依赖

    Args:
        permission_code: 需要的权限代码（如 "customer:read"）

    Returns:
        权限校验函数
    """
    async def permission_checker(
        request: Request,
        api_key: ApiKey = Depends(verify_api_key),
        db: Session = Depends(get_db)
    ) -> ApiKey:
        # 检查权限
        if not api_key_crud.has_permission(api_key, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission_code}"
            )

        return api_key

    return permission_checker


async def log_api_call(
    request: Request,
    response_code: int,
    response_body: Optional[str],
    duration_ms: int,
    api_key: ApiKey
):
    """
    记录 API 调用日志（在响应后调用）

    Args:
        request: FastAPI Request
        response_code: 响应码
        response_body: 响应体
        duration_ms: 耗时
        api_key: ApiKey 对象
    """
    api_call_logger.log_call(
        key_id=api_key.key_id,
        app_name=api_key.app_name,
        request_method=request.method,
        request_path=str(request.url.path),
        request_params=dict(request.query_params) if request.query_params else None,
        request_body=None,  # 请求体在路由中处理
        response_code=response_code,
        response_body=response_body,
        client_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        duration_ms=duration_ms
    )