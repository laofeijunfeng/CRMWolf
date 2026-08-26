"""Deterministic JSON Schema export for the frozen CRM Agent contracts."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, JsonValue, TypeAdapter

from app.services.agent.orchestrator.contracts import (
    ContextPolicy,
    ResultSetContext,
    RootContextSnapshot,
    RootDecision,
)
from app.services.agent.query.completed_work_contracts import (
    CompletedFollowUpTaskFact,
    CompletedFollowUpTaskPayload,
    CompletedWorkAppliedFilters,
    CompletedWorkAttribution,
    CompletedWorkCustomer,
    CompletedWorkFact,
    CompletedWorkHTTPError,
    CompletedWorkHTTPErrorCode,
    CompletedWorkQueryRequest,
    CompletedWorkQueryResponse,
    CompletedWorkSourceCounts,
    CompletedWorkSourceStatus,
    CompletedWorkWindow,
    CustomerActivityFact,
    CustomerActivityPayload,
)
from app.services.agent.query.schemas import (
    CRMFilter,
    CRMMetric,
    CRMQueryResult,
    CRMQuerySpec,
    CRMResource,
    CRMSort,
    EntityRef,
    GroundedFact,
    QueryError,
    QueryWarning,
)
from app.services.agent.ui.schemas import (
    ActionResultBlock,
    AgentChatInput,
    AgentChatRequest,
    AgentErrorCode,
    AgentTransportErrorEvent,
    AgentUIAction,
    AgentUIBlock,
    AgentUIDeltaStreamEvent,
    AgentUIEnvelope,
    AgentUIFinalStreamEvent,
    AgentUIMetadata,
    AgentUIStreamEvent,
    AgentUIStreamOperation,
    AgentUIValue,
    AppendTextOperation,
    EntityActionInput,
    EntityCardBlock,
    EntityListBlock,
    ErrorBlock,
    InteractionBlock,
    InteractionField,
    InteractionOption,
    InteractionSubmissionInput,
    MetricGroupBlock,
    NoticeBlock,
    PaginationBlock,
    TableBlock,
    TextAgentInput,
    TextBlock,
    TimelineBlock,
)

AGENT_CONTRACT_SCHEMA_BUNDLE_VERSION = "crm.agent.contracts.v2"


def _model_schema(model: type[BaseModel]) -> dict[str, JsonValue]:
    return cast("dict[str, JsonValue]", model.model_json_schema(mode="validation"))


def _adapter_schema(adapter: TypeAdapter[object]) -> dict[str, JsonValue]:
    return cast("dict[str, JsonValue]", adapter.json_schema(mode="validation"))


def build_agent_contract_schema_bundle() -> dict[str, JsonValue]:
    """Return a stable, content-free schema bundle for backend/frontend review."""

    models: dict[str, type[BaseModel]] = {
        "CompletedWorkCustomer": CompletedWorkCustomer,
        "CompletedWorkAttribution": CompletedWorkAttribution,
        "CompletedFollowUpTaskPayload": CompletedFollowUpTaskPayload,
        "CustomerActivityPayload": CustomerActivityPayload,
        "CompletedFollowUpTaskFact": CompletedFollowUpTaskFact,
        "CustomerActivityFact": CustomerActivityFact,
        "CompletedWorkSourceCounts": CompletedWorkSourceCounts,
        "CompletedWorkSourceStatus": CompletedWorkSourceStatus,
        "CompletedWorkAppliedFilters": CompletedWorkAppliedFilters,
        "CompletedWorkQueryRequest": CompletedWorkQueryRequest,
        "CompletedWorkQueryResponse": CompletedWorkQueryResponse,
        "CompletedWorkHTTPError": CompletedWorkHTTPError,
        "EntityRef": EntityRef,
        "CRMFilter": CRMFilter,
        "CRMSort": CRMSort,
        "CRMMetric": CRMMetric,
        "CRMQuerySpec": CRMQuerySpec,
        "GroundedFact": GroundedFact,
        "QueryWarning": QueryWarning,
        "QueryError": QueryError,
        "CRMQueryResult": CRMQueryResult,
        "ContextPolicy": ContextPolicy,
        "RootDecision": RootDecision,
        "ResultSetContext": ResultSetContext,
        "RootContextSnapshot": RootContextSnapshot,
        "AgentUIValue": AgentUIValue,
        "TextBlock": TextBlock,
        "EntityListBlock": EntityListBlock,
        "EntityCardBlock": EntityCardBlock,
        "TableBlock": TableBlock,
        "TimelineBlock": TimelineBlock,
        "MetricGroupBlock": MetricGroupBlock,
        "NoticeBlock": NoticeBlock,
        "ErrorBlock": ErrorBlock,
        "InteractionOption": InteractionOption,
        "InteractionField": InteractionField,
        "InteractionBlock": InteractionBlock,
        "ActionResultBlock": ActionResultBlock,
        "AppendTextOperation": AppendTextOperation,
        "AgentUIDeltaStreamEvent": AgentUIDeltaStreamEvent,
        "AgentUIFinalStreamEvent": AgentUIFinalStreamEvent,
        "AgentTransportErrorEvent": AgentTransportErrorEvent,
        "PaginationBlock": PaginationBlock,
        "AgentUIMetadata": AgentUIMetadata,
        "AgentUIEnvelope": AgentUIEnvelope,
        "TextAgentInput": TextAgentInput,
        "InteractionSubmissionInput": InteractionSubmissionInput,
        "EntityActionInput": EntityActionInput,
        "AgentChatRequest": AgentChatRequest,
    }
    schemas: dict[str, JsonValue] = {name: _model_schema(model) for name, model in models.items()}
    schemas.update(
        {
            "CompletedWorkWindow": _adapter_schema(TypeAdapter(CompletedWorkWindow)),
            "CompletedWorkFact": _adapter_schema(TypeAdapter(CompletedWorkFact)),
            "CompletedWorkHTTPErrorCode": _adapter_schema(TypeAdapter(CompletedWorkHTTPErrorCode)),
            "CRMResource": _adapter_schema(TypeAdapter(CRMResource)),
            "AgentErrorCode": _adapter_schema(TypeAdapter(AgentErrorCode)),
            "AgentUIAction": _adapter_schema(TypeAdapter(AgentUIAction)),
            "AgentUIBlock": _adapter_schema(TypeAdapter(AgentUIBlock)),
            "AgentUIStreamOperation": _adapter_schema(TypeAdapter(AgentUIStreamOperation)),
            "AgentUIStreamEvent": _adapter_schema(TypeAdapter(AgentUIStreamEvent)),
            "AgentChatInput": _adapter_schema(TypeAdapter(AgentChatInput)),
        }
    )
    return {
        "bundle_version": AGENT_CONTRACT_SCHEMA_BUNDLE_VERSION,
        "schemas": schemas,
    }
