"""Session 管理

Redis 存储对话状态，包括 pending action、recent_entities、history。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 七、Session 数据契约

Task 3.2: 统一 Session API 为 uuid 寻址
- key 从 ai:glue:session:{tenant}:{user} 改为 ai:glue:session:{session_id}
- GlueSession 增加 session_id 字段（uuid4）
- load/save/clear 改为 session_id 入参
- 保留 (tenant_id, crm_user_id) 作为 session 内字段用于权限校验
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from uuid import uuid4
import redis.asyncio as redis

from app.glue.config import GlueConfig, SessionMode


@dataclass
class PendingAction:
    """待确认动作"""

    action_id: str
    intent_type: Optional[str] = None  # 意图类型（create_follow_up, update_amount, ...）
    skill_name: Optional[str] = None  # Skill 名称（兼容旧数据，逐渐废弃）
    slots: Dict[str, Any] = None  # 槽位数据
    missing_slots: list = None  # 缺失的槽位列表
    preview_snapshot: Dict[str, Any] = None  # 预览快照
    ambiguity: Optional[Dict[str, Any]] = None  # {"slot": "customer_id", "candidates": [...]}
    expires_at: Optional[int] = None  # Unix timestamp

    def __post_init__(self):
        if self.slots is None:
            self.slots = {}
        if self.missing_slots is None:
            self.missing_slots = []
        if self.preview_snapshot is None:
            self.preview_snapshot = {}

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now().timestamp() > self.expires_at


@dataclass
class RecentEntities:
    """最近操作的实体"""

    customer_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    touched_at: Optional[int] = None  # Unix timestamp


@dataclass
class HistoryEntry:
    """对话历史条目"""

    role: str  # "user" | "assistant"
    text: str
    ts: int  # Unix timestamp


@dataclass
class GlueSession:
    """胶水层 Session"""

    session_id: str = ""  # UUID，唯一标识 session
    v: int = 1  # 版本号
    tenant_id: str = ""
    crm_user_id: int = 0
    mode: str = SessionMode.IDLE
    updated_at: int = 0  # Unix timestamp

    pending: Optional[PendingAction] = None
    pending_queue: list = None  # 多意图队列（存储多个 PendingAction）
    recent_entities: Optional[RecentEntities] = None
    history_last_n: list = None

    # 实体消解上下文
    entity_resolution_context: Optional[Dict[str, Any]] = None

    # 消歧上下文
    ambiguity_context: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.session_id == "":
            self.session_id = str(uuid4())
        if self.history_last_n is None:
            self.history_last_n = []
        if self.pending_queue is None:
            self.pending_queue = []
        if self.updated_at == 0:
            self.updated_at = int(datetime.now().timestamp())


class SessionManager:
    """Session 管理器

    Redis 存储，支持滑动续期。
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.config = GlueConfig()

    def _session_key(self, session_id: str) -> str:
        """生成 session key

        Task 3.2: key 从 ai:glue:session:{tenant}:{user} 改为 ai:glue:session:{session_id}
        """
        return f"{self.config.SESSION_KEY_PREFIX}:{session_id}"

    async def create(self, tenant_id: str, crm_user_id: int) -> str:
        """创建新 session 并返回 session_id

        Args:
            tenant_id: 租户 ID
            crm_user_id: CRM 用户 ID

        Returns:
            session_id: UUID 格式的 session 标识
        """
        session = GlueSession(
            tenant_id=tenant_id,
            crm_user_id=crm_user_id,
            mode=SessionMode.IDLE,
        )
        await self.save(session)
        return session.session_id

    def _serialize(self, session: GlueSession) -> str:
        """序列化 session"""
        data = {
            "v": session.v,
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "crm_user_id": session.crm_user_id,
            "mode": session.mode,
            "updated_at": session.updated_at,
            "pending": asdict(session.pending) if session.pending else None,
            "pending_queue": [asdict(p) if isinstance(p, PendingAction) else p for p in session.pending_queue],
            "recent_entities": asdict(session.recent_entities) if session.recent_entities else None,
            "history_last_n": [asdict(h) if isinstance(h, HistoryEntry) else h for h in session.history_last_n],
            "entity_resolution_context": session.entity_resolution_context,
            "ambiguity_context": session.ambiguity_context,
        }
        return json.dumps(data)

    def _deserialize(self, data: str) -> GlueSession:
        """反序列化 session"""
        obj = json.loads(data)

        # 重建 pending
        pending = None
        if obj.get("pending"):
            pending_data = obj["pending"]
            pending = PendingAction(
                action_id=pending_data.get("action_id", ""),
                intent_type=pending_data.get("intent_type"),
                skill_name=pending_data.get("skill_name"),  # 兼容旧数据
                slots=pending_data.get("slots", {}),
                missing_slots=pending_data.get("missing_slots", []),
                preview_snapshot=pending_data.get("preview_snapshot", {}),
                ambiguity=pending_data.get("ambiguity"),
                expires_at=pending_data.get("expires_at"),
            )

        # 重建 pending_queue
        pending_queue = []
        for p_data in obj.get("pending_queue", []):
            if isinstance(p_data, dict):
                pending_queue.append(PendingAction(
                    action_id=p_data.get("action_id", ""),
                    intent_type=p_data.get("intent_type"),
                    skill_name=p_data.get("skill_name"),  # 兼容旧数据
                    slots=p_data.get("slots", {}),
                    missing_slots=p_data.get("missing_slots", []),
                    preview_snapshot=p_data.get("preview_snapshot", {}),
                    ambiguity=p_data.get("ambiguity"),
                    expires_at=p_data.get("expires_at"),
                ))
            else:
                pending_queue.append(p_data)

        # 重建 recent_entities
        recent_entities = None
        if obj.get("recent_entities"):
            re_data = obj["recent_entities"]
            recent_entities = RecentEntities(
                customer_id=re_data.get("customer_id"),
                opportunity_id=re_data.get("opportunity_id"),
                touched_at=re_data.get("touched_at"),
            )

        # 重建 history
        history = []
        for h in obj.get("history_last_n", []):
            if isinstance(h, dict):
                history.append(HistoryEntry(
                    role=h.get("role", ""),
                    text=h.get("text", ""),
                    ts=h.get("ts", 0),
                ))
            else:
                history.append(h)

        return GlueSession(
            v=obj.get("v", 1),
            session_id=obj.get("session_id", ""),
            tenant_id=obj.get("tenant_id", ""),
            crm_user_id=obj.get("crm_user_id", 0),
            mode=obj.get("mode", SessionMode.IDLE),
            updated_at=obj.get("updated_at", 0),
            pending=pending,
            pending_queue=pending_queue,
            recent_entities=recent_entities,
            history_last_n=history,
            entity_resolution_context=obj.get("entity_resolution_context"),
            ambiguity_context=obj.get("ambiguity_context"),
        )

    async def load(self, session_id: str) -> Optional[GlueSession]:
        """加载 session

        Args:
            session_id: UUID 格式的 session 标识

        Returns:
            GlueSession 或 None（不存在时）
        """
        key = self._session_key(session_id)
        data = await self.redis.get(key)

        if data:
            # 滑动续期
            await self.redis.expire(key, self.config.SESSION_TTL)
            return self._deserialize(data)

        # 不存在时返回 None
        return None

    async def save(self, session: GlueSession) -> bool:
        """保存 session

        Args:
            session: GlueSession 实例（必须包含 session_id）

        Returns:
            True 表示成功
        """
        key = self._session_key(session.session_id)
        session.updated_at = int(datetime.now().timestamp())
        data = self._serialize(session)

        await self.redis.set(key, data, ex=self.config.SESSION_TTL)
        return True

    async def clear(self, session_id: str) -> bool:
        """清空 session

        Args:
            session_id: UUID 格式的 session 标识

        Returns:
            True 表示成功
        """
        key = self._session_key(session_id)
        await self.redis.delete(key)
        return True

    async def set_pending(self, session: GlueSession, pending: PendingAction) -> bool:
        """设置 pending action"""
        pending.expires_at = int((datetime.now() + timedelta(seconds=self.config.PENDING_EXPIRE)).timestamp())
        session.pending = pending
        session.mode = SessionMode.PREVIEW
        return await self.save(session)

    async def clear_pending(self, session: GlueSession) -> bool:
        """清空 pending action"""
        session.pending = None
        session.mode = SessionMode.IDLE
        return await self.save(session)

    async def update_recent_entities(
        self,
        session: GlueSession,
        entity_type: str,
        entity_id: int,
    ) -> bool:
        """更新最近操作的实体"""
        if session.recent_entities is None:
            session.recent_entities = RecentEntities()

        if entity_type == "Customer":
            session.recent_entities.customer_id = entity_id
        elif entity_type == "Opportunity":
            session.recent_entities.opportunity_id = entity_id

        session.recent_entities.touched_at = int(datetime.now().timestamp())
        return await self.save(session)

    async def add_history(self, session: GlueSession, role: str, text: str) -> bool:
        """添加对话历史"""
        entry = HistoryEntry(
            role=role,
            text=text,
            ts=int(datetime.now().timestamp()),
        )

        session.history_last_n.append(entry)

        # 限制历史长度
        if len(session.history_last_n) > self.config.HISTORY_MAX_LENGTH:
            session.history_last_n = session.history_last_n[-self.config.HISTORY_MAX_LENGTH:]

        return await self.save(session)


__all__ = [
    "PendingAction",
    "RecentEntities",
    "HistoryEntry",
    "GlueSession",
    "SessionManager",
]