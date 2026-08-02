from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


def _read_secret_file(file_path: str) -> str:
    """从 Docker secrets 文件读取内容"""
    try:
        return Path(file_path).read_text().strip()
    except Exception:
        return ""


class Settings(BaseSettings):
    # 数据库配置(拆分为独立变量, 支持密码特殊字符)
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_PASSWORD_FILE: str = ""  # Docker secrets 文件路径
    DB_NAME: str = "crm_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # 兼容旧配置(如果直接传入 DATABASE_URL, 优先使用)
    DATABASE_URL: str = ""

    SECRET_KEY: str = "your-secret-key-here"
    SECRET_KEY_FILE: str = ""  # Docker secrets 文件路径
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # Redis 配置(用于限流)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # Qdrant 配置(客户智能档案语义证据库)
    QDRANT_ENABLED: bool = True
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_CUSTOMER_EVIDENCE: str = "crm_customer_evidence"
    QDRANT_VECTOR_SIZE: int = 1024
    QDRANT_TIMEOUT_SECONDS: float = 5.0
    CUSTOMER_EVIDENCE_EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
    CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS: int = 1024
    CUSTOMER_EVIDENCE_EMBEDDING_DIMENSION: int = 0
    CUSTOMER_EVIDENCE_EMBEDDING_API_HOST: str = ""
    CUSTOMER_EVIDENCE_EMBEDDING_BASE_URL: str = ""
    CUSTOMER_EVIDENCE_EMBEDDING_API_KEY: str = ""
    CUSTOMER_EVIDENCE_EMBEDDING_API_KEY_FILE: str = ""
    CUSTOMER_EVIDENCE_SYNC_ENABLED: bool = True
    CUSTOMER_EVIDENCE_SYNC_BATCH_SIZE: int = 50
    CUSTOMER_EVIDENCE_SYNC_INTERVAL_SECONDS: int = 30
    AI_GENERATION_CONCURRENCY: int = 2
    CUSTOMER_INTELLIGENCE_RETRY_ENABLED: bool = True
    CUSTOMER_INTELLIGENCE_RETRY_INTERVAL_SECONDS: int = 60
    CUSTOMER_INTELLIGENCE_RETRY_BATCH_SIZE: int = 20
    CUSTOMER_INTELLIGENCE_BACKFILL_ENABLED: bool = True
    CUSTOMER_INTELLIGENCE_BACKFILL_INTERVAL_SECONDS: int = 300
    CUSTOMER_INTELLIGENCE_BACKFILL_BATCH_SIZE: int = 20

    # 飞书配置(已废弃, 保留兼容)
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    # 前端应用地址(用于飞书通知跳转链接)
    FRONTEND_URL: str = ""  # 例如: https://crm.example.com
    # 后端公网入口地址(用于飞书事件回调等外部系统访问; 通常与 FRONTEND_URL 同域)
    PUBLIC_API_BASE_URL: str = ""  # 例如: https://crm.example.com

    # 文件上传目录。默认跟随后端项目根目录: 本地为 CRM-Server/uploads, 容器内为 /app/uploads。
    UPLOAD_DIR: str = str(Path(__file__).resolve().parents[2] / "uploads")

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

    # AI 工具配置(Phase 3-5 功能开关)
    MULTI_TOOL_ENABLED: bool = True    # 是否启用多工具返回(parsed_multi)
    REACT_ENABLED: bool = True         # 是否启用 ReAct 循环(已稳定, 开启)
    AGENT_ENABLED: bool = False        # Agent 模式总开关(关闭则使用原有单工具模式)
    WORKFLOW_ENABLED: bool = True      # Workflow 模式开关(业务流程硬编码编排)
    REACT_MAX_ROUNDS: int = 10         # ReAct 最大轮数
    REACT_SINGLE_ROUND_TIMEOUT: int = 30  # 单轮超时(秒)
    REACT_TOTAL_TIMEOUT: int = 120     # 总超时(秒)
    AGENT_SESSION_TIMEOUT: int = 1800  # 会话过期时间(秒, 默认30分钟)
    WORKFLOW_SESSION_TIMEOUT: int = 1800  # Workflow Session 过期时间(秒)

    # LangSmith Tracing 配置(用于 AI Assistant 可视化调试)
    LANGCHAIN_TRACING_V2: bool = True  # 是否启用 LangSmith Tracing
    LANGSMITH_API_KEY: str = ""        # LangSmith API Key(从环境变量读取)
    LANGCHAIN_PROJECT: str = "CRMWolf-AI-Assistant"  # LangSmith 项目名称
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"  # LangSmith API 端点

    # Phase E: Agent 资源隔离配置
    AGENT_THREAD_POOL_SIZE: int = 4    # Agent 专用线程池大小
    AGENT_MAX_CONCURRENT: int = 10     # Agent 最大并发数
    AGENT_TIMEOUT: int = 120           # Agent 执行超时(秒)
    AGENT_USER_RATE_LIMIT: int = 10    # 每用户每分钟请求限制
    AGENT_GLOBAL_RATE_LIMIT: int = 100 # 全局每分钟请求限制
    AGENT_INTERNAL_API_BASE_URL: str = "http://127.0.0.1:8000/api"  # Agent Tool 调用现有后端 API 的基础地址

    def get_database_url(self) -> str:
        """获取数据库连接 URL, 支持密码特殊字符和 Docker secrets"""
        # 如果直接配置了 DATABASE_URL, 优先使用
        if self.DATABASE_URL:
            return self.DATABASE_URL

        # 从 secrets 文件读取密码(如果设置了 DB_PASSWORD_FILE)
        password = self.DB_PASSWORD
        if self.DB_PASSWORD_FILE:
            password = _read_secret_file(self.DB_PASSWORD_FILE)

        # 否则从拆分配置拼接, 自动处理特殊字符
        password_encoded = quote_plus(password)
        return f"mysql+pymysql://{self.DB_USER}:{password_encoded}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    def get_secret_key(self) -> str:
        """获取 SECRET_KEY, 支持从 Docker secrets 文件读取"""
        if self.SECRET_KEY_FILE:
            return _read_secret_file(self.SECRET_KEY_FILE)
        return self.SECRET_KEY

    def get_customer_evidence_embedding_api_key(self) -> str:
        """获取客户证据向量模型 API Key, 支持从 Docker secrets 文件读取"""
        if self.CUSTOMER_EVIDENCE_EMBEDDING_API_KEY_FILE:
            secret_value = _read_secret_file(self.CUSTOMER_EVIDENCE_EMBEDDING_API_KEY_FILE)
            if secret_value:
                return secret_value
        return self.CUSTOMER_EVIDENCE_EMBEDDING_API_KEY

    def get_customer_evidence_embedding_base_url(self) -> str:
        """获取客户证据向量模型 Base URL, 兼容历史 API_HOST 配置名"""
        return self.CUSTOMER_EVIDENCE_EMBEDDING_BASE_URL or self.CUSTOMER_EVIDENCE_EMBEDDING_API_HOST

    def get_customer_evidence_embedding_dimensions(self) -> int:
        """获取客户证据向量维度, 兼容单数 DIMENSION 配置名"""
        return self.CUSTOMER_EVIDENCE_EMBEDDING_DIMENSION or self.CUSTOMER_EVIDENCE_EMBEDDING_DIMENSIONS

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
