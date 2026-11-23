"""IM webhook schemas."""
from typing import Any

from pydantic import BaseModel

JsonDict = dict[str, Any]


class IMWebhookResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    challenge: str | None = None
    data: JsonDict | None = None
