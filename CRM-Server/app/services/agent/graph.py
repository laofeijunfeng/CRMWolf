"""CRM AI Agent LangGraph service."""
from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from app.services.agent import business_rules
from app.services.agent.business_response import BusinessResponseBuilder
from app.services.agent.customer_mentions import explicit_customer_hint_from_message
from app.services.agent.memory import AgentMemoryService, agent_memory_service
from app.services.agent.quality import (
    AgentFollowUpQualityEvaluator,
    AgentFollowUpQualityEvaluatorError,
    agent_follow_up_quality_evaluator,
)
from app.services.agent.schemas import AgentFollowUpQualityResult, AgentSemanticParseResult
from app.services.agent.semantic import AgentSemanticParser, AgentSemanticParserError, agent_semantic_parser
from app.services.agent.semantic_payload import parsed_from_semantic
from app.services.agent.state import AgentGraphState
from app.services.agent.response_builder import AgentResponseBuilder
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
        self.response_builder = AgentResponseBuilder(
            requires_clarification=self._requires_clarification,
            memory_current_customer=self._memory_current_customer,
            follow_up_quality_blocks=self._follow_up_quality_blocks,
            apply_follow_up_revision=self._apply_follow_up_revision,
            build_creation_duplicate_response=business_rules.build_creation_duplicate_response,
            build_business_response=self._build_business_response,
            stage_move_action_from_suggestions=business_rules.stage_move_action_from_suggestions,
            opportunity_next_task_from_suggestions=business_rules.opportunity_next_task_from_suggestions,
            append_suggestions_to_response=business_rules.append_suggestions_to_response,
            has_deferred_next_task=self._has_deferred_next_task,
        )
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("semantic_parse", self._semantic_parse)
        graph.add_node("search_creation_duplicates", self._search_creation_duplicates)
        graph.add_node("evaluate_follow_up_quality", self._evaluate_follow_up_quality)
        graph.add_node("search_customer", self._search_customer)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("generate_suggestions", self._generate_suggestions)
        graph.add_node("build_response", self._build_response)
        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "semantic_parse")
        graph.add_conditional_edges(
            "semantic_parse",
            self._route_after_semantic_parse,
            {
                "creation_duplicates": "search_creation_duplicates",
                "customer_search": "search_customer",
                "response": "build_response",
            },
        )
        graph.add_edge("search_creation_duplicates", "build_response")
        graph.add_conditional_edges(
            "search_customer",
            self._route_after_customer_search,
            {
                "quality": "evaluate_follow_up_quality",
                "context": "load_customer_context",
                "response": "build_response",
            },
        )
        graph.add_conditional_edges(
            "evaluate_follow_up_quality",
            self._route_after_follow_up_quality,
            {
                "context": "load_customer_context",
                "response": "build_response",
            },
        )
        graph.add_conditional_edges(
            "load_customer_context",
            self._route_after_customer_context,
            {
                "suggestions": "generate_suggestions",
                "response": "build_response",
            },
        )
        graph.add_edge("generate_suggestions", "build_response")
        graph.add_edge("build_response", END)
        return graph.compile()

    def _route_after_semantic_parse(self, state: AgentGraphState) -> str:
        if self._should_run_creation_duplicate_search(state):
            return "creation_duplicates"
        if self._should_enter_customer_resolution(state):
            return "customer_search"
        return "response"

    def _route_after_customer_search(self, state: AgentGraphState) -> str:
        if self._should_run_follow_up_quality(state):
            return "quality"
        if self._should_run_customer_context(state):
            return "context"
        return "response"

    def _route_after_follow_up_quality(self, state: AgentGraphState) -> str:
        if self._should_run_customer_context(state):
            return "context"
        return "response"

    def _route_after_customer_context(self, state: AgentGraphState) -> str:
        if self._should_run_suggestions(state):
            return "suggestions"
        return "response"

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

        parsed = parsed_from_semantic(
            semantic_result,
            state.get("content", ""),
            temporal_resolver=self.temporal_resolver,
            base_datetime=state.get("current_datetime"),
        )
        parsed = self._apply_explicit_customer_hint(
            semantic_result,
            parsed,
            state.get("content", ""),
            state.get("memory"),
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

    async def _search_creation_duplicates(self, state: AgentGraphState) -> AgentGraphState:
        semantic_result = state.get("semantic_result")
        intent = state.get("intent")
        parsed = state.get("parsed") or {}
        if (
            intent not in {"CREATE_LEAD", "CREATE_CUSTOMER"}
            or not state.get("authorization")
            or not state.get("db")
            or self._requires_clarification(semantic_result)
        ):
            return {}

        create_payload = (
            parsed.get("lead") or {}
            if intent == "CREATE_LEAD"
            else parsed.get("customer_create") or {}
        )
        name = create_payload.get("lead_name") if intent == "CREATE_LEAD" else create_payload.get("account_name")
        phone = create_payload.get("contact_phone")
        customer_keywords = business_rules.creation_duplicate_keywords(name)
        lead_keywords = list(customer_keywords)
        if not customer_keywords and not lead_keywords and not phone:
            return {}

        context = AgentToolContext(
            db=state["db"],
            team_id=state["team_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            authorization=state["authorization"],
        )
        events: List[Dict[str, Any]] = []
        result = await self.tool_registry.execute(
            "search_creation_duplicates",
            context,
            {
                "customer_keywords": customer_keywords,
                "lead_keywords": lead_keywords,
                "phone": phone,
                "limit": 5,
            },
        )
        events.append(result.to_event())
        if not result.success or not isinstance(result.data, dict):
            return {"events": events}

        duplicate_candidates = {
            "customers": result.data.get("customers") or [],
            "leads": result.data.get("leads") or [],
            "hidden_customer_count": result.data.get("hidden_customer_count") or 0,
            "hidden_lead_count": result.data.get("hidden_lead_count") or 0,
        }
        if (
            not duplicate_candidates["customers"]
            and not duplicate_candidates["leads"]
            and not duplicate_candidates["hidden_customer_count"]
            and not duplicate_candidates["hidden_lead_count"]
        ):
            return {"events": events}

        events.append({
            "event": "creation_duplicate_candidates",
            "customers": duplicate_candidates["customers"],
            "leads": duplicate_candidates["leads"],
            "hidden_customer_count": duplicate_candidates["hidden_customer_count"],
            "hidden_lead_count": duplicate_candidates["hidden_lead_count"],
        })
        return {"creation_duplicate_candidates": duplicate_candidates, "events": events}

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
        candidates = business_rules.extract_customer_candidates(result.data) if result.success else []
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
        return self.response_builder.build(state)

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
        step_labels = {
            "load_memory": "加载会话记忆",
            "semantic_parse": "AI 语义理解",
            "search_creation_duplicates": "检查创建重复",
            "search_customer": "搜索客户",
            "evaluate_follow_up_quality": "AI 跟进质量评估",
            "load_customer_context": "加载客户上下文",
            "generate_suggestions": "AI 生成业务建议",
            "build_response": "生成业务回复",
        }
        async for chunk in self._graph.astream(input_state, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for step_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                step_label = step_labels.get(step_name, step_name)
                if step_name != "build_response":
                    yield {"event": "agent_step", "step": step_name, "status": "started", "content": step_label}
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
                if step_name != "build_response":
                    yield {"event": "agent_step", "step": step_name, "status": "completed", "content": step_label}

    def _should_skip_stream_step(self, step_name: str, state: AgentGraphState) -> bool:
        if step_name == "search_creation_duplicates":
            return not self._should_run_creation_duplicate_search(state)
        if step_name == "search_customer":
            return not self._should_enter_customer_resolution(state)
        if step_name == "evaluate_follow_up_quality":
            return not self._should_run_follow_up_quality(state)
        if step_name == "load_customer_context":
            return not self._should_run_customer_context(state)
        if step_name == "generate_suggestions":
            return not self._should_run_suggestions(state)
        return False

    def _should_run_creation_duplicate_search(self, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        parsed = state.get("parsed") or {}
        lead = parsed.get("lead") or {}
        customer = parsed.get("customer_create") or {}
        return (
            bool(semantic_result)
            and semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}
            and bool(state.get("authorization"))
            and bool(state.get("db"))
            and not self._requires_clarification(semantic_result)
            and bool(
                lead.get("lead_name")
                or customer.get("account_name")
                or lead.get("contact_phone")
                or customer.get("contact_phone")
            )
        )

    def _should_run_customer_search(self, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        if not semantic_result or semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}:
            return False
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(state.get("memory"))
        return (
            not self._follow_up_quality_blocks(state)
            and bool(state.get("authorization"))
            and bool(state.get("db"))
            and bool(parsed.get("customer_name"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(memory_customer),
            )
            and not self._should_use_memory_customer(semantic_result, parsed, memory_customer)
        )

    def _should_enter_customer_resolution(self, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        if not semantic_result or semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}:
            return False
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(state.get("memory"))
        if self._should_run_customer_search(state):
            return True
        return (
            not self._follow_up_quality_blocks(state)
            and bool(state.get("authorization"))
            and bool(state.get("db"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(memory_customer),
            )
            and self._should_use_memory_customer(semantic_result, parsed, memory_customer)
        )

    def _should_run_follow_up_quality(self, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        return (
            bool(semantic_result)
            and semantic_result.intent == "CUSTOMER_FOLLOW_UP"
            and bool(state.get("db"))
            and self._has_single_customer(state)
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(self._memory_current_customer(state.get("memory"))),
            )
        )

    def _should_run_customer_context(self, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        return (
            not (semantic_result and semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"})
            and not self._follow_up_quality_blocks(state)
            and bool((state.get("selected_customer") or {}).get("id"))
            and bool(state.get("authorization"))
            and bool(state.get("db"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(self._memory_current_customer(state.get("memory"))),
            )
        )

    def _should_run_suggestions(self, state: AgentGraphState) -> bool:
        semantic_result = state.get("semantic_result")
        return (
            not (semantic_result and semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"})
            and not self._follow_up_quality_blocks(state)
            and bool(semantic_result)
            and bool(state.get("business_context"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(self._memory_current_customer(state.get("memory"))),
            )
        )

    @staticmethod
    def _merge_stream_update(state: AgentGraphState, update: AgentGraphState) -> None:
        for key, value in update.items():
            if key == "events":
                continue
            state[key] = value

    @staticmethod
    def _build_semantic_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        return AgentResponseBuilder.build_semantic_trace_events(state)

    @staticmethod
    def _build_suggestion_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        return AgentResponseBuilder.build_suggestion_trace_events(state)

    @staticmethod
    def _build_follow_up_quality_trace_events(state: AgentGraphState) -> List[Dict[str, Any]]:
        return AgentResponseBuilder.build_follow_up_quality_trace_events(state)

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
    def _customer_requires_procurement_method(customer: Dict[str, Any]) -> bool:
        return business_rules.customer_requires_procurement_method(customer)

    @staticmethod
    def _customer_default_procurement_method_id(customer: Dict[str, Any]) -> Optional[int]:
        return business_rules.customer_default_procurement_method_id(customer)

    @staticmethod
    def opportunity_interaction_fields(missing_fields: List[str]) -> List[str]:
        return business_rules.opportunity_interaction_fields(missing_fields)

    @staticmethod
    def opportunity_missing_display_fields(missing_fields: List[str]) -> List[str]:
        return business_rules.opportunity_missing_display_fields(missing_fields)

    @staticmethod
    def opportunity_field_defaults(customer: Dict[str, Any]) -> Dict[str, Any]:
        return business_rules.opportunity_field_defaults(customer)

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
                and semantic_result.intent not in {"CREATE_LEAD", "CREATE_CUSTOMER"}
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
        if parsed.get("_customer_name_source") == "EXPLICIT_TEXT_HINT":
            return False
        if semantic_result.intent in {"UNKNOWN", "CUSTOMER_QUERY"}:
            return False
        if semantic_result.customer.resolution_source == "MEMORY":
            return True
        return not parsed.get("customer_name")

    @staticmethod
    def _apply_explicit_customer_hint(
        semantic_result: AgentSemanticParseResult,
        parsed: Dict[str, Any],
        content: str,
        memory: Optional[Any],
    ) -> Dict[str, Any]:
        if semantic_result.customer.resolution_source == "EXPLICIT":
            return parsed
        if semantic_result.intent in {"UNKNOWN", "CUSTOMER_QUERY", "CREATE_LEAD", "CREATE_CUSTOMER"}:
            return parsed

        memory_customer = CRMAgentGraphService._memory_current_customer(memory)
        hint = explicit_customer_hint_from_message(
            content,
            memory_customer_name=(memory_customer or {}).get("account_name"),
        )
        if not hint:
            return parsed
        return {
            **parsed,
            "customer_name": hint,
            "_customer_name_source": "EXPLICIT_TEXT_HINT",
        }

    @staticmethod
    def _build_business_response(intent: str, parsed: Dict[str, Any], candidates: List[Dict[str, Any]], business_context: Dict[str, Any]):
        return BusinessResponseBuilder().build(
            intent,
            parsed,
            candidates,
            business_context,
        )


crm_agent_graph_service = CRMAgentGraphService()
