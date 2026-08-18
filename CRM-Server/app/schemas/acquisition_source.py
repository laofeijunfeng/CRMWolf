from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AcquisitionSourceInfo(BaseModel):
    public_id: str = Field(..., description="获客来源对外ID")
    name: str = Field(..., description="获客来源名称")
    is_active: bool = Field(..., description="是否启用")


class AcquisitionSourceOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    name: str
    code: str
    is_system: bool
    is_active: bool
    sort_order: int

    @field_validator("is_system", "is_active", mode="before")
    @classmethod
    def coerce_flag(cls, value: object) -> bool:
        return bool(int(value)) if value is not None else False


class AcquisitionSourceResponse(AcquisitionSourceOption):
    lead_count: int = 0
    customer_count: int = 0
    created_time: datetime
    updated_time: datetime


class AcquisitionSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="获客来源名称")
    sort_order: Optional[int] = Field(None, ge=0, description="排序号")


class AcquisitionSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50, description="获客来源名称")
    is_active: Optional[int] = Field(None, ge=0, le=1, description="是否启用：1启用, 0停用")
    sort_order: Optional[int] = Field(None, ge=0, description="排序号")


class AcquisitionSourceReorderItem(BaseModel):
    public_id: str = Field(..., min_length=1, description="获客来源对外ID")
    sort_order: int = Field(..., ge=0, description="排序号")


class AcquisitionSourceReorderRequest(BaseModel):
    items: list[AcquisitionSourceReorderItem] = Field(default_factory=list)
