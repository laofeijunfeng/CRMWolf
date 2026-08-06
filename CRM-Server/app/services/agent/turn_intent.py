"""Root-level turn intent routing for active Agent interrupts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.models.agent import AgentTaskStatus
from app.services.agent.input import AgentInputKind, AgentTurnInput
from app.services.agent.interrupts import (
    AgentInterruptPayload,
    AgentResumePayload,
    resume_payload_from_turn_input,
    validate_resume_payload,
)
from app.services.agent.schemas import AgentMemorySnapshot, AgentTurnIntentDecision
from app.services.agent.semantic import agent_semantic_parser
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.types import JSONDict, coerce_json_dict


_CANCEL_PATTERNS = (
    r"^(先|暂时|这次|当前|本次)?(不|不用|不要)(处理|做|建|创建|执行|继续|管)(了|啦)?$",
    r"^(先|暂时)?(放着|搁置|跳过|算了|取消)(吧|了|啦)?$",
    r"^(不用了|不要了|先记录就行|只记录跟进|后面再说)$",
)
_CONFIRM_TEXTS = {"是", "确认", "确认执行", "确定", "可以", "执行", "好的", "好", "yes", "y", "ok"}
_REJECT_TEXTS = {"否", "不", "不用", "不要", "取消", "先不处理", "暂不处理", "no", "n"}
_FIELD_SIGNAL_RE = re.compile(
    r"(\d+(\.\d+)?\s*(元|万|人|个|套|月|年|天)?)|金额|费用|报价|人数|席位|日期|时间|续购|新购|采购|阶段|负责人"
)


@dataclass(frozen=True)
class TurnIntentRoutingResult:
    decision: AgentTurnIntentDecision
    resume_payload: AgentResumePayload
    source: str


class AgentTurnIntentRouter:
    """Classify a user turn before resuming an active LangGraph interrupt.

    The router is intentionally layered:
    structured channel metadata is authoritative, obvious short replies are
    cheap deterministic signals, and ambiguous natural language is delegated to
    the semantic parser with the active interrupt/task context.
    """

    state_change_confidence_threshold = 0.76

    async def route_resume(
        self,
        db: Optional[Session],
        *,
        team_id: int,
        user_id: int,
        session,
        turn_input: AgentTurnInput,
        current_interrupt: AgentInterruptPayload,
        active_task=None,
        suspended_candidates: Optional[list[JSONDict]] = None,
    ) -> TurnIntentRoutingResult:
        local_decision = self._local_decision(
            turn_input,
            current_interrupt=current_interrupt,
            active_task=active_task,
        )
        if local_decision is not None:
            return self._result_from_decision(
                local_decision,
                turn_input=turn_input,
                current_interrupt=current_interrupt,
                source="local_signal",
            )

        if db is not None and session is not None:
            decision = await self._semantic_decision(
                db,
                team_id=team_id,
                user_id=user_id,
                session=session,
                turn_input=turn_input,
                current_interrupt=current_interrupt,
                active_task=active_task,
                suspended_candidates=suspended_candidates or [],
            )
            if self._should_trust_semantic_decision(decision):
                return self._result_from_decision(
                    decision,
                    turn_input=turn_input,
                    current_interrupt=current_interrupt,
                    source="semantic_router",
                )

        fallback = AgentTurnIntentDecision(
            intent="SUBMIT_FIELDS" if current_interrupt.get("type") == "form" else "START_NEW_FLOW",
            confidence=0.0,
            normalized_action=None,
            reason="本轮意图路由不可用或置信度不足，使用原有 interrupt resume 规则。",
        )
        return self._result_from_decision(
            fallback,
            turn_input=turn_input,
            current_interrupt=current_interrupt,
            source="fallback_resume_rule",
        )

    def _local_decision(
        self,
        turn_input: AgentTurnInput,
        *,
        current_interrupt: AgentInterruptPayload,
        active_task,
    ) -> AgentTurnIntentDecision | None:
        if turn_input.kind == AgentInputKind.CONFIRM:
            return AgentTurnIntentDecision(
                intent="CONFIRM_EXECUTION",
                confidence=1.0,
                target_task_id=self._task_id(active_task),
                normalized_action="approve",
                reason="结构化确认输入。",
            )
        if turn_input.kind == AgentInputKind.REJECT:
            return AgentTurnIntentDecision(
                intent="REJECT_EXECUTION",
                confidence=1.0,
                target_task_id=self._task_id(active_task),
                normalized_action="reject",
                reason="结构化拒绝输入。",
            )

        metadata = coerce_json_dict(turn_input.metadata)
        explicit_action = metadata.get("action") or metadata.get("resume_action")
        if explicit_action in {"cancel", "dismiss", "pause", "submit_fields", "approve", "reject"}:
            return AgentTurnIntentDecision(
                intent=self._intent_for_action(str(explicit_action), current_interrupt=current_interrupt),
                confidence=1.0,
                target_task_id=self._task_id(active_task),
                normalized_action=str(explicit_action),
                reason="结构化交互元数据指定了本轮动作。",
            )

        normalized = self._normalize(turn_input.content)
        if not normalized:
            return None
        if normalized in _CONFIRM_TEXTS and current_interrupt.get("type") == "confirm":
            return AgentTurnIntentDecision(
                intent="CONFIRM_EXECUTION",
                confidence=0.98,
                target_task_id=self._task_id(active_task),
                normalized_action="approve",
                reason="用户明确同意当前待确认动作。",
            )
        if normalized in _REJECT_TEXTS or any(re.match(pattern, normalized) for pattern in _CANCEL_PATTERNS):
            return AgentTurnIntentDecision(
                intent=(
                    "DISMISS_CURRENT_SUGGESTION"
                    if self._looks_like_system_suggestion(active_task)
                    else "CANCEL_CURRENT_TASK"
                ),
                confidence=0.96,
                target_task_id=self._task_id(active_task),
                normalized_action="dismiss" if self._looks_like_system_suggestion(active_task) else "cancel",
                reason="用户明确表达当前任务不继续处理。",
            )
        if current_interrupt.get("type") == "form" and _FIELD_SIGNAL_RE.search(normalized):
            return AgentTurnIntentDecision(
                intent="SUBMIT_FIELDS",
                confidence=0.86,
                target_task_id=self._task_id(active_task),
                normalized_action="submit_fields",
                reason="用户输入包含当前表单可吸收的字段信息。",
            )
        return None

    async def _semantic_decision(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session,
        turn_input: AgentTurnInput,
        current_interrupt: AgentInterruptPayload,
        active_task,
        suspended_candidates: list[JSONDict],
    ) -> AgentTurnIntentDecision:
        try:
            return await agent_semantic_parser.assess_turn_intent(
                db,
                team_id=team_id,
                user_message=turn_input.content,
                current_interrupt=current_interrupt,
                active_task=self._task_snapshot(active_task) if active_task else None,
                suspended_tasks=suspended_candidates or self._suspended_task_snapshots(
                    db,
                    session,
                    team_id=team_id,
                    user_id=user_id,
                ),
                memory=self._memory_snapshot(session, active_task),
                current_date=agent_temporal_resolver.now().date(),
            )
        except Exception:
            return AgentTurnIntentDecision(
                intent="ASK_CLARIFICATION",
                confidence=0.0,
                reason="LLM 本轮意图判断不可用。",
            )

    def _should_trust_semantic_decision(self, decision: AgentTurnIntentDecision) -> bool:
        if decision.intent in {"ASK_CLARIFICATION", "CHITCHAT"}:
            return decision.confidence >= 0.85
        return decision.confidence >= self.state_change_confidence_threshold

    def _result_from_decision(
        self,
        decision: AgentTurnIntentDecision,
        *,
        turn_input: AgentTurnInput,
        current_interrupt: AgentInterruptPayload,
        source: str,
    ) -> TurnIntentRoutingResult:
        payload = resume_payload_from_turn_input(turn_input, current_interrupt=current_interrupt)
        action = self._resume_action_for_decision(decision, current_interrupt=current_interrupt)
        if action is not None:
            payload["action"] = action
        metadata = coerce_json_dict(payload.get("metadata"))
        metadata["turn_intent"] = decision.model_dump(exclude_none=True)
        metadata["turn_intent_source"] = source
        payload["metadata"] = metadata
        validate_resume_payload(payload, current_interrupt=current_interrupt)
        return TurnIntentRoutingResult(decision=decision, resume_payload=payload, source=source)

    def _resume_action_for_decision(
        self,
        decision: AgentTurnIntentDecision,
        *,
        current_interrupt: AgentInterruptPayload,
    ) -> str | None:
        allowed = set(current_interrupt.get("allowed_resume_actions") or [])
        desired = decision.normalized_action
        intent_action_map = {
            "SUBMIT_FIELDS": "submit_fields",
            "CONFIRM_EXECUTION": "approve",
            "REJECT_EXECUTION": "reject",
            "CANCEL_CURRENT_TASK": "cancel",
            "DISMISS_CURRENT_SUGGESTION": "cancel",
            "PAUSE_CURRENT_TASK": "cancel",
            "PATCH_ACTIVE_DRAFT": "submit_fields",
            "RESUME_SUSPENDED_DRAFT": "submit",
        }
        action = desired if desired in {
            "cancel",
            "dismiss",
            "pause",
            "submit_fields",
            "approve",
            "reject",
            "submit",
            "resume",
            "patch",
        } else intent_action_map.get(decision.intent)
        if action in {"dismiss", "pause"}:
            action = "cancel"
        if action == "patch":
            action = "submit_fields" if current_interrupt.get("type") == "form" else "submit"
        if action and (not allowed or action in allowed):
            return action
        if decision.intent == "REJECT_EXECUTION" and "cancel" in allowed:
            return "cancel"
        return None

    def _intent_for_action(self, action: str, *, current_interrupt: AgentInterruptPayload) -> str:
        if action in {"cancel", "pause"}:
            return "CANCEL_CURRENT_TASK"
        if action == "dismiss":
            return "DISMISS_CURRENT_SUGGESTION"
        if action == "approve":
            return "CONFIRM_EXECUTION"
        if action == "reject":
            return "REJECT_EXECUTION"
        if action == "submit_fields":
            return "SUBMIT_FIELDS"
        return "START_NEW_FLOW"

    def _looks_like_system_suggestion(self, task) -> bool:
        state = coerce_json_dict(getattr(task, "state_json", None))
        action = state.get("action")
        if action in {"collect_opportunity_fields", "create_opportunity"}:
            return True
        payload = coerce_json_dict(getattr(task, "input_json", None))
        return bool(payload.get("suggestion") or state.get("suggestion"))

    def _memory_snapshot(self, session, task) -> AgentMemorySnapshot:
        return AgentMemorySnapshot(
            pending_task=self._task_snapshot(task) if task else None,
            session_context=coerce_json_dict(getattr(session, "context_json", None)),
        )

    def _suspended_task_snapshots(
        self,
        db: Session,
        session,
        *,
        team_id: int,
        user_id: int,
    ) -> list[JSONDict]:
        if not session:
            return []
        snapshots: list[JSONDict] = []
        for task in agent_task_crud.list_by_session(db, session.id, team_id=team_id, user_id=user_id):
            if getattr(task, "status", None) == AgentTaskStatus.SUSPENDED:
                snapshots.append(self._task_snapshot(task))
            if len(snapshots) >= 5:
                break
        return snapshots

    def _task_snapshot(self, task) -> JSONDict:
        state = coerce_json_dict(getattr(task, "state_json", None))
        payload = coerce_json_dict(getattr(task, "input_json", None))
        return {
            "id": self._task_id(task),
            "intent": getattr(task, "intent", None),
            "target_type": getattr(task, "target_type", None),
            "target_id": getattr(task, "target_id", None),
            "summary": getattr(task, "summary", None),
            "status": getattr(task, "status", None),
            "action": state.get("action") or payload.get("action"),
            "state": state,
            "input": payload,
        }

    def _task_id(self, task) -> int | None:
        task_id = getattr(task, "id", None)
        return int(task_id) if isinstance(task_id, int) else None

    def _normalize(self, content: str) -> str:
        text = str(content or "").strip().lower()
        text = re.sub(r"^引用消息：.*?本次指令：", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"^引用消息id：.*?本次指令：", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"@\S+", "", text).strip()
        text = text.strip(" \t\r\n。.!！?？,，;；:\"'“”‘’[]【】()（）")
        return re.sub(r"\s+", "", text)


agent_turn_intent_router = AgentTurnIntentRouter()
