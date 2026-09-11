"""Workflow schemas: Pydantic boundary for /v1/workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

WorkflowStatusLiteral = Literal["draft", "published", "paused"]


class WorkflowDslSchema(BaseModel):
    """CRMWolf Workflow DSL（schema_version 1）。结构校验由 workflow_dsl 服务执行。"""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(..., description="DSL 版本，当前为 1")
    nodes: list[dict[str, Any]] = Field(..., description="节点列表")
    edges: list[dict[str, Any]] = Field(default_factory=list, description="边列表")


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="工作流名称")
    description: Optional[str] = Field(None, description="描述")
    dsl: WorkflowDslSchema


class WorkflowUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="工作流名称")
    description: Optional[str] = Field(None, description="描述")
    dsl: WorkflowDslSchema
    expected_last_modified_time: datetime = Field(
        ..., description="乐观锁：客户端读取时的 last_modified_time"
    )


class WorkflowStatusUpdate(BaseModel):
    status: WorkflowStatusLiteral


class WorkflowSummary(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: WorkflowStatusLiteral
    node_count: int
    created_time: datetime
    last_modified_time: datetime


class WorkflowDetail(WorkflowSummary):
    dsl: WorkflowDslSchema
    created_by: Optional[int] = None
