"""
Agent SSE Stream Wrapper
实时输出 Agent 运行过程

扩展架构：
- 输出详细事件类型（react_start、round_start、tool_call 等）
- 支持前端现有 SSE 解析逻辑
- 包装 agent.run() 的结果
- 将中间状态转换为 SSE 事件

遵循规范：
- Pydantic 强制校验
- CRUD 统一入口
- team_id 必传
"""

from typing import AsyncGenerator
import json
import logging

logger = logging.getLogger(__name__)


class AgentSSEStreamer:
    """Agent SSE 流式输出（扩展版）"""

    @staticmethod
    async def stream_agent_run(
        agent,
        user_message: str,
        session_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        流式输出 Agent 运行过程（扩展版）

        Args:
            agent: CRMWolfAgent 实例
            user_message: 用户输入
            session_id: 会话 ID

        Returns:
            AsyncGenerator: SSE 事件流

        事件类型：
        - start: Session 启动（兼容旧格式）
        - react_start: ReAct 循环开始（前端期望）
        - round_start: 新轮次开始（前端期望）
        - tool_call: 工具调用开始
        - tool_result: 工具执行结果
        - round_completed: ReAct 循环一轮完成（前端期望）
        - react_complete: ReAct 循环完成（前端期望）
        - complete: Agent 完成（兼容旧格式）
        - error: 错误信息
        """
        try:
            # ===== 事件：Start =====
            yield f"event: start\ndata: {json.dumps({'session_id': session_id})}\n\n"

            # ===== 事件：React Start =====
            yield f"event: react_start\ndata: {json.dumps({'session_id': session_id, 'max_rounds': agent.MAX_ROUNDS})}\n\n"

            # ===== 执行 Agent =====
            response = await agent.run(user_message, session_id)

            # ===== 事件：Tool Calls（扩展版） =====
            if response.tool_calls:
                for i, tool_call in enumerate(response.tool_calls, 1):
                    # Round Start
                    yield f"event: round_start\ndata: {json.dumps({'round': i, 'max_rounds': agent.MAX_ROUNDS})}\n\n"

                    # Tool Call（扩展字段：reply_text）
                    tool_call_data = json.dumps({
                        'round': i,
                        'tool': tool_call['tool_name'],  # 前端期望字段名：tool
                        'tool_name': tool_call['tool_name'],  # 兼容新字段名
                        'params': tool_call['tool_params'],
                        'reply_text': f"准备执行：{tool_call['tool_name']}",  # 前端期望字段
                    })
                    yield f"event: tool_call\ndata: {tool_call_data}\n\n"

                    # Tool Result（修正格式：匹配前端期望）
                    # 前端期望：event.result.success, event.result.message
                    # 注意：tool_result 是 ToolResult dataclass，需要提取字段
                    result_obj = tool_call['tool_result']
                    result_dict = {
                        'success': result_obj.success,
                        'message': result_obj.message or str(result_obj.data or '执行完成'),
                        'data': result_obj.data if hasattr(result_obj, 'data') else None,
                    }

                    tool_result_data = json.dumps({
                        'round': i,
                        'tool': tool_call['tool_name'],  # 前端期望字段
                        'result': result_dict,
                    })
                    yield f"event: tool_result\ndata: {tool_result_data}\n\n"

                    # Round Completed
                    yield f"event: round_completed\ndata: {json.dumps({'round': i})}\n\n"

            # ===== 事件：React Complete =====
            yield f"event: react_complete\ndata: {json.dumps({'rounds': response.rounds})}\n\n"

            # ===== 事件：Complete（兼容旧格式） =====
            # 前端期望 'result' 事件，但新 API 使用 'complete'
            # 这里同时发送两个事件，确保兼容性
            result_data = json.dumps({
                'event': 'result',  # 前端期望字段
                'success': not response.is_partial,  # 成功标志（如果不是部分结果）
                'message': response.answer,  # 消息内容
                'content': response.answer,  # 前端期望字段名：content
                'answer': response.answer,   # 兼容新字段名
                'rounds': response.rounds,
                'is_partial': response.is_partial,
            })
            yield f"event: result\ndata: {result_data}\n\n"

            complete_data = json.dumps({
                'answer': response.answer,
                'rounds': response.rounds,
                'is_partial': response.is_partial,
            })
            yield f"event: complete\ndata: {complete_data}\n\n"

        except Exception as e:
            logger.error(f"Agent SSE stream error: {str(e)}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"


__all__ = ["AgentSSEStreamer"]