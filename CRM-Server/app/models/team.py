"""
团队模型

支持多团队模式\uff1a
- 用户可同时加入多个团队
- 通过 user_teams 关联表管理用户-团队关系
- current_team 标记当前活跃团队
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Team(Base):
    """团队表"""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="团队名称")
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True, comment="邀请码")
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="创建者ID"
    )
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="预留层级\uff08单级团队为NULL\uff09")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True, comment="创建时间"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关系
    members: Mapped[list["UserTeam"]] = relationship("UserTeam", back_populates="team", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name={self.name}, code={self.code})>"


class UserTeam(Base):
    """用户-团队关联表\uff08多团队模式\uff09"""
    __tablename__ = "user_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID"
    )
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True, comment="团队ID"
    )
    current_team: Mapped[bool | None] = mapped_column(
        Boolean, default=False, nullable=True, comment="是否为当前活跃团队"
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True, comment="加入时间"
    )

    # 每个用户在同一团队只能有一条记录
    __table_args__ = (UniqueConstraint('user_id', 'team_id', name='uq_user_team'),)

    # 关系
    team: Mapped[Team] = relationship("Team", back_populates="members")

    def __repr__(self) -> str:
        return f"<UserTeam(user_id={self.user_id}, team_id={self.team_id}, current={self.current_team})>"