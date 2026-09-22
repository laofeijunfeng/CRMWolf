"""Typed export request bodies shared by all resource export endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.list_export import is_unsafe_export_key
from app.core.list_query.types import FilterCondition, SortCondition


class BaseListExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[str] = Field(min_length=1, max_length=64)
    search: str | None = Field(default=None, max_length=200)
    filters: list[FilterCondition] = Field(default_factory=list)
    sorts: list[SortCondition] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, values: list[str]) -> list[str]:
        unsafe = next((key for key in values if is_unsafe_export_key(key)), None)
        if unsafe is not None:
            raise ValueError(f"不安全导出字段: {unsafe}")
        if len(values) != len(set(values)):
            raise ValueError("导出字段不能重复")
        return values


class CustomerListExportRequest(BaseListExportRequest):
    tab: Literal["all", "collaborated", "public"] = "all"


class LeadListExportRequest(BaseListExportRequest):
    tab: Literal["all", "public"] = "all"


class OpportunityListExportRequest(BaseListExportRequest):
    tab: Literal["all", "active", "won", "lost"] = "all"


class ContractListExportRequest(BaseListExportRequest):
    tab: Literal["all", "DRAFT", "PENDING_REVIEW", "SIGNED"] = "all"


class PaymentPlanListExportRequest(BaseListExportRequest):
    tab: Literal["all", "pending", "partial", "completed"] = "all"


class PaymentRecordListExportRequest(BaseListExportRequest):
    tab: Literal["all", "pending_submit", "pending_approval", "rejected", "confirmed"] = "all"


class InvoiceListExportRequest(BaseListExportRequest):
    tab: Literal["all", "pending", "approved", "invoiced"] = "all"


class FollowUpTaskListExportRequest(BaseListExportRequest):
    tab: Literal["all", "open", "completed", "cancelled"] = "open"


class ApprovalListExportRequest(BaseListExportRequest):
    tab: Literal["pending", "processed", "submitted"] = "pending"
