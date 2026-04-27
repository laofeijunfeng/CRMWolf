from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from app.core.database import Base


class ApiCallLog(Base):
    __tablename__ = "crm_api_call_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # API Key 信息
    key_id = Column(String(32), nullable=False, comment="API Key ID")
    app_name = Column(String(100), nullable=True, comment="应用名称")

    # 请求信息
    request_method = Column(String(10), nullable=False, comment="请求方法（GET/POST/PUT/PATCH/DELETE）")
    request_path = Column(String(255), nullable=False, comment="请求路径")
    request_params = Column(JSON, nullable=True, comment="请求参数（脱敏后）")
    request_body = Column(Text, nullable=True, comment="请求体（脱敏后）")

    # 响应信息
    response_code = Column(Integer, nullable=False, comment="响应码")
    response_body = Column(Text, nullable=True, comment="响应体（脱敏后）")

    # 客户端信息
    client_ip = Column(String(50), nullable=True, comment="客户端IP")
    user_agent = Column(String(255), nullable=True, comment="User-Agent")

    # 性能指标
    duration_ms = Column(Integer, nullable=False, comment="请求耗时（毫秒）")

    # 时间戳
    request_time = Column(DateTime, nullable=False, default=func.now(), comment="请求时间")

    __table_args__ = (
        Index('idx_key_id', 'key_id'),
        Index('idx_request_path', 'request_path'),
        Index('idx_request_time', 'request_time'),
        Index('idx_response_code', 'response_code'),
        Index('idx_app_name', 'app_name'),
        {'comment': 'API调用日志表'}
    )

    def __repr__(self):
        return f"<ApiCallLog(id={self.id}, key_id={self.key_id}, request_path={self.request_path}, response_code={self.response_code})>"