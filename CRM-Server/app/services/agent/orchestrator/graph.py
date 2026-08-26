"""Thin deterministic Root Orchestrator graph."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Annotated, Callable, TypedDict, TypeVar
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
    RootRuntimeContext,
    RootTurnInput,
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
from app.services.agent.orchestrator.query_executor import QueryExecutionConfigurationError
from app.services.agent.orchestrator.result_set import (
    ResultSetReferenceError,
    resolve_result_set_entity,
)
from app.services.agent.orchestrator.risk import (
    has_context_dependent_reference,
    has_explicit_follow_up_record_intent,
    has_explicit_independent_read_intent,
    has_explicit_write_intent,
)
from app.services.agent.principal import AgentPrincipal
from app.services.agent.workflow import (
    WorkflowInterruptPayload,
    WorkflowProgress,
    WorkflowReplayResult,
    WorkflowResourceStart,
    WorkflowTextStart,
    WorkflowTurnInput,
    WorkflowWaitingResult,
    workflow_result_adapter,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


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


def build_root_graph_config(turn: RootTurnInput) -> RunnableConfig:
    """Return the canonical checkpoint identity for one Root turn."""

    return {
        "configurable": {"thread_id": f"crm_agent:{turn.team_id}:{turn.user_id}:{turn.session_id}"},
        "metadata": {
            "team_id": turn.team_id,
            "user_id": turn.user_id,
            "session_id": turn.session_id,
            "client_request_id": turn.client_request_id,
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
    resolved_action: Annotated[dict[str, object] | None, _replace_state_value]
    workflow_input: Annotated[dict[str, object] | None, _replace_state_value]
    workflow_result: Annotated[dict[str, object] | None, _replace_state_value]
    dispatch_result: Annotated[dict[str, object] | None, _replace_state_value]


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
    ) -> None:
        self._checkpointer = checkpointer
        self._context_resolver = context_resolver
        self._decision_classifier = decision_classifier
        self._query_executor = query_executor
        self._interaction_resolver = interaction_resolver
        self._workflow_subgraph = workflow_subgraph
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
            if isinstance(turn.input, InteractionTurnInput):
                return await self._dispatch_interaction(
                    turn=turn,
                    runtime=runtime,
                    config=config,
                    on_progress=on_progress,
                )

            state, continuation = await self._invoke_graph(
                self._new_turn_state(turn),
                config,
                runtime=runtime,
                on_progress=on_progress,
            )
            return self._dispatch_result_from_state(state, continuation=continuation)
        except RootContextUnavailableError:
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="ROOT_CONTEXT_UNAVAILABLE",
                    message="会话上下文服务暂时不可用, 请稍后重试。",
                    retryable=True,
                )
            )
        except InteractionResolutionUnavailableError:
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="INTERACTION_RESOLUTION_UNAVAILABLE",
                    message="当前操作暂时无法验证, 请刷新后重试。",
                    retryable=True,
                )
            )
        except WorkflowCheckpointUnavailableError:
            return self._workflow_failure("WORKFLOW_CHECKPOINT_UNAVAILABLE")
        except WorkflowExecutionFailedError:
            return self._workflow_failure("WORKFLOW_EXECUTION_FAILED")
        except RootDecisionModelUnavailableError:
            logger.exception("Root decision model is unavailable")
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="ROOT_DECISION_MODEL_UNAVAILABLE",
                    message="任务识别服务暂时不可用, 请稍后重试。",
                    retryable=True,
                )
            )
        except RootDecisionInvalidOutputError:
            return FailureDispatchResult(
                error=AgentExecutionError(
                    code="ROOT_DECISION_INVALID_OUTPUT",
                    message="任务识别结果无效, 请重新描述你的需求。",
                    retryable=False,
                )
            )

    async def _dispatch_interaction(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
        config: RunnableConfig,
        on_progress: Callable[[WorkflowProgress], None] | None,
    ) -> RootDispatchResult:
        context = await self._context_resolver.resolve(turn=turn, runtime=runtime)
        resolution = await self._interaction_resolver.resolve(
            turn=turn,
            context=context,
            runtime=runtime,
        )
        if resolution.status == "REJECTED":
            return self._interaction_failure(resolution.reason_code)
        resolved_action = resolution.resolved_action
        if resolved_action is None:
            raise InteractionResolutionUnavailableError("Resolved interaction is missing its canonical action")

        decision = self._interaction_workflow_decision(
            turn=turn,
            reason_code=resolution.reason_code,
        )
        if resolved_action.claim_outcome == "REPLAY":
            if resolved_action.replay_message_id is None:
                raise InteractionResolutionUnavailableError("Replayed action is missing its result message")
            return WorkflowDispatchResult(
                decision=decision,
                workflow_result=WorkflowReplayResult(
                    workflow_ref=resolved_action.workflow_ref,
                    message_id=resolved_action.replay_message_id,
                ),
            )

        context = context.model_copy(update={"active_workflow": resolved_action.workflow_ref})
        try:
            continuation_config = self._config_for_continuation(
                config,
                resolved_action.continuation,
            )
            await self._require_continuation_checkpoint(continuation_config)
            state, continuation = await self._invoke_graph(
                Command(
                    resume=resolved_action.resume_payload,
                    update=self._resettable_state(
                        turn=turn,
                        context_snapshot=context.model_copy(
                            update={"active_workflow": resolved_action.workflow_ref}
                        ),
                        decision=decision,
                        resolved_action=resolved_action,
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
                action_claim_id=resolved_action.action_id,
            )
        except WorkflowExecutionFailedError:
            return self._workflow_failure(
                "WORKFLOW_EXECUTION_FAILED",
                action_claim_id=resolved_action.action_id,
            )
        return result.model_copy(update={"action_claim_id": resolved_action.action_id})

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
            "resolved_action": (resolved_action.model_dump(mode="json") if resolved_action is not None else None),
            "workflow_input": None,
            "workflow_result": None,
            "dispatch_result": None,
        }

    @staticmethod
    def _config_for_continuation(
        config: RunnableConfig,
        continuation: WorkflowContinuation,
    ) -> RunnableConfig:
        configurable = dict(config.get("configurable", {}))
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
        return final_state, WorkflowContinuation(
            workflow_ref=self._workflow_ref_from_interrupts(interrupts),
            parent_checkpoint_id=parent_checkpoint_id,
            subgraph_checkpoint_ns=subgraph_checkpoint_ns,
            subgraph_checkpoint_id=subgraph_checkpoint_id,
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
        graph.add_node("decide", self._decide)
        graph.add_node("apply_context_policy", self._apply_context_policy)
        graph.add_node("query_agent", self._run_query)
        graph.add_node("workflow_subgraph", self._workflow_subgraph)
        graph.add_node("finalize_workflow", self._finalize_workflow)
        graph.add_node("build_clarification", self._build_clarification)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "decide")
        graph.add_edge("decide", "apply_context_policy")
        graph.add_conditional_edges(
            "apply_context_policy",
            self._route_after_context_policy,
            {
                "QUERY": "query_agent",
                "WORKFLOW": "workflow_subgraph",
                "CLARIFY": "build_clarification",
            },
        )
        graph.add_edge("query_agent", END)
        graph.add_edge("workflow_subgraph", "finalize_workflow")
        graph.add_edge("finalize_workflow", END)
        graph.add_edge("build_clarification", END)
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

    async def _decide(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        turn = RootTurnInput.model_validate(state["turn"])
        context = RootContextSnapshot.model_validate(state["context_snapshot"])
        has_active_workflow = context.active_workflow is not None
        if isinstance(turn.input, WorkflowTriggerTurnInput):
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
            )
        elif isinstance(turn.input, TextTurnInput) and has_explicit_follow_up_record_intent(
            turn.input.text
        ):
            decision = self._explicit_follow_up_workflow_decision(
                has_active_workflow=has_active_workflow,
                use_selected_entity=(
                    turn.selected_entity_ref is not None
                    and has_context_dependent_reference(turn.input.text)
                ),
            )
        elif (
            isinstance(turn.input, TextTurnInput)
            and has_explicit_independent_read_intent(turn.input.text)
            and not has_explicit_write_intent(turn.input.text)
        ):
            decision = self._explicit_read_decision(
                has_active_workflow=has_active_workflow,
            )
        else:
            decision = await self._decision_classifier.classify(
                turn=turn,
                context=context,
                runtime=runtime.context,
            )
        return {"decision": decision.model_dump(mode="json")}

    @staticmethod
    def _workflow_failure(
        code: str,
        *,
        action_claim_id: str | None = None,
    ) -> FailureDispatchResult:
        if code == "WORKFLOW_CHECKPOINT_UNAVAILABLE":
            error = AgentExecutionError(
                code=code,
                message="工作流状态服务暂时不可用, 请稍后重试。",
                retryable=True,
            )
        else:
            error = AgentExecutionError(
                code="WORKFLOW_EXECUTION_FAILED",
                message="工作流执行暂时失败, 请稍后重试。",
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

    def _apply_context_policy(
        self,
        state: RootOrchestratorState,
        runtime: Runtime[RootRuntimeContext],
    ) -> RootOrchestratorState:
        turn = RootTurnInput.model_validate(state["turn"])
        runtime_context = runtime.context
        context = RootContextSnapshot.model_validate(state["context_snapshot"])
        decision = self._validated_decision(
            RootDecision.model_validate(state["decision"]),
            turn=turn,
            context=context,
        )
        if decision.route == "CLARIFY":
            return {"decision": decision.model_dump(mode="json")}

        principal = AgentPrincipal(
            team_id=turn.team_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            permission_codes=sorted(runtime_context.permission_codes),
        )
        selected_entity = turn.selected_entity_ref if decision.context_policy.selected_entity == "USE" else None
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
                ).model_dump(mode="json"),
            }
        if isinstance(turn.input, TextTurnInput):
            workflow_start = WorkflowTextStart(kind="text", text=turn.input.text)
        elif isinstance(turn.input, WorkflowTriggerTurnInput):
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
            "workflow_input": WorkflowTurnInput(
                workflow_id=_workflow_id_for_turn(turn),
                start=workflow_start,
                principal=principal,
                selected_entity=selected_entity,
            ).model_dump(mode="json"),
        }

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
                        message="查询服务暂时不可用, 请稍后重试。",
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
                if resolved_action is None
                else None
            )
        except (KeyError, ValidationError) as exc:
            raise WorkflowExecutionFailedError("Workflow subgraph returned an invalid result") from exc

        expected_workflow_id = (
            resolved_action.workflow_ref.workflow_id
            if resolved_action is not None
            else workflow_input.workflow_id
        )
        actual_workflow_ref = workflow_result.workflow_ref
        if actual_workflow_ref is None or actual_workflow_ref.workflow_id != expected_workflow_id:
            raise WorkflowExecutionFailedError(
                "Workflow subgraph result does not match the requested execution identity"
            )
        return {
            "dispatch_result": WorkflowDispatchResult(
                decision=RootDecision.model_validate(state["decision"]),
                workflow_result=workflow_result,
            ).model_dump(mode="json")
        }

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
            ),
            confidence=1.0,
            reason_code=reason_code,
            evidence=["结构化交互已通过权威动作与工作流绑定校验"],
        )

    @staticmethod
    def _clarification_result(
        decision: RootDecision,
    ) -> ClarificationDispatchResult:
        return ClarificationDispatchResult(
            decision=decision,
            clarification=ClarificationRequest(
                question="请明确你想继续当前任务, 还是开始一个新的查询或操作。",
                reason_code=decision.reason_code,
            ),
        )

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
        policy = decision.context_policy
        if decision.route == "CLARIFY":
            return decision
        invalid_reason: str | None = None
        if (
            isinstance(turn.input, TextTurnInput)
            and decision.route == "QUERY"
            and has_explicit_write_intent(turn.input.text)
        ):
            invalid_reason = "WRITE_INTENT_ROUTE_MISMATCH"
        elif policy.selected_entity == "USE" and turn.selected_entity_ref is None:
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
            and len(context.resumable_workflows) != 1
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
    def _explicit_follow_up_workflow_decision(
        *,
        has_active_workflow: bool,
        use_selected_entity: bool,
    ) -> RootDecision:
        evidence = ["用户文本包含已完成的客户沟通及业务进展或后续跟进计划"]
        return RootDecision(
            task_relation=("SWITCH_TASK" if has_active_workflow else "NEW_TASK"),
            route="WORKFLOW",
            risk="WRITE",
            context_policy=ContextPolicy(
                selected_entity=("USE" if use_selected_entity else "IGNORE"),
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow=("SUSPEND" if has_active_workflow else "NONE"),
            ),
            confidence=1.0,
            reason_code="EXPLICIT_FOLLOW_UP_WORKFLOW",
            evidence=evidence[-20:],
        )

    @staticmethod
    def _explicit_read_decision(
        *,
        has_active_workflow: bool,
    ) -> RootDecision:
        evidence = ["用户文本包含明确且独立的只读查询请求"]
        return RootDecision(
            task_relation=("SWITCH_TASK" if has_active_workflow else "NEW_TASK"),
            route="QUERY",
            risk="READ_ONLY",
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow=("SUSPEND" if has_active_workflow else "NONE"),
            ),
            confidence=1.0,
            reason_code="EXPLICIT_INDEPENDENT_READ_QUERY",
            evidence=evidence[-20:],
        )

    @staticmethod
    def _clarification_decision(decision: RootDecision, reason_code: str) -> RootDecision:
        return RootDecision(
            task_relation=decision.task_relation,
            route="CLARIFY",
            risk=decision.risk,
            context_policy=ContextPolicy(
                selected_entity="IGNORE",
                previous_query="IGNORE",
                result_set="IGNORE",
                active_workflow=("SUSPEND" if decision.context_policy.active_workflow != "NONE" else "NONE"),
            ),
            confidence=decision.confidence,
            reason_code=reason_code,
            evidence=decision.evidence,
        )


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
