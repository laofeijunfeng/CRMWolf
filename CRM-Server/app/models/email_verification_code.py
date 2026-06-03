import enum
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum
from sqlalchemy.sql import func
from app.core.database import Base


class VerificationPurpose(str, enum.Enum):
    REGISTER = "register"
    LOGIN = "login"
    RESET_PASSWORD = "reset_password"


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True, comment="邮箱地址")
    code = Column(String(6), nullable=False, comment="6位验证码")
    purpose = Column(Enum(VerificationPurpose), nullable=False, comment="验证码用途")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    used = Column(Boolean, default=False, comment="是否已使用")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")

    def __repr__(self):
        return f"<EmailVerificationCode(id={self.id}, email={self.email}, purpose={self.purpose})>"