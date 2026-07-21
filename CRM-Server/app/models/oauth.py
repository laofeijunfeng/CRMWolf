"""
OAuth 登录集成模型
"""
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.ai_config import AIConfig


class OAuthProviderConfig(Base):
    """团队级第三方登录配置"""
    __tablename__ = "oauth_provider_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, index=True, comment="团队ID")
    provider = Column(String(32), nullable=False, comment="OAuth 提供方")
    app_id = Column(String(128), nullable=False, comment="应用 ID")
    app_secret_encrypted = Column(String(1000), nullable=True, comment="加密后的应用密钥")
    redirect_uri = Column(String(500), nullable=False, comment="授权回调地址")
    enabled = Column(Boolean, nullable=False, default=False, comment="是否启用")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "provider", name="uq_oauth_provider_config_team_provider"),
        Index("idx_oauth_provider_configs_team_provider", "team_id", "provider"),
    )

    @staticmethod
    def encrypt_secret(secret: str) -> str:
        return AIConfig.encrypt_api_key(secret)

    @staticmethod
    def decrypt_secret(encrypted_secret: str) -> str:
        return AIConfig.decrypt_api_key(encrypted_secret)


class UserOAuthAccount(Base):
    """用户第三方账号绑定"""
    __tablename__ = "user_oauth_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="CRM 用户ID")
    team_id = Column(Integer, nullable=False, index=True, comment="团队ID")
    provider = Column(String(32), nullable=False, comment="OAuth 提供方")
    provider_user_id = Column(String(128), nullable=True, comment="提供方用户ID")
    open_id = Column(String(128), nullable=True, comment="Open ID")
    union_id = Column(String(128), nullable=True, comment="Union ID")
    tenant_key = Column(String(128), nullable=True, comment="租户标识")
    email = Column(String(255), nullable=True, comment="邮箱")
    mobile = Column(String(32), nullable=True, comment="手机号")
    name = Column(String(100), nullable=True, comment="第三方用户名")
    avatar_url = Column(String(500), nullable=True, comment="头像")
    raw_profile = Column(JSON().with_variant(Text(), "sqlite"), nullable=True, comment="原始用户资料")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "provider", "open_id", name="uq_user_oauth_team_provider_open_id"),
        UniqueConstraint("team_id", "provider", "user_id", name="uq_user_oauth_team_provider_user"),
        Index("idx_user_oauth_accounts_lookup", "team_id", "provider", "open_id"),
    )
