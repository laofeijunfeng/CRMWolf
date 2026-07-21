from typing import Any, Dict
from urllib.parse import urlencode

import httpx

from app.schemas.oauth import FeishuUserProfile


class FeishuOAuthService:
    auth_base_url = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
    api_base_url = "https://open.feishu.cn/open-apis"

    def build_auth_url(self, app_id: str, redirect_uri: str, state: str) -> str:
        query = urlencode({
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        })
        return f"{self.auth_base_url}?{query}"

    async def exchange_code(self, app_id: str, app_secret: str, code: str, redirect_uri: str) -> str:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base_url}/authen/v2/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"飞书换取访问令牌失败：{response.text}") from exc
            data = response.json()

        if data.get("code") != 0:
            raise RuntimeError(data.get("msg") or "飞书授权失败")
        token = data.get("access_token") or data.get("data", {}).get("access_token")
        if not token:
            raise RuntimeError("飞书未返回访问令牌")
        return token

    async def get_user_info(self, user_access_token: str) -> FeishuUserProfile:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.get(
                f"{self.api_base_url}/authen/v1/user_info",
                headers={"Authorization": f"Bearer {user_access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            raise RuntimeError(data.get("msg") or "获取飞书用户信息失败")

        raw: Dict[str, Any] = data.get("data") or {}
        avatar = raw.get("avatar_url") or raw.get("avatar_thumb") or raw.get("avatar_middle") or raw.get("avatar_big")
        email = raw.get("email") or raw.get("enterprise_email")
        return FeishuUserProfile(
            open_id=raw.get("open_id") or "",
            union_id=raw.get("union_id"),
            user_id=raw.get("user_id"),
            tenant_key=raw.get("tenant_key"),
            email=email,
            enterprise_email=raw.get("enterprise_email"),
            mobile=raw.get("mobile"),
            name=raw.get("name") or raw.get("en_name") or email,
            avatar_url=avatar,
            raw=raw,
        )


feishu_oauth_service = FeishuOAuthService()
