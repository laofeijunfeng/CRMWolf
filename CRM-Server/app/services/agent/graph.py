"""CRM AI Agent LangGraph service."""
from __future__ import annotations

from datetime import date, datetime
from typing import AsyncGenerator, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import business_rules
from app.services.agent.action_planning_graph import ActionPlanningGraphService
from app.services.agent.business_context_graph import BusinessContextGraphService
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    checkpoint_unavailable_fallback_event,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.creation_duplicates_graph import CreationDuplicateGraphService
from app.services.agent.customer_mentions import explicit_customer_hint_from_message
from app.services.agent.customer_resolution_graph import CustomerResolutionGraphService
from app.services.agent.follow_up_quality_graph import FollowUpQualityGraphService
from app.services.agent.memory import AgentMemoryService, agent_memory_service
from app.services.agent.quality import (
    AgentFollowUpQualityEvaluator,
    agent_follow_up_quality_evaluator,
)
from app.services.agent.read_query_planner import (
    AgentReadQueryPlanner,
    agent_read_query_planner,
)
from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentMemorySnapshot,
    AgentSemanticParseResult,
    AgentSuggestionResult,
)
from app.services.agent.semantic import AgentSemanticParser, AgentSemanticParserError, agent_semantic_parser
from app.services.agent.semantic_payload import parsed_from_semantic
from app.services.agent.state import (
    AgentGraphInput,
    AgentGraphResult,
    AgentGraphRuntimeContext,
    AgentGraphState,
    internal_graph_start_event,
    visible_graph_events,
)
from app.services.agent.suggestion import (
    AgentSuggestionGenerator,
    agent_suggestion_generator,
)
from app.services.agent.temporal import AgentTemporalResolver, agent_temporal_resolver
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.trace_events import (
    build_follow_up_quality_trace_events,
    build_semantic_trace_events,
    build_suggestion_trace_events,
)
from app.services.agent.types import JSONDict, coerce_json_dict

NEW_FLOW_CHECKPOINT_NS = "crm_agent_new_flow"


def build_new_flow_thread_id(*, team_id: int, user_id: int, session_id: int) -> str:
    """Return the stable LangGraph thread id for one new-flow conversation."""

    return f"crm_agent_new_flow:{team_id}:{user_id}:{session_id}"


def build_new_flow_graph_config(*, team_id: int, user_id: int, session_id: int) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_new_flow_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_new_flow",
            "runtime_namespace": NEW_FLOW_CHECKPOINT_NS,
        },
    }


class CRMAgentGraphService:
    def __init__(
        self,
        tool_service: Optional[CRMAgentToolService] = None,
        semantic_parser: Optional[AgentSemanticParser] = None,
        memory_service: Optional[AgentMemoryService] = None,
        tool_registry: Optional[AgentToolRegistry] = None,
        read_query_planner: Optional[AgentReadQueryPlanner] = None,
        temporal_resolver: Optional[AgentTemporalResolver] = None,
        suggestion_generator: Optional[AgentSuggestionGenerator] = None,
        follow_up_quality_evaluator: Optional[AgentFollowUpQualityEvaluator] = None,
        checkpointer: object | None = None,
    ) -> None:
        self.semantic_parser = semantic_parser or agent_semantic_parser
        self.memory_service = memory_service or agent_memory_service
        self.read_query_planner = read_query_planner or agent_read_query_planner
        self.temporal_resolver = temporal_resolver or agent_temporal_resolver
        self.suggestion_generator = suggestion_generator or agent_suggestion_generator
        self.follow_up_quality_evaluator = follow_up_quality_evaluator or agent_follow_up_quality_evaluator
        if tool_registry:
            self.tool_registry = tool_registry
        elif tool_service:
            self.tool_registry = AgentToolRegistry(tool_service)
        else:
            self.tool_registry = agent_tool_registry
        self.customer_resolution_graph_service = CustomerResolutionGraphService(
            tool_registry=self.tool_registry,
            checkpointer=checkpointer,
        )
        self.creation_duplicate_graph_service = CreationDuplicateGraphService(
            tool_registry=self.tool_registry,
            checkpointer=checkpointer,
        )
        self.follow_up_quality_graph_service = FollowUpQualityGraphService(
            follow_up_quality_evaluator=self.follow_up_quality_evaluator,
            checkpointer=checkpointer,
        )
        self.business_context_graph_service = BusinessContextGraphService(
            tool_registry=self.tool_registry,
            suggestion_generator=self.suggestion_generator,
            checkpointer=checkpointer,
        )
        self.action_planning_graph_service = ActionPlanningGraphService(checkpointer=checkpointer)
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(AgentGraphState, context_schema=AgentGraphRuntimeContext)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("semantic_parse", self._semantic_parse)
        graph.add_node("run_agent_read_tool", self._run_agent_read_tool)
        graph.add_node("search_creation_duplicates", self._search_creation_duplicates)
        graph.add_node("evaluate_follow_up_quality", self._evaluate_follow_up_quality)
        graph.add_node("search_customer", self._search_customer)
        graph.add_node("load_customer_context", self._load_customer_context)
        graph.add_node("build_response", self._build_response)
        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "semantic_parse")
        graph.add_conditional_edges(
            "semantic_parse",
            self._route_after_semantic_parse,
            {
                "agent_read_tool": "run_agent_read_tool",
                "creation_duplicates": "search_creation_duplicates",
                "customer_search": "search_customer",
                "response": "build_response",
            },
        )
        graph.add_edge("run_agent_read_tool", "build_response")
        graph.add_edge("search_creation_duplicates", "build_response")
        graph.add_conditional_edges(
            "search_customer",
            self._route_after_customer_search,
            {
                "agent_read_tool": "run_agent_read_tool",
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
                "response": "build_response",
            },
        )
        graph.add_edge("build_response", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    def _route_after_semantic_parse(self, state: AgentGraphState) -> str:
        if self._should_run_agent_read_tool(state):
            return "agent_read_tool"
        if self._should_run_creation_duplicate_search(state):
            return "creation_duplicates"
        if self._should_enter_customer_resolution(state):
            return "customer_search"
        return "response"

    def _route_after_customer_search(self, state: AgentGraphState) -> str:
        if self._should_run_customer_scoped_agent_read_tool(state):
            return "agent_read_tool"
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
        return "response"

    def _load_memory(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        current_datetime = context.current_datetime or self.temporal_resolver.now()
        context.side_effects.current_datetime = current_datetime
        current_date = current_datetime.date().isoformat()
        if not context.db:
            return {"current_date": current_date}
        memory = self.memory_service.load_snapshot(
            context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            session_context=context.session_context,
        )
        context.side_effects.memory = memory
        return {
            "current_date": current_date,
            "memory_snapshot": coerce_json_dict(memory.model_dump(exclude_none=True)),
            "events": [{"event": "memory_loaded"}],
        }

    async def _semantic_parse(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        memory = context.side_effects.memory
        try:
            if hasattr(self.semantic_parser, "parse_with_metadata"):
                envelope = await self.semantic_parser.parse_with_metadata(
                    context.db,
                    team_id=context.team_id,
                    user_message=state.get("content", ""),
                    memory=memory,
                    current_date=self._current_date(state),
                )
                semantic_result = envelope.result
                parse_source = envelope.parse_source
                model_name = envelope.model
                fallback_reason = envelope.fallback_reason
                fallback_error = envelope.fallback_error
            else:
                semantic_result = await self.semantic_parser.parse(
                    context.db,
                    team_id=context.team_id,
                    user_message=state.get("content", ""),
                    memory=memory,
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
            base_datetime=context.side_effects.current_datetime,
        )
        parsed = self._apply_explicit_customer_hint(
            semantic_result,
            parsed,
            state.get("content", ""),
            memory,
        )
        context.side_effects.semantic_result = semantic_result
        return {
            "intent": semantic_result.intent,
            "semantic": coerce_json_dict(semantic_result.model_dump(exclude_none=True)),
            "semantic_metadata": {
                "parse_source": parse_source,
                "model": model_name,
                "fallback_reason": fallback_reason,
                "fallback_error": fallback_error,
            },
            "parsed": parsed,
        }

    async def _search_creation_duplicates(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        semantic_result = context.side_effects.semantic_result
        if not semantic_result:
            return {}

        result = await self.creation_duplicate_graph_service.run({
            "db": context.db,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "content": state.get("content", ""),
            "authorization": context.authorization or "",
            "semantic_result": semantic_result,
            "parsed": state.get("parsed") or {},
            "events": [],
        })
        state_update: AgentGraphState = {"events": result.get("events") or []}
        duplicate_candidates = result.get("creation_duplicate_candidates")
        if duplicate_candidates:
            state_update["creation_duplicate_candidates"] = duplicate_candidates
        return state_update

    async def _run_agent_read_tool(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        read_query = self.read_query_planner.plan(
            semantic_result=_semantic_from_state(state),
            content=state.get("content", ""),
            parsed=state.get("parsed") or {},
            selected_customer=state.get("selected_customer") or None,
        )
        if (
            not read_query
            or read_query.requires_customer_resolution
            or not read_query.tool_name
            or not context.db
            or not context.authorization
        ):
            return {}
        tool_context = AgentToolContext(
            db=context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            authorization=context.authorization,
        )
        result = await self.tool_registry.execute(
            read_query.tool_name,
            tool_context,
            read_query.payload,
        )
        recent_follow_up_tasks = _recent_follow_up_tasks_from_tool_result(
            read_query.tool_name,
            result.data,
        )
        event: JSONDict = {
            "event": "agent_read_tool_executed",
            "tool_name": read_query.tool_name,
            "query_type": read_query.query_type,
            "trace_label": read_query.trace_label,
            "success": result.success,
        }
        if recent_follow_up_tasks:
            event["recent_follow_up_tasks"] = recent_follow_up_tasks
        return {
            "read_tool_name": read_query.tool_name,
            "read_tool_payload": coerce_json_dict(read_query.payload),
            "read_query_type": read_query.query_type,
            "read_query_trace_label": read_query.trace_label,
            "read_tool_result": coerce_json_dict(result.to_event()),
            "events": [event],
        }

    async def _evaluate_follow_up_quality(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        semantic_result = context.side_effects.semantic_result
        if not semantic_result:
            return {}

        result = await self.follow_up_quality_graph_service.run({
            "db": context.db,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "content": state.get("content", ""),
            "current_date": self._current_date(state) or "",
            "semantic_result": semantic_result,
            "memory": context.side_effects.memory,
            "has_single_customer": self._has_single_customer(state),
            "has_memory_customer": bool(self._memory_current_customer(context.side_effects.memory)),
            "events": [],
        })
        state_update: AgentGraphState = {"events": result.get("events") or []}
        follow_up_quality_result = result.get("follow_up_quality_result")
        if follow_up_quality_result:
            context.side_effects.follow_up_quality_result = follow_up_quality_result
            state_update["follow_up_quality"] = coerce_json_dict(
                follow_up_quality_result.model_dump(exclude_none=True)
            )
        follow_up_quality_metadata = result.get("follow_up_quality_metadata")
        if follow_up_quality_metadata:
            state_update["follow_up_quality_metadata"] = follow_up_quality_metadata
        follow_up_quality_error = result.get("follow_up_quality_error")
        if isinstance(follow_up_quality_error, str):
            state_update["follow_up_quality_error"] = follow_up_quality_error
        return state_update

    async def _search_customer(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        result = await self.customer_resolution_graph_service.run({
            "db": context.db,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "content": state.get("content", ""),
            "authorization": context.authorization or "",
            "intent": state.get("intent"),
            "memory": context.side_effects.memory,
            "semantic_result": context.side_effects.semantic_result,
            "parsed": state.get("parsed") or {},
            "events": [],
        })
        state_update: AgentGraphState = {
            "customer_candidates": result.get("customer_candidates") or [],
            "events": result.get("events") or [],
        }
        parsed = result.get("parsed")
        if parsed:
            state_update["parsed"] = parsed
        selected_customer = result.get("selected_customer")
        if selected_customer:
            state_update["selected_customer"] = selected_customer
        return state_update

    async def _load_customer_context(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        if (
            not self._should_run_customer_context(state)
            or not context.side_effects.semantic_result
        ):
            return {}

        result = await self.business_context_graph_service.run({
            "db": context.db,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "content": state.get("content", ""),
            "authorization": context.authorization or "",
            "current_date": self._current_date(state),
            "selected_customer": state.get("selected_customer") or {},
            "semantic_result": context.side_effects.semantic_result,
            "events": [],
        })
        state_update: AgentGraphState = {"events": result.get("events") or []}
        business_context = result.get("business_context")
        if business_context:
            state_update["business_context"] = business_context
        suggestion_result = result.get("suggestion_result")
        if suggestion_result:
            context.side_effects.suggestion_result = suggestion_result
            state_update["suggestion"] = coerce_json_dict(suggestion_result.model_dump(exclude_none=True))
        suggestion_metadata = result.get("suggestion_metadata")
        if suggestion_metadata:
            state_update["suggestion_metadata"] = suggestion_metadata
        suggestion_error = result.get("suggestion_error")
        if isinstance(suggestion_error, str):
            state_update["suggestion_error"] = suggestion_error
        return state_update

    async def _build_response(
        self,
        state: AgentGraphState,
        runtime: Runtime[AgentGraphRuntimeContext],
    ) -> AgentGraphState:
        context = runtime.context
        result = await self.action_planning_graph_service.run({
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "content": state.get("content", ""),
            "intent": state.get("intent"),
            "parsed": state.get("parsed") or {},
            "customer_candidates": state.get("customer_candidates") or [],
            "selected_customer": state.get("selected_customer"),
            "business_context": state.get("business_context") or {},
            "read_tool_name": state.get("read_tool_name"),
            "read_tool_payload": state.get("read_tool_payload") or {},
            "read_tool_result": state.get("read_tool_result") or {},
            "read_query_type": state.get("read_query_type"),
            "read_query_trace_label": state.get("read_query_trace_label"),
            "semantic": state.get("semantic") or {},
            "semantic_metadata": state.get("semantic_metadata") or {},
            "semantic_error": state.get("semantic_error"),
            "follow_up_quality": state.get("follow_up_quality") or {},
            "follow_up_quality_metadata": state.get("follow_up_quality_metadata") or {},
            "follow_up_quality_error": state.get("follow_up_quality_error"),
            "creation_duplicate_candidates": state.get("creation_duplicate_candidates") or {},
            "suggestion": state.get("suggestion") or {},
            "suggestion_metadata": state.get("suggestion_metadata") or {},
            "suggestion_error": state.get("suggestion_error"),
            "events": state.get("events") or [],
            "suppress_trace_events": bool(state.get("suppress_trace_events")),
            "memory": context.side_effects.memory,
            "semantic_result": context.side_effects.semantic_result,
            "follow_up_quality_result": context.side_effects.follow_up_quality_result,
            "suggestion_result": context.side_effects.suggestion_result,
        })
        return {
            "response": result.get("response"),
            "events": result.get("events") or [],
        }

    async def run(self, input_state: AgentGraphInput) -> AgentGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = _runtime_context_from_input(input_state)
        config = build_new_flow_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        try:
            return _with_visible_events(await self._graph.ainvoke(checkpoint_state, config, context=context))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_context = _runtime_context_from_input(input_state)
            result = _with_visible_events(await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context))
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_new_flow",
                graph=NEW_FLOW_CHECKPOINT_NS,
            )

    async def stream_events(self, input_state: AgentGraphInput) -> AsyncGenerator[JSONDict, None]:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        checkpoint_state["suppress_trace_events"] = True
        context = _runtime_context_from_input(input_state)
        config = build_new_flow_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        step_labels = {
            "load_memory": "加载会话记忆",
            "semantic_parse": "AI 语义理解",
            "run_agent_read_tool": "查询任务/工作事实",
            "search_creation_duplicates": "检查创建重复",
            "search_customer": "搜索客户",
            "evaluate_follow_up_quality": "AI 跟进质量评估",
            "load_customer_context": "加载客户上下文",
            "generate_suggestions": "AI 生成业务建议",
            "build_response": "生成业务回复",
        }
        try:
            async for event in self._stream_graph_updates(
                self._graph,
                checkpoint_state,
                context,
                config,
                step_labels,
            ):
                yield event
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_context = _runtime_context_from_input(input_state)
            yield checkpoint_unavailable_fallback_event(
                runtime="crm_agent_new_flow",
                graph=NEW_FLOW_CHECKPOINT_NS,
            )
            async for event in self._stream_graph_updates(
                self._fallback_graph,
                checkpoint_state,
                fallback_context,
                config,
                step_labels,
            ):
                yield event

    async def _stream_graph_updates(
        self,
        graph: object,
        checkpoint_state: AgentGraphState,
        context: AgentGraphRuntimeContext,
        config: RunnableConfig,
        step_labels: dict[str, str],
    ) -> AsyncGenerator[JSONDict, None]:
        state: AgentGraphState = dict(checkpoint_state)
        if not hasattr(graph, "astream"):
            return
        async for chunk in graph.astream(checkpoint_state, config, context=context, stream_mode="updates"):
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
                    yield coerce_json_dict(event)
                if step_name == "semantic_parse":
                    for event in self._build_semantic_trace_events(state):
                        yield coerce_json_dict(event)
                elif step_name == "evaluate_follow_up_quality":
                    for event in self._build_follow_up_quality_trace_events(state):
                        yield coerce_json_dict(event)
                elif step_name == "load_customer_context":
                    for event in self._build_suggestion_trace_events(state):
                        yield coerce_json_dict(event)
                elif step_name == "generate_suggestions":
                    for event in self._build_suggestion_trace_events(state):
                        yield coerce_json_dict(event)
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
        semantic_result = _semantic_from_state(state)
        parsed = state.get("parsed") or {}
        lead = parsed.get("lead") or {}
        customer = parsed.get("customer_create") or {}
        return (
            bool(semantic_result)
            and semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}
            and bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and not self._requires_clarification(semantic_result)
            and bool(
                lead.get("lead_name")
                or customer.get("account_name")
                or lead.get("contact_phone")
                or customer.get("contact_phone")
            )
        )

    def _should_run_agent_read_tool(self, state: AgentGraphState) -> bool:
        read_query = self.read_query_planner.plan(
            semantic_result=_semantic_from_state(state),
            content=state.get("content", ""),
            parsed=state.get("parsed") or {},
        )
        return (
            bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and bool(read_query)
            and not read_query.requires_customer_resolution
            and bool(read_query.tool_name)
        )

    def _should_run_customer_scoped_agent_read_tool(self, state: AgentGraphState) -> bool:
        read_query = self.read_query_planner.plan(
            semantic_result=_semantic_from_state(state),
            content=state.get("content", ""),
            parsed=state.get("parsed") or {},
            selected_customer=state.get("selected_customer") or None,
        )
        return (
            bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and bool((state.get("selected_customer") or {}).get("id"))
            and bool(read_query)
            and not read_query.requires_customer_resolution
            and bool(read_query.tool_name)
        )

    def _should_run_customer_search(self, state: AgentGraphState) -> bool:
        semantic_result = _semantic_from_state(state)
        if not semantic_result or semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}:
            return False
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(_memory_from_state(state))
        return (
            not self._follow_up_quality_blocks(state)
            and bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and bool(parsed.get("customer_name"))
            and not self._customer_resolution_clarification_blocks(
                semantic_result,
                parsed,
                has_memory_customer=bool(memory_customer),
            )
            and not self._should_use_memory_customer(semantic_result, parsed, memory_customer)
        )

    def _should_enter_customer_resolution(self, state: AgentGraphState) -> bool:
        semantic_result = _semantic_from_state(state)
        if not semantic_result or semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"}:
            return False
        parsed = state.get("parsed") or {}
        memory_customer = self._memory_current_customer(_memory_from_state(state))
        if self._should_run_customer_search(state):
            return True
        return (
            not self._follow_up_quality_blocks(state)
            and bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and not self._customer_resolution_clarification_blocks(
                semantic_result,
                parsed,
                has_memory_customer=bool(memory_customer),
            )
            and self._should_use_memory_customer(semantic_result, parsed, memory_customer)
        )

    def _should_run_follow_up_quality(self, state: AgentGraphState) -> bool:
        semantic_result = _semantic_from_state(state)
        return (
            bool(semantic_result)
            and semantic_result.intent == "CUSTOMER_ACTIVITY"
            and bool(state.get("has_db"))
            and self._has_single_customer(state)
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(self._memory_current_customer(_memory_from_state(state))),
            )
        )

    def _should_run_customer_context(self, state: AgentGraphState) -> bool:
        semantic_result = _semantic_from_state(state)
        return (
            not (semantic_result and semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"})
            and not self._follow_up_quality_blocks(state)
            and bool((state.get("selected_customer") or {}).get("id"))
            and bool(state.get("has_authorization"))
            and bool(state.get("has_db"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(self._memory_current_customer(_memory_from_state(state))),
            )
        )

    def _should_run_suggestions(self, state: AgentGraphState) -> bool:
        semantic_result = _semantic_from_state(state)
        return (
            not (semantic_result and semantic_result.intent in {"CREATE_LEAD", "CREATE_CUSTOMER"})
            and not self._follow_up_quality_blocks(state)
            and bool(semantic_result)
            and bool(state.get("business_context"))
            and not self._requires_clarification(
                semantic_result,
                has_memory_customer=bool(self._memory_current_customer(_memory_from_state(state))),
            )
        )

    @staticmethod
    def _merge_stream_update(state: AgentGraphState, update: AgentGraphState) -> None:
        for key, value in update.items():
            if key == "events":
                continue
            state[key] = value

    @staticmethod
    def _build_semantic_trace_events(state: AgentGraphState) -> List[Dict[str, object]]:
        return build_semantic_trace_events(_response_state_from_checkpoint(state))

    @staticmethod
    def _build_suggestion_trace_events(state: AgentGraphState) -> List[Dict[str, object]]:
        return build_suggestion_trace_events(_response_state_from_checkpoint(state))

    @staticmethod
    def _build_follow_up_quality_trace_events(state: AgentGraphState) -> List[Dict[str, object]]:
        return build_follow_up_quality_trace_events(_response_state_from_checkpoint(state))

    @staticmethod
    def _follow_up_quality_blocks(state: AgentGraphState) -> bool:
        quality = _follow_up_quality_from_state(state)
        return bool(quality and not quality.passed)

    @staticmethod
    def _has_single_customer(state: AgentGraphState) -> bool:
        if (state.get("selected_customer") or {}).get("id"):
            return True
        return len(state.get("customer_candidates") or []) == 1

    @staticmethod
    def _customer_requires_procurement_method(customer: Dict[str, object]) -> bool:
        return business_rules.customer_requires_procurement_method(customer)

    @staticmethod
    def _customer_default_procurement_method_id(customer: Dict[str, object]) -> Optional[int]:
        return business_rules.customer_default_procurement_method_id(customer)

    @staticmethod
    def opportunity_interaction_fields(missing_fields: List[str]) -> List[str]:
        return business_rules.opportunity_interaction_fields(missing_fields)

    @staticmethod
    def opportunity_missing_display_fields(missing_fields: List[str]) -> List[str]:
        return business_rules.opportunity_missing_display_fields(missing_fields)

    @staticmethod
    def opportunity_field_defaults(customer: Dict[str, object]) -> Dict[str, object]:
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
                and semantic_result.intent != "CRM_READ_QUERY"
                and semantic_result.intent != "FOLLOW_UP_TASK_TRANSITION"
                and semantic_result.intent not in {"CREATE_LEAD", "CREATE_CUSTOMER"}
                and not customer_from_memory
                and semantic_result.customer.confidence < 0.7
            )
        )

    @staticmethod
    def _customer_resolution_clarification_blocks(
        semantic_result: Optional[AgentSemanticParseResult],
        parsed: Dict[str, object],
        *,
        has_memory_customer: bool = False,
    ) -> bool:
        if semantic_result is None:
            return False
        if semantic_result.intent == "UNKNOWN" or semantic_result.intent_confidence < 0.75:
            return True
        customer_name = parsed.get("customer_name")
        if isinstance(customer_name, str) and customer_name.strip():
            return False
        return CRMAgentGraphService._requires_clarification(
            semantic_result,
            has_memory_customer=has_memory_customer,
        )

    @staticmethod
    def _current_date(state: AgentGraphState) -> date | None:
        current_date = state.get("current_date")
        if isinstance(current_date, str):
            try:
                return date.fromisoformat(current_date)
            except ValueError:
                return None
        return None

    @staticmethod
    def _memory_current_customer(memory: Optional[object]) -> Optional[Dict[str, object]]:
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
        parsed: Dict[str, object],
        memory_customer: Optional[Dict[str, object]],
    ) -> bool:
        if not semantic_result or not memory_customer:
            return False
        if parsed.get("_customer_name_source") == "EXPLICIT_TEXT_HINT":
            return False
        if semantic_result.intent in {"UNKNOWN", "CRM_READ_QUERY", "FOLLOW_UP_TASK_TRANSITION"}:
            return False
        if semantic_result.customer.resolution_source == "MEMORY":
            return True
        return not parsed.get("customer_name")

    @staticmethod
    def _apply_explicit_customer_hint(
        semantic_result: AgentSemanticParseResult,
        parsed: Dict[str, object],
        content: str,
        memory: Optional[object],
    ) -> Dict[str, object]:
        if semantic_result.customer.resolution_source == "EXPLICIT":
            return parsed
        if semantic_result.intent in {"UNKNOWN", "CREATE_LEAD", "CREATE_CUSTOMER"}:
            return parsed

        memory_customer = CRMAgentGraphService._memory_current_customer(memory)
        hint = explicit_customer_hint_from_message(
            content,
            memory_customer_name=(memory_customer or {}).get("account_name"),
        )
        if not hint:
            return parsed
        parsed_customer_name = parsed.get("customer_name")
        if (
            isinstance(parsed_customer_name, str)
            and parsed_customer_name.strip()
            and (
                parsed_customer_name.strip() == hint
                or parsed_customer_name.strip() in hint
            )
            and semantic_result.customer.confidence >= 0.7
        ):
            return parsed
        return {
            **parsed,
            "customer_name": hint,
            "_customer_name_source": "EXPLICIT_TEXT_HINT",
        }


def _checkpoint_state_from_input(input_state: AgentGraphInput) -> AgentGraphState:
    """Project caller input into serializable LangGraph checkpoint state."""

    state: AgentGraphState = {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "content": str(input_state.get("content") or ""),
        "has_db": input_state.get("db") is not None,
        "has_authorization": isinstance(input_state.get("authorization"), str)
        and bool(str(input_state.get("authorization")).strip()),
        "intent": None,
        "memory_snapshot": {},
        "semantic": {},
        "semantic_metadata": {},
        "semantic_error": None,
        "follow_up_quality": {},
        "follow_up_quality_metadata": {},
        "follow_up_quality_error": None,
        "parsed": {},
        "customer_candidates": [],
        "creation_duplicate_candidates": {},
        "selected_customer": None,
        "business_context": {},
        "read_tool_name": None,
        "read_tool_payload": {},
        "read_tool_result": {},
        "suggestion": {},
        "suggestion_metadata": {},
        "suggestion_error": None,
        "suppress_trace_events": False,
        "response": None,
        "events": [internal_graph_start_event("agent_graph_invocation_started")],
    }
    current_datetime = input_state.get("current_datetime")
    if isinstance(current_datetime, datetime):
        state["current_date"] = current_datetime.date().isoformat()
    events = input_state.get("events")
    if isinstance(events, list):
        state["events"].extend(
            coerce_json_dict(event)
            for event in events
            if isinstance(event, dict)
        )
    return state


def _with_visible_events(result: AgentGraphResult) -> AgentGraphResult:
    projected: AgentGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _runtime_context_from_input(input_state: AgentGraphInput) -> AgentGraphRuntimeContext:
    authorization = input_state.get("authorization")
    current_datetime = input_state.get("current_datetime")
    return AgentGraphRuntimeContext(
        db=input_state.get("db"),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        session_context=coerce_json_dict(input_state.get("session_context")),
        authorization=authorization if isinstance(authorization, str) else None,
        current_datetime=current_datetime if isinstance(current_datetime, datetime) else None,
    )


def _response_state_from_checkpoint(state: AgentGraphState) -> dict[str, object]:
    response_state: dict[str, object] = dict(state)
    memory = _memory_from_state(state)
    semantic_result = _semantic_from_state(state)
    follow_up_quality_result = _follow_up_quality_from_state(state)
    suggestion_result = _suggestion_from_state(state)
    if memory:
        response_state["memory"] = memory
    if semantic_result:
        response_state["semantic_result"] = semantic_result
    if follow_up_quality_result:
        response_state["follow_up_quality_result"] = follow_up_quality_result
    if suggestion_result:
        response_state["suggestion_result"] = suggestion_result
    return response_state


def _semantic_from_state(state: AgentGraphState) -> AgentSemanticParseResult | None:
    semantic = coerce_json_dict(state.get("semantic"))
    if not semantic:
        return None
    try:
        return AgentSemanticParseResult.model_validate(semantic)
    except ValueError:
        return None


def _memory_from_state(state: AgentGraphState) -> AgentMemorySnapshot | None:
    memory = coerce_json_dict(state.get("memory_snapshot"))
    if not memory:
        return None
    try:
        return AgentMemorySnapshot.model_validate(memory)
    except ValueError:
        return None


def _follow_up_quality_from_state(state: AgentGraphState) -> AgentFollowUpQualityResult | None:
    quality = coerce_json_dict(state.get("follow_up_quality"))
    if not quality:
        return None
    try:
        return AgentFollowUpQualityResult.model_validate(quality)
    except ValueError:
        return None


def _suggestion_from_state(state: AgentGraphState) -> AgentSuggestionResult | None:
    suggestion = coerce_json_dict(state.get("suggestion"))
    if not suggestion:
        return None
    try:
        return AgentSuggestionResult.model_validate(suggestion)
    except ValueError:
        return None


def _recent_follow_up_tasks_from_tool_result(tool_name: object, data: object) -> list[JSONDict]:
    if tool_name not in {"list_follow_up_tasks", "get_follow_up_task_detail"}:
        return []
    payload = coerce_json_dict(data)
    raw_items: list[object]
    if tool_name == "get_follow_up_task_detail":
        raw_items = [payload]
    else:
        items = payload.get("items")
        raw_items = items if isinstance(items, list) else []

    tasks: list[JSONDict] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = coerce_json_dict(raw_item)
        task_id = str(item.get("id") or item.get("task_id") or "").strip()
        if not task_id.startswith("fut_") or task_id in seen:
            continue
        seen.add(task_id)
        customer = coerce_json_dict(item.get("customer"))
        customer_name = (
            str(customer.get("name") or customer.get("account_name") or "").strip()
            if customer
            else ""
        )
        tasks.append({
            "id": task_id,
            "title": str(item.get("title") or item.get("description") or "").strip(),
            "customer_name": customer_name,
            "status": str(item.get("status") or "").strip(),
            "due_at": item.get("due_at"),
        })
        if len(tasks) >= 20:
            break
    return tasks


crm_agent_graph_service = CRMAgentGraphService(checkpointer=agent_checkpoint_saver)
