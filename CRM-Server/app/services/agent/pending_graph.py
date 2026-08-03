"""LangGraph orchestration for turns with a waiting task."""
from __future__ import annotations


from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from sqlalchemy.exc import SQLAlchemyError

from app.crud.agent import agent_task_crud
from app.models.agent import AgentTaskStatus
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent import agent_copy
from app.services.agent import execution_trace
from app.services.agent import interactions
from app.services.agent import session_state
from app.services.agent import task_display
from app.services.agent.hitl_runtime import interrupt_from_runtime_events
from app.services.agent.interrupts import AgentInterruptPayload, interrupt_from_waiting_event, interrupt_from_waiting_task
from app.services.agent.pending_interaction_graph import (
    PendingInteractionGraphService,
    pending_interaction_graph_service,
)
from app.services.agent.pending_preflight_graph import PendingPreflightGraphService, pending_preflight_graph_service
from app.services.agent.schemas import AgentConfirmationIntentDecision
from app.services.agent.state import (
    internal_graph_start_event,
    PendingTaskGraphInput,
    PendingTaskGraphResult,
    PendingTaskGraphSideEffects,
    PendingTaskGraphState,
    PendingTaskRuntimeContext,
    PendingTaskTurnResult,
    visible_graph_events,
)
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value


class PendingTaskGraphService:
    """Runs pending-task routing as a small business state machine."""

    state_change_confidence_threshold = 0.75

    def __init__(
        self,
        *,
        preflight_graph_service: PendingPreflightGraphService | None = None,
        interaction_graph_service: PendingInteractionGraphService | None = None,
        checkpointer: object | None = None,
    ) -> None:
        self.preflight_graph_service = preflight_graph_service or pending_preflight_graph_service
        self.interaction_graph_service = interaction_graph_service or pending_interaction_graph_service
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(PendingTaskGraphState, context_schema=PendingTaskRuntimeContext)
        graph.add_node("load_suspended_candidates", self._load_suspended_candidates)
        graph.add_node("classify_turn_relation", self._classify_turn_relation)
        graph.add_node("apply_turn_relation", self._apply_turn_relation)
        graph.add_node("wait_turn_relation_clarification", self._wait_turn_relation_clarification)
        graph.add_node("apply_resume_payload", self._apply_resume_payload)
        graph.add_node("apply_interaction_resume", self._apply_interaction_resume)
        graph.add_node("preflight", self._preflight)
        graph.add_node("plan_interaction", self._plan_interaction)
        graph.add_node("wait_interaction_interrupt", self._wait_interaction_interrupt)
        graph.add_edge(START, "load_suspended_candidates")
        graph.add_conditional_edges(
            "load_suspended_candidates",
            self._route_after_load_suspended_candidates,
            {
                "classify": "classify_turn_relation",
                "resume": "apply_resume_payload",
                "preflight": "preflight",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "apply_resume_payload",
            self._route_after_apply_resume_payload,
            {
                "field_resume": "apply_interaction_resume",
                "choice_resume": "apply_interaction_resume",
                "text_resume": "apply_interaction_resume",
                "preflight": "preflight",
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "apply_interaction_resume",
            self._route_after_resume_application,
            {
                "interrupt": "wait_interaction_interrupt",
                "end": END,
            },
        )
        graph.add_edge("classify_turn_relation", "apply_turn_relation")
        graph.add_conditional_edges(
            "apply_turn_relation",
            self._route_after_apply_turn_relation,
            {
                "interrupt": "wait_turn_relation_clarification",
                "preflight": "preflight",
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "wait_turn_relation_clarification",
            self._route_after_wait_turn_relation_clarification,
            {
                "classify": "classify_turn_relation",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "preflight",
            self._route_after_preflight,
            {
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "plan_interaction",
            self._route_after_plan_interaction,
            {
                "interrupt": "wait_interaction_interrupt",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "wait_interaction_interrupt",
            self._route_after_wait_interaction_interrupt,
            {
                "field_resume": "apply_interaction_resume",
                "choice_resume": "apply_interaction_resume",
                "text_resume": "apply_interaction_resume",
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        input_state: PendingTaskGraphInput,
        *,
        side_effects: PendingTaskGraphSideEffects | None = None,
    ) -> PendingTaskGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        graph_side_effects = side_effects or PendingTaskGraphSideEffects(task=input_state.get("task"))
        if graph_side_effects.task is None:
            graph_side_effects.task = input_state.get("task")
        context = _runtime_context_from_input(input_state, graph_side_effects)
        config = build_pending_task_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            task_id=_optional_object_id(context.task),
        )
        if self._checkpoint_enabled:
            graph_input = await _graph_input_from_turn(self._graph, input_state, checkpoint_state, config)
        else:
            graph_input = checkpoint_state
        try:
            result = await self._graph.ainvoke(graph_input, config, context=context)
            return _with_visible_events(_merge_side_effects(result))
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_side_effects = side_effects or PendingTaskGraphSideEffects(task=input_state.get("task"))
            if fallback_side_effects.task is None:
                fallback_side_effects.task = input_state.get("task")
            fallback_context = _runtime_context_from_input(input_state, fallback_side_effects)
            result = await self._fallback_graph.ainvoke(checkpoint_state, config, context=fallback_context)
            merged = _with_visible_events(_merge_side_effects(result))
            return with_checkpoint_unavailable_fallback_event(
                merged,
                runtime="crm_agent_pending_task",
                graph=PENDING_TASK_CHECKPOINT_NS,
            )

    async def run_with_trace(
        self,
        input_state: PendingTaskGraphInput,
        *,
        side_effects: PendingTaskGraphSideEffects | None = None,
    ) -> PendingTaskGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        graph_side_effects = side_effects or PendingTaskGraphSideEffects(task=input_state.get("task"))
        if graph_side_effects.task is None:
            graph_side_effects.task = input_state.get("task")
        context = _runtime_context_from_input(input_state, graph_side_effects)
        config = build_pending_task_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            task_id=_optional_object_id(context.task),
        )
        if self._checkpoint_enabled:
            graph_input = await _graph_input_from_turn(self._graph, input_state, checkpoint_state, config)
        else:
            graph_input = checkpoint_state
        try:
            return _with_visible_events(
                await self._run_graph_with_trace(self._graph, graph_input, checkpoint_state, context, config)
            )
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            fallback_side_effects = side_effects or PendingTaskGraphSideEffects(task=input_state.get("task"))
            if fallback_side_effects.task is None:
                fallback_side_effects.task = input_state.get("task")
            fallback_context = _runtime_context_from_input(input_state, fallback_side_effects)
            traced = await self._run_graph_with_trace(
                self._fallback_graph,
                checkpoint_state,
                checkpoint_state,
                fallback_context,
                config,
            )
            return with_checkpoint_unavailable_fallback_event(
                _with_visible_events(traced),
                runtime="crm_agent_pending_task",
                graph=PENDING_TASK_CHECKPOINT_NS,
            )

    async def _run_graph_with_trace(
        self,
        graph: object,
        graph_input: PendingTaskGraphState | Command[JSONDict],
        checkpoint_state: PendingTaskGraphState,
        context: PendingTaskRuntimeContext,
        config: RunnableConfig,
    ) -> PendingTaskGraphResult:
        astream = getattr(graph, "astream", None)
        if not callable(astream):
            result = await graph.ainvoke(graph_input, config, context=context)
            return _merge_side_effects(result)

        state: PendingTaskGraphState = dict(checkpoint_state)
        trace_events: list[JSONDict] = visible_graph_events(checkpoint_state.get("events"))
        async for chunk in astream(graph_input, config, context=context, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for step_name, update_value in chunk.items():
                if not isinstance(step_name, str) or not isinstance(update_value, dict):
                    continue
                update = coerce_json_dict(update_value)
                started_event = execution_trace.pending_task_step_started(step_name)
                if started_event:
                    trace_events.append(started_event)
                    await _publish_progress_event(context, started_event)
                _merge_stream_update(state, update)
                trace_events.extend(_events(update.get("events")))
                completed_event = execution_trace.pending_task_step_completed(step_name)
                if completed_event:
                    trace_events.append(completed_event)
                    await _publish_progress_event(context, completed_event)
        result = _merge_side_effects(state)
        result["events"] = trace_events
        return result

    def _load_suspended_candidates(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        context = runtime.context
        if context.task:
            return {}
        existing_candidates = _suspended_candidates(state.get("suspended_candidates"))
        if existing_candidates:
            return {"suspended_candidates": existing_candidates}
        return {}

    def _route_after_load_suspended_candidates(self, state: PendingTaskGraphState) -> str:
        if _resume_action(coerce_json_dict(state.get("resume_payload"))) == "cancel":
            return "resume"
        if state.get("resume_payload") and state.get("has_active_task"):
            return "resume"
        if state.get("has_active_task"):
            return "preflight"
        if state.get("suspended_candidates"):
            return "classify"
        return "end"

    def _apply_resume_payload(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        return self._apply_resume_payload_update(
            state=state,
            runtime=runtime,
            current_interrupt=None,
            emit_resume_event=False,
        )

    def _route_after_apply_resume_payload(self, state: PendingTaskGraphState) -> str:
        resume_route = state.get("resume_route")
        if (
            resume_route in {"field_resume", "choice_resume", "text_resume", "preflight", "interaction"}
            and state.get("has_active_task")
        ):
            return resume_route
        return "end"

    def _route_after_resume_application(self, state: PendingTaskGraphState) -> str:
        if state.get("pending_interrupt_requested") and state.get("current_interrupt"):
            return "interrupt"
        return "end"

    async def _apply_interaction_resume(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        task = runtime.context.task
        if not task:
            return {}
        result = await self._run_pending_interaction_subgraph(runtime, task)
        return _pending_turn_result_update(result, runtime=runtime, task=task)

    async def _run_pending_interaction_subgraph(
        self,
        runtime: Runtime[PendingTaskRuntimeContext],
        task: object,
    ) -> PendingTaskTurnResult:
        context = runtime.context
        return await self.interaction_graph_service.run({
            "db": context.db,
            "task": task,
            "content": context.content,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "authorization": context.authorization or "",
            "interaction_metadata": context.turn_input.metadata if context.turn_input else {},
            "events": [],
        })

    async def _classify_turn_relation(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        context = runtime.context
        if not context.turn_input:
            return {}
        structured_relation = _resume_turn_relation(state)
        if structured_relation is None:
            structured_relation = context.turn_input.metadata.get("turn_relation")
        if structured_relation == "START_NEW_FLOW":
            decision = session_state.AgentTurnRelationDecision(
                relation="START_NEW_FLOW",
                confidence=1.0,
                reason="用户通过结构化草稿选择控件选择作为新流程处理。",
            )
            runtime.context.side_effects.turn_relation_decision = decision
            return {
                "turn_relation_decision": _decision_projection(decision),
                "events": _events([{
                    "event": "turn_relation_classified",
                    "relation": decision.relation,
                    "confidence": decision.confidence,
                    "target_task_id": decision.target_task_id,
                    "detected_customer_name": decision.detected_customer_name,
                    "detected_intent": decision.detected_intent,
                    "reason": decision.reason,
                    "source": "interaction_metadata",
                }]),
            }
        selected_task_id = _resume_selected_task_id(state)
        if selected_task_id is None:
            selected_task_id = context.turn_input.metadata.get("selected_task_id")
        if selected_task_id is not None:
            try:
                selected_task_id = int(selected_task_id)
            except (TypeError, ValueError):
                selected_task_id = None
        if selected_task_id is not None:
            decision = session_state.AgentTurnRelationDecision(
                relation="RESUME_SUSPENDED_DRAFT",
                confidence=1.0,
                target_task_id=selected_task_id,
                reason="用户通过结构化草稿选择控件选择了要恢复的草稿。",
            )
            runtime.context.side_effects.turn_relation_decision = decision
            return {
                "turn_relation_decision": _decision_projection(decision),
                "events": _events([{
                    "event": "turn_relation_classified",
                    "relation": decision.relation,
                    "confidence": decision.confidence,
                    "target_task_id": decision.target_task_id,
                    "detected_customer_name": decision.detected_customer_name,
                    "detected_intent": decision.detected_intent,
                    "reason": decision.reason,
                    "source": "interaction_metadata",
                }]),
            }

        local_decision = _turn_relation_decision_from_text(
            context.content,
            state.get("suspended_candidates") or [],
        )
        if local_decision is not None:
            runtime.context.side_effects.turn_relation_decision = local_decision
            return {
                "turn_relation_decision": _decision_projection(local_decision),
                "events": _events([{
                    "event": "turn_relation_classified",
                    "relation": local_decision.relation,
                    "confidence": local_decision.confidence,
                    "target_task_id": local_decision.target_task_id,
                    "detected_customer_name": local_decision.detected_customer_name,
                    "detected_intent": local_decision.detected_intent,
                    "reason": local_decision.reason,
                    "source": "local_text_match",
                }]),
            }

        decision = await session_state._assess_turn_relation(
            context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            session=context.session,
            task=context.task,
            user_message=context.content,
        )
        context.side_effects.turn_relation_decision = decision
        return {
            "turn_relation_decision": _decision_projection(decision),
            "events": _events([{
                "event": "turn_relation_classified",
                "relation": decision.relation,
                "confidence": decision.confidence,
                "target_task_id": decision.target_task_id,
                "detected_customer_name": decision.detected_customer_name,
                "detected_intent": decision.detected_intent,
                "reason": decision.reason,
            }]),
        }

    def _apply_turn_relation(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        context = runtime.context
        decision = state.get("turn_relation_decision")
        if not decision:
            return {}

        relation = _decision_text(decision, "relation")
        confidence = _decision_confidence(decision)
        target_task_id = _decision_int(decision, "target_task_id")
        reason = _decision_text(decision, "reason")

        if relation == "ASK_USER":
            return self._turn_relation_clarification(state, decision)

        if relation not in {"RESUME_SUSPENDED_DRAFT", "PATCH_ACTIVE_DRAFT", "CONTINUE_ACTIVE_TASK"}:
            return {}

        if not target_task_id:
            return self._turn_relation_clarification(state, decision)
        if confidence < self.state_change_confidence_threshold:
            return self._turn_relation_clarification(state, decision)

        candidate_ids = {
            int(candidate["id"])
            for candidate in state.get("suspended_candidates") or []
            if isinstance(candidate, dict) and candidate.get("id") is not None
        }
        if context.task and getattr(context.task, "id", None) is not None:
            candidate_ids.add(int(context.task.id))
        if int(target_task_id) not in candidate_ids:
            return self._turn_relation_clarification(state, decision)

        task = agent_task_crud.get_by_id(
            context.db,
            target_task_id,
            team_id=context.team_id,
            user_id=context.user_id,
        )
        if not task or task.status != AgentTaskStatus.SUSPENDED:
            return {}

        task = session_state._resume_suspended_task(
            context.db,
            context.session,
            task,
        )
        context.task = task
        context.side_effects.task = task
        context.side_effects.resumed_task = task
        return {
            "has_active_task": True,
            "task_projection": _task_projection(task),
            "resumed_task_id": int(task.id),
            "events": _events([{
                "event": "suspended_task_resumed",
                "task_id": task.id,
                "relation": relation,
                "reason": reason,
            }]),
        }

    def _turn_relation_clarification(self, state: PendingTaskGraphState, decision: JSONDict) -> PendingTaskGraphState:
        assistant_content = self._safe_turn_relation_question(_decision_text(decision, "question"), state)
        waiting_event = _turn_relation_waiting_event(
            content=assistant_content,
            decision=decision,
            candidates=state.get("suspended_candidates") or [],
        )
        interaction_event = interactions._with_interaction(waiting_event)
        current_interrupt = interrupt_from_waiting_event(
            waiting_event,
            interaction=interaction_event.get("interaction") if isinstance(interaction_event.get("interaction"), dict) else None,
        )
        return {
            "handled": True,
            "assistant_content": assistant_content,
            "pending_interrupt_requested": True,
            "current_interrupt": current_interrupt,
            "events": _events([
                interaction_event,
                {"event": "final", "content": assistant_content},
            ]),
        }

    def _safe_turn_relation_question(self, question: str | None, state: PendingTaskGraphState) -> str:
        if question and question.strip() and "_" not in question:
            return question
        return self._default_turn_relation_question(state)

    def _default_turn_relation_question(self, state: PendingTaskGraphState) -> str:
        candidates = state.get("suspended_candidates") or []
        summaries = [
            self._turn_relation_candidate_summary(candidate, index)
            for index, candidate in enumerate(candidates[:2], start=1)
            if isinstance(candidate, dict)
        ]
        summaries = [
            summary
            for summary in summaries
            if summary
        ]
        if summaries:
            return agent_copy.turn_relation_clarification(summaries)
        return agent_copy.turn_relation_clarification()

    def _turn_relation_candidate_summary(self, candidate: dict[object, object], index: int) -> str:
        return task_display.readable_task_summary_from_candidate(candidate, index=index)

    def _route_after_apply_turn_relation(self, state: PendingTaskGraphState) -> str:
        if state.get("pending_interrupt_requested"):
            return "interrupt"
        if state.get("handled"):
            return "end"
        if state.get("resumed_task_id"):
            return "interaction"
        if state.get("has_active_task"):
            return "preflight"
        return "end"

    def _wait_turn_relation_clarification(self, state: PendingTaskGraphState) -> PendingTaskGraphState:
        current_interrupt = state.get("current_interrupt")
        if not current_interrupt:
            return {"pending_interrupt_requested": False}
        resume_payload = interrupt(current_interrupt)
        resume_payload_json = coerce_json_dict(resume_payload)
        return {
            "handled": False,
            "pending_interrupt_requested": False,
            "resume_payload": resume_payload_json,
            "events": _events([{
                "event": "pending_task_turn_relation_interrupt_resumed",
                "resume_action": resume_payload_json.get("action"),
            }]),
        }

    def _route_after_wait_turn_relation_clarification(self, state: PendingTaskGraphState) -> str:
        if _resume_action(coerce_json_dict(state.get("resume_payload"))) == "cancel":
            return "end"
        return "classify"

    async def _preflight(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        context = runtime.context
        if not context.turn_input:
            return {}
        result = await self.preflight_graph_service.run({
            "db": context.db,
            "session": context.session,
            "task": context.task,
            "turn_input": context.turn_input,
            "team_id": context.team_id,
            "session_id": context.session_id,
            "events": [],
        })
        context.task = result.task
        context.side_effects.task = result.task
        context.side_effects.suspended_task = result.suspended_task
        context.side_effects.preflight_result = result
        context.side_effects.confirmation_decision = result.confirmation_decision
        return {
            "has_active_task": bool(result.task),
            "task_projection": _task_projection(result.task),
            "handled": result.handled,
            "assistant_content": result.assistant_content,
            "switch_notice": result.switch_notice,
            "suspended_task_id": _optional_object_id(result.suspended_task),
            "suspend_reason": result.suspend_reason,
            "clear_pending_task_id": result.clear_pending_task_id,
            "confirmation_decision": _decision_projection(result.confirmation_decision),
            "preflight_result": _preflight_result_projection(result),
            "events": _events(result.events),
        }

    def _route_after_preflight(self, state: PendingTaskGraphState) -> str:
        if state.get("handled"):
            return "end"
        confirmation_decision = state.get("confirmation_decision")
        if confirmation_decision and _decision_text(confirmation_decision, "intent") == "confirm":
            return "end"
        if not state.get("has_active_task"):
            return "end"
        return "interaction"

    async def _plan_interaction(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        context = runtime.context
        task = context.task
        if not task:
            return {}
        result = await self.interaction_graph_service.run({
            "db": context.db,
            "task": task,
            "content": context.content,
            "team_id": context.team_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "authorization": context.authorization or "",
            "events": [],
        })
        context.side_effects.interaction_result = result
        update: PendingTaskGraphState = {
            "interaction_result": _interaction_result_projection(result),
            "events": _events(result.events),
        }
        if result.handled:
            update.update({
                "handled": True,
                "assistant_content": result.assistant_content,
                "remember_pending_task": result.remember_pending_task,
                "clear_pending_task_id": result.clear_pending_task_id,
            })
            if result.selected_customer:
                update["selected_customer"] = result.selected_customer
            current_interrupt = _interrupt_from_pending_result(
                result,
                task=context.task,
                events=_events(result.events),
                db=context.db,
                team_id=context.team_id,
            )
            if current_interrupt and self._checkpoint_enabled:
                current_interrupt["runtime_events"] = [
                    *_events(state.get("events") or []),
                    *_events(result.events),
                ]
                update["current_interrupt"] = current_interrupt
                update["pending_interrupt_requested"] = True
        return update

    def _route_after_plan_interaction(self, state: PendingTaskGraphState) -> str:
        if state.get("pending_interrupt_requested") and state.get("current_interrupt"):
            return "interrupt"
        return "end"

    def _wait_interaction_interrupt(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        current_interrupt = state.get("current_interrupt")
        if not current_interrupt:
            return {"pending_interrupt_requested": False}
        resume_payload = interrupt(current_interrupt)
        resume_payload_json = coerce_json_dict(resume_payload)
        update = self._apply_resume_payload_update(
            state={
                **state,
                "resume_payload": resume_payload_json,
            },
            runtime=runtime,
            current_interrupt=current_interrupt,
            emit_resume_event=True,
        )
        return update

    def _apply_resume_payload_update(
        self,
        *,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
        current_interrupt: JSONDict | None,
        emit_resume_event: bool,
    ) -> PendingTaskGraphState:
        resume_payload_json = coerce_json_dict(state.get("resume_payload"))
        update: PendingTaskGraphState = {
            "pending_interrupt_requested": False,
            "current_interrupt": None,
            "resume_payload": resume_payload_json,
        }
        if emit_resume_event:
            update["events"] = _events([{
                "event": "pending_task_interaction_interrupt_resumed",
                "resume_action": resume_payload_json.get("action"),
            }])
        action = _resume_action(resume_payload_json)
        reason = _resume_reason(resume_payload_json, current_interrupt)
        if action == "cancel":
            cancel_update = _cancel_pending_task_update(runtime.context.task)
            if runtime.context.task:
                runtime.context.side_effects.suspended_task = runtime.context.task
            runtime.context.side_effects.task = None
            runtime.context.task = None
            update.update(cancel_update)
            update["resume_route"] = "end"
            return update
        if reason == "pending_flow_switch_confirmation":
            if action == "approve":
                switch_update = _switch_pending_task_update(runtime.context.task)
                runtime.context.side_effects.suspended_task = runtime.context.task
                runtime.context.side_effects.task = None
                runtime.context.task = None
                update.update(switch_update)
                update["resume_route"] = "end"
                return update
            if action in {"reject", "edit"}:
                update["handled"] = False
                update["resume_route"] = "interaction"
                return update
        if reason == "write_confirmation":
            if action == "approve":
                decision = AgentConfirmationIntentDecision(
                    intent="confirm",
                    confidence=1.0,
                    reason="用户通过 LangGraph interrupt resume 批准执行。",
                )
                runtime.context.side_effects.confirmation_decision = decision
                update["handled"] = False
                update["resume_route"] = "end"
                update["confirmation_decision"] = _decision_projection(decision)
                return update
            if action in {"reject", "cancel"}:
                cancel_update = _cancel_pending_task_update(runtime.context.task)
                if runtime.context.task:
                    runtime.context.side_effects.suspended_task = runtime.context.task
                runtime.context.side_effects.task = None
                runtime.context.task = None
                decision = AgentConfirmationIntentDecision(
                    intent="reject",
                    confidence=1.0,
                    reason="用户通过 LangGraph interrupt resume 拒绝执行。",
                )
                runtime.context.side_effects.confirmation_decision = decision
                update.update(cancel_update)
                update["confirmation_decision"] = _decision_projection(decision)
                update["resume_route"] = "end"
                return update
            if action == "edit":
                update["handled"] = False
                update["resume_route"] = "interaction"
                return update
        if reason == "missing_required_fields" and action in {"submit_fields", "submit", "resume"}:
            update["handled"] = False
            update["resume_route"] = "field_resume" if current_interrupt else "preflight"
            return update
        if reason == "business_object_disambiguation" and action in {"select", "submit", "resume"}:
            update["handled"] = False
            update["resume_route"] = "choice_resume"
            return update
        if reason == "insufficient_follow_up_quality" and action in {"submit_text", "submit", "resume"}:
            update["handled"] = False
            update["resume_route"] = "text_resume" if current_interrupt else "preflight"
            return update
        if action in {"submit", "submit_fields", "submit_text", "resume", "edit"}:
            update["handled"] = False
            update["resume_route"] = "interaction"
        else:
            update["resume_route"] = "end"
        return update

    def _route_after_wait_interaction_interrupt(self, state: PendingTaskGraphState) -> str:
        resume_route = state.get("resume_route")
        if (
            resume_route in {"field_resume", "choice_resume", "text_resume", "interaction"}
            and state.get("has_active_task")
        ):
            return resume_route
        return "end"


PENDING_TASK_CHECKPOINT_NS = "crm_agent_pending_task"


def build_pending_task_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
) -> str:
    task_key = str(task_id) if task_id is not None else "session"
    return f"crm_agent_pending:{team_id}:{user_id}:{session_id}:{task_key}"


def build_pending_task_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_pending_task_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                task_id=task_id,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "runtime": "crm_agent_pending_task",
            "runtime_namespace": PENDING_TASK_CHECKPOINT_NS,
        },
    }


pending_task_graph_service = PendingTaskGraphService(checkpointer=agent_checkpoint_saver)


def _checkpoint_state_from_input(input_state: PendingTaskGraphInput) -> PendingTaskGraphState:
    task = input_state.get("task")
    state: PendingTaskGraphState = {
        "has_active_task": bool(task),
        "task_projection": _task_projection(task),
        "content": str(input_state.get("content") or ""),
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "events": [internal_graph_start_event("pending_task_graph_invocation_started")],
    }
    state["events"].extend(_events(input_state.get("events") or []))
    suspended_candidates = _suspended_candidates(input_state.get("suspended_candidates"))
    if suspended_candidates:
        state["suspended_candidates"] = suspended_candidates
    resume_payload = coerce_json_dict(input_state.get("resume_payload"))
    if resume_payload:
        state["resume_payload"] = resume_payload
    return state


async def _has_pending_graph_interrupt(graph: object, config: RunnableConfig) -> bool:
    get_state = getattr(graph, "aget_state", None)
    if not callable(get_state):
        return False
    snapshot = await get_state(config)
    return bool(getattr(snapshot, "interrupts", ()))


async def _graph_input_from_turn(
    graph: object,
    input_state: PendingTaskGraphInput,
    checkpoint_state: PendingTaskGraphState,
    config: RunnableConfig,
) -> PendingTaskGraphState | Command[JSONDict]:
    resume_payload = coerce_json_dict(input_state.get("resume_payload"))
    if resume_payload and await _has_pending_graph_interrupt(graph, config):
        return Command(resume=resume_payload)
    return checkpoint_state


def _runtime_context_from_input(
    input_state: PendingTaskGraphInput,
    side_effects: PendingTaskGraphSideEffects,
) -> PendingTaskRuntimeContext:
    return PendingTaskRuntimeContext(
        db=input_state.get("db"),
        session=input_state.get("session"),
        task=input_state.get("task"),
        turn_input=input_state.get("turn_input"),
        content=str(input_state.get("content") or ""),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=input_state.get("authorization"),
        side_effects=side_effects,
    )


def _merge_side_effects(state: PendingTaskGraphState) -> PendingTaskGraphResult:
    return dict(state)


def _with_visible_events(result: PendingTaskGraphResult) -> PendingTaskGraphResult:
    projected: PendingTaskGraphResult = dict(result)
    projected["events"] = visible_graph_events(projected.get("events"))
    return projected


def _merge_stream_update(state: PendingTaskGraphState, update: JSONDict) -> None:
    for key, value in update.items():
        if key == "events":
            state["events"] = [
                *_events(state.get("events")),
                *_events(value),
            ]
        else:
            state[key] = coerce_json_value(value)


def _pending_turn_result_update(
    result: PendingTaskTurnResult,
    *,
    runtime: Runtime[PendingTaskRuntimeContext],
    task: object,
) -> PendingTaskGraphState:
    runtime.context.side_effects.interaction_result = result
    update: PendingTaskGraphState = {
        "interaction_result": _interaction_result_projection(result),
        "events": _events(result.events),
        "handled": result.handled,
        "assistant_content": result.assistant_content,
        "remember_pending_task": result.remember_pending_task,
        "clear_pending_task_id": result.clear_pending_task_id,
        "has_active_task": bool(task),
        "task_projection": _task_projection(task),
    }
    if result.selected_customer:
        update["selected_customer"] = result.selected_customer
    current_interrupt = _interrupt_from_pending_result(
        result,
        task=task,
        events=_events(result.events),
        db=runtime.context.db,
        team_id=runtime.context.team_id,
    )
    if current_interrupt:
        current_interrupt["runtime_events"] = _events(result.events)
        update["current_interrupt"] = current_interrupt
        update["pending_interrupt_requested"] = True
    return update


def _events(events: object) -> list[JSONDict]:
    if not isinstance(events, list):
        return []
    return [coerce_json_dict(event) for event in events if isinstance(event, dict)]


def _suspended_candidates(candidates: object) -> list[JSONDict]:
    if not isinstance(candidates, list):
        return []
    return [coerce_json_dict(candidate) for candidate in candidates if isinstance(candidate, dict)][:5]


def _interrupt_from_pending_result(
    result: PendingTaskTurnResult,
    *,
    task: object | None,
    events: list[JSONDict],
    db: object | None,
    team_id: int,
) -> AgentInterruptPayload | None:
    current_interrupt = interrupt_from_runtime_events(events, db=db, team_id=team_id)
    if current_interrupt or not result.remember_pending_task:
        return current_interrupt
    if not task or getattr(task, "status", None) != AgentTaskStatus.WAITING_USER:
        return None
    if not _can_project_waiting_task_interrupt(task):
        return None
    interaction = interactions._pending_task_interaction(
        task,
        result.assistant_content or agent_copy.confirm_before_execute(),
        db=db,
        team_id=team_id,
    )
    return interrupt_from_waiting_task(task, interaction=interaction)


def _can_project_waiting_task_interrupt(task: object) -> bool:
    task_id = getattr(task, "id", None)
    task_key = getattr(task, "task_key", None)
    return task_id is not None and isinstance(task_key, str) and bool(task_key)


def _turn_relation_waiting_event(
    *,
    content: str,
    decision: JSONDict,
    candidates: list[JSONDict],
) -> JSONDict:
    return {
        "event": "turn_relation_clarification_required",
        "content": content,
        "decision": decision,
        "candidates": candidates,
    }


def _resume_selected_task_id(state: PendingTaskGraphState) -> int | str | None:
    resume_payload = coerce_json_dict(state.get("resume_payload"))
    metadata = coerce_json_dict(resume_payload.get("metadata"))
    selected_task_id = metadata.get("selected_task_id")
    if isinstance(selected_task_id, (int, str)):
        return selected_task_id
    task_projection_id = resume_payload.get("task_projection_id")
    if isinstance(task_projection_id, (int, str)):
        return task_projection_id
    return None


def _resume_turn_relation(state: PendingTaskGraphState) -> str | None:
    resume_payload = coerce_json_dict(state.get("resume_payload"))
    metadata = coerce_json_dict(resume_payload.get("metadata"))
    relation = metadata.get("turn_relation")
    return relation if isinstance(relation, str) else None


def _turn_relation_decision_from_text(
    content: str,
    candidates: list[JSONDict],
) -> session_state.AgentTurnRelationDecision | None:
    if _is_start_new_flow_text(content):
        return session_state.AgentTurnRelationDecision(
            relation="START_NEW_FLOW",
            confidence=1.0,
            reason="用户明确选择作为新流程处理。",
        )
    if not _is_continue_suspended_text(content):
        return None
    matched_task_ids = [
        task_id
        for index, candidate in enumerate(candidates[:2], start=1)
        for task_id in [_candidate_id_if_text_matches(content, candidate, index)]
        if task_id is not None
    ]
    if len(matched_task_ids) == 1:
        return session_state.AgentTurnRelationDecision(
            relation="RESUME_SUSPENDED_DRAFT",
            confidence=1.0,
            target_task_id=matched_task_ids[0],
            reason="用户输入匹配到一个挂起草稿的可见业务名称。",
        )
    if len(candidates) == 1:
        candidate_id = _candidate_id(candidates[0])
        if candidate_id is not None:
            return session_state.AgentTurnRelationDecision(
                relation="RESUME_SUSPENDED_DRAFT",
                confidence=1.0,
                target_task_id=candidate_id,
                reason="用户明确表示继续，且当前只有一个挂起草稿。",
            )
    return session_state.AgentTurnRelationDecision(
        relation="ASK_USER",
        confidence=1.0,
        reason="用户表示继续挂起草稿，但无法唯一定位是哪一个。",
    )


def _candidate_id_if_text_matches(content: str, candidate: JSONDict, index: int) -> int | None:
    summary = task_display.readable_task_summary_from_candidate(candidate, index=index)
    if not task_display.display_text_matches(content, summary):
        return None
    return _candidate_id(candidate)


def _candidate_id(candidate: JSONDict) -> int | None:
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, (int, str)):
        return None
    try:
        return int(candidate_id)
    except (TypeError, ValueError):
        return None


def _is_start_new_flow_text(content: str) -> bool:
    normalized = _normalized_turn_relation_text(content)
    return any(marker in normalized for marker in ("作为新流程处理", "新流程", "重新开始", "不接上", "不要接上"))


def _is_continue_suspended_text(content: str) -> bool:
    normalized = _normalized_turn_relation_text(content)
    return normalized.startswith("继续") or normalized.startswith("接着") or normalized.startswith("恢复")


def _normalized_turn_relation_text(content: str) -> str:
    return "".join(char.lower() for char in content if char.isalnum())


def _resume_action(resume_payload: JSONDict) -> str | None:
    action = resume_payload.get("action")
    return action if isinstance(action, str) else None


def _resume_reason(resume_payload: JSONDict, current_interrupt: JSONDict | None) -> str | None:
    if current_interrupt:
        reason = current_interrupt.get("reason")
        if isinstance(reason, str):
            return reason
    reason = resume_payload.get("interrupt_reason")
    return reason if isinstance(reason, str) else None


def _switch_pending_task_update(task: object) -> PendingTaskGraphState:
    switch_notice = agent_copy.pending_switch_notice()
    task_id = _optional_object_id(task)
    update: PendingTaskGraphState = {
        "handled": True,
        "has_active_task": False,
        "task_projection": {},
        "assistant_content": switch_notice,
        "switch_notice": switch_notice,
        "suspend_reason": "用户确认切换到新流程。",
        "events": _events([{
            "event": "pending_task_interrupted",
            "content": switch_notice,
        }]),
    }
    if task_id is not None:
        update["suspended_task_id"] = task_id
        update["events"] = _events([{
            "event": "pending_task_interrupted",
            "content": switch_notice,
            "suspended_task_id": task_id,
        }, {"event": "final", "content": switch_notice}])
    return update


def _cancel_pending_task_update(task: object) -> PendingTaskGraphState:
    assistant_content = agent_copy.task_put_aside()
    task_id = _optional_object_id(task)
    update: PendingTaskGraphState = {
        "handled": True,
        "assistant_content": assistant_content,
        "has_active_task": False,
        "task_projection": {},
        "suspend_reason": "用户选择先不处理。",
        "events": _events([
            {
                "event": "task_cancelled",
                "content": assistant_content,
            },
            {"event": "final", "content": assistant_content},
        ]),
    }
    if task_id is not None:
        update["clear_pending_task_id"] = task_id
        update["suspended_task_id"] = task_id
        update["events"] = _events([
            {
                "event": "task_cancelled",
                "task_id": task_id,
                "content": assistant_content,
            },
            {"event": "final", "content": assistant_content},
        ])
    return update


def _task_projection(task: object) -> JSONDict:
    if not task:
        return {}
    projection: JSONDict = {}
    for key in ("id", "task_key", "status", "intent", "target_type", "target_id"):
        value = getattr(task, key, None)
        if value is not None:
            projection[key] = coerce_json_value(value)
    return projection


def _optional_object_id(value: object) -> int | None:
    raw_id = getattr(value, "id", None)
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _preflight_result_projection(result: object) -> JSONDict:
    return {
        "handled": bool(getattr(result, "handled", False)),
        "has_task": bool(getattr(result, "task", None)),
        "has_suspended_task": bool(getattr(result, "suspended_task", None)),
        "event_count": len(getattr(result, "events", []) or []),
    }


def _interaction_result_projection(result: object) -> JSONDict:
    return {
        "handled": bool(getattr(result, "handled", False)),
        "remember_pending_task": bool(getattr(result, "remember_pending_task", False)),
        "has_selected_customer": bool(getattr(result, "selected_customer", None)),
        "event_count": len(getattr(result, "events", []) or []),
    }


def _decision_projection(decision: object) -> JSONDict:
    if decision is None:
        return {}
    model_dump = getattr(decision, "model_dump", None)
    if callable(model_dump):
        return coerce_json_dict(model_dump())
    if isinstance(decision, dict):
        return coerce_json_dict(decision)
    return {}


def _decision_text(decision: JSONDict, key: str) -> str | None:
    value = decision.get(key)
    if isinstance(value, str):
        return value
    return None


def _decision_int(decision: JSONDict, key: str) -> int | None:
    value = decision.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _decision_confidence(decision: JSONDict) -> float:
    value = decision.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


async def _publish_progress_event(
    context: PendingTaskRuntimeContext,
    event: JSONDict,
) -> None:
    sink = context.side_effects.event_sink
    if sink:
        await sink(coerce_json_dict(event))
