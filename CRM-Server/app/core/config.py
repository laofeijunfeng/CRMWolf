from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:N0k2x4gzjnbbH3zEmDPW@localhost:3306/crm_db"
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # Redis 配置（用于限流）
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # 飞书配置
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    # AI 配置
    AI_API_URL: str = "https://api.openai.com/v1/chat/completions"
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-3.5-turbo"
    AI_TIMEOUT: int = 180

    # 开放接口配置
    OPENAPI_RATE_LIMIT_TPS: int = 100  # 默认 TPS
    OPENAPI_BURST_LIMIT: int = 200     # 突发限制

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
