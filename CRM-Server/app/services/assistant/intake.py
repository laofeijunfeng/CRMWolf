"""Async entry adapter: run coordinator steps that need LLM calls.

The coordinator stays sync for pure state routing; kind classification and
structuring are the only async steps, invoked through this module so tests
can fake them without event-loop plumbing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.services.assistant.llm import AssistantLLM, AssistantLLMError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.assistant.llm_contracts import KindDecision, StructureDraftResult


class KindStructurer(Protocol):
    async def classify(self, db: Session, *, team_id: int, user_text: str) -> KindDecision: ...

    async def structure(
        self, db: Session, *, team_id: int, kind: str, user_text: str
    ) -> StructureDraftResult: ...


class RealKindStructurer:
    """Production adapter over the neutral structured model client."""

    def __init__(self, llm: AssistantLLM | None = None) -> None:
        self.llm = llm or AssistantLLM()

    async def classify(self, db: Session, *, team_id: int, user_text: str) -> KindDecision:
        return await self.llm.classify_kind(db, team_id=team_id, user_text=user_text)

    async def structure(
        self, db: Session, *, team_id: int, kind: str, user_text: str
    ) -> StructureDraftResult:
        return await self.llm.structure_draft(db, team_id=team_id, kind=kind, user_text=user_text)


__all__ = ["AssistantLLMError", "KindStructurer", "RealKindStructurer"]
