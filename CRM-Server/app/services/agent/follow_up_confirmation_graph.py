"""Domain subgraph for projecting and resolving follow-up confirmation cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime  # noqa: TC002 -- LangGraph resolves node hints at runtime.

from app.services.agent.state import merge_turn_scoped_events
from app.services.agent.types import (
    JSONDict,
    JSONValue,  # noqa: F401 -- JSONDict forward refs are resolved by LangGraph at runtime.
    coerce_json_dict,
)
from app.services.follow_up_task_confirmation_channel_service import (
    FollowUpTaskConfirmationChannelService,
    follow_up_task_confirmation_channel_service,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

FollowUpConfirmationGraphMode = Literal["prepare", "resolve"]


class FollowUpConfirmationGraphState(TypedDict, total=False):
    mode: FollowUpConfirmationGraphMode
    case_public_ids: list[str]
    interaction_scope: str
    prompt_override: str
    reason_code: str
    case_public_id: str
    reply_text: str
    prompt_event: JSONDict
    resolution_event: JSONDict
    events: Annotated[list[JSONDict], merge_turn_scoped_events]


@dataclass
class FollowUpConfirmationRuntimeContext:
    db: object | None = None
    team_id: int = 0
    user_id: int = 0


class FollowUpConfirmationGraphService:
    """Owns follow-up confirmation domain reads and writes behind one graph seam."""

    def __init__(
        self,
        *,
        channel_service: FollowUpTaskConfirmationChannelService = follow_up_task_confirmation_channel_service,
    ) -> None:
        self.channel_service = channel_service
        self._graph = self._build_graph()

    def _build_graph(self) -> CompiledStateGraph:
        graph = StateGraph(FollowUpConfirmationGraphState, context_schema=FollowUpConfirmationRuntimeContext)
        graph.add_node("prepare_prompt", self._prepare_prompt)
        graph.add_node("resolve_reply", self._resolve_reply)
        graph.add_conditional_edges(
            START,
            self._route_mode,
            {
                "prepare": "prepare_prompt",
                "resolve": "resolve_reply",
            },
        )
        graph.add_edge("prepare_prompt", END)
        graph.add_edge("resolve_reply", END)
        return graph.compile()

    async def prepare(
        self,
        *,
        db: object,
        team_id: int,
        user_id: int,
        case_public_ids: list[str],
        interaction_scope: str,
        include_owner_inbox_fallback: bool = True,
        prompt_override: str | None = None,
        reason_code: str = "ROOT_GRAPH_INTERRUPT_PLANNED",
    ) -> JSONDict:
        result = await self._graph.ainvoke(
            {
                "mode": "prepare",
                "case_public_ids": case_public_ids,
                "interaction_scope": interaction_scope,
                "prompt_override": prompt_override or "",
                "reason_code": reason_code,
                "prompt_event": {},
                "events": [],
            },
            context=FollowUpConfirmationRuntimeContext(db=db, team_id=team_id, user_id=user_id),
        )
        prompt_event = coerce_json_dict(result.get("prompt_event"))
        if prompt_event or not include_owner_inbox_fallback:
            return prompt_event
        pending = self.channel_service.list_pending_cases(
            db,
            team_id=team_id,
            user_id=user_id,
            limit=1,
        )
        pending_ids = [
            str(item.get("public_id"))
            for item in pending.get("items", [])
            if isinstance(item, dict) and item.get("public_id")
        ]
        if not pending_ids:
            return {}
        fallback_result = await self._graph.ainvoke(
            {
                "mode": "prepare",
                "case_public_ids": pending_ids,
                "interaction_scope": interaction_scope,
                "prompt_override": prompt_override or "",
                "reason_code": reason_code,
                "prompt_event": {},
                "events": [],
            },
            context=FollowUpConfirmationRuntimeContext(db=db, team_id=team_id, user_id=user_id),
        )
        return coerce_json_dict(fallback_result.get("prompt_event"))

    async def resolve(
        self,
        *,
        db: object,
        team_id: int,
        user_id: int,
        case_public_id: str,
        reply_text: str,
    ) -> JSONDict:
        result = await self._graph.ainvoke(
            {
                "mode": "resolve",
                "case_public_id": case_public_id,
                "reply_text": reply_text,
                "resolution_event": {},
                "events": [],
            },
            context=FollowUpConfirmationRuntimeContext(db=db, team_id=team_id, user_id=user_id),
        )
        return coerce_json_dict(result.get("resolution_event"))

    def mark_projected(self, db: object, *, team_id: int, prompt_key: str) -> object | None:
        return self.channel_service.mark_projection_projected(
            db,
            team_id=team_id,
            prompt_key=prompt_key,
        )

    def mark_projection_failed(
        self,
        db: object,
        *,
        team_id: int,
        prompt_key: str,
        error_message: str,
    ) -> object | None:
        return self.channel_service.mark_projection_failed(
            db,
            team_id=team_id,
            prompt_key=prompt_key,
            error_message=error_message,
        )

    def _route_mode(self, state: FollowUpConfirmationGraphState) -> FollowUpConfirmationGraphMode:
        return "resolve" if state.get("mode") == "resolve" else "prepare"

    def _prepare_prompt(
        self,
        state: FollowUpConfirmationGraphState,
        runtime: Runtime[FollowUpConfirmationRuntimeContext],
    ) -> FollowUpConfirmationGraphState:
        context = runtime.context
        if context.db is None:
            return {"prompt_event": {}}
        kwargs = {
            "team_id": context.team_id,
            "user_id": context.user_id,
            "case_public_ids": list(state.get("case_public_ids") or []),
            "interaction_scope": str(state.get("interaction_scope") or ""),
        }
        prompt_override = str(state.get("prompt_override") or "")
        reason_code = str(state.get("reason_code") or "")
        if prompt_override:
            kwargs["prompt_override"] = prompt_override
        if reason_code and reason_code != "ROOT_GRAPH_INTERRUPT_PLANNED":
            kwargs["reason_code"] = reason_code
        event = self.channel_service.prepare_case_prompt_by_public_ids(context.db, **kwargs)
        return {
            "prompt_event": coerce_json_dict(event),
            "events": [{
                "event": "follow_up_confirmation_graph_prompt_planned",
                "has_prompt": bool(event),
            }],
        }

    def _resolve_reply(
        self,
        state: FollowUpConfirmationGraphState,
        runtime: Runtime[FollowUpConfirmationRuntimeContext],
    ) -> FollowUpConfirmationGraphState:
        context = runtime.context
        if context.db is None:
            return {"resolution_event": {}}
        event = self.channel_service.resolve_reply_event(
            context.db,
            team_id=context.team_id,
            user_id=context.user_id,
            case_public_id=str(state.get("case_public_id") or ""),
            reply_text=str(state.get("reply_text") or ""),
        )
        return {
            "resolution_event": coerce_json_dict(event),
            "events": [{
                "event": "follow_up_confirmation_graph_reply_resolved",
                "case_public_id": state.get("case_public_id"),
            }],
        }


follow_up_confirmation_graph_service = FollowUpConfirmationGraphService()
