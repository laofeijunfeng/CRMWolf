from sqlalchemy import Column, Integer, BigInteger, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class UserRole(Base):
    """
    用户-角色-团队关联表

    支持用户在不同团队拥有不同角色：
    - 同一用户在不同团队可分配不同角色
    - 角色定义保持全局统一（roles 表无 team_id）
    - 唯一约束：(user_id, team_id, role_id)
    """
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True, comment="角色ID")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")

    # 唯一约束：同一用户在同一团队不能重复分配同一角色
    __table_args__ = (
        UniqueConstraint('user_id', 'team_id', 'role_id', name='uq_user_role_team'),
    )

    def __repr__(self):
        return f"<UserRole(user_id={self.user_id}, role_id={self.role_id}, team_id={self.team_id})>"
