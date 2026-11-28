"""Production assembly for the single CRM Root Orchestrator runtime."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from app.core.config import get_settings
from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.agent.orchestrator.context import DatabaseRootContextResolver
from app.services.agent.orchestrator.contracts import (
    RootContextSnapshot,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
)
from app.services.agent.orchestrator.decision import LangChainRootDecisionClassifier
from app.services.agent.orchestrator.graph import RootOrchestrator
from app.services.agent.orchestrator.interaction import DatabaseInteractionResolver
from app.services.agent.orchestrator.query_executor import CRMQueryAgentExecutor
from app.services.agent.query import (
    CRMQueryAgent,
    CRMReadToolRegistry,
    DefaultCRMQueryExecutor,
    DefaultCustomerContextReader,
)
from app.services.agent.query.executor import FollowUpTaskDetailAPIAdapter
from app.services.agent.query.semantic_intent import LLMQuerySemanticIntentResolver
from app.services.agent.semantic import agent_semantic_parser
from app.services.agent.semantic_plan import AgentSemanticPlan, semantic_plan_from_result
from app.services.agent.tools.api_client import InternalCRMAPIClient
from app.services.agent.workflow.execution import CRMWorkflowEffectExecutor
from app.services.agent.workflow.graph import build_workflow_subgraph
from app.services.agent.workflow.planning import CRMWorkflowPlanner

if TYPE_CHECKING:
    from app.services.agent.semantic import AgentSemanticParseEnvelope


class RootSemanticParser(Protocol):
    async def parse_with_metadata(
        self,
        db: object,
        *,
        team_id: int,
        user_message: str,
    ) -> AgentSemanticParseEnvelope: ...


class CRMRootSemanticPlanResolver:
    """Use the domain semantic parser as Root's bounded route-recovery seam."""

    def __init__(
        self, semantic_parser: RootSemanticParser = agent_semantic_parser
    ) -> None:
        self._semantic_parser = semantic_parser

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        context: RootContextSnapshot,
        runtime: RootRuntimeContext,
    ) -> AgentSemanticPlan | None:
        del context
        if not isinstance(turn.input, TextTurnInput) or runtime.db is None:
            return None
        envelope = await self._semantic_parser.parse_with_metadata(
            runtime.db,
            team_id=turn.team_id,
            user_message=turn.input.text,
        )
        return semantic_plan_from_result(envelope.result)


@lru_cache(maxsize=1)
def get_query_semantic_intent_resolver() -> LLMQuerySemanticIntentResolver:
    return LLMQuerySemanticIntentResolver(timeout_seconds=get_settings().AGENT_QUERY_SEMANTIC_TIMEOUT)


@lru_cache(maxsize=1)
def _internal_crm_api_client() -> InternalCRMAPIClient:
    return InternalCRMAPIClient()


@lru_cache(maxsize=1)
def get_crm_query_spec_executor() -> DefaultCRMQueryExecutor:
    """Deterministic, policy-validated QuerySpec executor (no model call)."""

    return DefaultCRMQueryExecutor(api_client=_internal_crm_api_client())


@lru_cache(maxsize=1)
def get_crm_query_agent_executor() -> CRMQueryAgentExecutor:
    """The one read-only CRM Query Agent seam shared by every channel."""

    query_agent = CRMQueryAgent(
        CRMReadToolRegistry(
            executor=get_crm_query_spec_executor(),
            customer_context_reader=DefaultCustomerContextReader(),
            follow_up_task_detail_reader=FollowUpTaskDetailAPIAdapter(_internal_crm_api_client()),
        )
    )
    return CRMQueryAgentExecutor(
        query_agent=query_agent,
        semantic_intent_resolver=get_query_semantic_intent_resolver(),
    )


@lru_cache(maxsize=1)
def get_root_orchestrator() -> RootOrchestrator:
    """Build the one production execution graph used by every Agent channel."""

    workflow_subgraph = build_workflow_subgraph(
        planner=CRMWorkflowPlanner(),
        effect_executor=CRMWorkflowEffectExecutor(),
    )
    return RootOrchestrator(
        checkpointer=agent_checkpoint_saver,
        context_resolver=DatabaseRootContextResolver(),
        decision_classifier=LangChainRootDecisionClassifier(),
        query_executor=get_crm_query_agent_executor(),
        interaction_resolver=DatabaseInteractionResolver(),
        workflow_subgraph=workflow_subgraph,
        semantic_intent_resolver=get_query_semantic_intent_resolver(),
        semantic_plan_resolver=CRMRootSemanticPlanResolver(),
        pending_case_ranker=agent_semantic_parser,
    )
