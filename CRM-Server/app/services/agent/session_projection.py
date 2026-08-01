"""Compatibility projection from persisted session context into Agent runtime state."""
from __future__ import annotations

from app.services.agent.state import AgentSessionRuntimeProjection
from app.services.agent.types import JSONDict, JSONValue, coerce_json_dict, coerce_json_value


CURRENT_CUSTOMER_KEY = "current_customer"


def project_session_runtime(session: object) -> AgentSessionRuntimeProjection:
    """Return the only session-context shape the LangGraph runtime should consume."""

    context = _runtime_session_context(getattr(session, "context_json", None))
    return AgentSessionRuntimeProjection(
        session_context=context,
        current_customer=coerce_json_dict(context.get(CURRENT_CUSTOMER_KEY)),
    )


def session_context(session: object) -> JSONDict:
    return _runtime_session_context(getattr(session, "context_json", None))


def with_current_customer(context: object, customer: object) -> JSONDict:
    customer_projection = coerce_json_dict(customer)
    customer_id = customer_projection.get("id")
    account_name = customer_projection.get("account_name")
    if not customer_id or not account_name:
        return coerce_json_dict(context)
    updated = coerce_json_dict(context)
    updated[CURRENT_CUSTOMER_KEY] = {
        "id": customer_id,
        "account_name": account_name,
        "owner_info": coerce_json_value(customer_projection.get("owner_info")),
        "collaborator_infos": _json_list_value(customer_projection.get("collaborator_infos")),
    }
    return updated


def _json_list_value(value: object) -> list[JSONValue]:
    if not isinstance(value, list):
        return []
    return [coerce_json_value(item) for item in value]


def _runtime_session_context(context: object) -> JSONDict:
    current_customer = coerce_json_dict(coerce_json_dict(context).get(CURRENT_CUSTOMER_KEY))
    if not current_customer:
        return {}
    return {CURRENT_CUSTOMER_KEY: current_customer}
