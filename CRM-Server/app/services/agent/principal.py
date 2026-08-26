"""Authoritative CRM Agent identity shared by Root, Query, and Workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentPrincipal(BaseModel):
    """Run-scoped tenant, user, session, and permission identity."""

    model_config = ConfigDict(extra="forbid", strict=True)

    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    permission_codes: list[str] = Field(default_factory=list)
