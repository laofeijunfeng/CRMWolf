"""HTTP client for CRM AI Agent tools.

The Agent must call existing backend APIs so auth, team scoping, validation and
approval side effects stay in the current system boundary.
"""
from typing import Dict, Optional

import httpx

from app.core.config import get_settings


class CRMAPIClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_json: object = None) -> None:
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
        params: Optional[Dict[str, object]] = None,
        json: Optional[Dict[str, object]] = None,
        idempotency_key: Optional[str] = None,
    ) -> object:
        headers = {"Authorization": authorization}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        url = f"{self.base_url}/{path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json)

        if response.status_code >= 400:
            response_json = self._safe_json(response)
            raise CRMAPIClientError(
                self._error_message(response.status_code, response_json),
                status_code=response.status_code,
                response_json=response_json,
            )
        return self._safe_json(response)

    @staticmethod
    def _error_message(status_code: int, response_json: object) -> str:
        """Surface FastAPI 422 field errors so callers can self-correct."""

        if isinstance(response_json, dict):
            detail = response_json.get("detail")
            if isinstance(detail, str) and detail.strip():
                fields = response_json.get("errors")
                if status_code == 422 and isinstance(fields, list):
                    parts = [
                        f"{item.get('field')}: {item.get('message')}"
                        for item in fields
                        if isinstance(item, dict) and item.get("field")
                    ]
                    if parts:
                        return f"{detail} ({'; '.join(parts[:5])})"
                return detail
        return f"CRM API调用失败：{status_code}"

    @staticmethod
    def _safe_json(response: httpx.Response) -> object:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}
