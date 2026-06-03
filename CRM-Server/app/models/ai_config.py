"""
AI 配置模型
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, Index
from sqlalchemy.sql import func
from app.core.database import Base
from cryptography.fernet import Fernet
import base64
import os


# 生成有效的 Fernet key（从固定种子生成）
# Fernet key 必须是 32 url-safe base64-encoded bytes
def _generate_fernet_key(seed: str) -> bytes:
    """从种子字符串生成有效的 Fernet key"""
    # 使用种子字符串生成 32 字节的 key，然后 base64 编码
    seed_bytes = seed.encode('utf-8')
    # 填充或截断到 32 字节
    padded = seed_bytes.ljust(32)[:32]
    # 转换为 URL-safe base64 编码（Fernet 要求）
    return base64.urlsafe_b64encode(padded)


# 加密密钥（从环境变量获取，或使用默认值）
_ENCRYPTION_SEED = os.environ.get("AI_KEY_ENCRYPTION_KEY", "CRMWolf_AI_Encryption_Key_2024!!")
ENCRYPTION_KEY = _generate_fernet_key(_ENCRYPTION_SEED)


class AIConfig(Base):
    """AI 配置模型（单条记录存储）"""
    __tablename__ = "crm_ai_config"

    id = Column(Integer, primary_key=True, default=1)  # 固定为1，只存储一条配置
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    api_host = Column(String(255), nullable=False, comment="AI接口基础地址（如 https://api.deepseek.com/v1）")
    api_key_encrypted = Column(String(255), nullable=False, comment="加密后的API密钥")
    model_name = Column(String(100), nullable=False, comment="模型名称（如 deepseek-chat）")
    temperature = Column(Float, nullable=False, default=0.1, comment="温度参数（固定0.1）")
    max_tokens = Column(Integer, nullable=False, default=1024, comment="最大tokens（固定1024）")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    updated_by = Column(Integer, comment="更新人ID")

    __table_args__ = (
        Index('idx_crm_ai_config_team_id', 'team_id'),
        {'comment': 'AI配置表'}
    )

    def __repr__(self):
        return f"<AIConfig(id={self.id}, api_host={self.api_host}, model_name={self.model_name})>"

    @staticmethod
    def encrypt_api_key(api_key: str) -> str:
        """加密 API Key"""
        fernet = Fernet(ENCRYPTION_KEY)
        return fernet.encrypt(api_key.encode()).decode()

    @staticmethod
    def decrypt_api_key(encrypted_key: str) -> str:
        """解密 API Key"""
        fernet = Fernet(ENCRYPTION_KEY)
        return fernet.decrypt(encrypted_key.encode()).decode()

    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """掩码 API Key（返回前8位 + ****）"""
        if len(api_key) <= 8:
            return "****"
        return api_key[:8] + "****"