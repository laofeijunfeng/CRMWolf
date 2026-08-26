"""Owned Agent session access used by API and application entry points."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from app.crud.agent import agent_session_crud
from app.schemas.agent import AgentSessionCreate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.agent import AgentCreateSessionRequest


def new_session_key() -> str:
    return f"agent_{uuid.uuid4().hex}"


def build_session_create(
    request: AgentCreateSessionRequest,
    *,
    team_id: int,
    user_id: int,
) -> AgentSessionCreate:
    return AgentSessionCreate(
        session_key=new_session_key(),
        team_id=team_id,
        user_id=user_id,
        title=request.title,
        context_json=request.context_json,
    )


def require_owned_session(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    session_id: int | None = None,
    session_key: str | None = None,
):
    if session_id is not None:
        session = agent_session_crud.get_by_id(
            db,
            session_id,
            team_id=team_id,
            user_id=user_id,
        )
    elif session_key:
        session = agent_session_crud.get_by_key(
            db,
            session_key,
            team_id=team_id,
            user_id=user_id,
        )
    else:
        session = None

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent会话不存在",
        )
    return session
