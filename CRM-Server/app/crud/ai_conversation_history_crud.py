"""
AI 对话历史 CRUD

用于管理用户的 AI 助手对话历史记录
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.models.ai_conversation_history import AIConversationHistory


class AIConversationHistoryCRUD:
    """AI 对话历史 CRUD 操作"""

    def create(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        title: str,
        messages: List[Dict[str, Any]],
        action_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        summary: Optional[str] = None,
        status: str = "active"
    ) -> AIConversationHistory:
        """创建对话历史"""
        db_obj = AIConversationHistory(
            team_id=team_id,
            user_id=user_id,
            title=title,
            summary=summary,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            messages=messages,
            status=status
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_id(
        self,
        db: Session,
        id: int,
        team_id: int
    ) -> Optional[AIConversationHistory]:
        """获取单个对话历史（团队隔离）"""
        return db.query(AIConversationHistory)\
            .filter(AIConversationHistory.id == id)\
            .filter(AIConversationHistory.team_id == team_id)\
            .filter(AIConversationHistory.status != "deleted")\
            .first()

    def get_multi(
        self,
        db: Session,
        team_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        status: str = "active"
    ) -> List[AIConversationHistory]:
        """获取对话历史列表（团队隔离）"""
        query = db.query(AIConversationHistory)\
            .filter(AIConversationHistory.team_id == team_id)\
            .filter(AIConversationHistory.status == status)

        if user_id:
            query = query.filter(AIConversationHistory.user_id == user_id)

        return query\
            .order_by(AIConversationHistory.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()

    def get_by_date_groups(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        limit: int = 50
    ) -> Dict[str, List[AIConversationHistory]]:
        """按日期分组获取对话历史"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start
        earlier_start = yesterday_start - timedelta(days=30)  # 最近30天

        # 获取所有对话
        all_conversations = self.get_multi(
            db,
            team_id=team_id,
            user_id=user_id,
            limit=limit
        )

        # 按日期分组
        groups: Dict[str, List[AIConversationHistory]] = {
            "today": [],
            "yesterday": [],
            "earlier": []
        }

        for conv in all_conversations:
            created_at = conv.created_at
            if created_at >= today_start:
                groups["today"].append(conv)
            elif created_at >= yesterday_start and created_at < yesterday_end:
                groups["yesterday"].append(conv)
            else:
                groups["earlier"].append(conv)

        return groups

    def update(
        self,
        db: Session,
        id: int,
        team_id: int,
        **kwargs: Any
    ) -> Optional[AIConversationHistory]:
        """更新对话历史"""
        db_obj = self.get_by_id(db, id, team_id)
        if db_obj:
            for key, value in kwargs.items():
                if hasattr(db_obj, key):
                    setattr(db_obj, key, value)
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def update_messages(
        self,
        db: Session,
        id: int,
        team_id: int,
        messages: List[Dict[str, Any]]
    ) -> Optional[AIConversationHistory]:
        """更新对话消息列表"""
        return self.update(db, id, team_id, messages=messages)

    def delete(
        self,
        db: Session,
        id: int,
        team_id: int
    ) -> bool:
        """删除对话历史（软删除）"""
        db_obj = self.get_by_id(db, id, team_id)
        if db_obj:
            db_obj.status = "deleted"
            db.commit()
            return True
        return False

    def hard_delete(
        self,
        db: Session,
        id: int,
        team_id: int
    ) -> bool:
        """硬删除对话历史"""
        db_obj = db.query(AIConversationHistory)\
            .filter(AIConversationHistory.id == id)\
            .filter(AIConversationHistory.team_id == team_id)\
            .first()
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False

    def search(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        keyword: str,
        limit: int = 10
    ) -> List[AIConversationHistory]:
        """搜索对话历史"""
        return db.query(AIConversationHistory)\
            .filter(AIConversationHistory.team_id == team_id)\
            .filter(AIConversationHistory.user_id == user_id)\
            .filter(AIConversationHistory.status == "active")\
            .filter(AIConversationHistory.title.contains(keyword))\
            .order_by(AIConversationHistory.created_at.desc())\
            .limit(limit)\
            .all()

    def count(
        self,
        db: Session,
        team_id: int,
        user_id: Optional[int] = None
    ) -> int:
        """统计对话数量"""
        query = db.query(AIConversationHistory)\
            .filter(AIConversationHistory.team_id == team_id)\
            .filter(AIConversationHistory.status == "active")

        if user_id:
            query = query.filter(AIConversationHistory.user_id == user_id)

        return query.count()


ai_conversation_history_crud = AIConversationHistoryCRUD()