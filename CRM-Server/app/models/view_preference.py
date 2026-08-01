"""
视图偏好模型

保存用户或团队对列表视图的展示偏好。字段定义仍由前端代码维护，
这里仅保存列顺序、显隐、宽度等偏好 JSON。
"""
import enum

from sqlalchemy import BigInteger, Column, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class ViewPreferenceScope(str, enum.Enum):
    PERSONAL = "personal"
    TEAM = "team"


class ViewPreference(Base):
    """列表视图偏好配置"""
    __tablename__ = "crm_view_preferences"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, server_default="0", comment="用户ID，团队级配置为0")
    view_key = Column(String(100), nullable=False, comment="视图标识，如 customers.list")
    scope = Column(String(20), nullable=False, comment="作用域：personal/team")
    preference_key = Column(String(120), nullable=False, server_default="default", comment="偏好标识，默认偏好为default")
    name = Column(String(100), nullable=True, comment="视图名称")
    is_default = Column(BigInteger, nullable=False, server_default="1", comment="是否默认视图")
    sort_order = Column(BigInteger, nullable=True, comment="自定义视图排序值，越小越靠前")
    config_json = Column(Text, nullable=False, comment="视图偏好JSON")
    created_by = Column(BigInteger, nullable=False, comment="创建人ID")
    updated_by = Column(BigInteger, nullable=False, comment="更新人ID")
    created_time = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "view_key", "scope", "user_id", "preference_key", name="uk_view_pref_owner_key"),
        Index("idx_view_pref_team_view", "team_id", "view_key"),
        Index("idx_view_pref_user", "team_id", "user_id"),
        {"comment": "视图偏好配置表"},
    )
