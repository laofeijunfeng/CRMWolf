"""SSE JSON 编码器（从 langgraph/sse_wrapper.py 迁出，仅保留 SSEJsonEncoder）。

迁移自 app/services/langgraph/sse_wrapper.py 的 SSEJsonEncoder，仅依赖
langchain_core.messages.BaseMessage，不依赖 langgraph/Pregel。其余 LangGraph
SSE 包装逻辑（build_*_event / stream_sse_events 等）随 sse_wrapper.py 整体删除。
"""
import json
from typing import Any

from langchain_core.messages import BaseMessage


class SSEJsonEncoder(json.JSONEncoder):
    """Custom JSON encoder for SSE events that handles LangChain message objects."""

    def default(self, obj: Any) -> Any:
        """Convert LangChain messages to JSON-serializable dicts."""
        if isinstance(obj, BaseMessage):
            return {
                "type": obj.type,
                "content": obj.content,
                "additional_kwargs": obj.additional_kwargs,
            }
        return super().default(obj)
