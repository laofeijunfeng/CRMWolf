"""Agent-owned confirmation and rejection intent assessment."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from app.services.agent.input import AgentInputKind, AgentTurnInput
from app.services.agent.schemas import AgentConfirmationIntentDecision
from app.services.agent.semantic import agent_semantic_parser
from app.services.agent.task_actions import _tool_name_for_action


class ConfirmationIntent(str, Enum):
    CONFIRM = "confirm"
    REJECT = "reject"
    UNKNOWN = "unknown"


class AgentConfirmationIntentService:
    """Classify replies to executable HITL confirmation tasks.

    IM adapters may provide structured confirm/reject events. Natural language
    remains Agent-layer semantics and is interpreted with the pending task
    context, not inside a channel gateway.
    """

    direct_confirmation_texts = {"是", "确认", "可以", "执行", "好的", "好", "yes", "y", "ok"}
    direct_rejection_texts = {"否", "不", "不用", "不要", "取消", "先不处理", "no", "n"}
    confidence_threshold = 0.82

    def is_executable_confirmation_task(self, task) -> bool:
        action = ((task.state_json or {}) if task else {}).get("action")
        return bool(_tool_name_for_action(action))

    async def assess(
        self,
        db: Session,
        *,
        team_id: int,
        turn_input: AgentTurnInput,
        task,
        memory=None,
    ) -> AgentConfirmationIntentDecision:
        if turn_input.kind == AgentInputKind.CONFIRM:
            return AgentConfirmationIntentDecision(intent="confirm", confidence=1.0, reason="结构化确认输入")
        if turn_input.kind == AgentInputKind.REJECT:
            return AgentConfirmationIntentDecision(intent="reject", confidence=1.0, reason="结构化拒绝输入")

        direct = self._direct_confirmation_intent(turn_input.content)
        if direct:
            return AgentConfirmationIntentDecision(intent=direct, confidence=1.0, reason="明确确认/拒绝文本")

        try:
            decision = await agent_semantic_parser.assess_confirmation_intent(
                db,
                team_id=team_id,
                user_message=turn_input.content,
                pending_task=self._pending_task_payload(task),
                memory=memory,
            )
        except Exception:
            return AgentConfirmationIntentDecision(intent="unknown", confidence=0.0, reason="确认语义判断不可用")

        if decision.intent in {"confirm", "reject"} and decision.confidence >= self.confidence_threshold:
            return decision
        return AgentConfirmationIntentDecision(
            intent="unknown",
            confidence=decision.confidence,
            reason=decision.reason or "确认语义置信度不足",
        )

    def _direct_confirmation_intent(self, content: str) -> Optional[str]:
        normalized = self._normalize_short_reply(content)
        if normalized in self.direct_confirmation_texts:
            return "confirm"
        if normalized in self.direct_rejection_texts:
            return "reject"
        return None

    def _normalize_short_reply(self, content: str) -> str:
        text = str(content or "").strip().lower()
        text = re.sub(r"^引用消息：.*?本次指令：", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"^引用消息id：.*?本次指令：", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"@\S+", "", text).strip()
        text = text.strip(" \t\r\n。.!！?？,，;；:\"'“”‘’[]【】()（）")
        return re.sub(r"\s+", " ", text)

    def _pending_task_payload(self, task) -> dict:
        return {
            "id": getattr(task, "id", None),
            "summary": getattr(task, "summary", None),
            "intent": getattr(task, "intent", None),
            "target_type": getattr(task, "target_type", None),
            "target_id": getattr(task, "target_id", None),
            "state": getattr(task, "state_json", None) or {},
            "input": getattr(task, "input_json", None) or {},
        }


agent_confirmation_intent_service = AgentConfirmationIntentService()
