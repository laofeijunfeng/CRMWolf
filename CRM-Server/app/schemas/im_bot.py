"""IM webhook schemas."""
from typing import Any, Dict, Optional

from pydantic import BaseModel


JsonDict = Dict[str, Any]


class IMWebhookResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    challenge: Optional[str] = None
    data: Optional[JsonDict] = None
