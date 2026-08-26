"""Behavioral tests for the permission-safe Query Agent customer context reader."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.services.agent.query import (
    CRMQueryExecutionError,
    CustomerContextRequest,
    DefaultCustomerContextReader,
    EntityRef,
)
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.tools.base import AgentToolContext


class RecordingAPIClient:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls = []

    async def request(self, method, path, authorization, **kwargs):
        self.calls.append((method, path, authorization, kwargs))
        if self.error is not None:
            raise self.error
        return self.payload


class StubIntelligenceContext:
    def to_agent_payload(self):
        return {
            "strong_context": {
                "customer": {
                    "id": 101,
                    "public_id": "cus_visible",
                    "account_name": "上海睿狐科技",
                    "city": "上海",
                    "owner_id": "42",
                    "customer_brief_status": "READY",
                    "customer_brief_markdown": "客户正在推进续约。",
                },
                "customer_facts": [
                    {"id": 901, "customer_id": 101, "content": "本周确认续约范围"}
                ],
                "contacts": [
                    {"id": 201, "name": "张总", "reports_to": 99, "is_decision_maker": True}
                ],
                "opportunities": [{"id": 301, "name": "续约", "stage": "NEGOTIATION"}],
                "contracts": [{"id": 401, "opportunity_id": 301, "contract_number": "HT-001"}],
                "payment_plans": [{"id": 501, "contract_id": 401, "planned_amount": "100000"}],
                "payment_records": [
                    {
                        "id": 601,
                        "payment_plan_id": 501,
                        "contract_id": 401,
                        "record_number": "PAY-001",
                    }
                ],
                "recent_activities": [{"id": 701, "content": "沟通续约"}],
                "same_industry_customers": ["上海同行客户"],
            },
            "semantic_evidence": [
                {
                    "evidence_id": "evidence-safe",
                    "business_object_id": "701",
                    "source_object_id": "internal-701",
                    "title": "客户跟进",
                    "text": "张总确认本周推进续约。",
                }
            ],
            "retrieval": {
                "status": "ok",
                "enabled": True,
                "returned_count": 1,
                "error_message": None,
            },
            "citations": [
                {
                    "evidence_id": "evidence-safe",
                    "business_object_id": "701",
                    "source_object_id": "internal-701",
                    "title": "客户跟进",
                    "source_type": "customer_activity",
                }
            ],
        }


class RecordingContextService:
    def __init__(self, payload=None) -> None:
        self.payload = payload or StubIntelligenceContext()
        self.calls = []

    def build_context_by_public_id(self, db, **kwargs):
        self.calls.append((db, kwargs))
        return self.payload


def _request(*sections: str, question: str | None = "客户续约进展") -> CustomerContextRequest:
    return CustomerContextRequest(
        customer_ref=EntityRef(
            ref_id="eref_customer_visible",
            resource="customer",
            public_id="cus_visible",
            display_name="上海睿狐科技",
        ),
        sections=list(sections),
        question=question,
        evidence_limit=6,
    )


def _context() -> AgentToolContext:
    return AgentToolContext(
        db=Mock(),
        team_id=2,
        user_id=3,
        session_id=4,
        authorization="Bearer test",
        permission_codes=frozenset({"customer:view:all"}),
    )


@pytest.mark.asyncio
async def test_customer_context_reader_authorizes_public_id_and_removes_internal_ids() -> None:
    api = RecordingAPIClient({"id": "cus_visible", "public_id": "cus_visible"})
    context_service = RecordingContextService()
    reader = DefaultCustomerContextReader(
        api_client=api,
        context_service=context_service,
    )

    result = await reader.read(
        _request("profile", "brief", "contacts", "contracts", "payments", "activities", "evidence"),
        _context(),
    )

    assert api.calls == [("GET", "/v1/customers/cus_visible", "Bearer test", {})]
    assert context_service.calls[0][1] == {
        "team_id": 2,
        "customer_public_id": "cus_visible",
        "query_text": "客户续约进展",
        "evidence_limit": 6,
    }
    serialized = result.model_dump(mode="json")
    serialized_text = str(serialized)
    assert "customer_id" not in serialized_text
    assert "contract_id" not in serialized_text
    assert "payment_plan_id" not in serialized_text
    assert "reports_to" not in serialized_text
    assert "business_object_id" not in serialized_text
    assert "source_object_id" not in serialized_text
    assert result.coverage.unavailable == []
    assert result.coverage.returned == [
        "profile",
        "brief",
        "contacts",
        "contracts",
        "payments",
        "activities",
        "evidence",
    ]
    assert result.citations[0].source_ref == "customer:cus_visible"
    assert result.citations[1].source_ref == "evidence:evidence-safe"
    assert result.degraded_reasons == []


@pytest.mark.asyncio
async def test_customer_context_reader_exposes_qdrant_degradation_without_fake_evidence() -> None:
    class DegradedContext:
        def to_agent_payload(self):
            return {
                "strong_context": {
                    "customer": {"id": 101, "public_id": "cus_visible", "account_name": "上海睿狐科技"},
                    "customer_facts": [],
                },
                "semantic_evidence": [],
                "retrieval": {"status": "embedding_unavailable", "enabled": True},
                "citations": [],
            }

    reader = DefaultCustomerContextReader(
        api_client=RecordingAPIClient({"public_id": "cus_visible"}),
        context_service=RecordingContextService(DegradedContext()),
    )

    result = await reader.read(_request("brief", "evidence"), _context())

    assert result.coverage.returned == ["brief"]
    assert result.coverage.unavailable == ["evidence"]
    assert result.degraded_reasons == ["customer_intelligence:embedding_unavailable"]
    assert all(citation.source != "QDRANT" for citation in result.citations)


@pytest.mark.asyncio
async def test_customer_context_reader_maps_api_permission_denial_before_domain_read() -> None:
    context_service = RecordingContextService()
    reader = DefaultCustomerContextReader(
        api_client=RecordingAPIClient(error=CRMAPIClientError("forbidden", status_code=403)),
        context_service=context_service,
    )

    with pytest.raises(CRMQueryExecutionError) as exc_info:
        await reader.read(_request("profile"), _context())

    assert exc_info.value.error.code == "PERMISSION_DENIED"
    assert context_service.calls == []
