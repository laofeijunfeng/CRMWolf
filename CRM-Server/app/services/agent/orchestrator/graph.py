"""Thin deterministic Root Orchestrator graph."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING, Annotated, TypedDict, TypeVar
from uuid import NAMESPACE_URL, uuid5

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import ValidationError

from app.services.agent.orchestrator.contracts import (
    AgentExecutionError,
    ClarificationDispatchResult,
    ClarificationRequest,
    ContextPolicy,
    FailureDispatchResult,
    InteractionResolver,
    InteractionTurnInput,
    QueryDispatchResult,
    QueryExecutionInput,
    QueryExecutor,
    ResolvedAgentAction,
    RootContextResolver,
    RootContextSnapshot,
    RootDecision,
    RootDecisionClassifier,
    RootDispatchResult,
    RootRoutingPlan,
    RootRuntimeContext,
    RootTurnInput,
    SemanticIntentResolver,
    SemanticPlanResolver,
    TextTurnInput,
    WorkflowContinuation,
    WorkflowDispatchResult,
    WorkflowRef,
    WorkflowTriggerTurnInput,
    root_dispatch_result_adapter,
)
from app.services.agent.orchestrator.decision import (
    RootDecisionInvalidOutputError,
    RootDecisionModelUnavailableError,
)
from app.services.agent.orchestrator.errors import (
    InteractionResolutionUnavailableError,
    RootContextUnavailableError,
    WorkflowCheckpointUnavailableError,
    WorkflowExecutionFailedError,
)
from app.services.agent.orchestrator.pending_case_matcher import match_pending_case
from app.services.agent.orchestrator.query_executor import (
    QueryExecutionConfigurationError,
    QueryIdentityResolutionUnavailableError,
    QuerySemanticResolutionUnavailableError,
)
from app.services.agent.orchestrator.result_set import (
    ResultSetReferenceError,
    resolve_result_set_entity,
)
from app.services.agent.principal import AgentPrincipal
from app.services.agent.query import CRMQueryAgentExecutionError
from app.services.agent.query.semantic_intent import (
    CRMQuerySemanticIntent,
    QuerySemanticIntentInvalidError,
    QuerySemanticIntentUnavailableError,
)
from app.services.agent.semantic_plan import (
    AgentSemanticPlan,
    query_intent_from_semantic_plan,
    semantic_plan_is_read,
    semantic_plan_is_write,
    semantic_plan_supports_workflow_write,
)
from app.services.agent.workflow import (
    WorkflowInterruptPayload,
    WorkflowOpportunitySuggestionStart,
    WorkflowProgress,
    WorkflowReplayResult,
    WorkflowResolvedCustomer,
    WorkflowResourceStart,
    WorkflowResumeInput,
    WorkflowTextStart,
    WorkflowTurnInput,
    WorkflowWaitingResult,
    workflow_result_adapter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


_QUERY_ERROR_MESSAGES = {
    "QUERY_INVALID": "我还没看懂你要查什么，请补充客户、时间或内容。",
    "QUERY_UNSUPPORTED": "暂不支持查询这类信息。",
    "QUERY_EMPTY": "没有找到符合条件的数据。",
    "PERMISSION_DENIED": "没有权限查看相关数据。",
    "QUERY_LIMIT_EXCEEDED": "查询结果较多，已按系统上限返回。",
    "UPSTREAM_TIMEOUT": "查询响应超时了，请再试一次。",
    "UPSTREAM_UNAVAILABLE": "查询暂时没有回应，请稍后再试。",
    "MODEL_OUTPUT_INVALID": "我还没看懂你要查什么，请换一种说法试试。",
    "INTERNAL_ERROR": "查询暂时没完成，请稍后再试。",
}


ROOT_RUNTIME_NAME = "crm_agent_root"
ROOT_RUNTIME_NAMESPACE = "crm_agent"

StateValue = TypeVar("StateValue")


def _workflow_id_for_turn(turn: RootTurnInput) -> str:
    """Derive one stable Workflow execution identity from the Root request identity."""

    identity = json.dumps(
        [turn.team_id, turn.user_id, turn.session_id, turn.client_request_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"wf_{uuid5(NAMESPACE_URL, f'crm-agent-workflow:{identity}').hex}"


def _workflow_id_for_server_trigger(
    turn: RootTurnInput,
    trigger: WorkflowTriggerTurnInput,
) -> str:
    """Derive a stable Workflow identity from the durable server trigger."""

    identity = json.dumps(
        [
            turn.team_id,
            turn.user_id,
            turn.session_id,
            trigger.workflow,
            trigger.resource_id or trigger.job_public_id,
            trigger.action,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"wf_{uuid5(NAMESPACE_URL, f'crm-agent-server-workflow:{identity}').hex}"


def _workflow_input_payload(request: WorkflowTurnInput) -> dict[str, object]:
    """Serialize Workflow input without adding optional semantic noise.

    Legacy checkpoints and test doubles intentionally omit the optional Root
    plan when no structured plan was supplied.  Known plans remain persisted
    for the selected Workflow to consume.
    """

    payload = request.model_dump(mode="json")
    start = payload.get("start")
    if isinstance(start, dict):
        plan = start.get("semantic_plan")
        if plan is None or (
            isinstance(plan, dict)
            and plan.get("speech_act") == "UNKNOWN"
            and plan.get("business_object") == "UNKNOWN"
            and plan.get("operation") == "UNKNOWN"
            and float(plan.get("confidence", 0.0) or 0.0) == 0.0
        ):
            start.pop("semantic_plan", None)
    return payload


def build_root_graph_config(turn: RootTurnInput) -> RunnableConfig:
    """Return a checkpoint identity owned by exactly one Root turn.

    A Session is a message container, not a LangGraph execution thread.  Using
    the request identity here prevents a pending interaction or a previous
    turn's state from becoming implicit state for an unrelated message in the
    same session.
    """

    turn_identity = json.dumps(
        [turn.team_id, turn.user_id, turn.session_id, turn.client_request_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    turn_token = uuid5(NAMESPACE_URL, f"crm-agent-root-turn:{turn_identity}").hex

    return {
        "configurable": {
            "thread_id": f"crm_agent_turn:{turn.team_id}:{turn.user_id}:{turn.session_id}:{turn_token}"
        },
        "metadata": {
            "team_id": turn.team_id,
            "user_id": turn.user_id,
            "session_id": turn.session_id,
            "client_request_id": turn.client_request_id,
            "turn_token": turn_token,
            "runtime": ROOT_RUNTIME_NAME,
            "runtime_namespace": ROOT_RUNTIME_NAMESPACE,
        },
    }


def _replace_state_value(_current: StateValue, new: StateValue) -> StateValue:
    """Treat Root state fields as latest-value registers across repeated resumes."""

    return new


class RootOrchestratorState(TypedDict, total=False):
    """Versioned JSON-safe latest-value registers persisted by Root."""

    turn: Annotated[dict[str, object], _replace_state_value]
    context_snapshot: Annotated[dict[str, object] | None, _replace_state_value]
    decision: Annotated[dict[str, object] | None, _replace_state_value]
    query_input: Annotated[dict[str, object] | None, _replace_state_value]
    semantic_intent: Annotated[dict[str, object] | None, _replace_state_value]
    resolved_action: Annotated[dict[str, object] | None, _replace_state_value]
    workflow_input: Annotated[dict[str, object] | None, _replace_state_value]
    workflow_result: Annotated[dict[str, object] | None, _replace_state_value]
    resumed_workflow_ref: Annotated[dict[str, object] | None, _replace_state_value]
    dispatch_result: Annotated[dict[str, object] | None, _replace_state_value]
    pending_case_public_id: Annotated[str | None, _replace_state_value]
    routing_plan: Annotated[dict[str, object] | None, _replace_state_value]


class RootOrchestrator:
    """Own task relation, context policy, and Query/Workflow dispatch."""

    def __init__(
        self,
        *,
        checkpointer: BaseCheckpointSaver,
        context_resolver: RootContextResolver,
        decision_classifier: RootDecisionClassifier,
        query_executor: QueryExecutor,
        interaction_resolver: InteractionResolver,
        workflow_subgraph: CompiledStateGraph,
        semantic_intent_resolver: SemanticIntentResolver | None = None,
        semantic_plan_resolver: SemanticPlanResolver | None = None,
        pending_case_ranker: object | None = None,
    ) -> None:
        self._checkpointer = checkpointer
        self._context_resolver = context_resolver
        self._decision_classifier = decision_classifier
        self._query_executor = query_executor
        self._interaction_resolver = interaction_resolver
        self._workflow_subgraph = workflow_subgraph
        self._semantic_intent_resolver = semantic_intent_resolver
        self._semantic_plan_resolver = semantic_plan_resolver
        self._pending_case_ranker = pending_case_ranker
        self._graph = self._build_graph()

    async def dispatch(
        self,
        turn: RootTurnInput,
        *,
        runtime: RootRuntimeContext,
        on_progress: Callable[[WorkflowProgress], None] | None = None,
    ) -> RootDispatchResult:
        config = build_root_graph_config(turn)
        try:
            state, continuation = await self._invoke_graph(
                self._new_turn_state(turn),
                config,
                runtime=runtime,
                on_progress=on_progress,
            )
            routing_plan = self._routing_plan_from_state(state)
            if routing_plan is not None:
                result = await self._execute_routing_plan(
                    turn=turn,
                    runtime=runtime,
                    config=config,
                    plan=routing_plan,
                    on_progress=on_progress,
                )
                self._persist_conversation_memory(
                    turn=turn,
                    context=routing_plan.context,
                    decision=result.decision,
                    state=state,
                    result=result,
                    runtime=runtime,
                )
                return result
            result = self._dispatch_result_from_state(state, continuation=continuation)
            self._persist_conversation_memory(
                turn=turn,
                context=RootContextSnapshot.model_validate(state["context_snapshot"]),
                decision=getattr(result, "decision", None),
                state=state,
                result=result,
                runtime=runtime,
            )
            return result
        except RootContextUnavailableError:
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="ROOT_CONTEXT_UNAVAILABLE",
                    message="当前对话状态没加载出来，请刷新后再试。",
                    retryable=True,
                )
            )
        except InteractionResolutionUnavailableError:
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="INTERACTION_RESOLUTION_UNAVAILABLE",
                    message="这个操作没接上，请刷新后再试。",
                    retryable=True,
                )
            )
        except WorkflowCheckpointUnavailableError:
            return self._workflow_failure("WORKFLOW_CHECKPOINT_UNAVAILABLE")
        except WorkflowExecutionFailedError:
            return self._workflow_failure("WORKFLOW_EXECUTION_FAILED")
        except RootDecisionModelUnavailableError as exc:
            logger.exception("Root decision model is unavailable")
            if exc.reason == "TIMEOUT":
                return FailureDispatchResult(
                    error=AgentExecutionError(
                        code="ROOT_DECISION_MODEL_TIMEOUT",
                        message="AI 刚才响应超时了，请再试一次。",
                        retryable=True,
                    )
                )
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="ROOT_DECISION_MODEL_UNAVAILABLE",
                    message="AI 暂时没有回应，请稍后再试。",
                    retryable=True,
                )
            )
        except RootDecisionInvalidOutputError:
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="ROOT_DECISION_INVALID_OUTPUT",
                    message="我还没理解这句话，请换一种说法试试。",
                    retryable=False,
                )
            )

    def _persist_conversation_memory(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        decision: RootDecision | None,
        state: dict[str, object],
        result: RootDispatchResult,
        runtime: RootRuntimeContext,
    ) -> None:
        """Best-effort write of short-term memory; never changes turn outcome."""

        persister = getattr(self._context_resolver, "persist_conversation_memory", None)
        if persister is None or decision is None or runtime.db is None:
            return
        memory = context.conversation_memory
        updates: dict[str, object] = {
            "last_agent_plan": f"{decision.route}:{decision.reason_code}",
        }
        workflow_input = state.get("workflow_input")
        parsed_workflow_input: WorkflowTurnInput | None = None
        if workflow_input is not None:
            try:
                parsed_workflow_input = WorkflowTurnInput.model_validate(workflow_input)
            except ValidationError:
                parsed_workflow_input = None

        # Only an ordinary text-start Workflow contributes activity working
        # memory.  A new task replaces the previous draft; a model-confirmed
        # continuation appends to it.  This keeps one stale sentence from
        # leaking into a later independent customer/task.
        if (
            isinstance(turn.input, TextTurnInput)
            and decision.route == "WORKFLOW"
            and parsed_workflow_input is not None
            and isinstance(parsed_workflow_input.start, WorkflowTextStart)
        ):
            updates["current_task"] = "customer_activity"
            if decision.task_relation == "CONTINUE_TASK" and memory.known_activity_content:
                updates["known_activity_content"] = (
                    f"{memory.known_activity_content}\n{turn.input.text}"
                )[-12000:]
            else:
                updates["known_activity_content"] = turn.input.text[:12000]

        if parsed_workflow_input is not None and parsed_workflow_input.resolved_customer is not None:
            updates["resolved_customer"] = parsed_workflow_input.resolved_customer
        if (
            isinstance(turn.input, TextTurnInput)
            and turn.selected_entity_ref is not None
            and turn.selected_entity_ref.resource == "customer"
        ):
            updates["resolved_customer"] = WorkflowResolvedCustomer(
                customer_id=turn.selected_entity_ref.public_id,
                customer_name=turn.selected_entity_ref.display_name,
                lookup_name=turn.selected_entity_ref.display_name,
            )
        if isinstance(result, WorkflowDispatchResult):
            if result.workflow_result.status == "WAITING":
                updates["pending_question"] = result.workflow_result.interaction.prompt
            else:
                updates["pending_question"] = None
        elif isinstance(result, ClarificationDispatchResult):
            updates["pending_question"] = result.clarification.question
        next_memory = memory.model_copy(update=updates)
        try:
            persister(runtime.db, turn=turn, memory=next_memory)
        except Exception:
            logger.warning(
                "Failed to persist Root conversation memory",
                extra={"session_id": turn.session_id, "client_request_id": turn.client_request_id},
                exc_info=True,
            )

    @staticmethod
    def _routing_plan_from_state(
        state: dict[str, object],
    ) -> RootRoutingPlan | None:
        raw_plan = state.get("routing_plan")
        if raw_plan is None:
            return None
        try:
            return RootRoutingPlan.model_validate(raw_plan)
        except ValidationError as exc:
            raise WorkflowExecutionFailedError("Root Graph returned an invalid routing plan") from exc

    async def _execute_routing_plan(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
        config: RunnableConfig,
        plan: RootRoutingPlan,
        on_progress: Callable[[WorkflowProgress], None] | None,
    ) -> RootDispatchResult:
        """Execute a server-authorized plan selected by the Root Graph.

        This adapter is deliberately limited to checkpoint mechanics.  Intent
        recognition, interaction binding, pending Case matching, and decision
        construction all happen in graph nodes before this method is reached.
        """

        if plan.kind == "INTERACTION_REPLAY":
            action = plan.resolved_action
            if action is None or action.replay_message_id is None:
                raise InteractionResolutionUnavailableError(
                    "Replayed action is missing its result message"
                )
            return WorkflowDispatchResult(
                decision=plan.decision,
                workflow_result=WorkflowReplayResult(
                    workflow_ref=(
                        action.workflow_ref
                        or WorkflowRef(
                            workflow_id=_workflow_id_for_server_trigger(turn, action.workflow_trigger)
                        )
                    ),
                    message_id=action.replay_message_id,
                ),
            )
        if plan.kind == "INTERACTION_RESUME":
            return await self._resume_interaction_plan(
                turn=turn,
                runtime=runtime,
                config=config,
                plan=plan,
                on_progress=on_progress,
            )
        if plan.kind == "TEXT_WORKFLOW_RESUME":
            return await self._resume_text_plan(
                turn=turn,
                runtime=runtime,
                config=config,
                plan=plan,
                on_progress=on_progress,
            )
        raise WorkflowExecutionFailedError("Unsupported Root routing plan")

    async def _resume_text_plan(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
        config: RunnableConfig,
        plan: RootRoutingPlan,
        on_progress: Callable[[WorkflowProgress], None] | None,
    ) -> RootDispatchResult:
        if not isinstance(turn.input, TextTurnInput) or plan.continuation is None:
            raise WorkflowExecutionFailedError("Text Workflow resume plan is invalid")
        continuation_config = self._config_for_continuation(config, plan.continuation)
        await self._require_continuation_checkpoint(continuation_config)
        resume = WorkflowResumeInput(
            kind="text",
            content=turn.input.text,
            source="agent_text",
            metadata={"continuation": "explicit"},
        )
        try:
            state, resumed_continuation = await self._invoke_graph(
                Command(
                    resume=resume.model_dump(mode="json"),
                    update=self._resettable_state(
                        turn=turn,
                        context_snapshot=plan.context,
                        decision=plan.decision,
                    )
                    | {
                        "resumed_workflow_ref": plan.continuation.workflow_ref.model_dump(mode="json"),
                    },
                ),
                continuation_config,
                runtime=runtime,
                on_progress=on_progress,
            )
            result = self._dispatch_result_from_state(state, continuation=resumed_continuation)
            if not isinstance(result, WorkflowDispatchResult):
                raise WorkflowExecutionFailedError(
                    "Text Workflow continuation returned a non-Workflow result"
                )
            return result
        except WorkflowCheckpointUnavailableError:
            return self._workflow_failure("WORKFLOW_CHECKPOINT_UNAVAILABLE")
        except WorkflowExecutionFailedError:
            logger.exception("Text Workflow continuation failed")
            return self._workflow_failure("WORKFLOW_EXECUTION_FAILED")

    async def _resume_interaction_plan(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
        config: RunnableConfig,
        plan: RootRoutingPlan,
        on_progress: Callable[[WorkflowProgress], None] | None,
    ) -> RootDispatchResult:
        action = plan.resolved_action
        if action is None:
            raise InteractionResolutionUnavailableError(
                "Interaction routing plan is missing its resolved action"
            )
        context = plan.context.model_copy(update={"active_workflow": action.workflow_ref})
        try:
            continuation_config = self._config_for_continuation(config, action.continuation)
            await self._require_continuation_checkpoint(continuation_config)
            state, continuation = await self._invoke_graph(
                Command(
                    resume=action.resume_payload,
                    update=self._resettable_state(
                        turn=turn,
                        context_snapshot=context,
                        decision=plan.decision,
                        resolved_action=action,
                    ),
                ),
                continuation_config,
                runtime=runtime,
                on_progress=on_progress,
            )
            result = self._dispatch_result_from_state(state, continuation=continuation)
            if not isinstance(result, WorkflowDispatchResult):
                raise WorkflowExecutionFailedError(
                    "Workflow continuation returned a non-Workflow result"
                )
        except WorkflowCheckpointUnavailableError:
            return self._workflow_failure(
                "WORKFLOW_CHECKPOINT_UNAVAILABLE",
                action_claim_id=action.action_id,
            )
        except WorkflowExecutionFailedError:
            return self._workflow_failure(
                "WORKFLOW_EXECUTION_FAILED",
                action_claim_id=action.action_id,
            )
        return result.model_copy(update={"action_claim_id": action.action_id})

    @staticmethod
    def _new_turn_state(
        turn: RootTurnInput,
    ) -> RootOrchestratorState:
        return RootOrchestrator._resettable_state(turn=turn)

    @staticmethod
    def _resettable_state(
        *,
        turn: RootTurnInput,
        context_snapshot: RootContextSnapshot | None = None,
        decision: RootDecision | None = None,
        resolved_action: ResolvedAgentAction | None = None,
    ) -> RootOrchestratorState:
        return {
            "turn": turn.model_dump(mode="json"),
            "context_snapshot": (context_snapshot.model_dump(mode="json") if context_snapshot is not None else None),
            "decision": decision.model_dump(mode="json") if decision is not None else None,
            "query_input": None,
            "semantic_intent": None,
            "resolved_action": (resolved_action.model_dump(mode="json") if resolved_action is not None else None),
            "workflow_input": None,
            "workflow_result": None,
            "resumed_workflow_ref": None,
            "dispatch_result": None,
            "pending_case_public_id": None,
            "routing_plan": None,
        }

    @staticmethod
    def _root_thread_id_from_config(config: RunnableConfig) -> str:
        thread_id = _thread_id_or_none(config)
        if thread_id is None:
            raise WorkflowCheckpointUnavailableError("Workflow continuation has no owning Root thread")
        return thread_id

    @staticmethod
    def _config_for_continuation(
        config: RunnableConfig,
        continuation: WorkflowContinuation,
    ) -> RunnableConfig:
        configurable = dict(config.get("configurable", {}))
        # Continuations are owned by the Root turn that created the interrupt.
        # The current request has a fresh turn thread; resuming it would make
        # LangGraph look for the old checkpoint in the wrong thread.
        configurable["thread_id"] = continuation.root_thread_id
        configurable["checkpoint_id"] = continuation.parent_checkpoint_id
        configurable["checkpoint_map"] = {
            "": continuation.parent_checkpoint_id,
            continuation.subgraph_checkpoint_ns: continuation.subgraph_checkpoint_id,
        }
        return {
            **config,
            "configurable": configurable,
        }

    async def _require_continuation_checkpoint(
        self,
        config: RunnableConfig,
    ) -> None:
        """Fail closed instead of letting LangGraph restart a missing continuation."""

        try:
            checkpoint = await self._checkpointer.aget_tuple(config)
        except Exception as exc:
            raise WorkflowCheckpointUnavailableError(
                "Workflow continuation checkpoint could not be loaded"
            ) from exc
        if checkpoint is None:
            raise WorkflowCheckpointUnavailableError(
                "Workflow continuation checkpoint no longer exists"
            )

    async def _invoke_graph(
        self,
        graph_input: RootOrchestratorState | Command,
        config: RunnableConfig,
        *,
        runtime: RootRuntimeContext,
        on_progress: Callable[[WorkflowProgress], None] | None = None,
    ) -> tuple[dict[str, object], WorkflowContinuation | None]:
        """Run one Root turn and capture the exact durable Workflow continuation."""

        final_state: dict[str, object] | None = None
        root_thread_id: str | None = None
        parent_checkpoint_id: str | None = None
        subgraph_checkpoint_ns: str | None = None
        subgraph_checkpoint_id: str | None = None
        async for namespace, mode, payload in self._graph.astream(
            graph_input,
            config,
            context=runtime,
            stream_mode=["values", "checkpoints", "custom"],
            subgraphs=True,
            durability="sync",
        ):
            if mode == "values":
                if not namespace and isinstance(payload, dict):
                    final_state = payload
                continue
            if mode == "custom":
                if on_progress is not None:
                    try:
                        on_progress(WorkflowProgress.model_validate(payload))
                    except ValidationError:
                        logger.warning("Ignored invalid Workflow progress event", exc_info=True)
                continue
            if mode != "checkpoints" or not isinstance(payload, dict):
                continue
            checkpoint_config = payload.get("config")
            checkpoint_id = _checkpoint_id_or_none(checkpoint_config)
            if not namespace:
                root_thread_id = _thread_id_or_none(checkpoint_config)
                next_nodes = payload.get("next")
                if checkpoint_id is not None and next_nodes == ["workflow_subgraph"]:
                    parent_checkpoint_id = checkpoint_id
                continue
            checkpoint_ns = _checkpoint_namespace_or_none(checkpoint_config)
            if checkpoint_id is not None and checkpoint_ns is not None and _is_workflow_subgraph_namespace(namespace):
                subgraph_checkpoint_ns = checkpoint_ns
                subgraph_checkpoint_id = checkpoint_id

        if final_state is None:
            raise WorkflowExecutionFailedError("Root graph produced no final state")
        interrupts = final_state.get("__interrupt__")
        if not isinstance(interrupts, (list, tuple)):
            return final_state, None
        if parent_checkpoint_id is None or subgraph_checkpoint_ns is None or subgraph_checkpoint_id is None:
            raise WorkflowCheckpointUnavailableError("Interrupted Workflow did not expose a durable continuation")
        workflow_ref = self._workflow_ref_from_interrupts(interrupts)
        interrupt_payload = WorkflowInterruptPayload.model_validate(
            getattr(interrupts[0], "value", None)
        )
        return final_state, WorkflowContinuation(
            workflow_ref=workflow_ref,
            root_thread_id=root_thread_id or self._root_thread_id_from_config(config),
            parent_checkpoint_id=parent_checkpoint_id,
            subgraph_checkpoint_ns=subgraph_checkpoint_ns,
            subgraph_checkpoint_id=subgraph_checkpoint_id,
            waiting_interaction_type=interrupt_payload.interaction.interaction_type,
        )

    def _dispatch_result_from_state(
        self,
        state: dict[str, object],
        *,
        continuation: WorkflowContinuation | None,
    ) -> RootDispatchResult:
        dispatch_result = state.get("dispatch_result")
        if dispatch_result is not None:
            try:
                return root_dispatch_result_adapter.validate_python(dispatch_result)
            except ValidationError as exc:
                raise WorkflowExecutionFailedError("Root graph returned an invalid dispatch result") from exc
        interrupts = state.get("__interrupt__")
        if not isinstance(interrupts, (list, tuple)):
            raise WorkflowExecutionFailedError("Root graph completed without a dispatch result")
        try:
            decision = RootDecision.model_validate(state.get("decision"))
        except ValidationError as exc:
            raise WorkflowExecutionFailedError("Interrupted Workflow is missing its Root decision") from exc
        return WorkflowDispatchResult(
            decision=decision,
            workflow_result=self._waiting_result_from_interrupts(interrupts),
            continuation=continuation,
        )

    @staticmethod
    def _workflow_ref_from_interrupts(interrupts: object) -> WorkflowRef:
        if not isinstance(interrupts, (list, tuple)) or len(interrupts) != 1:
            raise WorkflowCheckpointUnavailableError("Exactly one active Workflow interrupt is required")
        interrupt_value = getattr(interrupts[0], "value", None)
        interrupt_id = getattr(interrupts[0], "id", None)
        if not isinstance(interrupt_id, str) or not interrupt_id:
            raise WorkflowCheckpointUnavailableError("Active Workflow interrupt has no durable identity")
        try:
            payload = WorkflowInterruptPayload.model_validate(interrupt_value)
        except ValidationError as exc:
            raise WorkflowCheckpointUnavailableError("Active Workflow interrupt payload is invalid") from exc
        return WorkflowRef(
            workflow_id=payload.workflow_id,
            interrupt_id=interrupt_id,
        )

    @classmethod
    def _waiting_result_from_interrupts(
        cls,
        interrupts: object,
    ) -> WorkflowWaitingResult:
        workflow_ref = cls._workflow_ref_from_interrupts(interrupts)
        interrupt_value = getattr(interrupts[0], "value", None)
        try:
            payload = WorkflowInterruptPayload.model_validate(interrupt_value)
        except ValidationError as exc:
            raise WorkflowExecutionFailedError("Workflow interrupt payload could not be projected") from exc
        return WorkflowWaitingResult(
            workflow_ref=workflow_ref,
            assistant_text=payload.interaction.prompt,
            interaction=payload.interaction,
            progress=payload.progress,
        )

    def _build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(
            RootOrchestratorState,
            context_schema=RootRuntimeContext,
        )
        graph.add_node("load_context", self._load_context)
        graph.add_node("resolve_deterministic_continuation", self._resolve_deterministic_continuation)
        graph.add_node("decide", self._decide)
        graph.add_node("validate_decision", self._validate_decision)
        graph.add_node("apply_context_policy", self._apply_context_policy)
        graph.add_node("query_agent", self._run_query)
        graph.add_node("workflow_subgraph", self._workflow_subgraph)
        graph.add_node("finalize_workflow", self._finalize_workflow)
        graph.add_node("build_clarification", self._build_clarification)
        graph.add_node("finalize_dispatch", self._finalize_dispatch)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "resolve_deterministic_continuation")
        graph.add_conditional_edges(
            "resolve_deterministic_continuation",
            self._route_after_deterministic_continuation,
            {
                "DECIDE": "decide",
                "VALIDATE": "validate_decision",
                "ROUTING_PLAN": END,
                "DISPATCH_RESULT": END,
            },
        )
        graph.add_conditional_edges(
            "decide",
            self._route_after_decision,
            {
                "VALIDATE": "validate_decision",
                "ROUTING_PLAN": END,
            },
        )
        graph.add_edge("validate_decision", "apply_context_policy")
        graph.add_conditional_edges(
            "apply_context_policy",
            self._route_after_context_policy,
            {
                "QUERY": "query_agent",
                "WORKFLOW": "workflow_subgraph",
                "CLARIFY": "build_clarification",
            },
        )
        graph.add_edge("query_agent", "finalize_dispatch")
        graph.add_edge("workflow_subgraph", "finalize_workflow")
        graph.add_edge("finalize_workflow", "finalize_dispatch")
        graph.add_edge("build_clarification", "finalize_dispatch")
        graph.add_edge("finalize_dispatch", END)
        return graph.compile(checkpointer=self._checkpointer)

    async def _load_context(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        turn = RootTurnInput.model_validate(state["turn"])
        context = await self._context_resolver.resolve(
            turn=turn,
            runtime=runtime.context,
        )
        return {"context_snapshot": context.model_dump(mode="json")}

    async def _resolve_deterministic_continuation(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        """Resolve resources that must never be selected by the decision model."""

        turn = RootTurnInput.model_validate(state["turn"])
        context = RootContextSnapshot.model_validate(state["context_snapshot"])

        if isinstance(turn.input, InteractionTurnInput):
            resolution = await self._interaction_resolver.resolve(
                turn=turn,
                context=context,
                runtime=runtime.context,
            )
            if resolution.status == "REJECTED":
                return {
                    "dispatch_result": self._interaction_failure(
                        resolution.reason_code
                    ).model_dump(mode="json")
                }
            resolved_action = resolution.resolved_action
            if resolved_action is None:
                raise InteractionResolutionUnavailableError(
                    "Resolved interaction is missing its canonical action"
                )
            if resolved_action.workflow_trigger is not None:
                if resolved_action.claim_outcome == "REPLAY":
                    decision = self._server_workflow_trigger_decision(
                        context=context,
                        trigger=resolved_action.workflow_trigger,
                    )
                    plan = RootRoutingPlan(
                        kind="INTERACTION_REPLAY",
                        context=context,
                        decision=decision,
                        resolved_action=resolved_action,
                    )
                    return {"routing_plan": plan.model_dump(mode="json")}
                decision = self._server_workflow_trigger_decision(
                    context=context,
                    trigger=resolved_action.workflow_trigger,
                )
                return {
                    "decision": decision.model_dump(mode="json"),
                    "resolved_action": resolved_action.model_dump(mode="json"),
                }

            decision = self._interaction_workflow_decision(
                turn=turn,
                reason_code=resolution.reason_code,
            )
            plan = RootRoutingPlan(
                kind=(
                    "INTERACTION_REPLAY"
                    if resolved_action.claim_outcome == "REPLAY"
                    else "INTERACTION_RESUME"
                ),
                context=context,
                decision=decision,
                resolved_action=resolved_action,
                continuation=resolved_action.continuation,
            )
            return {"routing_plan": plan.model_dump(mode="json")}

        # Free text is intentionally not matched here. The Root Decision model
        # is the only semantic authority for ordinary language. This node remains
        # limited to typed interaction bindings; text Case/checkpoint validation
        # happens after Root classification.
        return {}

    async def _try_resolve_canonical_semantic_plan(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> AgentSemanticPlan | None:
        """Resolve canonical business meaning before capability routing.

        Root remains the owner of task relation and context policy. The domain
        semantic intake is a bounded semantic safety seam: when available, it
        runs before the query-only parser so a write assertion cannot be
        downgraded into a historical read. In degraded runtimes it is also
        retained as recovery for a QUERY/CLARIFY candidate. It receives the
        whole utterance and returns structured meaning; no lexical shortcut or
        query result is involved.
        """

        if not isinstance(turn.input, TextTurnInput) or self._semantic_plan_resolver is None:
            return None
        text = turn.input.text
        if text in runtime.semantic_plan_cache:
            return runtime.semantic_plan_cache[text]
        if text in runtime.semantic_plan_failures:
            return None
        try:
            plan = await self._semantic_plan_resolver.resolve(
                turn=turn,
                context=context,
                runtime=runtime,
            )
        except Exception:
            # Recovery must never make the Agent unavailable. The original Root
            # decision still flows into the existing fail-closed validation.
            runtime.semantic_plan_failures.add(text)
            logger.warning(
                "Canonical semantic intake unavailable during Root route recovery",
                extra={"session_id": turn.session_id, "client_request_id": turn.client_request_id},
                exc_info=True,
            )
            return None
        if plan is None:
            runtime.semantic_plan_failures.add(text)
            return None
        runtime.semantic_plan_cache[text] = plan
        return plan


    async def _try_resolve_semantic_query_intent(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> CRMQuerySemanticIntent | None:
        """Resolve query parameters after Root has selected the Query capability.

        This is a query-only semantic enrichment, not a top-level router. It
        fills the closed Query contract when Root did not provide complete
        query slots. Unknown, low-confidence, or unavailable results remain a
        Query failure/clarification; they cannot redirect a turn into or out of
        a Workflow. Result-set references remain owned by the deterministic
        result-set binding seam and therefore bypass this enrichment.
        """

        if not isinstance(turn.input, TextTurnInput):
            return None
        if (
            self._semantic_intent_resolver is None
            or runtime.query_model_config is None
            or context.result_set is not None
        ):
            return None
        text = turn.input.text
        intent = runtime.semantic_intent_cache.get(text)
        if intent is None and text in runtime.semantic_intent_failures:
            return None
        if intent is None:
            try:
                intent = await self._semantic_intent_resolver.resolve(
                    text,
                    model_config=runtime.query_model_config,
                    runtime=runtime,
                )
            except (QuerySemanticIntentUnavailableError, QuerySemanticIntentInvalidError):
                runtime.semantic_intent_failures.add(text)
                # Root remains available when the optional query preflight model
                # is unavailable. If Root selects QUERY, the Query seam will
                # report the same typed semantic failure without replaying the
                # provider call in this turn.
                return None
            runtime.semantic_intent_cache[text] = intent

        if intent.scope not in {"global_work", "customer_scoped", "customer_list"}:
            return None
        if intent.confidence < 0.80:
            return None
        return intent

    @staticmethod
    def _route_after_deterministic_continuation(state: RootOrchestratorState) -> str:
        if state.get("dispatch_result") is not None:
            return "DISPATCH_RESULT"
        if state.get("routing_plan") is not None:
            return "ROUTING_PLAN"
        if state.get("decision") is not None:
            return "VALIDATE"
        return "DECIDE"

    async def _select_pending_case_semantically(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        match: object,
        runtime: RootRuntimeContext,
    ) -> str | None:
        """Select an authorized pending Case without substring heuristics."""

        ranker = self._pending_case_ranker
        candidates = getattr(match, "candidates", ())
        if ranker is None or runtime.db is None or len(candidates) < 2:
            return None
        rows = [
            {
                "id": index,
                "customer_name": case.customer_name,
                "customer_aliases": case.customer_aliases,
                "task_title": case.task_title,
                "task_description": case.task_description,
                "due_at": case.due_at_text,
                "question": case.question_text,
            }
            for index, case in enumerate(candidates, start=1)
        ]
        try:
            rankings = await ranker.rank_resource_candidates(
                runtime.db,
                team_id=turn.team_id,
                user_message=turn.input.text if isinstance(turn.input, TextTurnInput) else "",
                resource_kind="pending_follow_up_confirmation",
                action_name="CONFIRM_FOLLOW_UP_TASK",
                target={
                    # The current utterance is already passed separately. Keep
                    # this target limited to the model-authorized reference and
                    # neutral session context; an old activity draft must not
                    # bias selection toward the wrong pending Case.
                    "pending_case_reference": getattr(match, "reference", None),
                    "current_task": context.conversation_memory.current_task,
                    "pending_question": context.conversation_memory.pending_question,
                },
                candidates=rows,
                current_date=None,
            )
        except Exception:
            # Semantic ranking improves ambiguous references, but must never
            # make the Root unavailable. The existing signed/clarification
            # path remains the safe fallback.
            return None

        if not isinstance(rankings, list):
            return None

        valid: list[tuple[int, float]] = []
        candidate_ids = {int(row["id"]) for row in rows}
        for ranking in rankings:
            if not isinstance(ranking, dict):
                continue
            resource_id = ranking.get("resource_id")
            confidence = ranking.get("confidence")
            if isinstance(resource_id, bool) or not isinstance(resource_id, int):
                continue
            if resource_id not in candidate_ids or not isinstance(confidence, (int, float)):
                continue
            confidence_value = float(confidence)
            if not math.isfinite(confidence_value) or not 0.0 <= confidence_value <= 1.0:
                continue
            valid.append((resource_id, confidence_value))
        valid.sort(key=lambda item: item[1], reverse=True)
        if not valid or valid[0][1] < 0.90:
            return None
        if len(valid) > 1 and valid[0][1] - valid[1][1] < 0.10:
            return None
        return candidates[valid[0][0] - 1].case_public_id

    async def _decide(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        """Route one ordinary text turn through the semantic safety boundary.

        Typed UI interactions and server triggers are handled deterministically
        before this node. Text first gets a canonical domain-semantic safety
        check when available; Root still owns task relation and context policy,
        while Query/Workflow modules only parse or execute the capability
        selected after the closed-world projection.
        """

        turn = RootTurnInput.model_validate(state["turn"])
        context = RootContextSnapshot.model_validate(state["context_snapshot"])
        semantic_intent: CRMQuerySemanticIntent | None = None

        if isinstance(turn.input, WorkflowTriggerTurnInput):
            if turn.input.workflow == "customer_opportunity_suggestion":
                decision = self._server_workflow_trigger_decision(
                    context=context,
                    trigger=turn.input,
                )
            else:
                has_active_workflow = context.active_workflow is not None
                decision = RootDecision(
                    task_relation="SWITCH_TASK" if has_active_workflow else "NEW_TASK",
                    route="WORKFLOW",
                    risk="WRITE",
                    context_policy=ContextPolicy(
                        selected_entity="IGNORE",
                        previous_query="IGNORE",
                        result_set="IGNORE",
                        active_workflow="SUSPEND" if has_active_workflow else "NONE",
                    ),
                    confidence=1.0,
                    reason_code="FOLLOW_UP_TASK_CONFIRMATION_TRIGGER",
                    evidence=["服务端触发跟进任务确认工作流"],
                    semantic_plan=AgentSemanticPlan(
                        speech_act="CONFIRM_ACTION",
                        business_object="FOLLOW_UP_TASK",
                        operation="TRANSITION",
                        confidence=1.0,
                    ),
                )
        elif isinstance(turn.input, TextTurnInput):
            # Root is the only top-level semantic router.  Query and canonical
            # parsers are capability-specific enrichers/recovery seams and must
            # never run before Root has selected the task boundary.  This is
            # important for both correctness (an event assertion must reach the
            # Activity Workflow) and availability (a normal query must not pay
            # for several independent model calls before it can execute).
            decision = await self._decision_classifier.classify(
                turn=turn,
                context=context,
                runtime=runtime.context,
            )

            root_plan = decision.semantic_plan
            root_plan_is_reliable_read = (
                root_plan.confidence >= 0.80 and semantic_plan_is_read(root_plan)
            )
            root_plan_is_reliable_write = (
                root_plan.confidence >= 0.80 and semantic_plan_is_write(root_plan)
            )

            # Recovery is deliberately bounded.  A reliable Root semantic plan
            # is authoritative for an otherwise valid turn, so a second
            # top-level parser is not allowed to reinterpret it.  There is one
            # structural exception: a model-selected Workflow continuation
            # cannot be valid when the server supplied no active Workflow. In
            # that case, use canonical domain intake to recover the complete
            # business meaning. Query-specific enrichment is deliberately not
            # involved because it is not authorized to decide the top-level
            # capability.
            root_context_policy_is_impossible = (
                decision.route == "WORKFLOW"
                and decision.task_relation == "CONTINUE_TASK"
                and decision.context_policy.active_workflow == "RESUME"
                and context.active_workflow is None
            )
            canonical_plan: AgentSemanticPlan | None = None
            if root_context_policy_is_impossible:
                # A missing continuation is a context inconsistency, not
                # evidence that the user asked for a read.  Re-run the
                # canonical business-semantic intake first and project that
                # result onto the capability.  The Query semantic resolver is
                # intentionally *not* allowed to repair Root routing here:
                # it is a query-only parser and a query-biased interpretation
                # could downgrade a new activity assertion into a read.
                #
                # If canonical intake is unavailable, the safe outcome is the
                # existing fail-closed clarification for the impossible
                # continuation.  It is better to ask once than to execute the
                # wrong read-only capability or lose a requested write.
                canonical_plan = await self._try_resolve_canonical_semantic_plan(
                    turn=turn,
                    context=context,
                    runtime=runtime.context,
                )
            elif not root_plan_is_reliable_read and not root_plan_is_reliable_write:
                canonical_plan = await self._try_resolve_canonical_semantic_plan(
                    turn=turn,
                    context=context,
                    runtime=runtime.context,
                )

            canonical_is_reliable = (
                canonical_plan is not None and canonical_plan.confidence >= 0.80
            )
            if canonical_is_reliable and (
                semantic_plan_is_write(canonical_plan)
                or semantic_plan_is_read(canonical_plan)
            ):
                # Keep Root's semantic meaning, but project the recovered
                # structured meaning onto the capability before validation.
                # _normalize_semantic_route owns the closed-world route/risk
                # projection and unsupported-write clarification.
                decision = decision.model_copy(
                    update={
                        "semantic_plan": canonical_plan,
                        "confidence": max(decision.confidence, canonical_plan.confidence),
                    }
                )
                if root_context_policy_is_impossible:
                    # The original CONTINUE_TASK/RESUME policy was based on a
                    # continuation that the server has just proved absent. A
                    # recovered meaning—whether read or write—must start as a
                    # fresh task; carrying RESUME forward would make the later
                    # context guard turn a valid request into a misleading
                    # clarification.
                    decision = decision.model_copy(
                        update={
                            "task_relation": "NEW_TASK",
                            "context_policy": decision.context_policy.model_copy(
                                update={
                                    "active_workflow": "NONE",
                                    "previous_query": "IGNORE",
                                    "result_set": "IGNORE",
                                }
                            ),
                        }
                    )

            # Query semantics are resolved only after Root (and any bounded
            # recovery) has selected QUERY.  The resolved intent is stored in
            # state and passed to the Query executor, so the executor performs
            # no second provider call for this turn.
            decision = self._normalize_semantic_route(decision, preserve_clarify=False)
            if decision.route == "QUERY" and semantic_intent is None:
                # Prefer complete query slots from the same Root semantic
                # intake.  The specialized Query parser is only a fallback for
                # older/incomplete Root outputs, never a second unconditional
                # router.
                semantic_intent = query_intent_from_semantic_plan(decision.semantic_plan)
            if decision.route == "QUERY" and semantic_intent is None:
                semantic_intent = await self._try_resolve_semantic_query_intent(
                    turn=turn,
                    context=context,
                    runtime=runtime.context,
                )

            # Pending Case IDs are server-owned bindings. The model can say
            # that the utterance is about a pending case, but it cannot invent
            # the Case identity. Match only after Root has selected that
            # capability, then either bind a unique case or clarify.
            if decision.pending_case_relation == "EXPLICIT_REFERENCE":
                if decision.route != "WORKFLOW":
                    decision = self._clarification_decision(
                        decision, "PENDING_CASE_ROUTE_MISMATCH"
                    )
                pending_match = match_pending_case(
                    turn.input.text,
                    context.pending_cases,
                    semantic_reference_authorized=True,
                )
                pending_case_public_id = None
                if pending_match.status == "MATCHED" and pending_match.case is not None:
                    pending_case_public_id = pending_match.case.case_public_id
                elif pending_match.status == "AMBIGUOUS":
                    pending_case_public_id = await self._select_pending_case_semantically(
                        turn=turn,
                        context=context,
                        match=pending_match,
                        runtime=runtime.context,
                    )
                if pending_case_public_id is not None:
                    return {
                        "decision": decision.model_dump(mode="json"),
                        "pending_case_public_id": pending_case_public_id,
                        "semantic_intent": None,
                    }
                reason_code = (
                    "PENDING_CASE_REFERENCE_AMBIGUOUS"
                    if pending_match.status == "AMBIGUOUS"
                    else "PENDING_CASE_NOT_FOUND"
                )
                decision = self._clarification_decision(decision, reason_code)

            if (
                decision.route == "WORKFLOW"
                and decision.task_relation == "CONTINUE_TASK"
                and decision.context_policy.active_workflow == "RESUME"
            ):
                continuation_result = self._text_continuation_routing(
                    context=context,
                    decision=decision,
                )
                if continuation_result.get("routing_plan") is not None:
                    return {
                        **continuation_result,
                        "semantic_intent": (
                            semantic_intent.model_dump(mode="json")
                            if semantic_intent is not None
                            else None
                        ),
                    }
                decision = RootDecision.model_validate(continuation_result["decision"])

        else:
            # Defensive fallback: current non-text inputs are resolved before
            # Root classification.
            decision = await self._decision_classifier.classify(
                turn=turn,
                context=context,
                runtime=runtime.context,
            )

        return {
            "decision": decision.model_dump(mode="json"),
            "semantic_intent": (
                semantic_intent.model_dump(mode="json")
                if semantic_intent is not None
                else None
            ),
        }

    def _text_continuation_routing(
        self,
        *,
        context: RootContextSnapshot,
        decision: RootDecision,
    ) -> dict[str, object]:
        """Validate a model-selected text continuation without re-routing it."""

        if context.active_workflow is None:
            return {
                "decision": self._clarification_decision(
                    decision, "ACTIVE_WORKFLOW_CONTEXT_MISSING"
                ).model_dump(mode="json")
            }
        continuations = context.resumable_workflow_continuations
        if len(continuations) != 1 or continuations[0].workflow_ref != context.active_workflow:
            return {
                "decision": self._clarification_decision(
                    decision, "ACTIVE_WORKFLOW_RESUME_AMBIGUOUS"
                ).model_dump(mode="json")
            }
        continuation = continuations[0]
        if continuation.waiting_interaction_type != "text_input":
            return {
                "decision": self._clarification_decision(
                    decision, "WORKFLOW_CONFIRMATION_REQUIRES_STRUCTURED_ACTION"
                ).model_dump(mode="json")
            }
        plan = RootRoutingPlan(
            kind="TEXT_WORKFLOW_RESUME",
            context=context,
            decision=decision,
            continuation=continuation,
        )
        return {"routing_plan": plan.model_dump(mode="json")}

    @staticmethod
    def _workflow_failure(
        code: str,
        *,
        action_claim_id: str | None = None,
    ) -> FailureDispatchResult:
        if code == "WORKFLOW_CHECKPOINT_UNAVAILABLE":
            error = AgentExecutionError(
                code=code,
                message="刚才的操作没接上，请重新说一下要做什么。",
                retryable=True,
            )
        else:
            error = AgentExecutionError(
                code="WORKFLOW_EXECUTION_FAILED",
                message="这次操作没完成，请稍后再试。",
                retryable=True,
            )
        return FailureDispatchResult(
            error=error,
            action_claim_id=action_claim_id,
        )

    @staticmethod
    def _interaction_failure(reason_code: str) -> FailureDispatchResult:
        error_by_reason = {
            "ACTION_ALREADY_CONSUMED": AgentExecutionError(
                code="ACTION_ALREADY_CONSUMED",
                message="该操作已被处理,请刷新会话查看最新结果。",
                retryable=False,
            ),
            "ACTION_EXPIRED": AgentExecutionError(
                code="ACTION_EXPIRED",
                message="该操作已过期,请刷新会话后重新发起。",
                retryable=False,
            ),
            "ACTION_NOT_FOUND": AgentExecutionError(
                code="PERMISSION_DENIED",
                message="无权访问或执行该操作。",
                retryable=False,
            ),
        }
        error = error_by_reason.get(
            reason_code,
            AgentExecutionError(
                code="ACTION_INVALID",
                message="提交的操作无效,请刷新会话后重试。",
                retryable=False,
            ),
        )
        return FailureDispatchResult(error=error)

    def _validate_decision(
        self,
        state: RootOrchestratorState,
    ) -> RootOrchestratorState:
        """Apply deterministic Root invariants after model/deterministic routing."""

        turn = RootTurnInput.model_validate(state["turn"])
        context = RootContextSnapshot.model_validate(state["context_snapshot"])
        decision = self._validated_decision(
            RootDecision.model_validate(state["decision"]),
            turn=turn,
            context=context,
        )
        return {"decision": decision.model_dump(mode="json")}


    def _apply_context_policy(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        turn = RootTurnInput.model_validate(state["turn"])
        runtime_context = runtime.context
        context = RootContextSnapshot.model_validate(state["context_snapshot"])
        decision = RootDecision.model_validate(state["decision"])
        if decision.route == "CLARIFY":
            return {"decision": decision.model_dump(mode="json")}

        principal = AgentPrincipal(
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            permission_codes=sorted(runtime_context.permission_codes),
        )
        selected_entity = turn.selected_entity_ref if decision.context_policy.selected_entity == "USE" else None
        remembered_customer = (
            context.conversation_memory.resolved_customer
            if (
                decision.context_policy.conversation_memory == "USE"
                and decision.task_relation == "CONTINUE_TASK"
            )
            else None
        )
        result_set = context.result_set if decision.context_policy.result_set == "USE" else None
        if isinstance(turn.input, TextTurnInput) and result_set is not None:
            try:
                resolved_entity = resolve_result_set_entity(
                    text=turn.input.text,
                    result_set=result_set,
                )
            except ResultSetReferenceError as exc:
                return {"decision": self._clarification_decision(decision, exc.code).model_dump(mode="json")}
            if resolved_entity is not None:
                selected_entity = resolved_entity
                result_set = None
        # A freshly selected result-set entity remains the authoritative
        # binding for this turn. Cached memory is only a supplement when the
        # user did not select/bind another entity; the Workflow planner then
        # revalidates the cached customer before mutation.
        resolved_customer = remembered_customer if selected_entity is None else None
        resolved_action = (
            ResolvedAgentAction.model_validate(state["resolved_action"])
            if state.get("resolved_action") is not None
            else None
        )
        server_trigger = resolved_action.workflow_trigger if resolved_action is not None else None
        if isinstance(turn.input, WorkflowTriggerTurnInput):
            server_trigger = turn.input
        if server_trigger is not None and server_trigger.workflow == "customer_opportunity_suggestion":
            workflow_start = WorkflowOpportunitySuggestionStart(
                kind="opportunity_suggestion",
                action=server_trigger.action or "CANCEL",
                job_public_id=server_trigger.job_public_id or "",
            )
            return {
                "decision": decision.model_dump(mode="json"),
                "workflow_input": _workflow_input_payload(WorkflowTurnInput(
                    workflow_id=_workflow_id_for_server_trigger(turn, server_trigger),
                    start=workflow_start,
                    principal=principal,
                    selected_entity=selected_entity,
                )),
            }
        if decision.route == "QUERY":
            if not isinstance(turn.input, TextTurnInput):
                return {
                    "decision": self._clarification_decision(decision, "QUERY_REQUIRES_TEXT").model_dump(mode="json")
                }
            return {
                "decision": decision.model_dump(mode="json"),
                "query_input": QueryExecutionInput(
                    text=turn.input.text,
                    principal=principal,
                    selected_entity=selected_entity,
                    previous_query=(
                        context.previous_query if decision.context_policy.previous_query == "USE" else None
                    ),
                    result_set=result_set,
                    semantic_intent=(
                        CRMQuerySemanticIntent.model_validate(state["semantic_intent"])
                        if state.get("semantic_intent") is not None
                        else None
                    ),
                    resolved_customer=resolved_customer,
                ).model_dump(mode="json"),
            }
        if isinstance(turn.input, TextTurnInput):
            pending_case_public_id = state.get("pending_case_public_id")
            if pending_case_public_id is not None:
                workflow_start = WorkflowResourceStart(
                    kind="resource",
                    workflow="follow_up_task_confirmation",
                    resource_id=str(pending_case_public_id),
                )
            else:
                workflow_start = WorkflowTextStart(
                    kind="text",
                    text=turn.input.text,
                    semantic_plan=decision.semantic_plan,
                )
        elif isinstance(turn.input, WorkflowTriggerTurnInput):
            if turn.input.workflow != "follow_up_task_confirmation" or turn.input.resource_id is None:
                return {
                    "decision": self._clarification_decision(decision, "WORKFLOW_START_INVALID").model_dump(mode="json")
                }
            workflow_start = WorkflowResourceStart(
                kind="resource",
                workflow=turn.input.workflow,
                resource_id=turn.input.resource_id,
            )
        else:
            return {
                "decision": self._clarification_decision(decision, "WORKFLOW_START_INVALID").model_dump(mode="json")
            }
        return {
            "decision": decision.model_dump(mode="json"),
            "workflow_input": _workflow_input_payload(WorkflowTurnInput(
                workflow_id=_workflow_id_for_turn(turn),
                start=workflow_start,
                principal=principal,
                selected_entity=selected_entity,
                resolved_customer=resolved_customer,
            )),
        }

    @staticmethod
    def _route_after_decision(state: RootOrchestratorState) -> str:
        """Stop before validation when the Root selected a checkpoint plan."""

        return "ROUTING_PLAN" if state.get("routing_plan") is not None else "VALIDATE"

    @staticmethod
    def _route_after_context_policy(state: RootOrchestratorState) -> str:
        return RootDecision.model_validate(state["decision"]).route

    async def _run_query(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        turn = RootTurnInput.model_validate(state["turn"])
        decision = RootDecision.model_validate(state["decision"])
        query_input = QueryExecutionInput.model_validate(state["query_input"])
        try:
            result = await self._query_executor.execute(
                query_input,
                runtime=runtime.context,
            )
        except QueryExecutionConfigurationError:
            return {
                "dispatch_result": FailureDispatchResult(
                    decision=decision,
                    error=AgentExecutionError(
                        code="QUERY_EXECUTION_NOT_CONFIGURED",
                        message="查询服务配置不完整, 无法执行本次请求。",
                        retryable=False,
                    ),
                ).model_dump(mode="json")
            }
        except QueryIdentityResolutionUnavailableError:
            return {
                "dispatch_result": FailureDispatchResult(
                    decision=decision,
                    error=AgentExecutionError(
                        code="QUERY_IDENTITY_UNAVAILABLE",
                        message="暂时没法确认客户信息，请稍后再试。",
                        retryable=True,
                    ),
                ).model_dump(mode="json")
            }
        except QuerySemanticResolutionUnavailableError:
            return {
                "dispatch_result": FailureDispatchResult(
                    decision=decision,
                    error=AgentExecutionError(
                        code="QUERY_SEMANTIC_INTENT_UNAVAILABLE",
                        message="查询条件暂时没解析出来，请稍后再试。",
                        retryable=True,
                    ),
                ).model_dump(mode="json")
            }
        except CRMQueryAgentExecutionError as exc:
            query_error = exc.error
            return {
                "dispatch_result": FailureDispatchResult(
                    decision=decision,
                    error=AgentExecutionError(
                        code=query_error.code,
                        message=_QUERY_ERROR_MESSAGES.get(
                            query_error.code, "查询服务暂时不可用，请稍后重试。"
                        ),
                        retryable=query_error.retryable,
                    ),
                ).model_dump(mode="json")
            }
        except Exception:
            logger.exception(
                "Root query execution failed",
                extra={"client_request_id": turn.client_request_id},
            )
            return {
                "dispatch_result": FailureDispatchResult(
                    decision=decision,
                    error=AgentExecutionError(
                        code="QUERY_EXECUTION_FAILED",
                        message="查询暂时没完成，请稍后再试。",
                        retryable=True,
                    ),
                ).model_dump(mode="json")
            }
        return {
            "dispatch_result": QueryDispatchResult(
                decision=decision,
                query_result=result,
            ).model_dump(mode="json")
        }

    @staticmethod
    def _finalize_workflow(state: RootOrchestratorState) -> RootOrchestratorState:
        try:
            workflow_result = workflow_result_adapter.validate_python(state["workflow_result"])
            resolved_action = (
                ResolvedAgentAction.model_validate(state["resolved_action"])
                if state.get("resolved_action") is not None
                else None
            )
            workflow_input = (
                WorkflowTurnInput.model_validate(state["workflow_input"])
                if state.get("workflow_input") is not None
                else None
            )
            resumed_workflow_ref = (
                WorkflowRef.model_validate(state["resumed_workflow_ref"])
                if state.get("resumed_workflow_ref") is not None
                else None
            )
        except (KeyError, ValidationError) as exc:
            raise WorkflowExecutionFailedError("Workflow subgraph returned an invalid result") from exc

        expected_workflow_id = (
            resolved_action.continuation.workflow_ref.workflow_id
            if resolved_action is not None and resolved_action.continuation is not None
            else workflow_input.workflow_id
            if workflow_input is not None and resumed_workflow_ref is None
            else resumed_workflow_ref.workflow_id
            if resumed_workflow_ref is not None
            else None
        )
        actual_workflow_ref = workflow_result.workflow_ref
        if (
            expected_workflow_id is None
            or actual_workflow_ref is None
            or actual_workflow_ref.workflow_id != expected_workflow_id
        ):
            raise WorkflowExecutionFailedError(
                "Workflow subgraph result does not match the requested execution identity"
            )
        return {
            "dispatch_result": WorkflowDispatchResult(
                decision=RootDecision.model_validate(state["decision"]),
                workflow_result=workflow_result,
                action_claim_id=(
                    resolved_action.action_id
                    if resolved_action is not None and resolved_action.claim_outcome == "ACQUIRED"
                    else None
                ),
            ).model_dump(mode="json")
        }

    @staticmethod
    def _server_workflow_trigger_decision(
        *,
        context: RootContextSnapshot,
        trigger: WorkflowTriggerTurnInput,
    ) -> RootDecision:
        action = trigger.action or "CANCEL"
        return RootDecision(
            task_relation="SWITCH_TASK" if context.active_workflow is not None else "NEW_TASK",
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow="SUSPEND" if context.active_workflow is not None else "NONE",
                conversation_memory="IGNORE",
            ),
            confidence=1.0,
            reason_code=(
                "CUSTOMER_OPPORTUNITY_SUGGESTION_TRIGGER"
                if trigger.workflow == "customer_opportunity_suggestion"
                else "SERVER_WORKFLOW_TRIGGER"
            ),
            evidence=[f"服务端触发独立工作流: {trigger.workflow}/{action}"],
            semantic_plan=AgentSemanticPlan(
                speech_act="CONFIRM_ACTION",
                business_object=(
                    "OPPORTUNITY"
                    if trigger.workflow == "customer_opportunity_suggestion"
                    else "FOLLOW_UP_TASK"
                ),
                operation=(
                    "CREATE"
                    if action == "CREATE_OPPORTUNITY"
                    else "TRANSITION"
                    if action == "MOVE_OPPORTUNITY_STAGE"
                    else "NONE"
                ),
                confidence=1.0,
            ),
        )


    @staticmethod
    def _interaction_workflow_decision(
        *,
        turn: RootTurnInput,
        reason_code: str,
    ) -> RootDecision:
        return RootDecision(
            task_relation="CONTINUE_TASK",
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity=("USE" if turn.selected_entity_ref is not None else "IGNORE"),
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow="RESUME",
                conversation_memory="IGNORE",
            ),
            confidence=1.0,
            reason_code=reason_code,
            evidence=["结构化交互已通过权威动作与工作流绑定校验"],
            semantic_plan=AgentSemanticPlan(
                speech_act="CONFIRM_ACTION",
                business_object="UNKNOWN",
                operation="UNKNOWN",
                confidence=1.0,
            ),
        )

    @staticmethod
    def _clarification_result(
        decision: RootDecision,
    ) -> ClarificationDispatchResult:
        return ClarificationDispatchResult(
            decision=decision,
            clarification=ClarificationRequest(
                question=(
                    decision.clarification_question
                    or RootOrchestrator._clarification_question_for_reason(decision.reason_code)
                ),
                reason_code=decision.reason_code,
            ),
        )

    @staticmethod
    def _clarification_question_for_reason(reason_code: str) -> str:
        """Return a narrow, user-facing fallback for server-side guardrails.

        Root is intentionally model-led for meaning. These messages are not
        an intent router; they are fail-safe UX for cases where a model claim
        cannot be executed because the required server-owned context is absent
        or ambiguous. Keeping them reason-specific prevents every safety
        boundary from collapsing into the old generic Workflow question.
        """

        return {
            "LOW_CONFIDENCE": "我还不能确定你想查询什么或执行什么操作，请补充客户、对象和你的具体目的。",
            "SELECTED_ENTITY_CONTEXT_MISSING": "请重新选择要操作的客户，或直接在消息中写明客户名称。",
            "PREVIOUS_QUERY_CONTEXT_MISSING": "我找不到上一条查询条件，请重新描述你要查询的内容。",
            "RESULT_SET_CONTEXT_MISSING": "我找不到上一轮查询结果，请重新说明要操作的客户或对象。",
            "RESULT_SET_REFERENCE_OUT_OF_RANGE": (
                "这个序号不在当前查询结果中，请选择结果里的有效序号，或直接说出客户名称。"
            ),
            "ACTIVE_WORKFLOW_CONTEXT_MISSING": "我找不到可继续的待处理任务，请直接说明你要查询或执行的事情。",
            "ACTIVE_WORKFLOW_RESUME_AMBIGUOUS": "当前有多个待处理任务，请说明要继续哪一个，或直接补充客户和操作。",
            "ACTIVE_WORKFLOW_RESUME_POLICY_INVALID": "请补充你要继续的具体任务内容，我不会替你猜测要恢复哪一步。",
            "ACTIVE_WORKFLOW_SWITCH_POLICY_INVALID": "请说明你要开始的新的查询或操作，以及对应的客户或对象。",
            "WORKFLOW_CONFIRMATION_REQUIRES_STRUCTURED_ACTION": (
                "这一步需要使用页面中的确认或选择按钮完成；如果要开始新操作，请直接描述你的需求。"
            ),
            "PENDING_CASE_ROUTE_MISMATCH": "请说明你是要查询这条待办的状态，还是要变更它的状态。",
            "PENDING_CASE_REFERENCE_AMBIGUOUS": "匹配到多条相似待办，请补充客户名称、待办标题或待办编号。",
            "PENDING_CASE_NOT_FOUND": "没有匹配到对应的历史待办，请补充客户名称、待办标题或待办编号。",
            "QUERY_REQUIRES_TEXT": "请用文字描述你要查询的内容。",
            "WORKFLOW_START_INVALID": "请重新描述你要执行的具体操作和对应客户。",
        }.get(reason_code, "请补充你要查询或执行的具体内容。")

    @staticmethod
    def _finalize_dispatch(state: RootOrchestratorState) -> RootOrchestratorState:
        """Validate the typed result at the Root Graph's single output node."""

        if state.get("dispatch_result") is None:
            raise WorkflowExecutionFailedError("Root Graph finalized without a dispatch result")
        try:
            result = root_dispatch_result_adapter.validate_python(state["dispatch_result"])
        except ValidationError as exc:
            raise WorkflowExecutionFailedError("Root Graph produced an invalid dispatch result") from exc
        return {"dispatch_result": result.model_dump(mode="json")}


    @staticmethod
    def _build_clarification(state: RootOrchestratorState) -> RootOrchestratorState:
        decision = RootDecision.model_validate(state["decision"])
        return {"dispatch_result": RootOrchestrator._clarification_result(decision).model_dump(mode="json")}

    def _validated_decision(
        self,
        decision: RootDecision,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
    ) -> RootDecision:
        decision = self._normalize_semantic_route(decision)
        decision = self._normalize_query_context_policy(decision, context=context)
        policy = decision.context_policy
        if decision.route == "CLARIFY":
            return decision
        invalid_reason: str | None = None
        if policy.selected_entity == "USE" and turn.selected_entity_ref is None:
            invalid_reason = "SELECTED_ENTITY_CONTEXT_MISSING"
        elif policy.previous_query == "USE" and context.previous_query is None:
            invalid_reason = "PREVIOUS_QUERY_CONTEXT_MISSING"
        elif policy.result_set == "USE" and context.result_set is None:
            invalid_reason = "RESULT_SET_CONTEXT_MISSING"
        elif context.active_workflow is None and policy.active_workflow != "NONE":
            invalid_reason = "ACTIVE_WORKFLOW_CONTEXT_MISSING"
        elif (
            isinstance(turn.input, TextTurnInput)
            and policy.active_workflow == "RESUME"
            and len(context.resumable_workflow_continuations) != 1
        ):
            invalid_reason = "ACTIVE_WORKFLOW_RESUME_AMBIGUOUS"
        elif context.active_workflow is not None:
            if policy.active_workflow == "RESUME":
                if decision.route != "WORKFLOW" or decision.task_relation != "CONTINUE_TASK":
                    invalid_reason = "ACTIVE_WORKFLOW_RESUME_POLICY_INVALID"
            elif policy.active_workflow == "SUSPEND":
                if decision.task_relation != "SWITCH_TASK":
                    invalid_reason = "ACTIVE_WORKFLOW_SWITCH_POLICY_INVALID"
            else:
                invalid_reason = "ACTIVE_WORKFLOW_SWITCH_POLICY_INVALID"
        if decision.confidence < 0.80:
            invalid_reason = "LOW_CONFIDENCE"
        if invalid_reason is None:
            return decision
        return self._clarification_decision(decision, invalid_reason)

    @staticmethod
    def _normalize_query_context_policy(
        decision: RootDecision,
        *,
        context: RootContextSnapshot,
    ) -> RootDecision:
        """Keep a confirmed read independent from stale Workflow context.

        The Root model decides meaning, but its context-policy fields are an
        execution hint rather than a second authority. Once the semantic plan
        has been projected to QUERY, a read cannot resume a write Workflow. A
        global-work query also has no customer/result/query carry-over by
        definition, so those context slots must be ignored even when the model
        accidentally retains them.

        This is a structural invariant over the typed decision and context; it
        does not inspect the user's words and does not affect Workflow routes.
        """

        if decision.route != "QUERY":
            return decision

        updates: dict[str, object] = {}
        if context.active_workflow is not None:
            updates.update(
                task_relation="SWITCH_TASK",
                context_policy=decision.context_policy.model_copy(
                    update={"active_workflow": "SUSPEND"}
                ),
            )
        elif decision.context_policy.active_workflow != "NONE":
            updates["context_policy"] = decision.context_policy.model_copy(
                update={"active_workflow": "NONE"}
            )

        query_plan = decision.semantic_plan.query_plan
        if query_plan is not None and query_plan.scope == "global_work":
            current_policy = updates.get("context_policy", decision.context_policy)
            updates["context_policy"] = current_policy.model_copy(
                update={
                    "selected_entity": "IGNORE",
                    "previous_query": "IGNORE",
                    "result_set": "IGNORE",
                }
            )

        if not updates:
            return decision
        return decision.model_copy(update=updates)


    @staticmethod
    def _normalize_semantic_route(
        decision: RootDecision,
        *,
        preserve_clarify: bool = True,
    ) -> RootDecision:
        """Project one model-produced semantic plan onto an authorized capability.

        The Root model owns language understanding.  This method is deliberately
        limited to a closed-world projection from the *structured* plan to the
        only capabilities this graph can dispatch; it never looks for words in
        the user message.  That keeps an activity assertion from falling into a
        read-only Query branch while avoiding a second classifier in the graph.

        A low-confidence semantic write must not be silently treated as a read.
        In that case the safe result is CLARIFY, because executing Query would be
        both semantically wrong and capable of hiding the user's requested write.
        """

        plan = decision.semantic_plan

        # A deliberate clarification remains terminal during later validation
        # passes (for example, after a continuation policy guard fires). During
        # the initial text decision pass, callers set ``preserve_clarify=False``
        # so a reliable structured activity assertion can recover a model that
        # emitted CLARIFY and would otherwise bypass the Workflow.
        if preserve_clarify and decision.route == "CLARIFY":
            return decision

        expected_route: str | None = None
        expected_risk: str | None = None
        reason_code: str | None = None

        is_read = semantic_plan_is_read(plan)
        is_write = semantic_plan_is_write(plan)
        supported_write = semantic_plan_supports_workflow_write(plan)
        if decision.route == "CLARIFY" and not (is_write and supported_write):
            return decision

        if is_read:
            expected_route = "QUERY"
            expected_risk = "READ_ONLY"
            reason_code = (
                "SEMANTIC_ACTIVITY_QUERY"
                if plan.business_object == "CUSTOMER_ACTIVITY"
                else "SEMANTIC_READ_ROUTE"
            )
        elif is_write:
            expected_route = "WORKFLOW"
            expected_risk = "WRITE"
            reason_code = (
                "SEMANTIC_ACTIVITY_WRITE"
                if plan.business_object == "CUSTOMER_ACTIVITY"
                else "SEMANTIC_WRITE_ROUTE"
            )

        # QUERY is executable only when the model explicitly produced a
        # sufficiently reliable read plan.  A reliable write plan is handled
        # by the projection below, even if the model's coarse route was QUERY;
        # otherwise the exact activity assertion bug we are guarding against
        # would still be allowed to enter Query.  Any plan that is neither a
        # reliable read nor a reliable write fails closed to clarification.
        if is_write and not supported_write:
            return RootOrchestrator._clarification_decision(
                decision,
                "SEMANTIC_WRITE_UNSUPPORTED",
                clarification_question=(
                    "当前 Agent 可以处理客户、客户资料（联系人、发票抬头、部署信息、客户成员）、"
                    "客户活动、商机及商机阶段推进；线索、回款、合同、License、发票申请等操作暂不支持。"
                ),
            )

        if decision.route == "QUERY" and not is_read and is_write and plan.confidence < 0.80:
            return RootOrchestrator._clarification_decision(
                decision,
                "SEMANTIC_ROUTE_AMBIGUOUS",
                clarification_question=(
                    "我理解到一个可能的业务操作，但还不能确定你是要查询已有信息，还是记录/执行这次操作，请补充你的具体目的。"
                ),
            )
        if decision.route == "QUERY" and not is_read and not is_write:
            return RootOrchestrator._clarification_decision(
                decision,
                "SEMANTIC_QUERY_PLAN_REQUIRED",
                clarification_question=(
                    "我还不能确定你是在查询已有信息，还是要记录/执行这次业务操作，请补充你的具体目的。"
                ),
            )

        if expected_route is None:
            return decision

        route_matches = decision.route == expected_route and decision.risk == expected_risk
        if route_matches:
            return decision

        # The server may only project a sufficiently reliable semantic claim.
        # For a weaker write claim, clarification is safer than allowing the
        # model's contradictory QUERY route to execute a read-only branch.
        if plan.confidence < 0.80:
            return RootOrchestrator._clarification_decision(
                decision,
                "SEMANTIC_ROUTE_AMBIGUOUS",
                clarification_question=(
                    "我理解到一个可能的业务操作，但还不能确定你是要查询已有信息，还是记录/执行这次操作，请补充你的具体目的。"
                ),
            )

        return decision.model_copy(
            update={
                "route": expected_route,
                "risk": expected_risk,
                "reason_code": reason_code,
                "context_policy": decision.context_policy.model_copy(
                    update=(
                        {"previous_query": "IGNORE", "result_set": "IGNORE"}
                        if expected_route == "WORKFLOW"
                        else {}
                    )
                ),
                "evidence": [
                    *decision.evidence,
                    "结构化语义计划与初始路由冲突，已按业务语义纠正能力路由",
                ][:20],
            }
        )

    @staticmethod
    def _clarification_decision(
        decision: RootDecision,
        reason_code: str,
        *,
        clarification_question: str | None = None,
    ) -> RootDecision:
        return RootDecision(
            task_relation=decision.task_relation,
            route="CLARIFY",
            risk=decision.risk,
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow=("SUSPEND" if decision.context_policy.active_workflow != "NONE" else "NONE"),
                conversation_memory="IGNORE",
            ),
            confidence=decision.confidence,
            reason_code=reason_code,
            evidence=decision.evidence,
            semantic_plan=decision.semantic_plan,
            clarification_question=(
                clarification_question
                if clarification_question is not None
                else RootOrchestrator._clarification_question_for_reason(reason_code)
            ),
            pending_case_relation=decision.pending_case_relation,
            pending_case_reference=decision.pending_case_reference,
        )


def _thread_id_or_none(config: object) -> str | None:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) and thread_id else None


def _checkpoint_id_or_none(config: object) -> str | None:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    checkpoint_id = configurable.get("checkpoint_id")
    return checkpoint_id if isinstance(checkpoint_id, str) and checkpoint_id else None


def _checkpoint_namespace_or_none(config: object) -> str | None:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    checkpoint_ns = configurable.get("checkpoint_ns")
    return checkpoint_ns if isinstance(checkpoint_ns, str) and checkpoint_ns else None


def _is_workflow_subgraph_namespace(namespace: object) -> bool:
    if not isinstance(namespace, tuple) or len(namespace) != 1:
        return False
    value = namespace[0]
    return isinstance(value, str) and value.split(":", maxsplit=1)[0] == "workflow_subgraph"
