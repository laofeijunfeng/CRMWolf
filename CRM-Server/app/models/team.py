"""
团队模型

支持多团队模式：
- 用户可同时加入多个团队
- 通过 user_teams 关联表管理用户-团队关系
- current_team 标记当前活跃团队
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Team(Base):
    """团队表"""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="团队名称")
    code = Column(String(20), unique=True, nullable=False, index=True, comment="邀请码")
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="创建者ID")
    parent_id = Column(Integer, nullable=True, comment="预留层级（单级团队为NULL）")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    members = relationship("UserTeam", back_populates="team", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Team(id={self.id}, name={self.name}, code={self.code})>"


class UserTeam(Base):
    """用户-团队关联表（多团队模式）"""
    __tablename__ = "user_teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True, comment="团队ID")
    current_team = Column(Boolean, default=False, comment="是否为当前活跃团队")
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), comment="加入时间")

    # 每个用户在同一团队只能有一条记录
    __table_args__ = (UniqueConstraint('user_id', 'team_id', name='uq_user_team'),)

    # 关系
    team = relationship("Team", back_populates="members")

    def __repr__(self):
        return f"<UserTeam(user_id={self.user_id}, team_id={self.team_id}, current={self.current_team})>"