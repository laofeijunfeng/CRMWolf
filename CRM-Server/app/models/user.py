from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    feishu_open_id = Column(String(100), unique=True, index=True, nullable=False, comment="飞书open_id")
    feishu_union_id = Column(String(100), index=True, comment="飞书union_id")
    feishu_user_id = Column(String(100), index=True, comment="飞书user_id")
    name = Column(String(100), nullable=False, comment="用户姓名")
    en_name = Column(String(100), comment="用户英文名")
    email = Column(String(255), index=True, comment="用户邮箱")
    mobile = Column(String(20), comment="用户手机号")
    avatar_url = Column(String(500), comment="用户头像URL")
    employee_no = Column(String(50), comment="用户工号")
    tenant_key = Column(String(100), comment="企业标识")
    region = Column(String(50), comment="所属地区")
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE, comment="用户状态")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name}, email={self.email})>"
