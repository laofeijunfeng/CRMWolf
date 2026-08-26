"""Golden JSON Schema and example validation for cross-channel Agent contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.services.agent.contract_schema import build_agent_contract_schema_bundle
from app.services.agent.orchestrator import RootContextSnapshot, RootDecision
from app.services.agent.query.completed_work_contracts import (
    CompletedWorkHTTPError,
    CompletedWorkQueryRequest,
    CompletedWorkQueryResponse,
)
from app.services.agent.query.schemas import CRMQueryResult, CRMQuerySpec, QueryError
from app.services.agent.ui import (
    AgentChatRequest,
    AgentTransportErrorEvent,
    AgentUIAction,
    AgentUIBlock,
    AgentUIEnvelope,
    AgentUIStreamEvent,
    InteractionBlock,
)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "agent_contracts"


def _read_json(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_generated_json_schema_matches_the_reviewed_golden_bundle() -> None:
    assert build_agent_contract_schema_bundle() == _read_json("crm_agent_contracts.schema.json")


def test_representative_examples_validate_through_public_contracts() -> None:
    examples = TypeAdapter(dict[str, object]).validate_python(_read_json("crm_agent_contract_examples.json"))

    RootDecision.model_validate(examples["root_decision"])
    RootContextSnapshot.model_validate(examples["root_context_snapshot"])
    CRMQuerySpec.model_validate(examples["query_spec"])
    CRMQueryResult.model_validate(examples["query_result"])
    QueryError.model_validate(examples["query_error"])
    CompletedWorkQueryRequest.model_validate(examples["completed_work_request"])
    CompletedWorkQueryResponse.model_validate(examples["completed_work_response"])
    CompletedWorkHTTPError.model_validate(examples["completed_work_error"])
    AgentUIEnvelope.model_validate(examples["agent_ui_envelope"])

    stream_events = TypeAdapter(list[object]).validate_python(examples["agent_ui_stream_events"])
    stream_adapter = TypeAdapter(AgentUIStreamEvent)
    assert len(stream_events) == 2
    for event in stream_events:
        stream_adapter.validate_python(event)

    chat_requests = TypeAdapter(list[object]).validate_python(examples["chat_requests"])
    assert len(chat_requests) == 3
    for request in chat_requests:
        AgentChatRequest.model_validate(request)


def test_completed_work_http_boundary_is_present_in_schema_bundle() -> None:
    schemas = TypeAdapter(dict[str, object]).validate_python(build_agent_contract_schema_bundle()["schemas"])

    assert {
        "CompletedWorkQueryRequest",
        "CompletedWorkQueryResponse",
        "CompletedWorkHTTPError",
        "CompletedWorkWindow",
        "CompletedWorkHTTPErrorCode",
    } <= schemas.keys()


def test_agent_ui_stream_contract_is_present_in_schema_bundle() -> None:
    schemas = TypeAdapter(dict[str, object]).validate_python(build_agent_contract_schema_bundle()["schemas"])

    assert {
        "AppendTextOperation",
        "AgentUIDeltaStreamEvent",
        "AgentUIFinalStreamEvent",
        "AgentUIStreamOperation",
        "AgentUIStreamEvent",
        "AgentTransportErrorEvent",
    } <= schemas.keys()


def test_typed_request_schema_contains_no_legacy_chat_fields() -> None:
    schema_bundle = build_agent_contract_schema_bundle()
    schemas = TypeAdapter(dict[str, object]).validate_python(schema_bundle["schemas"])
    request_schema = TypeAdapter(dict[str, object]).validate_python(schemas["AgentChatRequest"])
    properties = TypeAdapter(dict[str, object]).validate_python(request_schema["properties"])

    assert set(properties) == {"session_id", "session_key", "client_request_id", "input"}
    assert "content" not in properties
    assert "interaction_metadata" not in properties


def test_backend_contracts_match_the_shared_cross_language_conformance_corpus() -> None:
    corpus = TypeAdapter(dict[str, list[dict[str, object]]]).validate_python(
        _read_json("crm_agent_contract_conformance.json")
    )
    validators = {
        "RootDecision": TypeAdapter(RootDecision),
        "CRMQuerySpec": TypeAdapter(CRMQuerySpec),
        "CRMQueryResult": TypeAdapter(CRMQueryResult),
        "QueryError": TypeAdapter(QueryError),
        "AgentChatRequest": TypeAdapter(AgentChatRequest),
        "AgentUIAction": TypeAdapter(AgentUIAction),
        "AgentUIBlock": TypeAdapter(AgentUIBlock),
        "AgentUIEnvelope": TypeAdapter(AgentUIEnvelope),
        "InteractionBlock": TypeAdapter(InteractionBlock),
        "AgentUIStreamEvent": TypeAdapter(AgentUIStreamEvent),
        "AgentTransportErrorEvent": TypeAdapter(AgentTransportErrorEvent),
    }

    for case in corpus["valid"]:
        schema_name = TypeAdapter(str).validate_python(case["schema"])
        validators[schema_name].validate_python(case["payload"])

    for case in corpus["invalid"]:
        schema_name = TypeAdapter(str).validate_python(case["schema"])
        try:
            validators[schema_name].validate_python(case["payload"])
        except ValueError:
            continue
        raise AssertionError(f"{schema_name} accepted invalid conformance case: {case.get('reason')}")


def test_shared_conformance_corpus_covers_every_p0_agent_ui_variant() -> None:
    corpus = TypeAdapter(dict[str, list[dict[str, object]]]).validate_python(
        _read_json("crm_agent_contract_conformance.json")
    )
    valid_cases = corpus["valid"]
    block_types = {
        TypeAdapter(dict[str, object]).validate_python(case["payload"])["type"]
        for case in valid_cases
        if case["schema"] == "AgentUIBlock"
    }
    action_types = {
        TypeAdapter(dict[str, object]).validate_python(case["payload"])["type"]
        for case in valid_cases
        if case["schema"] == "AgentUIAction"
    }

    assert block_types == {
        "text",
        "entity_list",
        "entity_card",
        "table",
        "timeline",
        "metric_group",
        "notice",
        "error",
        "interaction",
        "action_result",
        "pagination",
    }
    assert action_types == {
        "open_entity",
        "query_refinement",
        "start_workflow",
        "submit_interaction",
        "retry",
    }
