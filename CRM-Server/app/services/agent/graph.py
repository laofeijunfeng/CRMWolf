"""CRM AI Agent LangGraph service."""
from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from app.services.agent.memory import AgentMemoryService, agent_memory_service
from app.services.agent.quality import (
    AgentFollowUpQualityEvaluator,
    AgentFollowUpQualityEvaluatorError,
    agent_follow_up_quality_evaluator,
)
from app.services.agent.schemas import AgentFollowUpQualityResult, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParser, AgentSemanticParserError, agent_semantic_parser
from app.services.agent.state import AgentGraphState
from app.services.agent.suggestion import (
    AgentSuggestionGenerator,
    AgentSuggestionGeneratorError,
    agent_suggestion_generator,
)
from app.services.agent.temporal import AgentTemporalResolver, agent_temporal_resolver
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext


class CRMAgentGraphService:
    def __init__(
        self,
        tool_service: Optional[CRMAgentToolService] = None,
        semantic_parser: Optional[AgentSemanticParser] = None,
        memory_service: Optional[AgentMemoryService] = None,
        tool_registry: Optional[AgentToolRegistry] = None,
        temporal_resolver: Optional[AgentTemporalResolver] = None,
        suggestion_generator: Optional[AgentSuggestionGenerator] = None,
        follow_up_quality_evaluator: Optional[AgentFollowUpQualityEvaluator] = None,
    ) -> None:
        self.semantic_parser = semantic_parser or agent_semantic_parser
        self.memory_service = memory_service or agent_memory_service
        self.temporal_resolver = temporal_resolver or agent_temporal_resolver
        self.suggestion_generator = suggestion_generator or agent_suggestion_generator
        self.follow_up_quality_evaluator = follow_up_quality_evaluator or agent_follow_up_quality_evaluator
        if tool_registry:
            self.tool_registry = tool_registry
        elif tool_service:
            self.tool_registry = AgentToolRegistry(tool_service)
        else:
            self.tool_registry = agent_tool_registry
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("semantic_parse", self._semantic_parse)
        graph.add_node("evaluate_follow_up_quality", self._evaluate_follow_up_quality)
        graph.add_node("search_customer", self._search_customer)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("generate_suggestions", self._generate_suggestions)
        graph.add_node("build_response", self._build_response)
        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "semantic_parse")
        graph.add_edge("semantic_parse", "search_customer")
        graph.add_edge("search_customer", "evaluate_follow_up_quality")
        graph.add_edge("evaluate_follow_up_quality", "load_customer_context")
        graph.add_edge("load_customer_context", "generate_suggestions")
        graph.add_edge("generate_suggestions", "build_response")
        graph.add_edge("build_response", END)
        return graph.compile()

    def _load_memory(self, state: AgentGraphState) -> AgentGraphState:
        db = state.get("db")
        current_datetime = state.get("current_datetime") or self.temporal_resolver.now()
        if not db:
            return {"current_datetime": current_datetime}
        memory = self.memory_service.load_snapshot(
            db,
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            session_context=state.get("session_context"),
        )
        return {
            "current_datetime": current_datetime,
            "memory": memory,
            "events": [{"event": "memory_loaded"}],
        }

    async def _semantic_parse(self, state: AgentGraphState) -> AgentGraphState:
        try:
            if hasattr(self.semantic_parser, "parse_with_metadata"):
                envelope = await self.semantic_parser.parse_with_metadata(
                    state["db"],
                    team_id=state["team_id"],
                    user_message=state.get("content", ""),
                    memory=state.get("memory"),
                    current_date=self._current_date(state),
                )
                semantic_result = envelope.result
                parse_source = envelope.parse_source
                model_name = envelope.model
                fallback_reason = envelope.fallback_reason
                fallback_error = envelope.fallback_error
            else:
                semantic_result = await self.semantic_parser.parse(
                    state["db"],
                    team_id=state["team_id"],
                    user_message=state.get("content", ""),
                    memory=state.get("memory"),
                )
                parse_source = "test_parser"
                model_name = None
                fallback_reason = None
                fallback_error = None
        except AgentSemanticParserError as exc:
            return {
                "intent": "UNKNOWN",
                "semantic_error": str(exc),
                "events": [{"event": "semantic_parse_failed", "message": str(exc)}],
            }

        parsed = self._parsed_from_semantic(
            semantic_result,
            state.get("content", ""),
            base_datetime=state.get("current_datetime"),
        )
        return {
            "intent": semantic_result.intent,
            "semantic_result": semantic_result,
            "semantic_metadata": {
                "parse_source": parse_source,
                "model": model_name,
                "fallback_reason": fallback_reason,
                "fallback_error": fallback_error,
            },
            "parsed": parsed,
        }

    async def _evaluate_follow_up_quality(self, state: AgentGraphState) -> AgentGraphState:
        semantic_result = state.get("semantic_result")
        if (
            not semantic_result
            or semantic_result.intent != "CUSTOMER_FOLLOW_UP"
            or self._requires_clarification(semantic_result, has_memory_customer=bool(self._memory_current_customer(state.get("memory"))))
            or not state.get("db")
            or not self._has_single_customer(state)
        ):
            return {}

        try:
            envelope = await self.follow_up_quality_evaluator.evaluate_with_metadata(
                state["db"],
                team_id=state["team_id"],
                user_message=state.get("content", ""),
                semantic_result=semantic_result,
                memory=state.get("memory"),
                current_date=self._current_date(state),
            )
        except AgentFollowUpQualityEvaluatorError as exc:
            return {
                "follow_up_quality_error": str(exc),
                "events": [{"event": "follow_up_quality_failed", "message": str(exc)}],
            }

        return {
            "follow_up_quality_result": envelope.result,
            "follow_up_quality_metadata": {
                "quality_source": envelope.quality_source,
                "model": envelope.model,
                "fallback_reason": envelope.fallback_reason,
                "fallback_error": envelope.fallback_error,
            },
        }

    async def _search_customer(self, state: AgentGraphState) -> AgentGraphState:
        semantic_result = state.get("semantic_result")
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(state.get("memory"))
        if self._should_use_memory_customer(semantic_result, parsed, memory_customer):
            parsed = {**parsed, "customer_name": memory_customer.get("account_name")}
            return {
                "parsed": parsed,
                "customer_candidates": [memory_customer],
                "selected_customer": memory_customer,
                "events": [{"event": "customer_memory_used", "customer": memory_customer}],
            }
        customer_name = parsed.get("customer_name")
        if (
            not customer_name
            or not state.get("authorization")
            or not state.get("db")
            or self._requires_clarification(semantic_result)
        ):
            return {}

        context = AgentToolContext(
            db=state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state["authorization"],
        )
        result = await self.tool_registry.execute(
            "search_customers",
            context,
            {"keyword": customer_name, "limit": 10},
        )
        events = [result.to_event()]
        candidates = self._extract_customer_candidates(result.data) if result.success else []
        if candidates:
            events.append({"event": "customer_candidates", "customers": candidates})
        state_update: AgentGraphState = {"customer_candidates": candidates, "events": events}
        if len(candidates) == 1:
            state_update["selected_customer"] = candidates[0]
        return state_update

    async def _load_customer_context(self, state: AgentGraphState) -> AgentGraphState:
        customer = state.get("selected_customer") or {}
        customer_id = customer.get("id")
        if (
            not customer_id
            or not state.get("authorization")
            or not state.get("db")
            or self._requires_clarification(state.get("semantic_result"), has_memory_customer=bool(self._memory_current_customer(state.get("memory"))))
            or self._follow_up_quality_blocks(state)
        ):
            return {}

        context = AgentToolContext(
            db=state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state["authorization"],
        )
        result = await self.tool_registry.execute(
            "get_customer_context",
            context,
            {"customer_id": customer_id},
        )
        events = [result.to_event()]
        if not result.success:
            return {"events": events}
        events.append({
            "event": "business_context_loaded",
            "customer_id": customer_id,
            "customer": customer,
        })
        return {"business_context": result.data or {}, "events": events}

    async def _generate_suggestions(self, state: AgentGraphState) -> AgentGraphState:
        semantic_result = state.get("semantic_result")
        business_context = state.get("business_context") or {}
        if not semantic_result or not business_context or self._requires_clarification(semantic_result, has_memory_customer=bool(self._memory_current_customer(state.get("memory")))):
            return {}
        if self._follow_up_quality_blocks(state):
            return {}

        try:
            envelope = await self.suggestion_generator.generate_with_metadata(
                state["db"],
                team_id=state["team_id"],
                user_message=state.get("content", ""),
                semantic_result=semantic_result,
                customer_context=business_context,
                current_date=self._current_date(state),
            )
        except AgentSuggestionGeneratorError as exc:
            return {
                "suggestion_error": str(exc),
                "events": [{"event": "suggestion_failed", "message": str(exc)}],
            }

        return {
            "suggestion_result": envelope.result,
            "suggestion_metadata": {
                "suggestion_source": envelope.suggestion_source,
                "model": envelope.model,
                "fallback_reason": getattr(envelope, "fallback_reason", None),
                "fallback_error": getattr(envelope, "fallback_error", None),
            },
        }

    def _build_response(self, state: AgentGraphState) -> AgentGraphState:
        intent = state.get("intent") or "UNKNOWN"
        semantic_result = state.get("semantic_result")
        parsed = state.get("parsed") or {}
        candidates = state.get("customer_candidates") or []
        suppress_trace_events = bool(state.get("suppress_trace_events"))
        events = [] if suppress_trace_events else [{"event": "intent", "intent": intent}]

        if semantic_result and not suppress_trace_events:
            semantic_metadata = state.get("semantic_metadata") or {}
            events.append({
                "event": "semantic_parsed",
                "intent": semantic_result.intent,
                "confidence": semantic_result.intent_confidence,
                "parse_source": semantic_metadata.get("parse_source"),
                "model": semantic_metadata.get("model"),
                "fallback_reason": semantic_metadata.get("fallback_reason"),
                "fallback_error": semantic_metadata.get("fallback_error"),
                "need_clarification": semantic_result.need_clarification,
                "parsed": parsed,
            })

        suggestion_result = state.get("suggestion_result")
        if state.get("business_context") and not suppress_trace_events:
            events.append({
                "event": "business_context_loaded",
                "customer_id": (state.get("selected_customer") or {}).get("id"),
                "customer": state.get("selected_customer"),
            })
        if suggestion_result and not suppress_trace_events:
            suggestion_metadata = state.get("suggestion_metadata") or {}
            events.append({
                "event": "business_suggestions",
                "summary": suggestion_result.summary,
                "suggestions": [
                    suggestion.model_dump(exclude_none=True)
                    for suggestion in suggestion_result.suggestions
                ],
                "need_user_choice": suggestion_result.need_user_choice,
                "clarification_question": suggestion_result.clarification_question,
                "suggestion_source": suggestion_metadata.get("suggestion_source"),
                "model": suggestion_metadata.get("model"),
                "fallback_reason": suggestion_metadata.get("fallback_reason"),
                "fallback_error": suggestion_metadata.get("fallback_error"),
            })
        follow_up_quality_result = state.get("follow_up_quality_result")
        if follow_up_quality_result and not suppress_trace_events:
            follow_up_quality_metadata = state.get("follow_up_quality_metadata") or {}
            events.append({
                "event": "follow_up_quality_evaluated",
                "score": follow_up_quality_result.score,
                "passed": follow_up_quality_result.passed,
                "reason": follow_up_quality_result.reason,
                "missing_aspects": follow_up_quality_result.missing_aspects,
                "quality_source": follow_up_quality_metadata.get("quality_source"),
                "model": follow_up_quality_metadata.get("model"),
                "fallback_reason": follow_up_quality_metadata.get("fallback_reason"),
                "fallback_error": follow_up_quality_metadata.get("fallback_error"),
            })
        elif state.get("follow_up_quality_error") and not suppress_trace_events:
            events.append({
                "event": "follow_up_quality_failed",
                "message": state["follow_up_quality_error"],
            })
        elif state.get("suggestion_error") and not suppress_trace_events:
            events.append({
                "event": "suggestion_failed",
                "message": state["suggestion_error"],
            })

        if state.get("events") and not suppress_trace_events:
            events.extend(state["events"])

        if state.get("semantic_error"):
            response = state["semantic_error"]
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        if self._requires_clarification(semantic_result, has_memory_customer=bool(self._memory_current_customer(state.get("memory")))):
            response = semantic_result.clarification_question or "我还不能可靠理解你的诉求，请补充客户名称、业务内容或要执行的动作。"
            events.append({
                "event": "clarification_required",
                "intent": intent,
                "content": response,
                "semantic": semantic_result.model_dump(exclude_none=True) if semantic_result else None,
            })
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}

        response, action = self._build_business_response(
            intent,
            self._apply_follow_up_revision(parsed, follow_up_quality_result),
            candidates,
            state.get("business_context") or {},
        )
        if self._follow_up_quality_blocks(state):
            quality = state["follow_up_quality_result"]
            response = quality.supplement_question or "这条跟进还差一点关键信息，请补充后我再帮你记录。"
            events.append({
                "event": "follow_up_quality_required",
                "action": "collect_follow_up_quality_fields",
                "content": response,
                "score": quality.score,
                "reason": quality.reason,
                "missing_aspects": quality.missing_aspects,
                "customer": state.get("selected_customer"),
                "payload": {
                    "customer_id": (state.get("selected_customer") or {}).get("id"),
                    "content": parsed.get("follow_up_content"),
                    "method": parsed.get("method") or "AI录入",
                    "next_action": parsed.get("next_action"),
                    "next_follow_time_text": parsed.get("next_follow_time_text"),
                    "next_follow_time_iso": parsed.get("next_follow_time_iso"),
                    "quality": quality.model_dump(exclude_none=True),
                },
            })
            events.append({"event": "final", "intent": intent, "content": response, "tool_execution_enabled": False})
            return {"response": response, "events": events}
        stage_move_action = self._stage_move_action_from_suggestions(
            suggestion_result.suggestions if suggestion_result else [],
            state.get("selected_customer") or {},
            state.get("business_context") or {},
        )
        opportunity_next_task = self._opportunity_next_task_from_suggestions(
            suggestion_result.suggestions if suggestion_result else [],
            parsed,
            state.get("selected_customer") or {},
        )
        if suggestion_result and not action and not self._has_deferred_next_task(action):
            response = self._append_suggestions_to_response(response, suggestion_result.suggestions)
        if stage_move_action:
            if action and action.get("action") == "create_customer_follow_up":
                action.setdefault("payload", {})["_next_task"] = stage_move_action
            elif not action:
                action = stage_move_action
                target_stage_name = stage_move_action["payload"].get("target_stage_name")
                response = (
                    f"我识别到这次跟进可能已经推进了商机阶段"
                    f"{f'到「{target_stage_name}」' if target_stage_name else ''}。"
                    "请确认是否推进？"
                )
        elif opportunity_next_task and action and action.get("action") == "create_customer_follow_up":
            action.setdefault("payload", {})["_next_task"] = opportunity_next_task
        if action:
            event_name = "confirmation_required"
            if action.get("action") in {
                "select_customer_for_follow_up",
                "select_customer_for_contact",
                "select_customer_for_invoice_title",
                "select_customer_for_deployment_info",
                "select_customer_for_customer_member",
                "select_customer_for_payment_record",
                "select_customer_for_opportunity",
            }:
                event_name = "customer_selection_required"
            elif action.get("action") == "collect_contact_fields":
                event_name = "contact_fields_required"
            elif action.get("action") == "collect_opportunity_fields":
                event_name = "opportunity_fields_required"
            elif action.get("action") == "collect_invoice_title_fields":
                event_name = "invoice_title_fields_required"
            elif action.get("action") == "collect_deployment_info_fields":
                event_name = "deployment_info_fields_required"
            elif action.get("action") == "collect_customer_member_fields":
                event_name = "customer_member_fields_required"
            elif action.get("action") == "collect_payment_fields":
                event_name = "payment_fields_required"
            elif action.get("action") in {"select_contract_for_payment_plan", "select_payment_plan_for_record"}:
                event_name = "business_selection_required"
            events.append({"event": event_name, **action})
        events.append({
            "event": "final",
            "intent": intent,
            "content": response,
            "tool_execution_enabled": False,
        })
        return {"response": response, "events": events}

    @staticmethod
    def _has_deferred_next_task(action: Optional[Dict[str, Any]]) -> bool:
        if not action:
            return False
        payload = action.get("payload")
        return isinstance(payload, dict) and isinstance(payload.get("_next_task"), dict)

    async def run(self, input_state: AgentGraphState) -> AgentGraphState:
        result: Dict[str, Any] = await self._graph.ainvoke(input_state)
        return result

    async def stream_events(self, input_state: AgentGraphState) -> AsyncGenerator[Dict[str, Any], None]:
        state: AgentGraphState = dict(input_state)
        steps = [
            ("load_memory", "加载会话记忆", self._load_memory),
            ("semantic_parse", "AI 语义理解", self._semantic_parse),
            ("search_customer", "搜索客户", self._search_customer),
            ("evaluate_follow_up_quality", "AI 跟进质量评估", self._evaluate_follow_up_quality),
            ("load_customer_context", "加载客户上下文", self._load_customer_context),
            ("generate_suggestions", "AI 生成业务建议", self._generate_suggestions),
        ]
        for step_name, step_label, handler in steps:
            if self._should_skip_stream_step(step_name, state):
                continue
            yield {"event": "agent_step", "step": step_name, "status": "started", "content": step_label}
            update = await handler(state) if step_name != "load_memory" else handler(state)
            self._merge_stream_update(state, update)
            for event in update.get("events", []):
                yield event
            if step_name == "semantic_parse":
                for event in self._build_semantic_trace_events(state):
                    yield event
            elif step_name == "evaluate_follow_up_quality":
                for event in self._build_follow_up_quality_trace_events(state):
                    yield event
            elif step_name == "generate_suggestions":
                for event in self._build_suggestion_trace_events(state):
                    yield event
            yield {"event": "agent_step", "step": step_name, "status": "completed", "content": step_label}

        state["suppress_trace_events"] = True
        final_update = self._build_response(state)
        state.update(final_update)
        for event in final_update.get("events", []):
            yield event

    def _should_skip_stream_step(self, step_name: str, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        has_memory_customer = bool(self._memory_current_customer(state.get("memory")))
        if step_name == "evaluate_follow_up_quality":
            return (
                not semantic_result
                or semantic_result.intent != "CUSTOMER_FOLLOW_UP"
                or not self._has_single_customer(state)
                or self._requires_clarification(semantic_result, has_memory_customer=has_memory_customer)
            )
        if step_name == "search_customer":
            parsed = state.get("parsed") or {}
            memory_customer = self._memory_current_customer(state.get("memory"))
            return (
                self._follow_up_quality_blocks(state)
                or not parsed.get("customer_name")
                or self._requires_clarification(semantic_result, has_memory_customer=has_memory_customer)
                or self._should_use_memory_customer(semantic_result, parsed, memory_customer)
            )
        if step_name == "load_customer_context":
            return (
                self._follow_up_quality_blocks(state)
                or not (state.get("selected_customer") or {}).get("id")
                or self._requires_clarification(semantic_result, has_memory_customer=has_memory_customer)
            )
        if step_name == "generate_suggestions":
            return (
                self._follow_up_quality_blocks(state)
                or not state.get("business_context")
                or self._requires_clarification(semantic_result, has_memory_customer=has_memory_customer)
            )
        return False

    @staticmethod
    def _merge_stream_update(state: AgentGraphState, update: AgentGraphState) -> None:
        for key, value in update.items():
            if key == "events":
                continue
            state[key] = value

    @staticmethod
    def _build_semantic_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        semantic_result = state.get("semantic_result")
        if not semantic_result:
            return []
        semantic_metadata = state.get("semantic_metadata") or {}
        return [
            {"event": "intent", "intent": semantic_result.intent},
            {
                "event": "semantic_parsed",
                "intent": semantic_result.intent,
                "confidence": semantic_result.intent_confidence,
                "parse_source": semantic_metadata.get("parse_source"),
                "model": semantic_metadata.get("model"),
                "fallback_reason": semantic_metadata.get("fallback_reason"),
                "fallback_error": semantic_metadata.get("fallback_error"),
                "need_clarification": semantic_result.need_clarification,
                "parsed": state.get("parsed") or {},
            },
        ]

    @staticmethod
    def _build_suggestion_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        suggestion_result = state.get("suggestion_result")
        if suggestion_result:
            suggestion_metadata = state.get("suggestion_metadata") or {}
            return [{
                "event": "business_suggestions",
                "summary": suggestion_result.summary,
                "suggestions": [
                    suggestion.model_dump(exclude_none=True)
                    for suggestion in suggestion_result.suggestions
                ],
                "need_user_choice": suggestion_result.need_user_choice,
                "clarification_question": suggestion_result.clarification_question,
                "suggestion_source": suggestion_metadata.get("suggestion_source"),
                "model": suggestion_metadata.get("model"),
                "fallback_reason": suggestion_metadata.get("fallback_reason"),
                "fallback_error": suggestion_metadata.get("fallback_error"),
            }]
        if state.get("suggestion_error"):
            return [{"event": "suggestion_failed", "message": state["suggestion_error"]}]
        return []

    @staticmethod
    def _build_follow_up_quality_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        quality = state.get("follow_up_quality_result")
        if quality:
            metadata = state.get("follow_up_quality_metadata") or {}
            return [{
                "event": "follow_up_quality_evaluated",
                "score": quality.score,
                "passed": quality.passed,
                "reason": quality.reason,
                "missing_aspects": quality.missing_aspects,
                "quality_source": metadata.get("quality_source"),
                "model": metadata.get("model"),
                "fallback_reason": metadata.get("fallback_reason"),
                "fallback_error": metadata.get("fallback_error"),
            }]
        if state.get("follow_up_quality_error"):
            return [{"event": "follow_up_quality_failed", "message": state["follow_up_quality_error"]}]
        return []

    @staticmethod
    def _follow_up_quality_blocks(state: AgentGraphState) -> bool:
        quality = state.get("follow_up_quality_result")
        return bool(quality and not quality.passed)

    @staticmethod
    def _apply_follow_up_revision(parsed: Dict[str, Any], quality: Optional[AgentFollowUpQualityResult]) -> Dict[str, Any]:
        revision = (quality.suggested_revision or "").strip() if quality else ""
        if not revision:
            return parsed
        return {**parsed, "follow_up_content": revision}

    @staticmethod
    def _has_single_customer(state: AgentGraphState) -> bool:
        if (state.get("selected_customer") or {}).get("id"):
            return True
        return len(state.get("customer_candidates") or []) == 1

    @staticmethod
    def _requires_clarification(semantic_result: Optional[AgentSemanticParseResult], *, has_memory_customer: bool = False) -> bool:
        if semantic_result is None:
            return False
        customer_from_memory = semantic_result.customer.resolution_source == "MEMORY" or has_memory_customer
        return (
            semantic_result.need_clarification
            or semantic_result.intent == "UNKNOWN"
            or semantic_result.intent_confidence < 0.75
            or (
                semantic_result.intent != "UNKNOWN"
                and semantic_result.intent != "CUSTOMER_QUERY"
                and not customer_from_memory
                and semantic_result.customer.confidence < 0.7
            )
        )

    @staticmethod
    def _current_date(state: AgentGraphState):
        current_datetime = state.get("current_datetime")
        if isinstance(current_datetime, datetime):
            return current_datetime.date()
        return None

    def _parsed_from_semantic(self, semantic_result: AgentSemanticParseResult, original_content: str, base_datetime: Optional[datetime] = None) -> Dict[str, Any]:
        contact = dict(semantic_result.contact or {})
        invoice_title = dict(semantic_result.invoice_title or {})
        deployment_info = dict(semantic_result.deployment_info or {})
        customer_member = dict(semantic_result.customer_member or {})
        payment = semantic_result.payment
        next_follow_time_iso = self.temporal_resolver.resolve_follow_up_time(
            semantic_result.follow_up.next_follow_time,
            base_datetime=base_datetime,
        )
        payment_date_iso = (
            self.temporal_resolver.resolve_date(payment.payment_date, base_datetime=base_datetime)
            if hasattr(self.temporal_resolver, "resolve_date")
            else None
        )
        opportunity = semantic_result.opportunity
        expected_closing_date_iso = (
            self.temporal_resolver.resolve_date(opportunity.expected_closing_date, base_datetime=base_datetime)
            if hasattr(self.temporal_resolver, "resolve_date")
            else None
        )
        computed_missing_opportunity_fields = CRMAgentGraphService.missing_opportunity_fields({
            "total_amount": opportunity.total_amount,
            "user_count": opportunity.user_count,
            "license_type": opportunity.license_type,
            "subscription_years": opportunity.subscription_years,
            "purchase_type": opportunity.purchase_type,
            "expected_closing_date": expected_closing_date_iso,
        })
        ai_missing_opportunity_fields = [
            field for field in semantic_result.missing_fields
            if field not in {"opportunity_name", "商机名称"}
        ]
        return {
            "customer_name": semantic_result.customer.name_text,
            "follow_up_content": semantic_result.follow_up.content or original_content,
            "method": semantic_result.follow_up.method or "AI录入",
            "payment": {
                "actual_amount": payment.actual_amount,
                "actual_payer_name": payment.actual_payer_name,
                "payment_date_text": payment.payment_date_text,
                "payment_date_iso": payment_date_iso,
                "notes": payment.notes,
            },
            "opportunity": {
                "total_amount": opportunity.total_amount,
                "user_count": opportunity.user_count,
                "license_type": opportunity.license_type,
                "subscription_years": opportunity.subscription_years,
                "purchase_type": opportunity.purchase_type,
                "decision_maker_count": opportunity.decision_maker_count,
                "expected_closing_date_text": opportunity.expected_closing_date_text,
                "expected_closing_date": expected_closing_date_iso,
            },
            "missing_opportunity_fields": (
                ai_missing_opportunity_fields or computed_missing_opportunity_fields
                if semantic_result.intent == "CREATE_OPPORTUNITY" and semantic_result.missing_fields
                else computed_missing_opportunity_fields
                if semantic_result.intent == "CREATE_OPPORTUNITY"
                else []
            ),
            "missing_payment_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "PAYMENT_RECORD" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_payment_fields(payment.actual_amount, payment_date_iso)
                if semantic_result.intent == "PAYMENT_RECORD"
                else []
            ),
            "contact": CRMAgentGraphService._drop_empty_values(contact),
            "missing_contact_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_CONTACT" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_contact_fields(contact)
                if semantic_result.intent == "CREATE_CONTACT"
                else []
            ),
            "invoice_title": CRMAgentGraphService._drop_empty_values(invoice_title),
            "missing_invoice_title_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_INVOICE_TITLE" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_invoice_title_fields(invoice_title)
                if semantic_result.intent == "CREATE_INVOICE_TITLE"
                else []
            ),
            "deployment_info": CRMAgentGraphService._drop_empty_values(deployment_info),
            "missing_deployment_info_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_DEPLOYMENT_INFO" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_deployment_info_fields(deployment_info)
                if semantic_result.intent == "CREATE_DEPLOYMENT_INFO"
                else []
            ),
            "customer_member": CRMAgentGraphService._drop_empty_values(customer_member),
            "missing_customer_member_fields": (
                semantic_result.missing_fields
                if semantic_result.intent == "CREATE_CUSTOMER_MEMBER" and semantic_result.missing_fields
                else CRMAgentGraphService.missing_customer_member_fields(customer_member)
                if semantic_result.intent == "CREATE_CUSTOMER_MEMBER"
                else []
            ),
            "next_action": semantic_result.follow_up.next_action,
            "next_follow_time_text": semantic_result.follow_up.next_follow_time_text,
            "next_follow_time_iso": next_follow_time_iso,
        }

    @staticmethod
    def _memory_current_customer(memory: Optional[Any]) -> Optional[Dict[str, Any]]:
        context = getattr(memory, "session_context", None) if memory else None
        if not isinstance(context, dict):
            return None
        customer = context.get("current_customer")
        if isinstance(customer, dict) and customer.get("id") and customer.get("account_name"):
            return customer
        return None

    @staticmethod
    def _should_use_memory_customer(
        semantic_result: Optional[AgentSemanticParseResult],
        parsed: Dict[str, Any],
        memory_customer: Optional[Dict[str, Any]],
    ) -> bool:
        if not semantic_result or not memory_customer:
            return False
        if semantic_result.intent in {"UNKNOWN", "CUSTOMER_QUERY"}:
            return False
        if semantic_result.customer.resolution_source == "MEMORY":
            return True
        return not parsed.get("customer_name")

    @staticmethod
    def _drop_empty_values(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in payload.items() if value not in (None, "")}

    @staticmethod
    def _extract_customer_candidates(data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        items = data.get("items") or []
        candidates = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            candidates.append({
                "id": item.get("id"),
                "account_name": item.get("account_name"),
                "owner_info": item.get("owner_info"),
                "collaborator_infos": item.get("collaborator_infos") or [],
            })
        return candidates

    @staticmethod
    def _build_business_response(intent: str, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], business_context: Dict[str, Any]):
        customer_name = parsed.get("customer_name")
        if intent == "CUSTOMER_FOLLOW_UP":
            if not customer_name:
                return "我识别到这是客户跟进，但还缺少明确客户名称。请补充客户名称。", None
            if len(candidates) == 1:
                customer = candidates[0]
                return (
                    f"我识别到客户「{customer.get('account_name')}」的跟进记录。"
                    "请确认是否创建这条跟进记录？"
                ), {
                    "action": "create_customer_follow_up",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "content": parsed.get("follow_up_content"),
                        "method": parsed.get("method") or "AI录入",
                        "next_action": parsed.get("next_action"),
                        "next_follow_time_text": parsed.get("next_follow_time_text"),
                        "next_follow_time_iso": parsed.get("next_follow_time_iso"),
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要记录到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_follow_up",
                    "customers": candidates,
                    "payload": {
                        "content": parsed.get("follow_up_content"),
                        "method": parsed.get("method") or "AI录入",
                        "next_action": parsed.get("next_action"),
                        "next_follow_time_text": parsed.get("next_follow_time_text"),
                        "next_follow_time_iso": parsed.get("next_follow_time_iso"),
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "PAYMENT_RECORD":
            if not customer_name:
                return "我识别到这是回款场景，但还缺少明确客户名称。请补充客户名称。", None
            if len(candidates) == 1:
                customer = candidates[0]
                return CRMAgentGraphService._build_payment_record_response(customer, parsed, business_context)
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要为哪一个客户处理回款："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_payment_record",
                    "customers": candidates,
                    "payload": {
                        "payment": parsed.get("payment") or {},
                        "missing_fields": parsed.get("missing_payment_fields") or [],
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "CREATE_OPPORTUNITY":
            if not customer_name:
                return "我识别到这是创建商机，但还缺少明确客户名称。请补充客户名称。", None
            opportunity = parsed.get("opportunity") or {}
            opportunity.pop("opportunity_name", None)
            missing_fields = CRMAgentGraphService.missing_opportunity_fields(opportunity)
            if len(candidates) == 1:
                customer = candidates[0]
                opportunity["customer_id"] = customer.get("id")
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建商机，"
                        f"还需要补充：{CRMAgentGraphService.format_opportunity_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_opportunity_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "opportunity": opportunity,
                            "missing_fields": missing_fields,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建商机，"
                    f"{CRMAgentGraphService.format_opportunity_summary(opportunity)}。请确认是否创建？"
                ), {
                    "action": "create_opportunity",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "opportunity": opportunity,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把商机创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_opportunity",
                    "customers": candidates,
                    "payload": {
                        "opportunity": opportunity,
                        "missing_fields": missing_fields,
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "CREATE_CONTACT":
            if not customer_name:
                return "我识别到这是创建联系人，但还缺少明确客户名称。请补充客户名称。", None
            contact = parsed.get("contact") or {}
            missing_fields = CRMAgentGraphService.missing_contact_fields(contact)
            if len(candidates) == 1:
                customer = candidates[0]
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建联系人，"
                        f"还需要补充：{CRMAgentGraphService.format_contact_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_contact_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "contact": contact,
                            "missing_fields": missing_fields,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建联系人「{contact.get('name')}」。"
                    "请确认是否创建？"
                ), {
                    "action": "create_contact",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "contact": contact,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把联系人创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_contact",
                    "customers": candidates,
                    "payload": {
                        "contact": contact,
                        "missing_fields": missing_fields,
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "CREATE_INVOICE_TITLE":
            if not customer_name:
                return "我识别到这是创建发票抬头，但还缺少明确客户名称。请补充客户名称。", None
            invoice_title = parsed.get("invoice_title") or {}
            missing_fields = CRMAgentGraphService.missing_invoice_title_fields(invoice_title)
            set_default = bool(invoice_title.pop("set_default", False))
            if len(candidates) == 1:
                customer = candidates[0]
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建发票抬头，"
                        f"还需要补充：{CRMAgentGraphService.format_invoice_title_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_invoice_title_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "invoice_title": invoice_title,
                            "missing_fields": missing_fields,
                            "set_default": set_default,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建发票抬头「{invoice_title.get('title')}」。"
                    "请确认是否创建？"
                ), {
                    "action": "create_invoice_title",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "invoice_title": invoice_title,
                        "set_default": set_default,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把发票抬头创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_invoice_title",
                    "customers": candidates,
                    "payload": {
                        "invoice_title": invoice_title,
                        "missing_fields": missing_fields,
                        "set_default": set_default,
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "CREATE_DEPLOYMENT_INFO":
            if not customer_name:
                return "我识别到这是创建部署信息，但还缺少明确客户名称。请补充客户名称。", None
            deployment_info = parsed.get("deployment_info") or {}
            missing_fields = CRMAgentGraphService.missing_deployment_info_fields(deployment_info)
            if len(candidates) == 1:
                customer = candidates[0]
                deployment_info["customer_id"] = customer.get("id")
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」创建部署信息，"
                        f"还需要补充：{CRMAgentGraphService.format_deployment_info_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_deployment_info_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "deployment_info": deployment_info,
                            "missing_fields": missing_fields,
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」创建部署信息「{deployment_info.get('deployment_name')}」。"
                    "请确认是否创建？"
                ), {
                    "action": "create_deployment_info",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "deployment_info": deployment_info,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要把部署信息创建到哪一个客户："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_deployment_info",
                    "customers": candidates,
                    "payload": {
                        "deployment_info": deployment_info,
                        "missing_fields": missing_fields,
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "CREATE_CUSTOMER_MEMBER":
            if not customer_name:
                return "我识别到这是设置客户成员，但还缺少明确客户名称。请补充客户名称。", None
            member = parsed.get("customer_member") or {}
            missing_fields = CRMAgentGraphService.missing_customer_member_fields(member)
            if len(candidates) == 1:
                customer = candidates[0]
                if missing_fields:
                    return (
                        f"我识别到要为「{customer.get('account_name')}」设置客户成员，"
                        f"还需要补充：{CRMAgentGraphService.format_customer_member_missing_fields(missing_fields)}。"
                    ), {
                        "action": "collect_customer_member_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "customer_member": member,
                            "missing_fields": missing_fields,
                            "member_candidates": business_context.get("member_candidates"),
                        },
                    }
                resolved_member, member_error = CRMAgentGraphService.resolve_customer_member(member, business_context)
                if member_error:
                    return member_error, {
                        "action": "collect_customer_member_fields",
                        "customer": customer,
                        "payload": {
                            "customer_id": customer.get("id"),
                            "customer_member": member,
                            "missing_fields": ["user_name"],
                            "member_candidates": business_context.get("member_candidates"),
                        },
                    }
                return (
                    f"我识别到要为「{customer.get('account_name')}」添加客户成员「{resolved_member.get('user_name') or resolved_member.get('user_id')}」。"
                    "请确认是否添加？"
                ), {
                    "action": "create_customer_member",
                    "customer": customer,
                    "payload": {
                        "customer_id": customer.get("id"),
                        "member": resolved_member,
                    },
                }
            if len(candidates) > 1:
                candidate_lines = [
                    f"{index}. {customer.get('account_name')}"
                    for index, customer in enumerate(candidates, start=1)
                ]
                return (
                    "我找到了多个可能的客户，请回复序号或客户名称确认要给哪一个客户设置成员："
                    + "；".join(candidate_lines)
                ), {
                    "action": "select_customer_for_customer_member",
                    "customers": candidates,
                    "payload": {
                        "customer_member": member,
                        "missing_fields": missing_fields,
                    },
                }
            return CRMAgentGraphService._customer_not_found_response(customer_name), None

        if intent == "CUSTOMER_QUERY":
            return "我识别到这是查询请求。下一步会接入客户上下文查询和汇总能力。", None

        return "我还不能可靠理解这条消息，请补充客户名称、业务内容或你希望我执行的动作。", None

    @staticmethod
    def _customer_not_found_response(customer_name: str) -> str:
        return f"我识别到客户「{customer_name}」，但没有找到你可访问的客户。可以换成客户全称试试。"

    @staticmethod
    def _build_payment_record_response(customer: Dict[str, Any], parsed: Dict[str, Any], business_context: Dict[str, Any]):
        payment = parsed.get("payment") or {}
        missing_fields = CRMAgentGraphService.missing_payment_fields(
            payment.get("actual_amount"),
            payment.get("payment_date_iso"),
        )
        contracts = CRMAgentGraphService._context_items(business_context.get("contracts"))
        opportunities = CRMAgentGraphService._context_items(business_context.get("opportunities"))
        payment_plans = [
            plan
            for plan in CRMAgentGraphService._context_items(business_context.get("payment_plans"))
            if CRMAgentGraphService._is_open_payment_plan(plan)
        ]
        commission_member_id = CRMAgentGraphService._resolve_commission_member_id(customer)

        if not contracts:
            if not opportunities:
                return (
                    f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到商机和可用于登记回款的合同。"
                    "按 CRM 业务链路，需要先补齐商机，再处理合同、回款计划和回款登记。"
                    "创建合同暂未接入 Agent，因为当前创建合同需要上传合同附件。"
                ), None
            return (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到可用于登记回款的合同。"
                "该客户已有商机，但合同环节还未补齐；创建合同暂未接入 Agent，因为当前创建合同需要上传合同附件。"
            ), None

        if missing_fields:
            return (
                f"我识别到「{customer.get('account_name')}」的回款信息，"
                f"还需要补充：{CRMAgentGraphService.format_payment_missing_fields(missing_fields)}。"
            ), {
                "action": "collect_payment_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": payment,
                    "contracts": contracts,
                    "payment_plans": payment_plans,
                    "missing_fields": missing_fields,
                    "commission_member_id": commission_member_id,
                },
            }

        if not commission_member_id:
            return (
                f"我识别到「{customer.get('account_name')}」的回款信息，但没有找到可用于登记的提成协作成员或负责人。"
                "请先在客户中配置协作成员或负责人后再登记。"
            ), None

        if len(payment_plans) == 1:
            plan = payment_plans[0]
            return (
                f"我识别到「{customer.get('account_name')}」已回款，匹配到回款计划「{plan.get('stage_name')}」。"
                "请确认是否登记这笔回款？"
            ), {
                "action": "create_payment_record",
                "customer": customer,
                "payload": CRMAgentGraphService._payment_record_payload(plan, payment, commission_member_id),
            }

        if len(payment_plans) > 1:
            plan_lines = [
                f"{index}. {plan.get('contract_name') or '未命名合同'} / {plan.get('stage_name')} / 待回款 {plan.get('remaining_amount')}"
                for index, plan in enumerate(payment_plans, start=1)
            ]
            return (
                "我找到了多个未完成回款计划，请回复序号确认登记到哪一个计划："
                + "；".join(plan_lines)
            ), {
                "action": "select_payment_plan_for_record",
                "customer": customer,
                "payment_plans": payment_plans,
                "payload": {
                    "customer_id": customer.get("id"),
                    "payment": payment,
                    "commission_member_id": commission_member_id,
                },
            }

        if len(contracts) == 1:
            contract = contracts[0]
            return (
                f"我识别到「{customer.get('account_name')}」已回款，找到了合同「{contract.get('contract_name')}」，但没有找到回款计划。"
                "请确认是否先按本次回款金额创建一条回款计划？"
            ), {
                "action": "create_payment_plan",
                "customer": customer,
                "payload": CRMAgentGraphService._payment_plan_payload(contract, payment, commission_member_id),
            }

        contract_lines = [
            f"{index}. {contract.get('contract_name')} / 金额 {contract.get('total_amount')} / 状态 {contract.get('status')}"
            for index, contract in enumerate(contracts, start=1)
        ]
        return (
            "我找到了多个合同，但没有可直接登记的回款计划。请回复序号确认要基于哪一个合同创建回款计划："
            + "；".join(contract_lines)
        ), {
            "action": "select_contract_for_payment_plan",
            "customer": customer,
            "contracts": contracts,
            "payload": {
                "customer_id": customer.get("id"),
                "payment": payment,
                "commission_member_id": commission_member_id,
            },
        }

    @staticmethod
    def _context_items(value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            items = value.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    @staticmethod
    def _is_open_payment_plan(plan: Dict[str, Any]) -> bool:
        status = str(plan.get("status") or "").upper()
        remaining_amount = plan.get("remaining_amount")
        try:
            has_remaining = remaining_amount is None or float(remaining_amount) > 0
        except (TypeError, ValueError):
            has_remaining = True
        return status != "COMPLETED" and has_remaining

    @staticmethod
    def _resolve_commission_member_id(customer: Dict[str, Any]) -> Optional[str]:
        collaborators = customer.get("collaborator_infos") or []
        if collaborators:
            first = collaborators[0] or {}
            member_id = first.get("id") or first.get("user_id") or first.get("userId")
            if member_id:
                return str(member_id)
        owner = customer.get("owner_info") or {}
        owner_id = owner.get("id") or owner.get("user_id") or owner.get("userId")
        return str(owner_id) if owner_id else None

    @staticmethod
    def _payment_record_payload(plan: Dict[str, Any], payment: Dict[str, Any], commission_member_id: str) -> Dict[str, Any]:
        return {
            "payment_plan_id": plan.get("id"),
            "actual_amount": payment.get("actual_amount"),
            "payment_date": payment.get("payment_date_iso"),
            "actual_payer_name": payment.get("actual_payer_name"),
            "commission_member_id": commission_member_id,
            "notes": payment.get("notes"),
        }

    @staticmethod
    def _payment_plan_payload(contract: Dict[str, Any], payment: Dict[str, Any], commission_member_id: Optional[str]) -> Dict[str, Any]:
        return {
            "contract_id": contract.get("id"),
            "stage_name": "AI登记回款计划",
            "planned_amount": payment.get("actual_amount"),
            "due_date": payment.get("payment_date_iso"),
            "notes": payment.get("notes") or "由 CRM AI Agent 根据回款登记场景创建",
            "pending_payment_record": {
                "actual_amount": payment.get("actual_amount"),
                "payment_date": payment.get("payment_date_iso"),
                "actual_payer_name": payment.get("actual_payer_name"),
                "commission_member_id": commission_member_id,
                "notes": payment.get("notes"),
            },
        }

    @staticmethod
    def _append_suggestions_to_response(response: str, suggestions: List[Any]) -> str:
        actionable = [
            suggestion
            for suggestion in suggestions
            if getattr(suggestion, "action", None) != "NO_ACTION" and getattr(suggestion, "confidence", 0.0) >= 0.7
        ]
        if not actionable:
            return response
        suggestion_lines = [
            f"{index}. {suggestion.title}"
            for index, suggestion in enumerate(actionable[:3], start=1)
        ]
        return response + "\n\n基于客户上下文，我建议下一步可以：" + "；".join(suggestion_lines) + "。"

    @staticmethod
    def _opportunity_next_task_from_suggestions(
        suggestions: List[Any],
        parsed: Dict[str, Any],
        customer: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not customer.get("id"):
            return None
        suggestion = next(
            (
                item
                for item in suggestions
                if getattr(item, "action", None) == "CREATE_OPPORTUNITY"
                and getattr(item, "confidence", 0.0) >= 0.7
            ),
            None,
        )
        if suggestion is None:
            return None

        opportunity = dict(parsed.get("opportunity") or {})
        opportunity.pop("opportunity_name", None)
        opportunity["customer_id"] = customer.get("id")
        missing_fields = CRMAgentGraphService.missing_opportunity_fields(opportunity)
        title = getattr(suggestion, "title", None) or "创建商机"
        if missing_fields:
            return {
                "action": "collect_opportunity_fields",
                "customer": customer,
                "payload": {
                    "customer_id": customer.get("id"),
                    "opportunity": opportunity,
                    "missing_fields": missing_fields,
                },
                "content": f"我看这条还挺像「{title}」。要不要我继续帮你补齐商机信息？",
            }
        return {
            "action": "create_opportunity",
            "customer": customer,
            "payload": {
                "customer_id": customer.get("id"),
                "opportunity": opportunity,
            },
            "content": (
                f"我看这条还挺像「{title}」，"
                f"{CRMAgentGraphService.format_opportunity_summary(opportunity)}。请确认是否创建？"
            ),
        }

    @staticmethod
    def _stage_move_action_from_suggestions(
        suggestions: List[Any],
        customer: Dict[str, Any],
        business_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not customer.get("id"):
            return None
        stage_suggestion = next(
            (
                suggestion
                for suggestion in suggestions
                if getattr(suggestion, "action", None) == "MOVE_OPPORTUNITY_STAGE"
                and getattr(suggestion, "requires_confirmation", True)
                and getattr(suggestion, "confidence", 0.0) >= 0.8
                and not getattr(suggestion, "missing_fields", None)
            ),
            None,
        )
        if not stage_suggestion:
            return None
        execution_payload = getattr(stage_suggestion, "execution_payload", None) or {}
        opportunity_id = getattr(stage_suggestion, "related_object_id", None)
        stage_template_id = execution_payload.get("stage_template_id")
        if not opportunity_id or not stage_template_id:
            return None

        opportunity = CRMAgentGraphService._find_opportunity_in_context(business_context, int(opportunity_id))
        opportunity_name = opportunity.get("opportunity_name") or opportunity.get("name") or f"商机 {opportunity_id}"
        target_stage_name = execution_payload.get("target_stage_name")
        content = (
            f"我还识别到商机「{opportunity_name}」可能需要推进阶段"
            f"{f'到「{target_stage_name}」' if target_stage_name else ''}。"
            "请确认是否推进？"
        )
        return {
            "action": "move_opportunity_stage",
            "customer": customer,
            "content": content,
            "payload": {
                "customer_id": customer.get("id"),
                "opportunity_id": int(opportunity_id),
                "stage_template_id": int(stage_template_id),
                "opportunity_name": opportunity_name,
                "target_stage_name": target_stage_name,
                "suggestion_title": getattr(stage_suggestion, "title", None),
                "suggestion_reason": getattr(stage_suggestion, "reason", None),
            },
        }

    @staticmethod
    def _find_opportunity_in_context(business_context: Dict[str, Any], opportunity_id: int) -> Dict[str, Any]:
        for opportunity in CRMAgentGraphService._context_items(business_context.get("opportunities")):
            if opportunity.get("id") is not None and int(opportunity["id"]) == opportunity_id:
                return opportunity
        for item in CRMAgentGraphService._context_items(business_context.get("active_opportunity_stage_context")):
            opportunity = item.get("opportunity") or {}
            if opportunity.get("id") is not None and int(opportunity["id"]) == opportunity_id:
                return opportunity
        return {"id": opportunity_id}

    @staticmethod
    def missing_contact_fields(contact: Dict[str, Any]) -> List[str]:
        required_fields = ["name", "mobile", "position", "gender"]
        return [field for field in required_fields if not contact.get(field)]

    @staticmethod
    def format_contact_missing_fields(fields: List[str]) -> str:
        labels = {
            "name": "联系人姓名",
            "mobile": "手机号",
            "position": "职务",
            "gender": "性别（男/女/未知）",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def missing_invoice_title_fields(invoice_title: Dict[str, Any]) -> List[str]:
        required_fields = ["title_type", "title", "taxpayer_id"]
        return [field for field in required_fields if not invoice_title.get(field)]

    @staticmethod
    def format_invoice_title_missing_fields(fields: List[str]) -> str:
        labels = {
            "title_type": "抬头类型（单位/个人）",
            "title": "开票抬头",
            "taxpayer_id": "纳税人识别号",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def missing_deployment_info_fields(deployment_info: Dict[str, Any]) -> List[str]:
        required_fields = ["deployment_name", "server_address", "authorized_users"]
        return [field for field in required_fields if not deployment_info.get(field)]

    @staticmethod
    def format_deployment_info_missing_fields(fields: List[str]) -> str:
        labels = {
            "deployment_name": "部署名称",
            "server_address": "服务器地址（需以 http:// 或 https:// 开头）",
            "authorized_users": "授权人数",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def missing_customer_member_fields(member: Dict[str, Any]) -> List[str]:
        if member.get("user_id") or member.get("user_name"):
            return []
        return ["user_name"]

    @staticmethod
    def format_customer_member_missing_fields(fields: List[str]) -> str:
        labels = {
            "user_name": "成员姓名",
            "user_id": "成员用户 ID",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def resolve_customer_member(member: Dict[str, Any], business_context: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
        normalized = {
            "user_id": member.get("user_id"),
            "member_role": member.get("member_role") or "PRESALES",
            "access_level": member.get("access_level") or "VIEW",
            "remark": member.get("remark"),
        }
        if normalized["user_id"]:
            return CRMAgentGraphService._drop_empty_values({
                **normalized,
                "user_name": member.get("user_name"),
            }), None

        user_name = str(member.get("user_name") or "").strip()
        if not user_name:
            return member, None

        candidates_value = business_context.get("member_candidates")
        if isinstance(candidates_value, dict) and candidates_value.get("error"):
            return member, f"我识别到要添加客户成员「{user_name}」，但读取成员候选人失败。请确认你有客户成员管理权限。"

        candidates = CRMAgentGraphService._context_items(candidates_value)
        matches = [
            item
            for item in candidates
            if str(item.get("name") or "") == user_name
            or (user_name and user_name in str(item.get("name") or ""))
        ]
        available_matches = [item for item in matches if not item.get("already_member")]
        if len(available_matches) == 1:
            candidate = available_matches[0]
            return CRMAgentGraphService._drop_empty_values({
                **normalized,
                "user_id": candidate.get("id"),
                "user_name": candidate.get("name"),
            }), None
        if len(matches) == 1 and matches[0].get("already_member"):
            return member, f"「{matches[0].get('name')}」已经是这个客户的负责人或成员，不需要重复添加。"
        if len(available_matches) > 1:
            names = "；".join(f"{index}. {item.get('name')}" for index, item in enumerate(available_matches, start=1))
            return member, f"我找到了多个叫「{user_name}」的候选成员，请补充更明确的成员信息：{names}"
        return member, f"我没在客户成员候选人里找到「{user_name}」。请确认成员姓名，或先把这个人加入团队。"

    @staticmethod
    def missing_payment_fields(actual_amount: Any, payment_date: Any) -> List[str]:
        fields = []
        if not actual_amount:
            fields.append("actual_amount")
        if not payment_date:
            fields.append("payment_date")
        return fields

    @staticmethod
    def missing_opportunity_fields(opportunity: Dict[str, Any]) -> List[str]:
        fields = []
        required_fields = [
            "total_amount",
            "user_count",
            "license_type",
            "purchase_type",
            "expected_closing_date",
        ]
        for field in required_fields:
            if not opportunity.get(field):
                fields.append(field)
        if opportunity.get("license_type") == "SUBSCRIPTION" and not opportunity.get("subscription_years"):
            fields.append("subscription_years")
        return fields

    @staticmethod
    def format_payment_missing_fields(fields: List[str]) -> str:
        labels = {
            "actual_amount": "实际回款金额",
            "payment_date": "实际回款日期",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def format_opportunity_missing_fields(fields: List[str]) -> str:
        labels = {
            "total_amount": "预计成交金额",
            "user_count": "采购用户数",
            "license_type": "授权模式",
            "subscription_years": "订阅年限",
            "purchase_type": "采购类型（新购/续购/增购）",
            "expected_closing_date": "预计成交日期",
        }
        return "、".join(labels.get(field, field) for field in fields)

    @staticmethod
    def format_opportunity_summary(opportunity: Dict[str, Any]) -> str:
        parts = []
        if opportunity.get("total_amount"):
            parts.append(f"预计金额 {opportunity.get('total_amount')}")
        if opportunity.get("user_count"):
            parts.append(f"{opportunity.get('user_count')} 人")
        if opportunity.get("license_type") == "SUBSCRIPTION":
            years = opportunity.get("subscription_years") or 1
            parts.append(f"订阅 {years} 年")
        elif opportunity.get("license_type") == "PERPETUAL":
            parts.append("买断")
        return "，".join(parts) if parts else "商机名称将由系统自动生成"


crm_agent_graph_service = CRMAgentGraphService()
