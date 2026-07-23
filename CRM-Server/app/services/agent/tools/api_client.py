"""HTTP client for CRM AI Agent tools.

The Agent must call existing backend APIs so auth, team scoping, validation and
approval side effects stay in the current system boundary.
"""
from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings


class CRMAPIClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_json: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_json = response_json


class InternalCRMAPIClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.AGENT_INTERNAL_API_BASE_URL).rstrip("/")
        self.timeout = timeout

    async def request(
        self,
        method: str,
        path: str,
        authorization: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        headers = {"Authorization": authorization}
        url = f"{self.base_url}/{path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json)

        if response.status_code >= 400:
            response_json = self._safe_json(response)
            detail = response_json.get("detail") if isinstance(response_json, dict) else None
            raise CRMAPIClientError(
                detail or f"CRM API调用失败：{response.status_code}",
                status_code=response.status_code,
                response_json=response_json,
            )
        return self._safe_json(response)

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}
