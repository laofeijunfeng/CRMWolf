from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import random

from app.models.email_verification_code import EmailVerificationCode, VerificationPurpose
from app.core.config import get_settings

settings = get_settings()


class EmailVerificationCodeCRUD:
    def create(
        self,
        db: Session,
        email: str,
        purpose: VerificationPurpose
    ) -> EmailVerificationCode:
        """创建验证码"""
        code = self._generate_code()
        expires_at = datetime.utcnow() + timedelta(minutes=settings.VERIFICATION_CODE_EXPIRE_MINUTES)

        db_obj = EmailVerificationCode(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=expires_at,
            used=False
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def _generate_code(self) -> str:
        """生成6位数字验证码"""
        return str(random.randint(100000, 999999))

    def get_valid_code(
        self,
        db: Session,
        email: str,
        code: str,
        purpose: VerificationPurpose
    ) -> Optional[EmailVerificationCode]:
        """获取有效的验证码"""
        now = datetime.utcnow()
        return db.query(EmailVerificationCode).filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.code == code,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.expires_at > now,
            EmailVerificationCode.used == False
        ).first()

    def mark_used(self, db: Session, db_obj: EmailVerificationCode) -> EmailVerificationCode:
        """标记验证码已使用"""
        db_obj.used = True
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete_expired(self, db: Session) -> int:
        """删除过期验证码"""
        now = datetime.utcnow()
        count = db.query(EmailVerificationCode).filter(
            EmailVerificationCode.expires_at < now
        ).delete()
        db.commit()
        return count


email_verification_code_crud = EmailVerificationCodeCRUD()