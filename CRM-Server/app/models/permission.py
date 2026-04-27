from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True, comment="权限名称")
    code = Column(String(100), unique=True, nullable=False, index=True, comment="权限代码")
    resource = Column(String(50), nullable=False, comment="资源类型")
    action = Column(String(50), nullable=False, comment="操作类型")
    scope = Column(String(50), comment="权限范围")
    description = Column(Text, comment="权限描述")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<Permission(id={self.id}, name={self.name}, code={self.code})>"
