"""LangGraph orchestration for turns with a waiting task."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from sqlalchemy.exc import SQLAlchemyError

from app.models.agent import AgentTaskStatus
from app.schemas.agent import AgentTaskUpdate
from app.services.agent import (
    action_workflow,
    agent_copy,
    execution_trace,
    interactions,
    session_state,
    task_display,
    workflow_action_ledger,
)
from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.hitl_runtime import interrupt_from_runtime_events
from app.services.agent.interrupts import (
    AgentInterruptPayload,
    interrupt_from_waiting_event,
    interrupt_from_waiting_task,
    interrupt_payload_from_json,
)
from app.services.agent.pending_application_step_contracts import (
    PENDING_APPLICATION_STEP_SCHEMA,
    build_pending_application_step_request,
)
from app.services.agent.pending_checkpoint import PendingTaskCheckpointStore
from app.services.agent.pending_continuation import (
    PENDING_TASK_RUNTIME,
    PendingTaskContinuationRef,
    bind_pending_task_namespace,
    new_pending_task_continuation,
    pending_task_checkpoint_config,
    pending_task_continuation_from_json,
    pending_task_thread_id,
)
from app.services.agent.pending_outcome import (
    PendingTaskAbortVerificationRequest,
    PendingTaskOutcomeRecovery,
    pending_task_outcome_assembler,
)
from app.services.agent.schemas import AgentConfirmationIntentDecision
from app.services.agent.state import (
    AgentTurnInput,
    PendingTaskEffectIntent,
    PendingTaskGraphInput,
    PendingTaskGraphResult,
    PendingTaskGraphSideEffects,
    PendingTaskGraphState,
    PendingTaskRuntimeContext,
    PendingTaskTurnResult,
    internal_graph_start_event,
)
from app.services.agent.task_projection import (
    agent_task_snapshot,
    materialized_agent_task_snapshot,
    runtime_agent_task_view,
    source_agent_task,
    task_projection_intent,
)
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value
from app.services.agent.workflow_action_cancellation_contracts import (
    expected_ledger_cancellation_snapshot,
    expected_task_cancellation_snapshot,
)


class PendingTaskGraphService:
    """Runs pending-task routing as a small business state machine."""

    state_change_confidence_threshold = 0.75

    def __init__(
        self,
        *,
        preflight_graph_service: object | None = None,
        interaction_graph_service: object | None = None,
        checkpointer: object | None = None,
        application_step_protocol: bool | None = None,
    ) -> None:
        self.application_step_protocol = (
            application_step_protocol
            if application_step_protocol is not None
            else preflight_graph_service is None and interaction_graph_service is None
        )
        if not self.application_step_protocol and (
            preflight_graph_service is None or interaction_graph_service is None
        ):
            raise ValueError("legacy pending graph mode requires explicit application adapters")
        self.preflight_graph_service = preflight_graph_service
        self.interaction_graph_service = interaction_graph_service
        self._checkpoint_store = PendingTaskCheckpointStore(checkpointer)
        self._checkpoint_enabled = self._checkpoint_store.enabled
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(PendingTaskGraphState, context_schema=PendingTaskRuntimeContext)
        graph.add_node("load_suspended_candidates", self._load_suspended_candidates)
        graph.add_node("classify_turn_relation", self._classify_turn_relation)
        graph.add_node("apply_turn_relation", self._apply_turn_relation)
        graph.add_node("project_task_transition", self._project_task_transition)
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
                "task_transition": "project_task_transition",
                "preflight": "preflight",
                "interaction": "plan_interaction",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "project_task_transition",
            self._route_after_task_transition,
            {
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
        """Run one pending-task invocation through the authoritative outcome seam."""

        prepared = self._prepare_invocation(input_state, side_effects=side_effects)
        try:
            observed_state = await self._graph.ainvoke(
                prepared.graph_input,
                prepared.config,
                context=prepared.context,
            )
            return await self._authoritative_outcome(
                continuation=prepared.continuation,
                observed_state=observed_state,
                interrupts=coerce_json_dict(observed_state).get("__interrupt__"),
            )
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            task_snapshot = _task_snapshot_from_input(input_state)
            fallback_context = _runtime_context_from_input(
                input_state,
                PendingTaskGraphSideEffects(task=task_snapshot or None),
            )
            observed_state = await self._fallback_graph.ainvoke(
                prepared.checkpoint_state,
                prepared.config,
                context=fallback_context,
            )
            outcome = pending_task_outcome_assembler.assemble(observed_state=observed_state)
            return with_checkpoint_unavailable_fallback_event(
                outcome,
                runtime=PENDING_TASK_RUNTIME,
                graph=PENDING_TASK_CHECKPOINT_NS,
            )

    async def run_with_trace(
        self,
        input_state: PendingTaskGraphInput,
        *,
        side_effects: PendingTaskGraphSideEffects | None = None,
    ) -> PendingTaskGraphResult:
        """Run with live progress while keeping the checkpoint as business authority."""

        prepared = self._prepare_invocation(input_state, side_effects=side_effects)
        try:
            observed_state, trace_events, interrupts = await self._run_graph_with_trace(
                self._graph,
                prepared.graph_input,
                prepared.checkpoint_state,
                prepared.context,
                prepared.config,
            )
            return await self._authoritative_outcome(
                continuation=prepared.continuation,
                observed_state=observed_state,
                trace_events=trace_events,
                interrupts=interrupts,
            )
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            task_snapshot = _task_snapshot_from_input(input_state)
            fallback_side_effects = PendingTaskGraphSideEffects(task=task_snapshot or None)
            fallback_context = _runtime_context_from_input(input_state, fallback_side_effects)
            observed_state, trace_events, interrupts = await self._run_graph_with_trace(
                self._fallback_graph,
                prepared.checkpoint_state,
                prepared.checkpoint_state,
                fallback_context,
                prepared.config,
            )
            outcome = pending_task_outcome_assembler.assemble(
                observed_state=observed_state,
                trace_events=trace_events,
                interrupts=interrupts,
            )
            return with_checkpoint_unavailable_fallback_event(
                outcome,
                runtime=PENDING_TASK_RUNTIME,
                graph=PENDING_TASK_CHECKPOINT_NS,
            )

    async def verify_projection_aborted(
        self,
        request: PendingTaskAbortVerificationRequest,
    ) -> PendingTaskOutcomeRecovery:
        """Verify the durable proof written by a root-owned terminal abort."""

        continuation = pending_task_continuation_from_json(
            request.continuation,
            expected_team_id=request.team_id,
            expected_user_id=request.user_id,
            expected_session_id=request.session_id,
        )
        if continuation is None:
            return PendingTaskOutcomeRecovery(failure_reason="invalid_continuation")
        aborted = await self._checkpoint_store.load_result(continuation)
        snapshot = aborted.snapshot
        if snapshot is None:
            return PendingTaskOutcomeRecovery(
                failure_reason=aborted.failure_reason or "projection_abort_checkpoint_missing"
            )
        if not _is_projection_abort_complete(
            snapshot.values,
            snapshot.interrupts,
            expected_interrupt=request.expected_interrupt,
        ):
            return PendingTaskOutcomeRecovery(failure_reason="projection_abort_incomplete")
        return PendingTaskOutcomeRecovery(
            outcome=pending_task_outcome_assembler.assemble(
                checkpoint_values=snapshot.values,
                interrupts=snapshot.interrupts,
            )
        )

    async def load_checkpointed_outcome(
        self,
        checkpoint_ref: PendingTaskContinuationRef,
        *,
        expected_interrupt: AgentInterruptPayload | None = None,
        trace_events: list[JSONDict] | None = None,
    ) -> PendingTaskOutcomeRecovery:
        """Recover one exact suspended child continuation, failing closed."""

        load_result = await self._checkpoint_store.load_result(
            checkpoint_ref,
            expected_interrupt=expected_interrupt,
        )
        snapshot = load_result.snapshot
        if snapshot is None:
            return PendingTaskOutcomeRecovery(failure_reason=load_result.failure_reason)
        return PendingTaskOutcomeRecovery(
            outcome=pending_task_outcome_assembler.assemble(
                checkpoint_values=snapshot.values,
                trace_events=trace_events or [],
                interrupts=snapshot.interrupts,
            )
        )

    def _prepare_invocation(
        self,
        input_state: PendingTaskGraphInput,
        *,
        side_effects: PendingTaskGraphSideEffects | None,
    ) -> _PendingTaskInvocation:
        task_snapshot = _task_snapshot_from_input(input_state)
        checkpoint_state = _checkpoint_state_from_input(input_state)
        graph_side_effects = side_effects or PendingTaskGraphSideEffects(task=task_snapshot or None)
        if graph_side_effects.task is None and task_snapshot:
            graph_side_effects.task = task_snapshot
        continuation = prepare_pending_task_continuation(
            input_state,
            side_effects=graph_side_effects,
        )
        uses_persisted_namespace = bool(continuation.get("checkpoint_ns"))
        continuation = _bind_continuation_namespace_from_runtime(
            continuation,
            side_effects=graph_side_effects,
        )
        context = _runtime_context_from_input(input_state, graph_side_effects)
        config = pending_task_checkpoint_config(
            continuation,
            # A new nested invocation inherits the namespace LangGraph assigned
            # to the current root node. A resumed continuation must instead
            # address the exact namespace persisted in its interrupt payload;
            # inheriting the new root-node namespace would resume an empty
            # checkpoint and silently lose the child outcome.
            include_namespace=uses_persisted_namespace,
        )
        graph_input = _graph_input_from_turn_sync(
            checkpoint_state=checkpoint_state,
            resume_payload=coerce_json_dict(input_state.get("resume_payload")),
        )
        return _PendingTaskInvocation(
            checkpoint_state=checkpoint_state,
            graph_input=graph_input,
            context=context,
            continuation=continuation,
            config=config,
        )

    async def _authoritative_outcome(
        self,
        *,
        continuation: PendingTaskContinuationRef,
        observed_state: object,
        trace_events: list[JSONDict] | None = None,
        interrupts: object | None = None,
    ) -> PendingTaskGraphResult:
        observed = coerce_json_dict(observed_state)
        if not self._checkpoint_enabled:
            return pending_task_outcome_assembler.assemble(
                observed_state=observed,
                trace_events=trace_events or [],
                interrupts=interrupts,
            )
        expected_interrupt = interrupt_from_state(observed)
        load_result = await self._checkpoint_store.load_result(
            continuation,
            expected_interrupt=expected_interrupt,
        )
        snapshot = load_result.snapshot
        if snapshot is None:
            reason = load_result.failure_reason or "checkpoint_not_found"
            raise RuntimeError(f"pending_task_authoritative_outcome_unavailable:{reason}")
        return pending_task_outcome_assembler.assemble(
            observed_state=observed,
            checkpoint_values=snapshot.values,
            trace_events=trace_events or [],
            interrupts=snapshot.interrupts or interrupts,
        )

    async def _run_graph_with_trace(
        self,
        graph: object,
        graph_input: PendingTaskGraphState | Command[JSONDict],
        checkpoint_state: PendingTaskGraphState,
        context: PendingTaskRuntimeContext,
        config: RunnableConfig,
    ) -> tuple[PendingTaskGraphState, list[JSONDict], object | None]:
        astream = getattr(graph, "astream", None)
        if not callable(astream):
            result = await graph.ainvoke(graph_input, config, context=context)
            return coerce_json_dict(result), [], coerce_json_dict(result).get("__interrupt__")

        streamed_state: PendingTaskGraphState = dict(checkpoint_state)
        trace_events: list[JSONDict] = []
        stream_interrupts: object | None = None
        async for chunk in astream(graph_input, config, context=context, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            if "__interrupt__" in chunk:
                stream_interrupts = chunk["__interrupt__"]
            for step_name, update_value in chunk.items():
                if not isinstance(step_name, str) or not isinstance(update_value, dict):
                    continue
                update = coerce_json_dict(update_value)
                started_event = execution_trace.pending_task_step_started(step_name)
                if started_event:
                    trace_events.append(started_event)
                _merge_stream_update(streamed_state, update)
                trace_events.extend(_events(update.get("events")))
                completed_event = execution_trace.pending_task_step_completed(step_name)
                if completed_event:
                    trace_events.append(completed_event)
        return streamed_state, trace_events, stream_interrupts

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
        if _resume_action(coerce_json_dict(state.get("resume_payload"))) in {"cancel", "abort_projection"}:
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
        if self.application_step_protocol:
            application_result = self._execute_application_step_interrupt(
                step_type="interaction",
                state=state,
                runtime=runtime,
            )
            return _interaction_application_step_update(
                application_result,
                runtime=runtime,
                effect_intents=state.get("effect_intents"),
            )
        runtime_task = runtime_agent_task_view(task)
        runtime.context.task = runtime_task
        runtime.context.side_effects.task = source_agent_task(runtime_task)
        result = await self._run_pending_interaction_subgraph(runtime, runtime_task)
        return _pending_turn_result_update(
            result,
            runtime=runtime,
            task=runtime_task,
            effect_intents=state.get("effect_intents"),
        )

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

        if self.application_step_protocol:
            application_result = self._execute_application_step_interrupt(
                step_type="turn_relation_assessment",
                state=state,
                runtime=runtime,
            )
            return _turn_relation_application_step_update(application_result, runtime=runtime)
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

        task_snapshot = next(
            (
                candidate
                for candidate in state.get("suspended_candidates") or []
                if isinstance(candidate, dict)
                and _optional_object_id(candidate) == int(target_task_id)
            ),
            None,
        )
        if not task_snapshot or task_snapshot.get("status") != AgentTaskStatus.SUSPENDED:
            return {}

        runtime_task = runtime_agent_task_view(task_snapshot)
        resumed_state = coerce_json_dict(getattr(runtime_task, "state_json", None))
        resumed_state.pop("suspended_reason", None)
        runtime_task.stage_agent_task_update(AgentTaskUpdate(
            status=AgentTaskStatus.WAITING_USER,
            state_json=resumed_state,
        ))
        materialized_task_snapshot = materialized_agent_task_snapshot(runtime_task)
        context.task = runtime_task
        context.side_effects.task = source_agent_task(runtime_task)
        context.side_effects.resumed_task = None
        return {
            "has_active_task": True,
            "task_snapshot": materialized_task_snapshot,
            "task_projection": _task_projection(materialized_task_snapshot),
            "resumed_task_id": int(runtime_task.id),
            "effect_intents": _with_task_projection_intent(
                state.get("effect_intents"),
                runtime_task,
            ),
            "events": _events([{
                "event": "suspended_task_resumed",
                "task_id": runtime_task.id,
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
            interaction=(
                interaction_event.get("interaction")
                if isinstance(interaction_event.get("interaction"), dict)
                else None
            ),
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
            if self.application_step_protocol and state.get("effect_intents"):
                return "task_transition"
            return "interaction"
        if state.get("has_active_task"):
            return "preflight"
        return "end"

    def _project_task_transition(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        application_result = self._execute_application_step_interrupt(
            step_type="task_transition",
            state=state,
            runtime=runtime,
        )
        return _task_transition_application_step_update(
            application_result,
            runtime=runtime,
        )

    def _route_after_task_transition(self, state: PendingTaskGraphState) -> str:
        if state.get("handled") or not state.get("has_active_task"):
            return "end"
        return "interaction"

    def _wait_turn_relation_clarification(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        current_interrupt = state.get("current_interrupt")
        if not current_interrupt:
            return {"pending_interrupt_requested": False}
        current_interrupt = _with_pending_checkpoint_ref(current_interrupt, runtime.context)
        resume_payload = interrupt(current_interrupt)
        resume_payload_json = coerce_json_dict(resume_payload)
        return {
            "handled": False,
            "pending_interrupt_requested": False,
            "current_interrupt": None,
            "assistant_content": None,
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

    def _execute_application_step_interrupt(
        self,
        *,
        step_type: str,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> JSONDict:
        continuation = pending_task_continuation_from_json(
            runtime.context.side_effects.checkpoint_ref,
            expected_team_id=runtime.context.team_id,
            expected_user_id=runtime.context.user_id,
            expected_session_id=runtime.context.session_id,
        )
        if continuation is None:
            raise ValueError("pending application step requires an authenticated continuation")
        # LangGraph resumes an interrupted node from the beginning. Therefore
        # every value participating in the application-step identity must come
        # from the checkpointed graph state, not from mutable hydrated runtime
        # objects that the application projection may have changed meanwhile.
        task_snapshot = coerce_json_dict(state.get("task_snapshot"))
        turn_input_projection = coerce_json_dict(state.get("turn_input"))
        request = build_pending_application_step_request(
            step_type=step_type,
            continuation=continuation,
            task_snapshot=task_snapshot,
            content=str(state.get("content") or ""),
            turn_input=turn_input_projection,
            interaction_metadata=turn_input_projection.get("metadata"),
            effect_intents=(
                state.get("effect_intents")
                if step_type == "task_transition"
                else []
            ),
        )
        acknowledgement = coerce_json_dict(interrupt(request))
        if acknowledgement.get("schema_version") != PENDING_APPLICATION_STEP_SCHEMA:
            raise ValueError("pending application-step acknowledgement schema mismatch")
        if acknowledgement.get("step_id") != request["step_id"]:
            raise ValueError(
                "pending application-step acknowledgement identity mismatch "
                f"for {step_type}: expected {request['step_id']}, "
                f"received {acknowledgement.get('step_id')}"
            )
        if acknowledgement.get("status") == "FAILED":
            failure_reason = str(
                acknowledgement.get("failure_reason") or "pending application step failed"
            )
            return {
                "step_type": step_type,
                "task_snapshot": coerce_json_dict(request.get("task_snapshot")),
                "application_step_failed": True,
                "failure_reason": failure_reason,
                "retryable": bool(acknowledgement.get("retryable")),
                "result": {
                    "handled": True,
                    "assistant_content": "当前待处理流程执行失败，请重新发起。",
                    "events": [{
                        "event": "pending_application_step_failed",
                        "step_type": step_type,
                        "reason": failure_reason,
                        "retryable": bool(acknowledgement.get("retryable")),
                        "internal": True,
                    }],
                },
            }
        if acknowledgement.get("status") != "COMPLETED":
            raise ValueError("pending application-step acknowledgement status mismatch")
        return coerce_json_dict(acknowledgement.get("result"))

    async def _preflight(
        self,
        state: PendingTaskGraphState,
        runtime: Runtime[PendingTaskRuntimeContext],
    ) -> PendingTaskGraphState:
        context = runtime.context
        if not context.turn_input:
            return {}
        if self.application_step_protocol:
            application_result = self._execute_application_step_interrupt(
                step_type="preflight",
                state=state,
                runtime=runtime,
            )
            return _preflight_application_step_update(application_result, runtime=runtime)
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
        context.side_effects.task = source_agent_task(result.task)
        context.side_effects.suspended_task = source_agent_task(result.suspended_task)
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
            "suspension_kind": getattr(result, "suspension_kind", None),
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
        if self.application_step_protocol:
            application_result = self._execute_application_step_interrupt(
                step_type="interaction",
                state=state,
                runtime=runtime,
            )
            return _interaction_application_step_update(
                application_result,
                runtime=runtime,
                effect_intents=state.get("effect_intents"),
                prior_events=state.get("events"),
            )
        runtime_task = runtime_agent_task_view(task)
        context.task = runtime_task
        context.side_effects.task = source_agent_task(runtime_task)
        result = await self.interaction_graph_service.run({
            "db": context.db,
            "task": runtime_task,
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
            "has_active_task": True,
            "task_projection": _task_projection(runtime_task),
            "effect_intents": _with_task_projection_intent(
                state.get("effect_intents"),
                runtime_task,
            ),
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
                task=runtime_task,
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
        current_interrupt = _with_pending_checkpoint_ref(current_interrupt, runtime.context)
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
            "effect_intents": [],
        }
        if emit_resume_event:
            update["events"] = _events([{
                "event": "pending_task_interaction_interrupt_resumed",
                "resume_action": resume_payload_json.get("action"),
            }])
        action = _resume_action(resume_payload_json)
        reason = _resume_reason(resume_payload_json, current_interrupt)
        if action == "abort_projection":
            return {
                **update,
                "handled": False,
                "has_active_task": False,
                "task_projection": {},
                "assistant_content": None,
                "confirmation_decision": {},
                "projection_aborted": True,
                "projection_abort_interrupt": coerce_json_dict(current_interrupt),
                "resume_route": "end",
                "events": [],
            }
        if action == "skip_current_action" or (
            action in {"reject", "cancel"}
            and action_workflow.is_optional_skip_interrupt(current_interrupt)
        ):
            skip_update = _skip_pending_action_update(
                runtime.context.task,
                current_interrupt=current_interrupt,
                resume_payload=resume_payload_json,
            )
            if runtime.context.task:
                runtime.context.side_effects.suspended_task = source_agent_task(runtime.context.task)
            runtime.context.side_effects.task = None
            runtime.context.task = None
            update.update(skip_update)
            update["resume_route"] = "end"
            return update
        if action == "cancel":
            cancel_update = _cancel_pending_task_update(runtime.context.task, resume_payload=resume_payload_json)
            workflow_intent = _cancel_workflow_action_intent(
                runtime.context,
                current_interrupt=current_interrupt,
                resume_payload=resume_payload_json,
                reason="用户取消当前等待动作。",
            )
            if workflow_intent:
                update["effect_intents"] = [workflow_intent]
            if runtime.context.task:
                runtime.context.side_effects.suspended_task = source_agent_task(runtime.context.task)
            runtime.context.side_effects.task = None
            runtime.context.task = None
            update.update(cancel_update)
            update["resume_route"] = "end"
            return update
        if reason == "pending_flow_switch_confirmation":
            if action == "approve":
                switch_update = _switch_pending_task_update(runtime.context.task)
                runtime.context.side_effects.suspended_task = source_agent_task(runtime.context.task)
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
                cancel_update = _cancel_pending_task_update(runtime.context.task, resume_payload=resume_payload_json)
                workflow_intent = _cancel_workflow_action_intent(
                    runtime.context,
                    current_interrupt=current_interrupt,
                    resume_payload=resume_payload_json,
                    reason="用户通过 LangGraph interrupt resume 拒绝执行。",
                )
                if workflow_intent:
                    update["effect_intents"] = [workflow_intent]
                if runtime.context.task:
                    runtime.context.side_effects.suspended_task = source_agent_task(runtime.context.task)
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


PENDING_TASK_CHECKPOINT_NS = PENDING_TASK_RUNTIME


@dataclass(frozen=True)
class _PendingTaskInvocation:
    checkpoint_state: PendingTaskGraphState
    graph_input: PendingTaskGraphState | Command[JSONDict]
    context: PendingTaskRuntimeContext
    continuation: PendingTaskContinuationRef
    config: RunnableConfig


def build_pending_task_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
    continuation_id: str | None = None,
) -> str:
    """Return the canonical legacy or isolated continuation thread."""

    return pending_task_thread_id(
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        continuation_id=continuation_id,
    )


def _bind_continuation_namespace_from_runtime(
    continuation: PendingTaskContinuationRef,
    *,
    side_effects: PendingTaskGraphSideEffects,
) -> PendingTaskContinuationRef:
    """Capture a new child namespace without rewriting a durable locator."""

    try:
        runtime_config = get_config()
    except RuntimeError:
        runtime_config = {}
    configurable = coerce_json_dict(runtime_config.get("configurable"))
    checkpoint_ns = continuation.get("checkpoint_ns", "")
    if not checkpoint_ns:
        runtime_checkpoint_ns = configurable.get("checkpoint_ns")
        if isinstance(runtime_checkpoint_ns, str):
            checkpoint_ns = runtime_checkpoint_ns
    bound = bind_pending_task_namespace(continuation, checkpoint_ns)
    side_effects.checkpoint_ref = bound
    return bound


def _with_pending_checkpoint_ref(
    interrupt_payload: AgentInterruptPayload,
    context: PendingTaskRuntimeContext,
) -> AgentInterruptPayload:
    """Attach the exact authenticated continuation before native suspension."""

    continuation = context.side_effects.checkpoint_ref
    if continuation is None:
        return interrupt_payload
    projected: AgentInterruptPayload = dict(interrupt_payload)
    projected["checkpoint_ref"] = dict(continuation)
    return projected


def prepare_pending_task_continuation(
    input_state: PendingTaskGraphInput,
    *,
    side_effects: PendingTaskGraphSideEffects,
) -> PendingTaskContinuationRef:
    """Resolve a new invocation or an explicit continuation for resume."""

    resume_payload = coerce_json_dict(input_state.get("resume_payload"))
    raw_continuation = input_state.get("continuation_ref") or side_effects.checkpoint_ref
    if raw_continuation is not None:
        continuation = pending_task_continuation_from_json(
            raw_continuation,
            expected_team_id=int(input_state.get("team_id") or 0),
            expected_user_id=int(input_state.get("user_id") or 0),
            expected_session_id=int(input_state.get("session_id") or 0),
        )
        if continuation is None:
            raise ValueError("invalid pending-task continuation")
    elif resume_payload:
        raise ValueError("pending-task resume requires an explicit continuation")
    else:
        continuation = new_pending_task_continuation(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
            task_id=_optional_object_id(
                side_effects.task or _task_snapshot_from_input(input_state)
            ),
        )
    side_effects.checkpoint_ref = continuation
    input_state["continuation_ref"] = continuation
    return continuation


def prepare_pending_task_checkpoint(
    input_state: PendingTaskGraphInput,
    *,
    side_effects: PendingTaskGraphSideEffects,
) -> PendingTaskContinuationRef:
    """Compatibility alias for the explicit continuation contract."""

    return prepare_pending_task_continuation(input_state, side_effects=side_effects)


def build_pending_task_checkpoint_ref(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
    continuation_id: str | None = None,
) -> PendingTaskContinuationRef:
    """Create a continuation whose returned identity must be persisted for resume."""

    return new_pending_task_continuation(
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        continuation_id=continuation_id,
    )


def pending_task_graph_config_from_ref(
    checkpoint_ref: PendingTaskContinuationRef,
) -> RunnableConfig:
    return pending_task_checkpoint_config(checkpoint_ref)


def build_pending_task_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None = None,
    continuation_id: str | None = None,
) -> RunnableConfig:
    return pending_task_checkpoint_config(
        build_pending_task_checkpoint_ref(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            continuation_id=continuation_id,
        )
    )


pending_task_graph_service = PendingTaskGraphService(checkpointer=agent_checkpoint_saver)


def _checkpoint_state_from_input(input_state: PendingTaskGraphInput) -> PendingTaskGraphState:
    task_snapshot = _task_snapshot_from_input(input_state)
    task = runtime_agent_task_view(task_snapshot) if task_snapshot else None
    turn_input = input_state.get("turn_input")
    turn_input_projection = (
        coerce_json_dict(turn_input.model_dump(mode="json"))
        if isinstance(turn_input, AgentTurnInput)
        else coerce_json_dict(turn_input)
    )
    state: PendingTaskGraphState = {
        "has_active_task": bool(task),
        "task_snapshot": task_snapshot,
        "turn_input": turn_input_projection,
        "task_projection": _task_projection(task),
        "content": str(input_state.get("content") or ""),
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "effect_intents": [],
        "events": [internal_graph_start_event("pending_task_graph_invocation_started")],
    }
    state["events"].extend(_events(input_state.get("events") or []))
    suspended_candidates = _suspended_candidates(input_state.get("suspended_candidates"))
    if suspended_candidates:
        state["suspended_candidates"] = suspended_candidates
    projected_resume_payload = coerce_json_dict(input_state.get("projected_resume_payload"))
    if projected_resume_payload:
        state["resume_payload"] = projected_resume_payload
    return state


def _task_snapshot_from_input(input_state: PendingTaskGraphInput) -> JSONDict:
    snapshot = coerce_json_dict(input_state.get("task_snapshot"))
    if snapshot:
        return snapshot
    # Temporary compatibility for direct service callers. The object is
    # serialized before LangGraph state/runtime construction and never crosses
    # the checkpoint seam. Root/Application callers use ``task_snapshot``.
    return agent_task_snapshot(input_state.get("task"))


def _graph_input_from_turn_sync(
    *,
    checkpoint_state: PendingTaskGraphState,
    resume_payload: JSONDict,
) -> PendingTaskGraphState | Command[JSONDict]:
    return Command(resume=resume_payload) if resume_payload else checkpoint_state


def interrupt_from_state(state: object) -> AgentInterruptPayload | None:
    return interrupt_payload_from_json(coerce_json_dict(state).get("current_interrupt"))


def _runtime_context_from_input(
    input_state: PendingTaskGraphInput,
    side_effects: PendingTaskGraphSideEffects,
) -> PendingTaskRuntimeContext:
    return PendingTaskRuntimeContext(
        db=input_state.get("db"),
        session=input_state.get("session"),
        task=(
            runtime_agent_task_view(_task_snapshot_from_input(input_state))
            if _task_snapshot_from_input(input_state)
            else None
        ),
        turn_input=input_state.get("turn_input"),
        content=str(input_state.get("content") or ""),
        team_id=int(input_state.get("team_id") or 0),
        user_id=int(input_state.get("user_id") or 0),
        session_id=int(input_state.get("session_id") or 0),
        authorization=input_state.get("authorization"),
        side_effects=side_effects,
    )


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
    effect_intents: object = None,
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
        "effect_intents": _with_task_projection_intent(effect_intents, task),
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


def _is_projection_abort_complete(
    checkpoint_values: object,
    interrupts: object,
    *,
    expected_interrupt: AgentInterruptPayload | None = None,
) -> bool:
    """Verify the exact durable proof of a released child interrupt."""

    values = coerce_json_dict(checkpoint_values)
    abort_interrupt = coerce_json_dict(values.get("projection_abort_interrupt"))
    return (
        not interrupts
        and values.get("projection_aborted") is True
        and values.get("pending_interrupt_requested") is False
        and values.get("current_interrupt") is None
        and values.get("resume_route") == "end"
        and values.get("effect_intents") == []
        and (
            expected_interrupt is None
            or abort_interrupt == coerce_json_dict(expected_interrupt)
        )
    )


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


def _cancel_pending_task_update(task: object, *, resume_payload: JSONDict | None = None) -> PendingTaskGraphState:
    assistant_content = agent_copy.task_put_aside()
    task_id = _optional_object_id(task)
    update: PendingTaskGraphState = {
        "handled": True,
        "assistant_content": assistant_content,
        "has_active_task": False,
        "task_projection": {},
        "suspend_reason": "用户选择先不处理。",
        "suspension_kind": _suspension_kind_from_resume_payload(resume_payload),
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


def _with_task_projection_intent(
    existing_intents: object,
    task: object,
) -> list[PendingTaskEffectIntent]:
    """Upsert the final task mutation contract while preserving other effects."""

    intents = [
        coerce_json_dict(intent)
        for intent in existing_intents or []
        if isinstance(intent, dict)
    ]
    projection = task_projection_intent(task)
    if projection is None:
        return intents
    task_id = projection.get("task_id")
    retained = [
        intent
        for intent in intents
        if not (
            intent.get("intent_type") in {
                "project_pending_task_state",
                "resume_suspended_task",
            }
            and intent.get("task_id") == task_id
        )
    ]
    retained.append(projection)
    return retained


def _cancel_workflow_action_intent(
    context: PendingTaskRuntimeContext,
    *,
    current_interrupt: JSONDict | None,
    resume_payload: JSONDict | None,
    reason: str,
) -> PendingTaskEffectIntent | None:
    workflow = action_workflow.workflow_from_mapping(
        (current_interrupt or {}).get("workflow")
        if isinstance(current_interrupt, dict)
        else None
    )
    task_id = _optional_object_id(context.task)
    if not workflow or task_id is None:
        return None
    resume_payload_json = coerce_json_dict(resume_payload)
    decision: JSONDict = {
        "decision": _resume_action(resume_payload_json) or "cancel",
        "resume_reason": _resume_reason(resume_payload_json, current_interrupt),
    }
    resume_content = resume_payload_json.get("content")
    if isinstance(resume_content, str) and resume_content.strip():
        decision["content"] = resume_content.strip()
    expected_task = expected_task_cancellation_snapshot(context.task)
    expected_ledger = expected_ledger_cancellation_snapshot(workflow, task_id=task_id)
    if not expected_task or not expected_ledger:
        raise ValueError("pending workflow cancellation cannot capture optimistic snapshots")
    action_id = str(workflow["action_id"])
    return {
        "intent_id": f"cancel_workflow_action:{action_id}:{task_id}",
        "intent_type": "cancel_workflow_action",
        "task_id": task_id,
        "workflow": workflow,
        "expected_task": expected_task,
        "expected_ledger": expected_ledger,
        "reason": reason,
        "source_type": workflow_action_ledger.SOURCE_PENDING_RESUME,
        "decision": decision,
    }


def _skip_pending_action_update(
    task: object,
    *,
    current_interrupt: JSONDict | None,
    resume_payload: JSONDict | None = None,
) -> PendingTaskGraphState:
    task_id = _optional_object_id(task)
    workflow = action_workflow.workflow_from_mapping(
        (current_interrupt or {}).get("workflow")
        if isinstance(current_interrupt, dict)
        else None
    )
    action_id = workflow.get("action_id") if workflow else None
    action_type = workflow.get("action_type") if workflow else None
    action_label = task_display.readable_execution_label(action_type)
    assistant_content = f"已跳过{action_label}建议。" if action_label else "已跳过这项建议。"
    resume_text = (resume_payload or {}).get("content")
    status_reason = (
        resume_text
        if isinstance(resume_text, str) and resume_text.strip()
        else "用户跳过当前可选建议动作。"
    )
    event: JSONDict = {
        "event": "workflow_action_skipped",
        "content": assistant_content,
        "reason": status_reason,
    }
    if isinstance(action_id, str):
        event["action_id"] = action_id
    if isinstance(action_type, str):
        event["action_type"] = action_type
    if task_id is not None:
        event["task_id"] = task_id
    update: PendingTaskGraphState = {
        "handled": True,
        "assistant_content": assistant_content,
        "has_active_task": False,
        "task_projection": {},
        "suspend_reason": status_reason,
        "suspension_kind": "dismissed",
        "events": _events([event, {"event": "final", "content": assistant_content}]),
    }
    if task_id is not None:
        update["clear_pending_task_id"] = task_id
        update["suspended_task_id"] = task_id
    return update


def _suspension_kind_from_resume_payload(resume_payload: JSONDict | None = None) -> str:
    metadata = coerce_json_dict((resume_payload or {}).get("metadata"))
    turn_intent = coerce_json_dict(metadata.get("turn_intent"))
    intent = turn_intent.get("intent")
    if intent in {"DISMISS_CURRENT_SUGGESTION", "CANCEL_CURRENT_TASK", "REJECT_EXECUTION"}:
        return "dismissed"
    if intent == "PAUSE_CURRENT_TASK":
        return "paused"
    return "paused"


def _task_projection(task: object) -> JSONDict:
    snapshot = agent_task_snapshot(task)
    return {
        key: snapshot[key]
        for key in ("id", "task_key", "status", "intent", "target_type", "target_id")
        if key in snapshot
    }


def _optional_object_id(value: object) -> int | None:
    raw_id = value.get("id") if isinstance(value, dict) else getattr(value, "id", None)
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _preflight_application_step_update(
    application_result: JSONDict,
    *,
    runtime: Runtime[PendingTaskRuntimeContext],
) -> PendingTaskGraphState:
    result = coerce_json_dict(application_result.get("result"))
    task_snapshot = coerce_json_dict(application_result.get("task_snapshot"))
    suspended_snapshot = coerce_json_dict(application_result.get("suspended_task_snapshot"))
    confirmation_decision = coerce_json_dict(result.get("confirmation_decision"))
    events = _events(result.get("events"))
    runtime.context.task = runtime_agent_task_view(task_snapshot) if task_snapshot else None
    runtime.context.side_effects.task = task_snapshot or None
    runtime.context.side_effects.suspended_task = suspended_snapshot or None
    runtime.context.side_effects.confirmation_decision = (
        AgentConfirmationIntentDecision.model_validate(confirmation_decision)
        if confirmation_decision
        else None
    )
    update: PendingTaskGraphState = {
        "has_active_task": bool(task_snapshot),
        "task_snapshot": task_snapshot,
        "task_projection": _task_projection(task_snapshot),
        "handled": bool(result.get("handled")),
        "events": events,
        "confirmation_decision": confirmation_decision,
        "preflight_result": {
            "handled": bool(result.get("handled")),
            "has_task": bool(task_snapshot),
            "has_suspended_task": bool(suspended_snapshot),
            "event_count": len(events),
        },
    }
    for key in ("assistant_content", "switch_notice", "suspend_reason", "suspension_kind"):
        value = result.get(key)
        if isinstance(value, str):
            update[key] = value
    clear_pending_task_id = result.get("clear_pending_task_id")
    if isinstance(clear_pending_task_id, int):
        update["clear_pending_task_id"] = clear_pending_task_id
    if suspended_snapshot.get("id") is not None:
        update["suspended_task_id"] = int(suspended_snapshot["id"])
    return update


def _turn_relation_application_step_update(
    application_result: JSONDict,
    *,
    runtime: Runtime[PendingTaskRuntimeContext],
) -> PendingTaskGraphState:
    result = coerce_json_dict(application_result.get("result"))
    decision_projection = coerce_json_dict(result.get("decision"))
    if not decision_projection:
        raise ValueError("turn-relation application step returned no decision")
    decision = session_state.AgentTurnRelationDecision.model_validate(decision_projection)
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
            "source": "application_step",
        }]),
    }


def _task_transition_application_step_update(
    application_result: JSONDict,
    *,
    runtime: Runtime[PendingTaskRuntimeContext],
) -> PendingTaskGraphState:
    result = coerce_json_dict(application_result.get("result"))
    task_snapshot = coerce_json_dict(application_result.get("task_snapshot"))
    if not task_snapshot:
        raise ValueError("task-transition application step returned no task snapshot")
    runtime_task = runtime_agent_task_view(task_snapshot)
    runtime.context.task = runtime_task
    runtime.context.side_effects.task = task_snapshot
    return {
        "has_active_task": True,
        "task_snapshot": task_snapshot,
        "task_projection": _task_projection(task_snapshot),
        "effect_intents": [],
        "events": _events([{
            "event": "pending_task_transition_projected",
            "task_id": task_snapshot.get("id"),
            "consumed_intent_ids": result.get("consumed_intent_ids") or [],
            "internal": True,
        }]),
    }


def _interaction_application_step_update(
    application_result: JSONDict,
    *,
    runtime: Runtime[PendingTaskRuntimeContext],
    effect_intents: object = None,
    prior_events: object = None,
) -> PendingTaskGraphState:
    result = coerce_json_dict(application_result.get("result"))
    task_snapshot = coerce_json_dict(application_result.get("task_snapshot"))
    events = _events(result.get("events"))
    runtime_task = runtime_agent_task_view(task_snapshot) if task_snapshot else None
    runtime.context.task = runtime_task
    runtime.context.side_effects.task = task_snapshot or None
    runtime.context.side_effects.interaction_result = result
    update: PendingTaskGraphState = {
        "interaction_result": _interaction_result_projection_from_json(result),
        "events": events,
        "handled": bool(result.get("handled")),
        "remember_pending_task": bool(result.get("remember_pending_task")),
        "has_active_task": bool(task_snapshot),
        "task_snapshot": task_snapshot,
        "task_projection": _task_projection(task_snapshot),
        "effect_intents": _with_task_projection_intent(effect_intents, task_snapshot),
    }
    assistant_content = result.get("assistant_content")
    if isinstance(assistant_content, str):
        update["assistant_content"] = assistant_content
    clear_pending_task_id = result.get("clear_pending_task_id")
    if isinstance(clear_pending_task_id, int):
        update["clear_pending_task_id"] = clear_pending_task_id
    selected_customer = coerce_json_dict(result.get("selected_customer"))
    if selected_customer:
        update["selected_customer"] = selected_customer
    current_interrupt = coerce_json_dict(result.get("current_interrupt"))
    if current_interrupt:
        current_interrupt["runtime_events"] = [
            *_events(prior_events),
            *events,
        ]
        update["current_interrupt"] = interrupt_payload_from_json(current_interrupt)
        update["pending_interrupt_requested"] = True
    return update


def _interaction_result_projection_from_json(result: JSONDict) -> JSONDict:
    return {
        "handled": bool(result.get("handled")),
        "remember_pending_task": bool(result.get("remember_pending_task")),
        "has_selected_customer": bool(coerce_json_dict(result.get("selected_customer"))),
        "event_count": len(_events(result.get("events"))),
    }


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
