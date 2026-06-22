"""
Agent Memory System
会话级记忆 + 最近实体 + 工具调用历史

核心设计：
- 复用现有的 checkpointer（Redis 持久化）
- 会话管理（创建/加载）
- 工具调用历史
- 最近实体记忆
- 上下文文本生成（用于 System Prompt）
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class AgentMemory:
    """Agent 记忆系统"""

    MEMORY_TTL = 1800  # 30分钟 TTL

    def __init__(self, db, team_id: int, user_id: int, redis_client=None):
        """
        初始化记忆系统

        Args:
            db: 数据库会话
            team_id: 团队 ID
            user_id: 用户 ID
            redis_client: Redis 客户端（可选）
        """
        self.db = db
        self.team_id = team_id
        self.user_id = user_id

        # 复用现有的 Redis 客户端
        if redis_client:
            self.redis_client = redis_client
        else:
            # 直接创建 Redis 客户端（不依赖 langgraph）
            import redis
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0)

        # 会话状态
        self.session_id: Optional[str] = None
        self.messages: List[Dict[str, str]] = []
        self.tool_history: List[Dict[str, Any]] = []
        self.recent_entities: Dict[str, Dict[str, Any]] = {}

    def create_session(self) -> str:
        """
        创建新会话

        Returns:
            str: 会话 ID
        """
        import uuid
        self.session_id = str(uuid.uuid4())

        # 初始化会话状态
        self.messages = []
        self.tool_history = []
        self.recent_entities = {}

        # 保存到 Redis
        self._save_session()

        logger.info(f"Session created: {self.session_id}")
        return self.session_id

    def load_session(self, session_id: str):
        """
        加载已有会话

        Args:
            session_id: 会话 ID
        """
        self.session_id = session_id

        # 从 Redis 加载
        session_data = self.redis_client.get(f"agent_session:{session_id}")

        if session_data:
            data = json.loads(session_data)
            self.messages = data.get("messages", [])
            self.tool_history = data.get("tool_history", [])
            self.recent_entities = data.get("recent_entities", {})

            logger.info(f"Session loaded: {session_id}")
        else:
            logger.warning(f"Session not found: {session_id}")
            # 初始化空会话
            self.messages = []
            self.tool_history = []
            self.recent_entities = {}

    def add_user_message(self, message: str):
        """
        添加用户消息

        Args:
            message: 用户输入
        """
        self.messages.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_session()

    def add_agent_message(self, message: str):
        """
        添加 Agent 消息

        Args:
            message: Agent 响应
        """
        self.messages.append({
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_session()

    def add_tool_call(
        self,
        tool_name: str,
        tool_params: Dict[str, Any],
        tool_result: Any,
        reasoning: str,
    ):
        """
        记录工具调用

        Args:
            tool_name: 工具名称
            tool_params: 工具参数
            tool_result: 工具结果
            reasoning: 推理过程
        """
        self.tool_history.append({
            "tool_name": tool_name,
            "tool_params": tool_params,
            "tool_result": tool_result,
            "reasoning": reasoning,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_session()

    def update_recent_entity(self, entity_type: str, entity_id: int, entity_name: str):
        """
        更新最近实体

        Args:
            entity_type: 实体类型（Customer、Opportunity）
            entity_id: 实体 ID
            entity_name: 实体名称
        """
        self.recent_entities[entity_type] = {
            "id": entity_id,
            "name": entity_name,
            "timestamp": datetime.now().isoformat(),
        }
        self._save_session()

        logger.info(f"Recent entity updated: {entity_type}={entity_name} (ID: {entity_id})")

    def get_context(self) -> str:
        """
        获取当前上下文

        Returns:
            str: 上下文文本（用于 System Prompt）
        """
        context = f"当前日期：{datetime.now().strftime('%Y-%m-%d')}\n"
        context += f"当前用户：用户ID={self.user_id}\n"
        context += f"当前团队：团队ID={self.team_id}\n"

        if self.recent_entities:
            context += "\n【最近操作的实体】\n"
            for entity_type, entity_info in self.recent_entities.items():
                context += f"- {entity_type}: {entity_info['name']} (ID: {entity_info['id']})\n"

        if self.messages:
            context += "\n【会话历史】\n"
            for msg in self.messages[-5:]:  # 最近5条消息
                role = "用户" if msg['role'] == "user" else "AI"
                context += f"- {role}: {msg['content']}\n"

        return context

    def get_tool_history(self) -> List[Dict[str, Any]]:
        """
        获取工具调用历史

        Returns:
            List[Dict]: 工具历史
        """
        return self.tool_history

    def get_recent_entities(self) -> Dict[str, Any]:
        """
        获取最近实体

        Returns:
            Dict: 最近实体
        """
        return self.recent_entities

    def _save_session(self):
        """
        保存会话到 Redis
        """
        session_data = {
            "team_id": self.team_id,
            "user_id": self.user_id,
            "messages": self.messages,
            "tool_history": self.tool_history,
            "recent_entities": self.recent_entities,
        }

        self.redis_client.setex(
            f"agent_session:{self.session_id}",
            self.MEMORY_TTL,
            json.dumps(session_data, ensure_ascii=False),
        )

    def clear_session(self):
        """
        清空会话
        """
        self.messages = []
        self.tool_history = []
        self.recent_entities = {}
        self._save_session()


__all__ = ["AgentMemory"]