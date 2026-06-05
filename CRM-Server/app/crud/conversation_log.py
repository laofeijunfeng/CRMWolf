"""
会话日志 CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from app.models.conversation_log import ConversationLog


class ConversationLogCRUD:
    """会话日志 CRUD 操作"""

    def create_log(
        self,
        db: Session,
        user_id: Optional[int] = None,
        channel_user_id: str = None,
        channel_type: str = "feishu",
        request_text: str = None,
        ai_skill: Optional[str] = None,
        ai_action: Optional[str] = None,
        ai_params: Optional[Dict[str, Any]] = None,
        ai_reply_text: Optional[str] = None,
        execution_result: Optional[str] = None,
        status: str = "PENDING",
        error_message: Optional[str] = None,
        session_id: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        team_id: Optional[int] = None
    ) -> ConversationLog:
        """创建会话日志"""
        db_obj = ConversationLog(
            team_id=team_id or 1,
            user_id=user_id,
            channel_user_id=channel_user_id,
            channel_type=channel_type,
            request_text=request_text,
            ai_skill=ai_skill,
            ai_action=ai_action,
            ai_params=ai_params,
            ai_reply_text=ai_reply_text,
            execution_result=execution_result,
            status=status,
            error_message=error_message,
            session_id=session_id,
            context_data=context_data
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_result(
        self,
        db: Session,
        log_id: int,
        execution_result: Optional[str] = None,
        status: str = None,
        error_message: Optional[str] = None
    ) -> Optional[ConversationLog]:
        """更新执行结果"""
        db_obj = db.query(ConversationLog).filter(ConversationLog.id == log_id).first()
        if db_obj:
            if execution_result:
                db_obj.execution_result = execution_result
            if status:
                db_obj.status = status
            if error_message:
                db_obj.error_message = error_message
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def get_logs_by_user(self, db: Session, user_id: int, limit: int = 50) -> List[ConversationLog]:
        """获取用户的会话日志"""
        return db.query(ConversationLog)\
            .filter(ConversationLog.user_id == user_id)\
            .order_by(ConversationLog.created_at.desc())\
            .limit(limit)\
            .all()

    def get_logs_by_channel_user_id(self, db: Session, channel_user_id: str, limit: int = 50) -> List[ConversationLog]:
        """根据渠道用户标识获取会话日志"""
        return db.query(ConversationLog)\
            .filter(ConversationLog.channel_user_id == channel_user_id)\
            .order_by(ConversationLog.created_at.desc())\
            .limit(limit)\
            .all()

    def get_by_id(self, db: Session, log_id: int) -> Optional[ConversationLog]:
        """获取单条日志"""
        return db.query(ConversationLog).filter(ConversationLog.id == log_id).first()

    def get_by_session(self, db: Session, session_id: str, limit: int = 10) -> List[ConversationLog]:
        """根据会话 ID 获取历史日志（多轮对话）"""
        return db.query(ConversationLog)\
            .filter(ConversationLog.session_id == session_id)\
            .order_by(ConversationLog.created_at.asc())\
            .limit(limit)\
            .all()


conversation_log_crud = ConversationLogCRUD()