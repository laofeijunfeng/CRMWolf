"""SSE JSON 编码器

用于 SSE 流式响应的 JSON 编码器，处理特殊类型序列化。
已移除对 langchain_core 的依赖（该库已不在 requirements.txt 中）。
"""
import json
from typing import Any


class SSEJsonEncoder(json.JSONEncoder):
    """Custom JSON encoder for SSE events."""

    def default(self, obj: Any) -> Any:
        """Handle special types for JSON serialization."""
        # 处理 datetime 对象
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        # 处理其他无法序列化的对象
        try:
            return str(obj)
        except Exception:
            return super().default(obj)