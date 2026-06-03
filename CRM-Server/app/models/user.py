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
    email = Column(String(255), unique=True, index=True, nullable=False, comment="邮箱（主登录标识）")
    password_hash = Column(String(255), nullable=True, comment="密码哈希（可选）")
    name = Column(String(100), nullable=False, comment="用户姓名")
    mobile = Column(String(20), nullable=True, comment="用户手机号")
    avatar_url = Column(String(500), nullable=True, comment="用户头像URL")
    employee_no = Column(String(50), nullable=True, comment="用户工号")
    region = Column(String(50), nullable=True, comment="所属地区")
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE, comment="用户状态")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 废弃字段（nullable，兼容旧数据迁移）
    feishu_open_id = Column(String(100), nullable=True, index=True, comment="飞书open_id（已废弃）")
    feishu_union_id = Column(String(100), nullable=True, comment="飞书union_id（已废弃）")
    feishu_user_id = Column(String(100), nullable=True, comment="飞书user_id（已废弃）")
    en_name = Column(String(100), nullable=True, comment="用户英文名（已废弃）")
    tenant_key = Column(String(100), nullable=True, comment="企业标识（已废弃）")

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name}, email={self.email})>"
