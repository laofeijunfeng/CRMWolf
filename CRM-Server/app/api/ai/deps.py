"""AI OpenAPI 认证依赖

双重认证机制：
1. JWT Bearer Token（Web 端）
2. API Key（MCP/外部调用）

参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.deps import get_current_user
from app.models.user import User
from app.core.database import get_db
from sqlalchemy.orm import Session


# HTTP Bearer 认证
oauth2_scheme = HTTPBearer(auto_error=False)


async def get_ai_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme),
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """获取 AI OpenAPI 用户（双重认证）

    认证流程：
    1. 优先使用 JWT Token 认证（Web 端）
    2. 如果提供 API Key，额外校验（MCP/外部调用）

    Args:
        credentials: HTTP Bearer Token
        api_key: X-API-Key Header
        db: 数据库会话

    Returns:
        User: 认证成功的用户

    Raises:
        HTTPException: 认证失败
    """

    # 1. JWT Token 认证
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_current_user(credentials, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. API Key 校验（可选，用于外部调用）
    if api_key:
        # TODO: API Key 功能待实现，当前仅记录日志
        # 当 api_key_crud 实现后，启用完整校验逻辑
        pass  # 暂不校验，等待 API Key 模型实现

    return user


# ==================== 导出 ====================

__all__ = [
    "oauth2_scheme",
    "get_ai_user",
]