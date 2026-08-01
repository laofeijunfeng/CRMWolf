"""Channel-neutral Agent turn input contracts."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentInputKind(str, Enum):
    TEXT = "text"
    CONFIRM = "confirm"
    REJECT = "reject"


class AgentTurnInput(BaseModel):
    kind: AgentInputKind = AgentInputKind.TEXT
    content: str = ""
    source: str = "web"
    provider: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def text(
        cls,
        content: str,
        *,
        source: str = "web",
        provider: Optional[str] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> "AgentTurnInput":
        return cls(
            kind=AgentInputKind.TEXT,
            content=content,
            source=source,
            provider=provider,
            metadata=metadata or {},
        )

    @classmethod
    def confirm(
        cls,
        *,
        source: str = "system",
        provider: Optional[str] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> "AgentTurnInput":
        return cls(
            kind=AgentInputKind.CONFIRM,
            content="确认",
            source=source,
            provider=provider,
            metadata=metadata or {},
        )

    @classmethod
    def reject(
        cls,
        *,
        source: str = "system",
        provider: Optional[str] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> "AgentTurnInput":
        return cls(
            kind=AgentInputKind.REJECT,
            content="取消",
            source=source,
            provider=provider,
            metadata=metadata or {},
        )
