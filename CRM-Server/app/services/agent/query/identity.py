"""Deterministic customer binding for customer-scoped Query turns.

The Query Agent may plan a read, but it must not be responsible for deciding
which CRM customer a natural-language mention refers to.  This module owns the
small, server-authoritative seam between the Root Query execution boundary and
the existing customer identity resolver.
"""

from __future__ import annotations

import re
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
    "query_follow_up_tasks",
    "get_customer_context",
]


@dataclass(frozen=True)
class CustomerQueryIntent:
    """Deterministic resource hint for one customer-scoped read request."""

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
    """Bind customer-scoped queries before the model receives any CRM tools.

    The binder intentionally does not run for a customer-list query.  A city,
    status, or other list filter is a set query and must never be collapsed to
    one customer merely because identity retrieval found a plausible match.
    """

    def __init__(
        self,
        *,
        identity_service: CustomerIdentityResolutionApplicationService | None = None,
    ) -> None:
        self._identity_service = identity_service or customer_identity_resolution_application_service

    def classify(self, text: str) -> CustomerQueryIntent | None:
        normalized = _strip_question(text)
        if not normalized or _is_customer_list_query(normalized):
            return None

        customer_text = _extract_customer_text(normalized)
        if not customer_text:
            return None

        if re.search(r"联系人|决策人|关键联系人|关键决策", normalized):
            tool_name: CustomerScopedTool = "query_customer_contacts"
        elif re.search(r"最近跟进|最新进展|最近沟通|活动记录|跟进记录", normalized):
            tool_name = "query_customer_activities"
        elif re.search(r"待办|跟进任务|任务列表|未完成任务", normalized):
            tool_name = "query_follow_up_tasks"
        else:
            tool_name = "get_customer_context"
        return CustomerQueryIntent(tool_name=tool_name, customer_text=customer_text)

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
        candidates = tuple(_entity_ref(item) for item in resolution.items if _entity_ref(item) is not None)
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


def _is_customer_list_query(text: str) -> bool:
    if re.search(r"联系人|决策人|商机|合同|回款|跟进|档案|资料|情况|进展", text):
        return False
    return bool(
        re.search(
            r"(?:有哪些|有多少|多少(?:个|家)?|列表|清单).{0,8}(?:客户|公司)"
            r"|(?:客户|公司).{0,8}(?:有哪些|有多少|多少(?:个|家)?|列表|清单)",
            text,
        )
    )


def _extract_customer_text(text: str) -> str | None:
    """Extract the customer mention without making a CRM lookup decision."""

    candidate = re.sub(r"^(?:我想知道|我想查询|请问|帮我查一下|帮我查|查询|查看|看看)\s*", "", text)
    # Prefer a legal-entity-shaped span.  This handles a full name embedded in
    # a sentence and avoids sending the whole question to keyword search.
    legal_match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9\uFF08\uFF09()·.&_-]{2,100}?(?:股份有限公司|有限公司|集团公司|集团|公司))",
        candidate,
    )
    if legal_match:
        return legal_match.group(1).strip()

    # Approved aliases normally do not carry a legal suffix (for example
    # “凡亚信息”).  For those, use the text before the first relation marker.
    alias_match = re.match(
        r"(.{2,80}?)(?:现在|目前|有哪些|有多少|的|联系人|决策人|商机|合同|回款|跟进|情况|进展)",
        candidate,
    )
    if not alias_match:
        return None
    value = alias_match.group(1).strip(" \uFF0C,\uFF1A:的")
    return value if len(value) >= 2 else None


def _strip_question(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", str(text or "").strip(" \uFF1F?。"))
