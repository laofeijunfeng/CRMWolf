from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import quote_plus
from pathlib import Path


def _read_secret_file(file_path: str) -> str:
    """从 Docker secrets 文件读取内容"""
    try:
        return Path(file_path).read_text().strip()
    except Exception:
        return ""


class Settings(BaseSettings):
    # 数据库配置（拆分为独立变量，支持密码特殊字符）
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_PASSWORD_FILE: str = ""  # Docker secrets 文件路径
    DB_NAME: str = "crm_db"

    # 兼容旧配置（如果直接传入 DATABASE_URL，优先使用）
    DATABASE_URL: str = ""

    SECRET_KEY: str = "your-secret-key-here"
    SECRET_KEY_FILE: str = ""  # Docker secrets 文件路径
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # Redis 配置（用于限流）
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # 飞书配置（已废弃，保留兼容）
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    # 邮件服务配置
    SMTP_PROVIDER: str = "console"  # console | smtp | aliyun
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "CRMWolf"
    SMTP_USE_SSL: bool = True

    # 阿里云邮件推送专用
    ALIYUN_MAIL_REGION: str = "cn-hangzhou"
    ALIYUN_MAIL_ACCESS_KEY: str = ""
    ALIYUN_MAIL_SECRET_KEY: str = ""

    # 验证码配置
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 10
    VERIFICATION_CODE_LENGTH: int = 6

    # 开放接口配置
    OPENAPI_RATE_LIMIT_TPS: int = 100  # 默认 TPS
    OPENAPI_BURST_LIMIT: int = 200     # 突发限制

    def get_database_url(self) -> str:
        """获取数据库连接 URL，支持密码特殊字符和 Docker secrets"""
        # 如果直接配置了 DATABASE_URL，优先使用
        if self.DATABASE_URL:
            return self.DATABASE_URL

        # 从 secrets 文件读取密码（如果设置了 DB_PASSWORD_FILE）
        password = self.DB_PASSWORD
        if self.DB_PASSWORD_FILE:
            password = _read_secret_file(self.DB_PASSWORD_FILE)

        # 否则从拆分配置拼接，自动处理特殊字符
        password_encoded = quote_plus(password)
        return f"mysql+pymysql://{self.DB_USER}:{password_encoded}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    def get_secret_key(self) -> str:
        """获取 SECRET_KEY，支持从 Docker secrets 文件读取"""
        if self.SECRET_KEY_FILE:
            return _read_secret_file(self.SECRET_KEY_FILE)
        return self.SECRET_KEY

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()