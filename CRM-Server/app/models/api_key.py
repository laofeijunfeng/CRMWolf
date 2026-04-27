from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Text, JSON, Index, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import enum
import secrets
import hashlib


class ApiKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


class ApiKey(Base):
    __tablename__ = "crm_api_keys"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # 对外展示的 Key ID（前缀 + 随机字符串，如：key_xxxx）
    key_id = Column(String(32), unique=True, nullable=False, comment="API Key ID（对外展示）")

    # 加密存储的 API Key（SHA-256 哈希）
    api_key_hash = Column(String(64), unique=True, nullable=False, comment="API Key哈希值（SHA-256）")

    # 应用信息
    app_name = Column(String(100), nullable=False, comment="应用名称")
    description = Column(Text, nullable=True, comment="应用描述")

    # 权限配置
    permissions = Column(JSON, nullable=True, comment="权限列表，如：['customer:read', 'customer:list']")

    # IP 白名单
    ip_whitelist = Column(JSON, nullable=True, comment="IP白名单列表")

    # 限流配置
    rate_limit_tps = Column(Integer, nullable=False, default=100, comment="每秒请求限制（TPS）")

    # 状态
    status = Column(Enum(ApiKeyStatus), nullable=False, default=ApiKeyStatus.ACTIVE, comment="状态")

    # 过期时间
    expires_at = Column(DateTime, nullable=True, comment="过期时间（NULL表示永不过期）")

    # 最后使用时间
    last_used_at = Column(DateTime, nullable=True, comment="最后使用时间")

    # 创建人
    created_by = Column(BigInteger, nullable=True, comment="创建人ID")

    # 时间戳
    created_at = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_key_id', 'key_id'),
        Index('idx_status', 'status'),
        Index('idx_app_name', 'app_name'),
        Index('idx_created_at', 'created_at'),
        {'comment': 'API Key管理表'}
    )

    def __repr__(self):
        return f"<ApiKey(id={self.id}, key_id={self.key_id}, app_name={self.app_name}, status={self.status})>"

    @staticmethod
    def generate_key_id() -> str:
        """生成 Key ID（对外展示）"""
        return f"key_{secrets.token_hex(8)}"

    @staticmethod
    def generate_api_key() -> str:
        """生成原始 API Key（仅创建时返回给用户一次）"""
        return f"sk_{secrets.token_hex(16)}"

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """对 API Key 进行 SHA-256 哈希"""
        return hashlib.sha256(api_key.encode()).hexdigest()