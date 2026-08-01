"""Reusable LangGraph subgraph for precise CRM business-resource resolution."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.checkpointer import (
    agent_checkpoint_saver,
    is_checkpoint_storage_error,
    with_checkpoint_unavailable_fallback_event,
)
from app.services.agent.state import (
    ResourceResolutionGraphInput,
    ResourceResolutionGraphResult,
    ResourceResolutionGraphState,
    ResourceResolutionRuntimeContext,
)
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict, coerce_json_value


RESOURCE_RESOLUTION_CHECKPOINT_NS = "crm_agent_resource_resolution"
AUTO_SELECT_CONFIDENCE = 0.82
AUTO_SELECT_MARGIN = 0.15


def build_resource_resolution_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    resource_kind: str,
    action_name: str,
) -> str:
    return f"crm_agent_resource_resolution:{team_id}:{user_id}:{session_id}:{resource_kind}:{action_name}"


def build_resource_resolution_graph_config(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    resource_kind: str,
    action_name: str,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": build_resource_resolution_thread_id(
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                resource_kind=resource_kind,
                action_name=action_name,
            ),
        },
        "metadata": {
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "runtime": "crm_agent_resource_resolution",
            "runtime_namespace": RESOURCE_RESOLUTION_CHECKPOINT_NS,
            "resource_kind": resource_kind,
            "action_name": action_name,
        },
    }


class ResourceResolutionGraphService:
    """Ranks candidate CRM resources and decides auto-selection versus HITL choice."""

    def __init__(self, *, checkpointer: object | None = None) -> None:
        self._checkpoint_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)
        self._fallback_graph = self._build_graph(None)

    def _build_graph(self, checkpointer: object | None):
        graph = StateGraph(
            ResourceResolutionGraphState,
            context_schema=ResourceResolutionRuntimeContext,
        )
        graph.add_node("rank_candidates", self._rank_candidates)
        graph.add_node("apply_resolution_policy", self._apply_resolution_policy)
        graph.add_node("finalize_resolution", self._finalize_resolution)
        graph.add_edge(START, "rank_candidates")
        graph.add_edge("rank_candidates", "apply_resolution_policy")
        graph.add_edge("apply_resolution_policy", "finalize_resolution")
        graph.add_edge("finalize_resolution", END)
        if checkpointer is None:
            return graph.compile()
        return graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        input_state: ResourceResolutionGraphInput,
        *,
        ranker=None,
    ) -> ResourceResolutionGraphResult:
        checkpoint_state = _checkpoint_state_from_input(input_state)
        context = ResourceResolutionRuntimeContext(
            team_id=int(input_state.get("team_id") or 0),
            user_id=int(input_state.get("user_id") or 0),
            session_id=int(input_state.get("session_id") or 0),
            ranker=ranker,
        )
        config = build_resource_resolution_graph_config(
            team_id=context.team_id,
            user_id=context.user_id,
            session_id=context.session_id,
            resource_kind=str(input_state.get("resource_kind") or "unknown"),
            action_name=str(input_state.get("action_name") or "unknown"),
        )
        try:
            return await self._graph.ainvoke(checkpoint_state, config, context=context)
        except SQLAlchemyError as exc:
            if not self._checkpoint_enabled or not is_checkpoint_storage_error(exc):
                raise
            result = await self._fallback_graph.ainvoke(checkpoint_state, config, context=context)
            return with_checkpoint_unavailable_fallback_event(
                result,
                runtime="crm_agent_resource_resolution",
                graph=RESOURCE_RESOLUTION_CHECKPOINT_NS,
            )

    async def _rank_candidates(
        self,
        state: ResourceResolutionGraphState,
        runtime: Runtime[ResourceResolutionRuntimeContext],
    ) -> ResourceResolutionGraphState:
        candidates = _candidate_list(state.get("candidates"))
        if not candidates:
            return {"ranked_candidates": [], "events": [_event(state, "no_candidate")]}
        if len(candidates) == 1:
            ranked = [{**candidates[0], "confidence": 1.0, "evidence": ["只有一个可执行候选资源"], "risk_notes": []}]
            return {"ranked_candidates": ranked, "events": [_event(state, "single_candidate")]}
        if runtime.context.ranker:
            rankings = await runtime.context.ranker(state)
            if rankings:
                ranked = _merge_rankings(candidates, rankings)
                return {"ranked_candidates": ranked, "events": [_event(state, "ranked_by_model")]}
        return {
            "ranked_candidates": _heuristic_rank_candidates(
                content=str(state.get("content") or ""),
                target=coerce_json_dict(state.get("target")),
                candidates=candidates,
            ),
            "events": [_event(state, "ranked_by_guardrail")],
        }

    def _apply_resolution_policy(
        self,
        state: ResourceResolutionGraphState,
    ) -> ResourceResolutionGraphState:
        ranked = _candidate_list(state.get("ranked_candidates"))
        if not ranked:
            return {"resolution_status": "no_candidate", "resolution_reason": "没有可执行候选资源"}
        top = ranked[0]
        if len(ranked) == 1:
            return {
                "selected_candidate": top,
                "resolution_status": "selected",
                "resolution_reason": "唯一候选资源",
            }
        top_confidence = _float_value(top.get("confidence"))
        second_confidence = _float_value(ranked[1].get("confidence"))
        if top_confidence >= AUTO_SELECT_CONFIDENCE and top_confidence - second_confidence >= AUTO_SELECT_MARGIN:
            return {
                "selected_candidate": top,
                "resolution_status": "selected",
                "resolution_reason": "候选资源匹配度明显高于其他资源",
            }
        return {
            "resolution_status": "needs_user_choice",
            "resolution_reason": "多个候选资源匹配度接近，需要用户选择",
        }

    def _finalize_resolution(
        self,
        state: ResourceResolutionGraphState,
    ) -> ResourceResolutionGraphState:
        selected = coerce_json_dict(state.get("selected_candidate"))
        event = _event(
            state,
            str(state.get("resolution_status") or "unknown"),
            selected_resource_id=selected.get("id"),
            reason=state.get("resolution_reason"),
        )
        return {"events": [event]}


def _checkpoint_state_from_input(input_state: ResourceResolutionGraphInput) -> ResourceResolutionGraphState:
    return {
        "team_id": int(input_state.get("team_id") or 0),
        "user_id": int(input_state.get("user_id") or 0),
        "session_id": int(input_state.get("session_id") or 0),
        "resource_kind": str(input_state.get("resource_kind") or "unknown"),
        "action_name": str(input_state.get("action_name") or "unknown"),
        "content": str(input_state.get("content") or ""),
        "target": coerce_json_dict(input_state.get("target")),
        "candidates": _candidate_list(input_state.get("candidates")),
        "events": [],
    }


def _candidate_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, dict)]


def _merge_rankings(candidates: list[JSONDict], rankings: list[JSONDict]) -> list[JSONDict]:
    candidate_by_id: dict[int, JSONDict] = {}
    for candidate in candidates:
        candidate_id = _int_value(candidate.get("id"))
        if candidate_id is not None:
            candidate_by_id[candidate_id] = candidate
    merged: list[JSONDict] = []
    used_ids: set[int] = set()
    for ranking in rankings:
        resource_id = _int_value(ranking.get("resource_id"))
        if resource_id is None or resource_id not in candidate_by_id or resource_id in used_ids:
            continue
        candidate = dict(candidate_by_id[resource_id])
        candidate["confidence"] = _float_value(ranking.get("confidence"))
        candidate["evidence"] = _string_list(ranking.get("evidence"))
        candidate["risk_notes"] = _string_list(ranking.get("risk_notes"))
        merged.append(candidate)
        used_ids.add(resource_id)
    for candidate in candidates:
        resource_id = _int_value(candidate.get("id"))
        if resource_id is None or resource_id in used_ids:
            continue
        fallback = dict(candidate)
        fallback["confidence"] = 0.0
        fallback["evidence"] = []
        fallback["risk_notes"] = ["模型未返回该候选资源评分"]
        merged.append(fallback)
    return sorted(merged, key=lambda item: _float_value(item.get("confidence")), reverse=True)


def _heuristic_rank_candidates(*, content: str, target: JSONDict, candidates: list[JSONDict]) -> list[JSONDict]:
    normalized_content = _normalize(content)
    target_name = str(target.get("target_name") or target.get("target_stage_name") or "")
    ranked: list[JSONDict] = []
    for candidate in candidates:
        score = 0.5
        evidence: list[str] = []
        risk_notes: list[str] = []
        for name in _candidate_names(candidate):
            normalized_name = _normalize(name)
            if normalized_name and normalized_name in normalized_content:
                score += 0.42
                evidence.append(f"用户输入明确提到「{name}」")
                break
        if target_name and _normalize(target_name) in normalized_content:
            score += 0.06
            evidence.append(f"用户输入提到目标阶段「{target_name}」")
        step_count = _step_count(candidate)
        if step_count == 1:
            score += 0.03
            evidence.append("该资源距离目标阶段最近")
        elif step_count > 1:
            risk_notes.append("需要连续推进多个阶段")
        ranked_candidate = dict(candidate)
        ranked_candidate["confidence"] = min(score, 1.0)
        ranked_candidate["evidence"] = evidence
        ranked_candidate["risk_notes"] = risk_notes
        ranked.append(ranked_candidate)
    return sorted(ranked, key=lambda item: _float_value(item.get("confidence")), reverse=True)


def _candidate_names(candidate: JSONDict) -> list[str]:
    fields = ["name", "opportunity_name", "contract_name", "payment_plan_name", "deployment_name", "display_name"]
    names: list[str] = []
    for field in fields:
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    return list(dict.fromkeys(names))


def _step_count(candidate: JSONDict) -> int:
    steps = candidate.get("stage_move_steps")
    return len(steps) if isinstance(steps, list) else 0


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def _string_list(value: object) -> list[JSONValue]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _int_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _float_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _event(state: ResourceResolutionGraphState, status: str, **extra: object) -> JSONDict:
    event: JSONDict = {
        "event": "resource_resolution",
        "resource_kind": str(state.get("resource_kind") or "unknown"),
        "action_name": str(state.get("action_name") or "unknown"),
        "status": status,
    }
    for key, value in extra.items():
        event[key] = coerce_json_value(value)
    return event


resource_resolution_graph_service = ResourceResolutionGraphService(checkpointer=agent_checkpoint_saver)
