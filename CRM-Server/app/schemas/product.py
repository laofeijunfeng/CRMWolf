from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves this annotation at runtime.
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ModuleRole = Literal["BASE", "ADD_ON"]

class ProductIntentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str
    name: str


class ProductModuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    module_role: Literal["ADD_ON"] = "ADD_ON"
    is_active: bool = True
    sort_order: int = Field(0, ge=0)


class ProductModuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None
    sort_order: int | None = Field(None, ge=0)


class ProductModuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., validation_alias="public_id")
    public_id: str
    name: str
    description: str | None
    module_role: ModuleRole
    is_active: bool
    sort_order: int
    created_by: str
    updated_by: str | None
    created_time: datetime
    updated_time: datetime

    @field_validator("is_active", mode="before")
    @classmethod
    def coerce_active(cls, value: object) -> bool:
        return bool(int(value)) if isinstance(value, int) else bool(value)


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., validation_alias="public_id")
    public_id: str
    name: str
    description: str | None
    is_active: bool
    created_by: str
    updated_by: str | None
    created_time: datetime
    updated_time: datetime
    modules: list[ProductModuleResponse] = Field(default_factory=list)

    @field_validator("is_active", mode="before")
    @classmethod
    def coerce_active(cls, value: object) -> bool:
        return bool(int(value)) if isinstance(value, int) else bool(value)
