"""
CRMWolf Agent Module
ReAct 循环架构

核心组件：
- CRMWolfAgent：Agent 核心（ReAct 循环）
- AgentPrompts：完整的 System Prompt（工具定义 + 业务流程图）
- ToolRegistry：工具注册（复用 skills handlers）
- AgentMemory：上下文记忆（会话历史 + 工具调用历史）

使用示例：
```python
from app.services.agent import CRMWolfAgent

agent = CRMWolfAgent(db, team_id=4, user_id=2)
response = await agent.run("跟进光大证券")
```
"""

from app.services.agent.core import (
    CRMWolfAgent,
    ReasoningResult,
    ObservationResult,
    ReflectionResult,
    AgentResponse,
)

from app.services.agent.prompts import AgentPrompts
from app.services.agent.tools import ToolRegistry, ToolResult
from app.services.agent.memory import AgentMemory
from app.services.agent.sse_streamer import AgentSSEStreamer


__all__ = [
    # Core
    "CRMWolfAgent",
    "ReasoningResult",
    "ObservationResult",
    "ReflectionResult",
    "AgentResponse",

    # Components
    "AgentPrompts",
    "ToolRegistry",
    "ToolResult",
    "AgentMemory",

    # SSE
    "AgentSSEStreamer",
]