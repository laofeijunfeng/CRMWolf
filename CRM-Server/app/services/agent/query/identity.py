"""Server-authoritative customer identity binding for Query turns.

Semantic meaning (including whether a turn is customer-scoped and which CRM
resource it asks for) is resolved before this module is called.  This module
must stay deliberately boring: it accepts a structured customer hint and only
binds that hint to an authorized CRM entity.  It does not maintain a keyword
list, parse Chinese phrasing, or decide whether a turn is a customer query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

from app.services.agent.query.schemas import EntityRef
from app.services.customer_identity_resolution_application_service import (
    CustomerIdentityResolutionApplicationService,
    customer_identity_resolution_application_service,
)

if TYPE_CHECKING:
    from app.services.agent.tools.base import AgentToolContext


CustomerScopedTool: TypeAlias = Literal[
    "query_customer_contacts",
    "query_customer_activities",
    "query_customer_deployment_infos",
    "query_follow_up_tasks",
    "query_completed_work",
    "get_customer_context",
]


@dataclass(frozen=True)
class CustomerQueryIntent:
    """Structured customer resource and lookup hint produced upstream.

    ``customer_text`` is not an identity.  It is only the text to pass to the
    authorized identity resolver.  The binder never treats it as a CRM ID.
    """

    tool_name: CustomerScopedTool
    customer_text: str


@dataclass(frozen=True)
class CustomerBinding:
    """Authoritative binding outcome used by the Query execution seam."""

    status: Literal["BOUND", "AMBIGUOUS", "NOT_FOUND"]
    entity_ref: EntityRef | None = None
    candidates: tuple[EntityRef, ...] = ()
    query_text: str | None = None


class CustomerIdentityBindingError(RuntimeError):
    """The authoritative identity resolver could not complete."""


class CustomerQueryIdentityBinder:
    """Bind a structured customer hint to an authorized CRM entity.

    The binder intentionally has no ``classify`` or text-parsing method.  A
    customer-list query, a global work query, and a customer-scoped query must
    be distinguished by the semantic-intent boundary, not by another growing
    set of regular expressions here.
    """

    def __init__(
        self,
        *,
        identity_service: CustomerIdentityResolutionApplicationService | None = None,
    ) -> None:
        self._identity_service = identity_service or customer_identity_resolution_application_service

    def bind(self, intent: CustomerQueryIntent, context: AgentToolContext) -> CustomerBinding:
        try:
            resolution = self._identity_service.resolve(
                context.db,
                team_id=context.team_id,
                user_id=context.user_id,
                permission_codes=context.permission_codes,
                query_text=intent.customer_text,
                limit=5,
            )
        except Exception as exc:  # pragma: no cover - concrete DB/vector failures vary by deployment
            raise CustomerIdentityBindingError("customer identity resolution failed") from exc

        decision = str(resolution.metadata.get("identity_decision") or "no_match")
        candidates = tuple(
            candidate
            for item in resolution.items
            if (candidate := _entity_ref(item)) is not None
        )
        if decision in {"auto_select", "ranked_auto_selectable"} and candidates:
            return CustomerBinding(
                status="BOUND",
                entity_ref=candidates[0],
                candidates=candidates,
                query_text=intent.customer_text,
            )
        if decision == "requires_confirmation" and candidates:
            return CustomerBinding(
                status="AMBIGUOUS",
                candidates=candidates,
                query_text=intent.customer_text,
            )
        return CustomerBinding(status="NOT_FOUND", candidates=candidates, query_text=intent.customer_text)


def _entity_ref(item: object) -> EntityRef | None:
    if not isinstance(item, dict):
        return None
    public_id = item.get("id")
    account_name = item.get("account_name")
    if not isinstance(public_id, (str, int)) or not str(public_id):
        return None
    if not isinstance(account_name, str) or not account_name.strip():
        return None
    return EntityRef(
        ref_id=f"eref_customer_{public_id}",
        resource="customer",
        public_id=str(public_id),
        display_name=account_name.strip(),
    )
