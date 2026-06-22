"""
CRMWolf Agent Core - ReAct 循环架构

核心设计：
- Reason → Act → Observe → Reflection 循环
- 复用现有的 ai_service（不依赖具体 LLM 供应商）
- 完整的 System Prompt（工具定义 + 业务流程图）
- 上下文记忆（会话历史 + 工具调用历史）

安全机制（新增）：
- Guardrails 置信度拦截（从 workflow.guardrails 复用）
- Preview 模式（危险工具执行前预览）
- Human-in-the-Loop（暂停等待用户确认）

遵循规范：
- Pydantic 强制校验
- CRUD 统一入口
- team_id 必传
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
import json
import logging

from app.services.agent.memory import AgentMemory
from app.services.agent.tools import ToolRegistry, ToolResult
from app.services.agent.prompts import AgentPrompts
from app.services.ai_service import ai_service
from app.crud.ai_config import ai_config_crud

# ===== 新增：导入 Guardrails =====
from app.services.workflow.guardrails import (
    ConfidenceGuardrail,
    GuardrailDecision,
    DecisionType,
)

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================


@dataclass
class ReasoningResult:
    """推理结果（新增安全机制字段）"""
    is_complete: bool
    needs_tool: bool
    tool_name: Optional[str]
    tool_params: Optional[Dict[str, Any]]
    thinking: str
    final_answer: Optional[str]
    # ===== 新增：安全机制字段 =====
    confidence: float = 1.0  # LLM 输出的置信度
    waiting_for_user: bool = False  # 是否需要等待用户
    pending_question: Optional[str] = None  # 待询问的问题
    pending_options: Optional[List[str]] = None  # 待选择的选项
    preview_data: Optional[Dict[str, Any]] = None  # Preview 数据
    preview_required: bool = False  # 是否需要 Preview（危险工具）


@dataclass
class ObservationResult:
    """观察结果"""
    success: bool
    error: Optional[str]
    data: Optional[Any]
    extracted_info: Optional[Dict[str, Any]]


@dataclass
class ReflectionResult:
    """反思结果"""
    should_continue: bool
    adjust_strategy: Optional[str] = None
    final_answer: Optional[str] = None


@dataclass
class AgentResponse:
    """Agent 最终响应（新增 Human-in-the-Loop 支持）"""
    session_id: str
    answer: str
    tool_calls: List[Dict[str, Any]]
    rounds: int
    is_partial: bool = False
    # ===== 新增：Human-in-the-Loop 字段 =====
    waiting_for_user: bool = False  # 是否等待用户回复
    pending_question: Optional[str] = None  # 待询问的问题
    pending_options: Optional[List[str]] = None  # 待选择的选项
    preview_data: Optional[Dict[str, Any]] = None  # Preview 变更计划


# ==================== Agent Core ====================


class CRMWolfAgent:
    """CRMWolf Agent - ReAct 循环架构（集成安全机制）"""

    MAX_ROUNDS = 10  # ReAct 循环最大轮数

    # ===== 新增：危险工具列表（需要 Preview） =====
    DANGEROUS_TOOLS = [
        "win_opportunity",
        "lose_opportunity",
        "delete_customer",
        "delete_opportunity",
        "create_contract",
        "update_amount",
    ]

    def __init__(self, db, team_id: int, user_id: int):
        """
        初始化 Agent（集成 Guardrails）

        Args:
            db: 数据库会话
            team_id: 团队 ID（用于获取 AIConfig）
            user_id: 用户 ID
        """
        self.db = db
        self.team_id = team_id
        self.user_id = user_id

        # ===== 复用现有基础设施 =====
        # 获取 AI 配置（支持自定义供应商）
        self.config = ai_config_crud.get_config(db, team_id)
        self.api_key = ai_config_crud.get_decrypted_api_key(db, team_id)

        if not self.config or not self.api_key:
            raise ValueError("AI 配置未找到或 API Key 无效")

        # 其他组件
        self.memory = AgentMemory(db, team_id, user_id)
        self.tool_registry = ToolRegistry(db, team_id)
        self.prompts = AgentPrompts()

        # ===== 新增：Guardrails =====
        self.guardrail = ConfidenceGuardrail()

        logger.info(f"Agent initialized: team_id={team_id}, model={self.config.model_name}")

    async def run(self, user_message: str, session_id: Optional[str] = None) -> AgentResponse:
        """
        执行 Agent ReAct 循环（支持 Human-in-the-Loop）

        Args:
            user_message: 用户输入
            session_id: 会话 ID（可选，用于恢复会话）

        Returns:
            AgentResponse: Agent 响应
        """
        logger.info(f"Agent started: user_message='{user_message}'")

        # 加载或初始化会话记忆
        if session_id:
            self.memory.load_session(session_id)
        else:
            session_id = self.memory.create_session()

        # 添加用户消息到记忆
        self.memory.add_user_message(user_message)

        # ===== ReAct 循环 =====
        for round_num in range(self.MAX_ROUNDS):
            logger.info(f"ReAct Round {round_num + 1}/{self.MAX_ROUNDS}")

            # Step 1: Reason（推理）
            reasoning = await self._reason(user_message, round_num)

            # ===== 新增：处理 waiting_for_user（Guardrails 拦截） =====
            if reasoning.waiting_for_user:
                # Guardrails 拦截，暂停循环等待用户回复
                logger.info(f"Agent paused by Guardrails: waiting_for_user at round {round_num + 1}")
                return AgentResponse(
                    session_id=session_id,
                    answer=reasoning.pending_question,
                    waiting_for_user=True,
                    pending_question=reasoning.pending_question,
                    pending_options=reasoning.pending_options,
                    preview_data=reasoning.preview_data,
                    tool_calls=self.memory.get_tool_history(),
                    rounds=round_num + 1,
                )

            # Step 2: 判断是否完成
            if reasoning.is_complete:
                # 任务完成，返回最终答案
                final_answer = reasoning.final_answer or "任务完成"
                self.memory.add_agent_message(final_answer)

                logger.info(f"Agent completed at round {round_num + 1}")
                return AgentResponse(
                    session_id=session_id,
                    answer=final_answer,
                    tool_calls=self.memory.get_tool_history(),
                    rounds=round_num + 1,
                )

            # Step 3: Act（工具调用）
            if reasoning.needs_tool:
                tool_result = await self._act(reasoning.tool_name, reasoning.tool_params)

                # ===== 新增：处理 tool_result.waiting_for_user（Preview） =====
                if tool_result.waiting_for_user:
                    # Preview 状态，等待用户确认
                    logger.info(f"Agent paused by Preview: waiting for confirmation at round {round_num + 1}")
                    return AgentResponse(
                        session_id=session_id,
                        answer=tool_result.message,
                        waiting_for_user=True,
                        pending_question=f"是否确认执行 {reasoning.tool_name}？",
                        pending_options=["确认执行", "取消"],
                        preview_data=tool_result.preview_data,
                        tool_calls=self.memory.get_tool_history(),
                        rounds=round_num + 1,
                    )

                # Step 4: Observe（观察）
                observation = self._observe(tool_result)

                # Step 5: Reflection（反思）
                reflection = self._reflect(observation, reasoning)

                # 记录工具调用历史
                self.memory.add_tool_call(
                    tool_name=reasoning.tool_name,
                    tool_params=reasoning.tool_params,
                    tool_result=tool_result,
                    reasoning=reasoning.thinking,
                )

                # Step 6: 判断是否继续循环
                if not reflection.should_continue:
                    # Reflection 判断应该终止
                    final_answer = reflection.final_answer or "部分完成，请继续..."
                    self.memory.add_agent_message(final_answer)

                    return AgentResponse(
                        session_id=session_id,
                        answer=final_answer,
                        tool_calls=self.memory.get_tool_history(),
                        rounds=round_num + 1,
                    )

        # 超过最大轮数，返回部分结果
        logger.warning(f"Agent exceeded max rounds ({self.MAX_ROUNDS})")
        partial_answer = self._build_partial_answer()
        self.memory.add_agent_message(partial_answer)

        return AgentResponse(
            session_id=session_id,
            answer=partial_answer,
            tool_calls=self.memory.get_tool_history(),
            rounds=self.MAX_ROUNDS,
            is_partial=True,
        )

    async def _reason(self, user_message: str, round_num: int) -> ReasoningResult:
        """
        Reason: 调用 LLM 推理（集成 Guardrails 置信度拦截）

        Args:
            user_message: 用户输入
            round_num: 当前轮数

        Returns:
            ReasoningResult: 推理结果
        """
        logger.info("Reasoning...")

        # 构建 System Prompt（完整信息）
        system_prompt = self.prompts.build_system_prompt(
            tools=self.tool_registry.get_tools_definition(),
            business_workflow=self.prompts.BUSINESS_WORKFLOW,
            context=self.memory.get_context(),
            round_num=round_num,
        )

        # 构建 User Prompt（包含历史）
        user_prompt = self.prompts.build_user_prompt(
            user_message=user_message,
            tool_history=self.memory.get_tool_history(),
            recent_entities=self.memory.get_recent_entities(),
        )

        # ===== 调用 LLM（通过 ai_service，不依赖具体供应商）=====
        try:
            # 构建 messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # 使用 ai_service._stream_chat_collect
            response_text = await ai_service._stream_chat_collect(
                api_host=self.config.api_host,
                api_key=self.api_key,
                model=self.config.model_name,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # 解析 LLM 输出（结构化 JSON）
            reasoning = self._parse_reasoning_response(response_text)

            # ===== 新增：Guardrails 置信度检查 =====
            confidence = reasoning.confidence

            # 调用 Guardrails 决策
            guardrail_decision = self.guardrail.check(
                confidence=confidence,
                action_type=reasoning.tool_name or "unknown",
                context={"round_num": round_num}
            )

            logger.info(f"Guardrails decision: {guardrail_decision.decision.value}, confidence={confidence:.2f}")

            # 根据决策类型处理
            if guardrail_decision.decision == DecisionType.BLOCK:
                # 极低置信度：阻断操作
                logger.warning(f"Guardrails BLOCK: confidence={confidence:.2f}")
                return ReasoningResult(
                    is_complete=True,
                    needs_tool=False,
                    tool_name=None,
                    tool_params=None,
                    final_answer=f"操作被拦截：置信度过低 ({confidence:.2f})，请提供更准确的信息",
                    thinking=f"Guardrails: confidence={confidence:.2f} < 0.5 → block",
                    confidence=confidence,
                )

            elif guardrail_decision.decision == DecisionType.HUMAN_LOOP:
                # 低置信度：需人工确认
                logger.info(f"Guardrails HUMAN_LOOP: confidence={confidence:.2f}")
                return ReasoningResult(
                    is_complete=False,
                    needs_tool=False,
                    tool_name=reasoning.tool_name,
                    tool_params=reasoning.tool_params,
                    thinking=f"Guardrails: confidence={confidence:.2f} < 0.7 → human_loop",
                    final_answer=None,
                    confidence=confidence,
                    waiting_for_user=True,
                    pending_question=f"操作置信度较低 ({confidence:.2f})，是否继续执行？",
                    pending_options=["确认执行", "取消"],
                )

            elif guardrail_decision.decision == DecisionType.STRONG_CONFIRM:
                # 高风险操作：强确认（在 _act 中处理 Preview）
                logger.info(f"Guardrails STRONG_CONFIRM: confidence={confidence:.2f}")
                # 继续执行，但标记需要 Preview
                reasoning.preview_required = True
                return reasoning

            # AUTO 或 WEAK_CONFIRM：正常执行
            logger.info(f"Reasoning result: needs_tool={reasoning.needs_tool}, "
                       f"tool_name={reasoning.tool_name}, is_complete={reasoning.is_complete}, "
                       f"confidence={confidence:.2f}")

            return reasoning

        except Exception as e:
            logger.error(f"Reason failed: {str(e)}")
            # Fallback：返回错误
            return ReasoningResult(
                is_complete=True,
                needs_tool=False,
                tool_name=None,
                tool_params=None,
                final_answer=f"推理失败：{str(e)}",
                thinking="",
                confidence=0.0,
            )

    async def _act(self, tool_name: str, tool_params: Dict[str, Any]) -> ToolResult:
        """
        Act: 执行工具（集成 Preview 模式）

        Args:
            tool_name: 工具名称
            tool_params: 工具参数

        Returns:
            ToolResult: 工具执行结果
        """
        logger.info(f"Act: tool_name={tool_name}, params={tool_params}")

        # 获取工具 Handler
        handler = self.tool_registry.get_handler(tool_name)

        if not handler:
            logger.error(f"Tool handler not found: {tool_name}")
            return ToolResult(
                success=False,
                error=f"工具'{tool_name}'不存在",
                data=None,
                message=None,
            )

        # ===== 新增：Preview 检查 =====
        if tool_name in self.DANGEROUS_TOOLS:
            # 危险工具：生成 Preview
            logger.info(f"Preview required for dangerous tool: {tool_name}")

            try:
                # 调用 Handler 的 preview 方法
                preview_result = await handler.preview(
                    db=self.db,
                    team_id=self.team_id,
                    user_id=self.user_id,
                    params=tool_params,
                )

                # 返回等待状态（不执行）
                logger.info(f"Preview generated for {tool_name}, waiting for user confirmation")
                return ToolResult(
                    success=False,  # 暂时返回失败，等待用户确认
                    waiting_for_user=True,  # 需要在 ToolResult 中添加
                    preview_data=preview_result,
                    message=f"请确认变更计划：\n{preview_result.get('description', '执行操作')}",
                    error=None,
                    data=None,
                )

            except Exception as e:
                logger.error(f"Preview failed for {tool_name}: {str(e)}")
                # Preview 失败，降级策略：直接执行
                logger.warning(f"Fallback: executing {tool_name} directly due to Preview failure")
                return await self._execute_tool(handler, tool_params)

        # 正常工具：直接执行
        return await self._execute_tool(handler, tool_params)

    async def _execute_tool(self, handler: Any, tool_params: Dict[str, Any]) -> ToolResult:
        """
        执行工具（抽取为独立方法，支持复用）

        Args:
            handler: 工具 Handler
            tool_params: 工具参数

        Returns:
            ToolResult: 工具执行结果
        """
        try:
            result = await handler.execute(
                db=self.db,
                team_id=self.team_id,
                user_id=self.user_id,
                params=tool_params,
            )

            logger.info(f"Tool result: success={result.success}, message={result.message}")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {str(e)}")
            return ToolResult(
                success=False,
                error=str(e),
                data=None,
                message=None,
            )

    def _observe(self, tool_result: ToolResult) -> ObservationResult:
        """
        Observe: 观察工具结果

        Args:
            tool_result: 工具执行结果

        Returns:
            ObservationResult: 观察结果
        """
        logger.info("Observing...")

        if tool_result.success:
            # 提取关键信息（customer_id、opportunity_id）
            extracted_info = self._extract_key_info(tool_result.data)

            # 更新最近实体记忆
            if extracted_info.get("customer_id"):
                # 从数据中获取实体名称
                entity_name = self._get_entity_name_from_data(tool_result.data, "customer")
                self.memory.update_recent_entity("Customer", extracted_info["customer_id"], entity_name)

            if extracted_info.get("opportunity_id"):
                entity_name = self._get_entity_name_from_data(tool_result.data, "opportunity")
                self.memory.update_recent_entity("Opportunity", extracted_info["opportunity_id"], entity_name)

            return ObservationResult(
                success=True,
                data=tool_result.data,
                extracted_info=extracted_info,
            )
        else:
            # 工具失败，记录错误
            return ObservationResult(
                success=False,
                error=tool_result.error,
                data=None,
                extracted_info=None,
            )

    def _reflect(self, observation: ObservationResult, reasoning: ReasoningResult) -> ReflectionResult:
        """
        Reflection: 反思并决定下一步

        Args:
            observation: 观察结果
            reasoning: 推理结果

        Returns:
            ReflectionResult: 反思结果
        """
        logger.info("Reflecting...")

        if observation.success:
            # 工具成功，判断是否需要继续

            # 搜索工具的特殊处理
            if reasoning.tool_name in ["search_customer", "search_opportunity"]:
                data = observation.data

                if not data:
                    # 0 结果，询问用户
                    return ReflectionResult(
                        should_continue=False,
                        final_answer=f"未找到匹配的实体，是否创建新实体？",
                    )

                if len(data) > 1:
                    # 多个候选，让用户选择
                    candidates = "\n".join([f"{i+1}. {item['name']} (ID: {item['id']})" for i, item in enumerate(data[:5])])
                    return ReflectionResult(
                        should_continue=False,
                        final_answer=f"找到多个实体，请选择：\n{candidates}",
                    )

                # 唯一候选，继续执行
                return ReflectionResult(should_continue=True)

            # 其他工具成功，默认继续（多步骤任务）
            return ReflectionResult(should_continue=True)

        else:
            # 工具失败，调整策略
            logger.warning(f"Tool failed: {observation.error}")

            # 根据错误类型判断
            if "不存在" in observation.error or "未找到" in observation.error:
                # 实体不存在，重新搜索或询问
                return ReflectionResult(
                    should_continue=True,
                    adjust_strategy="search_again",
                )

            # 其他错误，询问用户
            return ReflectionResult(
                should_continue=False,
                final_answer=f"操作失败：{observation.error}，请提供更多信息",
            )

    def _parse_reasoning_response(self, response_text: str) -> ReasoningResult:
        """
        解析 LLM 输出（结构化 JSON，支持 confidence）

        Args:
            response_text: LLM 响应文本

        Returns:
            ReasoningResult: 推理结果
        """
        try:
            # 提取 JSON（可能包含其他文本）
            import re

            # 查找 JSON block
            json_match = re.search(r'\{[\s\S]*\}', response_text)

            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)

                # ===== 提取 confidence（新增） =====
                confidence = float(result.get("confidence", 1.0))

                return ReasoningResult(
                    is_complete=not result.get("needs_tool", False),
                    needs_tool=result.get("needs_tool", False),
                    tool_name=result.get("tool_name"),
                    tool_params=result.get("tool_params", {}),
                    thinking=result.get("reasoning", ""),
                    final_answer=result.get("final_answer", ""),
                    confidence=confidence,  # ← 新增字段
                )

            # 无 JSON，fallback
            return ReasoningResult(
                is_complete=True,
                needs_tool=False,
                tool_name=None,
                tool_params=None,
                final_answer=response_text,
                thinking="",
                confidence=0.0,  # 无法解析，默认低置信度
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {str(e)}")
            # JSON 解析失败，fallback
            return ReasoningResult(
                is_complete=True,
                needs_tool=False,
                tool_name=None,
                tool_params=None,
                final_answer=response_text,
                thinking="",
                confidence=0.0,  # 解析失败，默认低置信度
            )

    def _extract_key_info(self, data: Any) -> Dict[str, Any]:
        """
        提取关键信息（customer_id、opportunity_id）

        Args:
            data: 工具返回数据

        Returns:
            Dict: 关键信息
        """
        extracted = {}

        if isinstance(data, list) and len(data) > 0:
            # 搜索结果列表，提取第一个的 ID
            first_item = data[0]

            if "id" in first_item:
                # 判断是 Customer 还是 Opportunity
                # 这里简化判断：如果有 name 字段，认为是 Customer
                if "name" in first_item:
                    # 根据工具名称判断类型
                    # 实际应该从 tool_name 传递过来
                    extracted["customer_id"] = first_item["id"]

        elif isinstance(data, dict):
            # 单个对象，提取 ID
            if "customer_id" in data:
                extracted["customer_id"] = data["customer_id"]
            if "opportunity_id" in data:
                extracted["opportunity_id"] = data["opportunity_id"]

        return extracted

    def _get_entity_name_from_data(self, data: Any, entity_type: str) -> str:
        """
        从数据中获取实体名称

        Args:
            data: 工具返回数据
            entity_type: 实体类型

        Returns:
            str: 实体名称
        """
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            return first_item.get("name", f"{entity_type}_{first_item.get('id', 0)}")

        elif isinstance(data, dict):
            return data.get("name", f"{entity_type}_{data.get('id', 0)}")

        return f"{entity_type}_unknown"

    def _build_partial_answer(self) -> str:
        """
        构建部分结果答案

        Returns:
            str: 部分结果文本
        """
        tool_history = self.memory.get_tool_history()

        if tool_history:
            last_tool = tool_history[-1]
            return f"部分完成。最近执行：{last_tool['tool_name']}。请继续提供更多信息。"

        return "任务未完成，请提供更多信息。"


__all__ = [
    "CRMWolfAgent",
    "ReasoningResult",
    "ObservationResult",
    "ReflectionResult",
    "AgentResponse",
]