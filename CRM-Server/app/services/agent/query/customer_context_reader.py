"""Permission-safe customer context reader for the CRM Query Agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

from app.services.agent.query.executor import CRMQueryExecutionError
from app.services.agent.query.registry import (
    CustomerContextCitation,
    CustomerContextCoverage,
    CustomerContextRequest,
    CustomerContextResult,
    CustomerContextSection,
)
from app.services.agent.query.schemas import JsonDict, QueryError
from app.services.agent.tools.api_client import CRMAPIClientError, InternalCRMAPIClient
from app.services.customer_intelligence_context_service import (
    CustomerIntelligenceContextNotFound,
    customer_intelligence_context_service,
)

if TYPE_CHECKING:
    from pydantic import JsonValue
    from sqlalchemy.orm import Session

    from app.services.agent.tools.base import AgentToolContext


class CustomerContextBuilder(Protocol):
    def build_context_by_public_id(
        self,
        db: Session,
        *,
        team_id: int,
        customer_public_id: str,
        query_text: str | None = None,
        evidence_limit: int = 8,
    ) -> object: ...


class DefaultCustomerContextReader:
    """Authorize through the CRM API, then project sanitized customer intelligence."""

    def __init__(
        self,
        *,
        api_client: InternalCRMAPIClient | None = None,
        context_service: CustomerContextBuilder = customer_intelligence_context_service,
    ) -> None:
        self._api_client = api_client or InternalCRMAPIClient()
        self._context_service = context_service

    async def read(
        self,
        request: CustomerContextRequest,
        context: AgentToolContext,
    ) -> CustomerContextResult:
        public_id = request.customer_ref.public_id
        await self._authorize_customer(public_id, context)
        db = context.db
        try:
            intelligence = self._context_service.build_context_by_public_id(
                db,
                team_id=context.team_id,
                customer_public_id=public_id,
                query_text=request.question,
                evidence_limit=request.evidence_limit,
            )
        except CustomerIntelligenceContextNotFound as exc:
            raise CRMQueryExecutionError(
                QueryError(
                    code="QUERY_INVALID",
                    message="Customer context target does not exist",
                    retryable=False,
                )
            ) from exc
        payload = self._payload(intelligence)
        sections, returned, unavailable = _project_sections(request, payload)
        citations = _project_citations(request, payload, returned)
        degraded_reasons = _degraded_reasons(request, payload, unavailable)
        return CustomerContextResult(
            customer_ref=request.customer_ref,
            sections=sections,
            citations=citations,
            coverage=CustomerContextCoverage(
                requested=request.sections,
                returned=returned,
                unavailable=unavailable,
            ),
            degraded_reasons=degraded_reasons,
        )

    async def _authorize_customer(
        self,
        public_id: str,
        context: AgentToolContext,
    ) -> None:
        try:
            payload = await self._api_client.request(
                "GET",
                f"/v1/customers/{public_id}",
                context.authorization,
            )
        except CRMAPIClientError as exc:
            if exc.status_code == 403:
                error = QueryError(
                    code="PERMISSION_DENIED",
                    message="Customer context access denied",
                    retryable=False,
                )
            elif exc.status_code == 404:
                error = QueryError(
                    code="QUERY_INVALID",
                    message="Customer context target does not exist",
                    retryable=False,
                )
            else:
                error = QueryError(
                    code="INTERNAL_ERROR",
                    message="Customer context authorization failed",
                    retryable=bool(exc.status_code and exc.status_code >= 500),
                )
            raise CRMQueryExecutionError(error) from exc
        if not isinstance(payload, dict):
            raise CRMQueryExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="Customer detail API returned an invalid response",
                    retryable=False,
                )
            )
        authorized_public_id = payload.get("public_id") or payload.get("id")
        if authorized_public_id != public_id:
            raise CRMQueryExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="Customer detail API returned the wrong customer",
                    retryable=False,
                )
            )

    @staticmethod
    def _payload(intelligence: object) -> JsonDict:
        to_agent_payload = getattr(intelligence, "to_agent_payload", None)
        if not callable(to_agent_payload):
            raise CRMQueryExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="Customer intelligence context is invalid",
                    retryable=False,
                )
            )
        payload = to_agent_payload()
        if not isinstance(payload, dict):
            raise CRMQueryExecutionError(
                QueryError(
                    code="INTERNAL_ERROR",
                    message="Customer intelligence context is invalid",
                    retryable=False,
                )
            )
        return cast("JsonDict", payload)


_STRONG_SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "profile": ("customer", "same_industry_customers"),
    "brief": ("customer_facts",),
    "contacts": ("contacts",),
    "opportunities": ("opportunities",),
    "contracts": ("contracts",),
    "payments": ("payment_plans", "payment_records"),
    "activities": ("recent_activities",),
}
_DEGRADED_EVIDENCE_STATES = {
    "disabled",
    "embedding_unavailable",
    "failed",
    "low_confidence",
    "empty",
    "skipped_empty_query",
}


def _project_sections(
    request: CustomerContextRequest,
    payload: JsonDict,
) -> tuple[JsonDict, list[CustomerContextSection], list[CustomerContextSection]]:
    strong = payload.get("strong_context")
    strong_context = strong if isinstance(strong, dict) else {}
    sections: JsonDict = {}
    returned: list[CustomerContextSection] = []
    unavailable: list[CustomerContextSection] = []
    for section in request.sections:
        if section == "evidence":
            evidence = payload.get("semantic_evidence")
            retrieval = payload.get("retrieval")
            evidence_rows = evidence if isinstance(evidence, list) else []
            retrieval_state = retrieval if isinstance(retrieval, dict) else {}
            if evidence_rows:
                sections[section] = {
                    "items": _strip_internal_ids(evidence_rows),
                    "retrieval": _safe_retrieval_state(retrieval_state),
                }
                returned.append(section)
            else:
                unavailable.append(section)
            continue

        keys = _STRONG_SECTION_KEYS[section]
        if section == "profile":
            value: JsonValue = {
                "customer": strong_context.get("customer", {}),
                "same_industry_customers": strong_context.get("same_industry_customers", []),
            }
        elif section == "brief":
            customer = strong_context.get("customer")
            customer_profile = customer if isinstance(customer, dict) else {}
            value = {
                "customer_brief_status": customer_profile.get("customer_brief_status"),
                "customer_brief_markdown": customer_profile.get("customer_brief_markdown"),
                "customer_facts": strong_context.get("customer_facts", []),
            }
        elif len(keys) == 1:
            value = strong_context.get(keys[0], [])
        else:
            value = {key: strong_context.get(key, []) for key in keys}
        sections[section] = _strip_internal_ids(value)
        returned.append(section)
    return sections, returned, unavailable


def _project_citations(
    request: CustomerContextRequest,
    payload: JsonDict,
    returned: list[CustomerContextSection],
) -> list[CustomerContextCitation]:
    citations: list[CustomerContextCitation] = []
    if any(section != "evidence" for section in returned):
        citations.append(
            CustomerContextCitation(
                citation_id=f"cite_customer_{request.customer_ref.public_id}",
                source="CRM_API",
                source_ref=f"customer:{request.customer_ref.public_id}",
                label=request.customer_ref.display_name,
            )
        )
    if "evidence" not in returned:
        return citations
    raw_citations = payload.get("citations")
    if not isinstance(raw_citations, list):
        return citations
    for index, item in enumerate(raw_citations[: request.evidence_limit]):
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            continue
        title = item.get("title")
        source_type = item.get("source_type")
        citations.append(
            CustomerContextCitation(
                citation_id=f"cite_qdrant_{index}_{evidence_id}",
                source="QDRANT",
                source_ref=f"evidence:{evidence_id}",
                label=(
                    title
                    if isinstance(title, str) and title.strip()
                    else str(source_type or "客户证据")
                ),
            )
        )
    return citations


def _degraded_reasons(
    request: CustomerContextRequest,
    payload: JsonDict,
    unavailable: list[CustomerContextSection],
) -> list[str]:
    if "evidence" not in request.sections:
        return []
    retrieval = payload.get("retrieval")
    retrieval_state = retrieval if isinstance(retrieval, dict) else {}
    status = retrieval_state.get("status")
    reasons: list[str] = []
    if isinstance(status, str) and status in _DEGRADED_EVIDENCE_STATES:
        reasons.append(f"customer_intelligence:{status}")
    if "evidence" in unavailable and not reasons:
        reasons.append("customer_intelligence:empty")
    return reasons


def _safe_retrieval_state(retrieval: dict[str, Any]) -> JsonDict:
    allowed = {
        "status",
        "enabled",
        "query_text_present",
        "requested_limit",
        "raw_count",
        "returned_count",
        "dropped_count",
        "top_score",
        "min_score",
        "source_types",
        "strategy",
    }
    return cast("JsonDict", {key: value for key, value in retrieval.items() if key in allowed})


def _strip_internal_ids(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_strip_internal_ids(item) for item in value]
    if not isinstance(value, dict):
        return value
    projected: JsonDict = {}
    for key, item in value.items():
        if key in {"id", "reports_to"} or (key.endswith("_id") and key != "public_id"):
            continue
        projected[key] = _strip_internal_ids(item)
    return projected
