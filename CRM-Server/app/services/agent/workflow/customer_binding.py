"""Bind all workflow customer evidence before authoritative CRM resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.services.agent.query.schemas import EntityRef
    from app.services.agent.schemas import AgentSemanticParseResult

CustomerIdentityEvidenceSource = Literal[
    "USER_EXPLICIT",
    "ACTION_FIELD",
]


@dataclass(frozen=True)
class CustomerNameEvidence:
    """One user-derived name that may identify the target CRM customer."""

    name: str
    source: CustomerIdentityEvidenceSource
    field_path: str

    def __post_init__(self) -> None:
        normalized = self.name.strip()
        if not normalized:
            raise ValueError("customer name evidence cannot be blank")
        object.__setattr__(self, "name", normalized)


@dataclass(frozen=True)
class WorkflowCustomerBinding:
    """Canonical inputs for the authorized customer identity resolver."""

    lookup_name: str | None
    trusted_context_customer: EntityRef | None
    selected_customer_id: str | None
    name_evidence: tuple[CustomerNameEvidence, ...]


def bind_workflow_customer(
    *,
    semantic: AgentSemanticParseResult,
    trusted_context_customer: EntityRef | None,
    selected_customer_id: str | None,
) -> WorkflowCustomerBinding:
    """Normalize target-customer evidence behind one Workflow-wide seam.

    The semantic model extracts candidates; this module owns their business role
    and precedence. The resulting name is still only a lookup hint and must pass
    the authorized CRM identity resolver before a customer ID is bound.
    """

    action_evidence = _action_customer_evidence(semantic)
    semantic_name = _optional_non_blank_text(semantic.customer.name_text)
    explicit_evidence = (
        CustomerNameEvidence(
            name=semantic_name,
            source="USER_EXPLICIT",
            field_path="customer.name_text",
        )
        if semantic_name is not None and semantic.customer.resolution_source == "EXPLICIT"
        else None
    )

    if explicit_evidence is not None:
        return WorkflowCustomerBinding(
            lookup_name=explicit_evidence.name,
            trusted_context_customer=trusted_context_customer,
            selected_customer_id=selected_customer_id,
            name_evidence=(explicit_evidence, *action_evidence),
        )
    if trusted_context_customer is not None:
        return WorkflowCustomerBinding(
            lookup_name=None,
            trusted_context_customer=trusted_context_customer,
            selected_customer_id=selected_customer_id,
            name_evidence=action_evidence,
        )

    return WorkflowCustomerBinding(
        lookup_name=action_evidence[0].name if action_evidence else None,
        trusted_context_customer=None,
        selected_customer_id=selected_customer_id,
        name_evidence=action_evidence,
    )


def _action_customer_evidence(semantic: AgentSemanticParseResult) -> tuple[CustomerNameEvidence, ...]:
    """Extract only fields whose domain role can identify the target customer.

    This is intentionally intent- and role-aware. A payer, deployment name, or
    contact name may be another legal/person entity and must never become a CRM
    customer merely because it looks like a company name.
    """

    if semantic.intent != "CREATE_INVOICE_TITLE":
        return ()

    invoice_title = semantic.invoice_title
    title = _optional_non_blank_text(invoice_title.title)
    if invoice_title.title_type != "COMPANY" or title is None:
        return ()
    return (
        CustomerNameEvidence(
            name=title,
            source="ACTION_FIELD",
            field_path="invoice_title.title",
        ),
    )


def _optional_non_blank_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
