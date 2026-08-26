"""Production assembly for the single CRM Root Orchestrator runtime."""

from __future__ import annotations

from functools import lru_cache

from app.services.agent.checkpointer import agent_checkpoint_saver
from app.services.agent.orchestrator.context import DatabaseRootContextResolver
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
from app.services.agent.workflow.execution import CRMWorkflowEffectExecutor
from app.services.agent.workflow.graph import build_workflow_subgraph
from app.services.agent.workflow.planning import CRMWorkflowPlanner


@lru_cache(maxsize=1)
def get_root_orchestrator() -> RootOrchestrator:
    """Build the one production execution graph used by every Agent channel."""

    query_agent = CRMQueryAgent(
        CRMReadToolRegistry(
            executor=DefaultCRMQueryExecutor(),
            customer_context_reader=DefaultCustomerContextReader(),
        )
    )
    workflow_subgraph = build_workflow_subgraph(
        planner=CRMWorkflowPlanner(),
        effect_executor=CRMWorkflowEffectExecutor(),
    )
    return RootOrchestrator(
        checkpointer=agent_checkpoint_saver,
        context_resolver=DatabaseRootContextResolver(),
        decision_classifier=LangChainRootDecisionClassifier(),
        query_executor=CRMQueryAgentExecutor(query_agent=query_agent),
        interaction_resolver=DatabaseInteractionResolver(),
        workflow_subgraph=workflow_subgraph,
    )
