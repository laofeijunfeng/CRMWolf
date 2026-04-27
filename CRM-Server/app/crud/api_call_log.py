from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app.models.api_call_log import ApiCallLog


class ApiCallLogCRUD:
    def get_by_id(self, db: Session, log_id: int) -> Optional[ApiCallLog]:
        return db.query(ApiCallLog).filter(ApiCallLog.id == log_id).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        key_id: Optional[str] = None,
        request_path: Optional[str] = None,
        response_code: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[ApiCallLog]:
        query = db.query(ApiCallLog)

        if key_id:
            query = query.filter(ApiCallLog.key_id == key_id)
        if request_path:
            query = query.filter(ApiCallLog.request_path == request_path)
        if response_code:
            query = query.filter(ApiCallLog.response_code == response_code)
        if start_time:
            query = query.filter(ApiCallLog.request_time >= start_time)
        if end_time:
            query = query.filter(ApiCallLog.request_time <= end_time)

        return query.order_by(ApiCallLog.request_time.desc()).offset(skip).limit(limit).all()

    def create(
        self,
        db: Session,
        key_id: str,
        app_name: Optional[str],
        request_method: str,
        request_path: str,
        request_params: Optional[dict],
        request_body: Optional[str],
        response_code: int,
        response_body: Optional[str],
        client_ip: Optional[str],
        user_agent: Optional[str],
        duration_ms: int,
        request_time: Optional[datetime] = None
    ) -> ApiCallLog:
        db_obj = ApiCallLog(
            key_id=key_id,
            app_name=app_name,
            request_method=request_method,
            request_path=request_path,
            request_params=request_params,
            request_body=request_body,
            response_code=response_code,
            response_body=response_body,
            client_ip=client_ip,
            user_agent=user_agent,
            duration_ms=duration_ms,
            request_time=request_time or datetime.utcnow()
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_stats_by_key_id(
        self,
        db: Session,
        key_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> dict:
        """获取指定 Key 的调用统计"""
        query = db.query(ApiCallLog).filter(ApiCallLog.key_id == key_id)

        if start_time:
            query = query.filter(ApiCallLog.request_time >= start_time)
        if end_time:
            query = query.filter(ApiCallLog.request_time <= end_time)

        logs = query.all()

        total_calls = len(logs)
        success_calls = len([l for l in logs if l.response_code == 0])
        error_calls = total_calls - success_calls
        avg_duration = sum(l.duration_ms for l in logs) / total_calls if total_calls > 0 else 0

        return {
            "total_calls": total_calls,
            "success_calls": success_calls,
            "error_calls": error_calls,
            "avg_duration_ms": round(avg_duration, 2)
        }

    def delete_old_logs(self, db: Session, before_date: datetime) -> int:
        """删除指定日期之前的日志（用于清理）"""
        count = db.query(ApiCallLog).filter(ApiCallLog.request_time < before_date).delete()
        db.commit()
        return count


api_call_log_crud = ApiCallLogCRUD()