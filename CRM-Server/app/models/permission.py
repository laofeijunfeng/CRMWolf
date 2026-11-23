from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True, comment="权限名称")
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True, comment="权限代码")
    resource: Mapped[str] = mapped_column(String(50), nullable=False, comment="资源类型")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作类型")
    scope: Mapped[str | None] = mapped_column(String(50), comment="权限范围")
    description: Mapped[str | None] = mapped_column(Text, comment="权限描述")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", comment="是否可用于新授权"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, name={self.name}, code={self.code})>"
