from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ViewPreferenceScope = Literal["personal", "team"]


class ViewPreferenceColumn(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    order: int | None = None
    visible: bool | None = None
    width: int | None = Field(None, ge=40, le=1000)
    fixed: Literal["left", "right"] | None = None


class ViewPreferenceConfig(BaseModel):
    version: int = Field(1, ge=1)
    columns: list[ViewPreferenceColumn] = Field(default_factory=list, max_length=100)
    sorts: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    filters: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    density: str | None = Field(None, max_length=20)


class ViewPreferenceSaveRequest(BaseModel):
    scope: ViewPreferenceScope
    config: ViewPreferenceConfig
    name: str | None = Field(None, max_length=100)
    is_default: bool = True


class ViewPreferenceCustomViewCreateRequest(BaseModel):
    config: ViewPreferenceConfig


class ViewPreferenceCustomViewUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: ViewPreferenceConfig | None = None
    sort_order: int | None = None


class ViewPreferenceItem(BaseModel):
    id: int
    team_id: int
    user_id: int
    view_key: str
    scope: ViewPreferenceScope
    preference_key: str
    name: str | None
    is_default: bool
    sort_order: int | None
    config: ViewPreferenceConfig
    created_by: int
    updated_by: int
    created_time: datetime
    updated_time: datetime


class ViewPreferenceResponse(BaseModel):
    view_key: str
    personal: ViewPreferenceItem | None
    team: ViewPreferenceItem | None
    effective_scope: ViewPreferenceScope | None
    effective_config: ViewPreferenceConfig | None


class ViewPreferenceCustomViewListResponse(BaseModel):
    view_key: str
    items: list[ViewPreferenceItem]
