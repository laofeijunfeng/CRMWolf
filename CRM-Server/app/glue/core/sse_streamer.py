"""Glue SSE Streamer ——事件契约对齐 ReAct（兼容前端）。

Glue SSE 输出的事件格式与 ReAct 兼容：
- start: 会话启动（前端依赖）
- result: 最终结果（前端依赖）
- complete: 完成标记（前端依赖）
- error: 错误信息（前端依赖）

Phase 3.1 MVP: 基于 dispatch() 包装，先实现基础事件。
后续可扩展中间事件：intent/entity/preview/execute。
"""

import json
import logging
from typing import AsyncGenerator

from app.glue.core.dialogue import DialogueEngine
from app.glue.core.session import GlueSession

logger = logging.getLogger(__name__)


class GlueSSEStreamer:
    """Glue 对话 SSE 流式封装，事件契约对齐 ReAct（兼容前端）。"""

    async def stream(
        self,
        engine: DialogueEngine,
        session: GlueSession,
        session_id: str,
        text: str,
        auth_token: str = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式输出 Glue 对话过程。

        Phase 3.1 MVP: 基于 dispatch() 包装，yield start/result/complete/error。
        前端兼容事件确保可用，中间事件后续扩展。

        Args:
            engine: DialogueEngine 实例
            session: GlueSession 会话状态
            session_id: 会话 ID（uuid）
            text: 用户输入文本
            auth_token: 用户认证 token（可选）

        Returns:
            AsyncGenerator: SSE 事件流

        事件类型：
        - start: 会话启动（前端依赖）
        - result: 最终结果（前端依赖）
        - complete: 完成标记（前端依赖）
        - error: 错误信息（前端依赖）
        """
        try:
            # ===== 事件：Start =====
            yield self._evt("start", {"session_id": session_id})

            # ===== 执行 dispatch =====
            result = await engine.dispatch(session, text, auth_token)

            # ===== 事件：Result =====
            answer = result.message or ""
            success = result.success

            result_data = {
                "event": "result",
                "success": success,
                "message": answer,
                "content": answer,
                "answer": answer,
                "rounds": 1,
                "is_partial": False,
            }
            yield self._evt("result", result_data)

            # ===== 事件：Complete =====
            complete_data = {
                "answer": answer,
                "rounds": 1,
                "is_partial": False,
            }
            yield self._evt("complete", complete_data)

        except Exception as e:
            logger.error(f"Glue SSE stream error: {str(e)}", exc_info=True)
            yield self._evt("error", {"message": str(e)})

    @staticmethod
    def _evt(name: str, data: dict) -> str:
        """生成 SSE 事件字符串。"""
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


__all__ = ["GlueSSEStreamer"]