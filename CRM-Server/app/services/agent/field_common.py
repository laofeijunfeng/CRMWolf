"""Shared Agent field collection parsing and merge helpers."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.agent.schemas import AgentMemorySnapshot, AgentSemanticParseResult
from app.services.agent.semantic import agent_semantic_parser
from app.services.agent.temporal import agent_temporal_resolver

async def _parse_task_field_supplement(db: Session, task, content: str) -> AgentSemanticParseResult:
    memory = AgentMemorySnapshot(
        pending_task={
            "id": task.id,
            "intent": task.intent,
            "target_type": task.target_type,
            "target_id": task.target_id,
            "summary": task.summary,
            "state": task.state_json,
        },
    )
    return await agent_semantic_parser.parse(
        db,
        team_id=task.team_id,
        user_message=content,
        memory=memory,
        current_date=agent_temporal_resolver.now().date(),
    )

def _extract_generated_form_int(content: str, key: str) -> Optional[int]:
    marker = f"{key}="
    if marker not in content:
        return None
    tail = content.split(marker, 1)[1]
    digits = []
    for char in tail:
        if char.isdigit():
            digits.append(char)
            continue
        break
    if not digits:
        return None
    value = int("".join(digits))
    return value if value > 0 else None

def _drop_empty_values(payload: dict) -> dict:
    return {key: value for key, value in (payload or {}).items() if value not in (None, "")}
