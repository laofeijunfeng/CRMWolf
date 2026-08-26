"""Deterministic CRM query contracts and execution boundary.

The package exposes a stable facade without importing the executor/runtime graph
when callers only need query contracts.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, str] = {
    "CRMQueryAgent": "app.services.agent.query.agent",
    "CRMQueryAgentExecutionError": "app.services.agent.query.agent",
    "CRMQueryAgentLimits": "app.services.agent.query.agent",
    "CRMQueryAgentModelConfig": "app.services.agent.query.agent",
    "CRMQueryAgentRequest": "app.services.agent.query.agent",
    "CRMQueryAgentResponse": "app.services.agent.query.agent",
    "CRMQueryAgentResult": "app.services.agent.query.agent",
    "CRMQueryAgentToolCallTrace": "app.services.agent.query.agent",
    "CRMQueryAgentTrace": "app.services.agent.query.agent",
    "CRMQueryCatalog": "app.services.agent.query.catalog",
    "CRMQueryCatalogError": "app.services.agent.query.catalog",
    "CRMQueryResourceDefinition": "app.services.agent.query.catalog",
    "CompletedFollowUpTaskFact": "app.services.agent.query.completed_work_contracts",
    "CompletedFollowUpTaskPayload": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkAppliedFilters": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkAttribution": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkCustomer": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkFact": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkHTTPError": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkHTTPErrorCode": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkQueryRequest": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkQueryResponse": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkSourceCounts": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkSourceStatus": "app.services.agent.query.completed_work_contracts",
    "CompletedWorkWindow": "app.services.agent.query.completed_work_contracts",
    "CustomerActivityFact": "app.services.agent.query.completed_work_contracts",
    "CustomerActivityPayload": "app.services.agent.query.completed_work_contracts",
    "map_completed_work_http_error": "app.services.agent.query.completed_work_contracts",
    "DefaultCustomerContextReader": "app.services.agent.query.customer_context_reader",
    "CRMQueryExecutionError": "app.services.agent.query.executor",
    "CRMQueryExecutor": "app.services.agent.query.executor",
    "DefaultCRMQueryExecutor": "app.services.agent.query.executor",
    "QueryPolicyError": "app.services.agent.query.policy",
    "QueryPolicyValidator": "app.services.agent.query.policy",
    "CRMReadToolInputError": "app.services.agent.query.registry",
    "CRMReadToolRegistry": "app.services.agent.query.registry",
    "CRMReadToolSpec": "app.services.agent.query.registry",
    "CustomerContextCitation": "app.services.agent.query.registry",
    "CustomerContextCoverage": "app.services.agent.query.registry",
    "CustomerContextReader": "app.services.agent.query.registry",
    "CustomerContextRequest": "app.services.agent.query.registry",
    "CustomerContextResult": "app.services.agent.query.registry",
    "CRMFilter": "app.services.agent.query.schemas",
    "CRMMetric": "app.services.agent.query.schemas",
    "CRMQueryResult": "app.services.agent.query.schemas",
    "CRMQuerySpec": "app.services.agent.query.schemas",
    "CRMResource": "app.services.agent.query.schemas",
    "CRMSort": "app.services.agent.query.schemas",
    "EntityRef": "app.services.agent.query.schemas",
    "GroundedFact": "app.services.agent.query.schemas",
    "QueryError": "app.services.agent.query.schemas",
    "QueryWarning": "app.services.agent.query.schemas",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
