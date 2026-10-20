"""回款图表只读响应。"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import Literal

from pydantic import BaseModel, Field

PaymentRecordChartKey = Literal["license_type", "purchase_type", "amount_band", "payment_month"]


class PaymentRecordChartPreview(BaseModel):
    id: int
    record_number: str | None = None
    customer_name: str | None = None
    amount: float
    payment_date: date | None = None


class PaymentRecordChartBucket(BaseModel):
    key: str
    label: str
    count: int
    amount: float
    ratio: int
    amount_ratio: int
    preview: list[PaymentRecordChartPreview]
    preview_total: int


class PaymentRecordChartCard(BaseModel):
    key: PaymentRecordChartKey
    title: str
    description: str
    buckets: list[PaymentRecordChartBucket]


class PaymentRecordChartResponse(BaseModel):
    population: int = Field(..., description="当前筛选回款笔数")
    total_amount: float = Field(..., description="当前筛选回款金额合计")
    cards: list[PaymentRecordChartCard]


class PaymentRecordChartBucketRecords(BaseModel):
    chart: PaymentRecordChartKey
    bucket: str
    total: int
    records: list[PaymentRecordChartPreview]
