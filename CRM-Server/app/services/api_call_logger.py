"""
API 调用日志服务 - 异步记录 API 调用日志
"""
import time
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from app.core.database import SessionLocal
from app.crud.api_call_log import api_call_log_crud
from app.services.data_masker import data_masker


class ApiCallLogger:
    """API 调用日志记录器"""

    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = True

    def log_call(
        self,
        key_id: str,
        app_name: Optional[str],
        request_method: str,
        request_path: str,
        request_params: Optional[Dict],
        request_body: Optional[str],
        response_code: int,
        response_body: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        duration_ms: int
    ):
        """
        异步记录 API 调用日志

        Args:
            key_id: API Key ID
            app_name: 应用名称
            request_method: 请求方法
            request_path: 请求路径
            request_params: 请求参数
            request_body: 请求体
            response_code: 响应码
            response_body: 响应体
            client_ip: 客户端 IP
            user_agent: User-Agent
            duration_ms: 耗时（毫秒）
        """
        # 在后台线程中执行日志记录
        self.executor.submit(
            self._write_log,
            key_id,
            app_name,
            request_method,
            request_path,
            request_params,
            request_body,
            response_code,
            response_body,
            client_ip,
            user_agent,
            duration_ms
        )

    def _write_log(
        self,
        key_id: str,
        app_name: Optional[str],
        request_method: str,
        request_path: str,
        request_params: Optional[Dict],
        request_body: Optional[str],
        response_code: int,
        response_body: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        duration_ms: int
    ):
        """在独立线程中写入日志"""
        db = SessionLocal()
        try:
            # 脱敏处理
            masked_params = data_masker.mask_request_params(request_params)
            masked_request_body = data_masker.mask_response_body(request_body, max_length=500)
            masked_response_body = data_masker.mask_response_body(response_body, max_length=1000)

            api_call_log_crud.create(
                db=db,
                key_id=key_id,
                app_name=app_name,
                request_method=request_method,
                request_path=request_path,
                request_params=masked_params,
                request_body=masked_request_body,
                response_code=response_code,
                response_body=masked_response_body,
                client_ip=client_ip,
                user_agent=user_agent,
                duration_ms=duration_ms
            )
        except Exception as e:
            print(f"API 调用日志记录失败: {e}")
        finally:
            db.close()

    def shutdown(self):
        """关闭日志服务"""
        self._running = False
        self.executor.shutdown(wait=True)


# 全局单例
api_call_logger = ApiCallLogger()