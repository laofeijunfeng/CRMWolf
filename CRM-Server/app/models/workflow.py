import json
from typing import TypeAlias, cast

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, String, Text, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeEngine

from app.core.database import Base
from app.utils.time import business_now

_JSONScalar: TypeAlias = str | int | float | bool | None
_JSONValue: TypeAlias = _JSONScalar | list["_JSONValue"] | dict[str, "_JSONValue"]


class WorkflowDslType(TypeDecorator[_JSONValue]):
    """Store workflow DSL as native JSON where supported and serialized text on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[str] | TypeEngine[_JSONValue]:
        return dialect.type_descriptor(Text() if dialect.name == "sqlite" else JSON())

    def process_bind_param(self, value: _JSONValue, dialect: Dialect) -> _JSONValue:
        if value is None or dialect.name != "sqlite":
            return value
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: _JSONValue, _dialect: Dialect) -> _JSONValue:
        if isinstance(value, str):
            try:
                return cast(_JSONValue, json.loads(value))
            except (TypeError, ValueError):
                return value
        return value


class WorkflowStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"


VALID_TRANSITIONS = {
    WorkflowStatus.DRAFT: {WorkflowStatus.PUBLISHED},
    WorkflowStatus.PUBLISHED: {WorkflowStatus.PAUSED},
    WorkflowStatus.PAUSED: {WorkflowStatus.PUBLISHED},
}


class Workflow(Base):
    """CRMWolf workflow definition with a version-1 DSL."""

    __tablename__ = "crm_workflows"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID\uff08NULL表示系统级\uff09")
    name = Column(String(100), nullable=False, comment="工作流名称")
    description = Column(Text, nullable=True, comment="描述")
    status = Column(String(20), nullable=False, default=WorkflowStatus.DRAFT, comment="draft/published/paused")
    dsl = Column(WorkflowDslType, nullable=False, comment="Workflow DSL JSON")
    created_by = Column(BigInteger, nullable=True, comment="创建人用户ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=business_now,
                                onupdate=business_now, comment="最后修改时间\uff08兼乐观锁版本\uff09")

    __table_args__ = (
        Index('idx_crm_workflows_team_id', 'team_id'),
        Index('idx_crm_workflows_status', 'status'),
        {'comment': 'CRMWolf 工作流定义表'}
    )
