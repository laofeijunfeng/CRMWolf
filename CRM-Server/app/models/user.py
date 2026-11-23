import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base):
    __tablename__ = "users"

    if TYPE_CHECKING:
        # Authenticated request state, not a mapped field.
        _token_payload: dict[str, object]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False, comment="邮箱\uff08主登录标识\uff09"
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="密码哈希\uff08可选\uff09")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="用户姓名")
    mobile: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="用户手机号")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="用户头像URL")
    employee_no: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="用户工号")
    region: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="所属地区")
    status: Mapped[UserStatus | None] = mapped_column(
        Enum(UserStatus), default=UserStatus.ACTIVE, nullable=True, comment="用户状态"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True, comment="创建时间"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 废弃字段(nullable,兼容旧数据迁移)
    feishu_open_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True, comment="飞书open_id\uff08已废弃\uff09"
    )
    feishu_union_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="飞书union_id\uff08已废弃\uff09"
    )
    feishu_user_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="飞书user_id\uff08已废弃\uff09"
    )
    en_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="用户英文名\uff08已废弃\uff09")
    tenant_key: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="企业标识\uff08已废弃\uff09")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name={self.name}, email={self.email})>"
