"""Durable follow-up confirmation delivery orchestration.

LangGraph stores only checkpoint-safe lifecycle state and routing decisions.
Database mutations are delegated to the application projection and channel I/O
is executed by the runtime adapter outside graph nodes.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.customer_activity_ai.checkpointer import customer_activity_checkpoint_saver
from app.services.follow_up_confirmation_delivery_contracts import (
    ConfirmationDeliveryAdapter,
    ConfirmationDeliveryInput,
    ConfirmationDispatchResult,
)
from app.services.follow_up_confirmation_delivery_projection import (
    FollowUpConfirmationDeliveryProjection,
)

ConfirmationDeliveryAction = Literal["ENSURE_QUEUE", "CLAIM", "DISPATCH", "ACKNOWLEDGE", "FINISH"]


class ConfirmationDeliveryState(TypedDict, total=False):
    request: dict[str, Any]
    phase: str
    next_action: ConfirmationDeliveryAction
    delivery_public_id: str
    prompt: dict[str, Any]
    status: str
    execution_status: str
    lease_token: str
    reason_code: str | None
    error_message: str | None
    provider_message_id: str | None
    events: list[dict[str, Any]]


class _CompiledDeliveryGraph(Protocol):
    async def ainvoke(self, state: ConfirmationDeliveryState, config: dict[str, Any]) -> ConfirmationDeliveryState: ...


class ConfirmationCenterDeliveryAdapter:
    """Acknowledges the durable confirmation center as the visible channel."""

    async def dispatch(
        self,
        request: ConfirmationDeliveryInput,
        *,
        prompt: dict[str, object],
    ) -> ConfirmationDispatchResult:
        del prompt
        return ConfirmationDispatchResult.sent(provider_message_id=f"inbox:{request.case_public_id}")


class FollowUpConfirmationDeliveryWorkflow:
    """Orchestrate graph decisions, durable projection and channel runtime.

    The public ``run`` seam is replay-safe.  Graph nodes never open a database
    session and never invoke a transport adapter.
    """

    _MAX_LIFECYCLE_STEPS = 8

    def __init__(
        self,
        *,
        adapters: dict[str, ConfirmationDeliveryAdapter] | None = None,
        projection: FollowUpConfirmationDeliveryProjection | None = None,
        checkpointer: object | None = customer_activity_checkpoint_saver,
    ) -> None:
        self.adapters = adapters if adapters is not None else {"web": ConfirmationCenterDeliveryAdapter()}
        self.projection = projection or FollowUpConfirmationDeliveryProjection()
        self._graph = self._build_graph(checkpointer)

    @staticmethod
    def _build_graph(checkpointer: object | None) -> _CompiledDeliveryGraph:
        graph = StateGraph(ConfirmationDeliveryState)
        graph.add_node("decide_next_action", FollowUpConfirmationDeliveryWorkflow._decide_next_action)
        graph.add_edge(START, "decide_next_action")
        graph.add_edge("decide_next_action", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(self, request: ConfirmationDeliveryInput) -> ConfirmationDeliveryState:
        thread_id = self.thread_id(request)
        config = {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": "confirmation_delivery"},
            "metadata": {
                "case_public_id": request.case_public_id,
                "team_id": request.team_id,
                "owner_id": request.owner_id,
                "channel": request.channel,
                "purpose": request.purpose,
            },
        }
        state: ConfirmationDeliveryState = {
            "request": request.model_dump(mode="json"),
            "phase": "START",
            "events": [],
        }
        for _ in range(self._MAX_LIFECYCLE_STEPS):
            state = await self._graph.ainvoke(state, config)
            action = state.get("next_action")
            if action == "FINISH":
                return state
            state = await self._execute_application_action(request, state, action)
        return self._merge_state(
            state,
            {
                "phase": "TERMINAL",
                "status": state.get("status") or "FAILED",
                "execution_status": "LIFECYCLE_LIMIT_EXCEEDED",
                "reason_code": "DELIVERY_LIFECYCLE_LIMIT_EXCEEDED",
            },
            event={"event": "confirmation_delivery_lifecycle_limit_exceeded"},
        )

    async def _execute_application_action(
        self,
        request: ConfirmationDeliveryInput,
        state: ConfirmationDeliveryState,
        action: ConfirmationDeliveryAction | None,
    ) -> ConfirmationDeliveryState:
        if action == "ENSURE_QUEUE":
            result = self.projection.ensure_and_validate(
                request,
                prompt_key=self.prompt_key(request),
                thread_id=self.thread_id(request),
            )
            return self._merge_state(
                state,
                result.as_state_update(),
                event={"event": "confirmation_delivery_projected", "phase": result.phase, "status": result.status},
            )

        if action == "CLAIM":
            delivery_public_id = state.get("delivery_public_id")
            if not delivery_public_id:
                return self._invalid_state(state, "DELIVERY_ID_MISSING")
            result = self.projection.claim(request, delivery_public_id=delivery_public_id)
            return self._merge_state(
                state,
                result.as_state_update(),
                event={"event": "confirmation_delivery_claimed", "execution_status": result.execution_status},
            )

        if action == "DISPATCH":
            delivery_public_id = state.get("delivery_public_id")
            if not delivery_public_id:
                return self._invalid_state(state, "DELIVERY_ID_MISSING")
            dispatch_request = request.model_copy(
                update={
                    "delivery_public_id": delivery_public_id,
                    "idempotency_key": f"follow-up-confirmation:{delivery_public_id}",
                }
            )
            adapter = self.adapters.get(request.channel)
            if adapter is None:
                dispatch_result = ConfirmationDispatchResult.skipped("CHANNEL_ADAPTER_MISSING")
            else:
                try:
                    dispatch_result = await adapter.dispatch(
                        dispatch_request,
                        prompt=dict(state.get("prompt") or {}),
                    )
                except Exception as exc:  # Channel failures are persisted by the acknowledgement projection.
                    dispatch_result = ConfirmationDispatchResult.failed("CHANNEL_EXCEPTION", str(exc))
            return self._merge_state(
                state,
                {
                    "phase": "DISPATCHED",
                    "status": dispatch_result.status,
                    "execution_status": "DISPATCHED",
                    "provider_message_id": dispatch_result.provider_message_id,
                    "reason_code": dispatch_result.reason_code,
                    "error_message": dispatch_result.error_message,
                },
                event={"event": "confirmation_delivery_dispatched", "status": dispatch_result.status},
            )

        if action == "ACKNOWLEDGE":
            delivery_public_id = state.get("delivery_public_id")
            lease_token = state.get("lease_token")
            if not delivery_public_id:
                return self._invalid_state(state, "DELIVERY_ID_MISSING")
            if not lease_token:
                return self._invalid_state(state, "DISPATCH_LEASE_MISSING")
            result = self.projection.acknowledge(
                request,
                delivery_public_id=delivery_public_id,
                lease_token=lease_token,
                dispatch_status=state.get("status") or "FAILED",
                provider_message_id=state.get("provider_message_id"),
                reason_code=state.get("reason_code"),
                error_message=state.get("error_message"),
            )
            return self._merge_state(
                state,
                result.as_state_update(),
                event={
                    "event": "confirmation_delivery_acknowledged",
                    "execution_status": result.execution_status,
                    "status": result.status,
                },
            )

        return self._invalid_state(state, "UNKNOWN_DELIVERY_ACTION")

    @staticmethod
    def _decide_next_action(state: ConfirmationDeliveryState) -> ConfirmationDeliveryState:
        phase = state.get("phase") or "START"
        if phase == "START":
            action: ConfirmationDeliveryAction = "ENSURE_QUEUE"
        elif phase == "ENSURED":
            action = "CLAIM"
        elif phase == "CLAIMED":
            action = "DISPATCH"
        elif phase == "DISPATCHED":
            action = "ACKNOWLEDGE"
        else:
            action = "FINISH"
        return {
            "next_action": action,
            "events": [
                *(state.get("events") or []),
                {"event": "confirmation_delivery_action_decided", "phase": phase, "action": action},
            ],
        }

    @staticmethod
    def _merge_state(
        state: ConfirmationDeliveryState,
        update: dict[str, Any],
        *,
        event: dict[str, Any],
    ) -> ConfirmationDeliveryState:
        merged: ConfirmationDeliveryState = {**state, **update}
        merged["events"] = [*(state.get("events") or []), event]
        return merged

    @staticmethod
    def _invalid_state(state: ConfirmationDeliveryState, reason_code: str) -> ConfirmationDeliveryState:
        return FollowUpConfirmationDeliveryWorkflow._merge_state(
            state,
            {
                "phase": "TERMINAL",
                "status": state.get("status") or "FAILED",
                "execution_status": "INVALID_STATE",
                "reason_code": reason_code,
            },
            event={"event": "confirmation_delivery_invalid_state", "reason_code": reason_code},
        )

    @staticmethod
    def thread_id(request: ConfirmationDeliveryInput) -> str:
        # Recovery requests add ``delivery_public_id`` after the initial run.
        # Thread identity must remain derived from the immutable delivery
        # contract so LangGraph resumes the same durable execution history.
        return f"confirmation_delivery:{FollowUpConfirmationDeliveryWorkflow.prompt_key(request)}"

    @staticmethod
    def prompt_key(request: ConfirmationDeliveryInput) -> str:
        raw = ":".join(
            [
                request.case_public_id,
                str(request.team_id),
                request.owner_id,
                request.channel,
                request.purpose,
                request.provider or "",
                request.recipient_id or "",
                str(request.agent_session_id or ""),
                request.origin_turn_id or "",
                str(request.origin_message_id or ""),
                str(request.source_activity_id or ""),
                str(request.expected_activity_revision or ""),
            ]
        )
        return f"delivery:{hashlib.sha256(raw.encode()).hexdigest()}"


follow_up_confirmation_delivery_workflow = FollowUpConfirmationDeliveryWorkflow()

__all__ = [
    "ConfirmationDeliveryAdapter",
    "ConfirmationDeliveryInput",
    "ConfirmationDispatchResult",
    "FollowUpConfirmationDeliveryWorkflow",
    "follow_up_confirmation_delivery_workflow",
]
