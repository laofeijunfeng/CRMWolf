"""Channel-neutral Agent turn input contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


class AgentInputKind(str, Enum):
    TEXT = "text"
    CONFIRM = "confirm"
    REJECT = "reject"


@dataclass(frozen=True)
class AgentChannelContext:
    """Trusted channel metadata applied after typed input validation."""

    source: str = "web"
    provider: str | None = None
    input_kind: AgentInputKind = AgentInputKind.TEXT
    metadata: dict[str, object] = field(default_factory=dict)


class AgentTurnInput(BaseModel):
    kind: AgentInputKind = AgentInputKind.TEXT
    content: str = ""
    source: str = "web"
    provider: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def text(
        cls,
        content: str,
        *,
        source: str = "web",
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentTurnInput:
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
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentTurnInput:
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
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentTurnInput:
        return cls(
            kind=AgentInputKind.REJECT,
            content="取消",
            source=source,
            provider=provider,
            metadata=metadata or {},
        )
