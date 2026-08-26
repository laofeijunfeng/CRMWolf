"""Opt-in real-model regression for CRM Query Agent tool calling.

Run manually with:
CRMWOLF_QUERY_AGENT_REAL_MODEL_REGRESSION=1 \
  AI_API_URL=... AI_API_KEY=... AI_MODEL=... \
  pytest tests/integration/test_agent_query_real_model.py -q --no-cov
"""

from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

from app.services.agent.query import (
    CRMQueryAgent,
    CRMQueryAgentModelConfig,
    CRMQueryAgentRequest,
    CRMQueryResult,
    CRMQuerySpec,
    CRMReadToolRegistry,
    CustomerContextCoverage,
    CustomerContextRequest,
    CustomerContextResult,
    EntityRef,
)
from app.services.agent.tools.base import AgentToolContext

pytestmark = pytest.mark.skipif(
    os.getenv("CRMWOLF_QUERY_AGENT_REAL_MODEL_REGRESSION") != "1",
    reason="real-model Query Agent regression is opt-in",
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[CRMQuerySpec] = []

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryResult:
        self.calls.append(spec)
        refs = [
            EntityRef(
                ref_id="eref_customer_shanghai_1",
                resource="customer",
                public_id="cus_00000000000000000000000000000001",
                display_name="上海示例客户一",
            ),
            EntityRef(
                ref_id="eref_customer_shanghai_2",
                resource="customer",
                public_id="cus_00000000000000000000000000000002",
                display_name="上海示例客户二",
            ),
        ]
        return CRMQueryResult(
            query_id="qry_real_model_shanghai",
            resource="customer",
            status="SUCCESS",
            rows=[
                {
                    "public_id": ref.public_id,
                    "account_name": ref.display_name,
                    "city": "上海",
                }
                for ref in refs
            ],
            entity_refs=refs,
            total=2,
            applied_filters=spec.filters,
            applied_sorts=spec.sorts,
        )


class EmptyCustomerContextReader:
    async def read(
        self,
        request: CustomerContextRequest,
        context: AgentToolContext,
    ) -> CustomerContextResult:
        return CustomerContextResult(
            customer_ref=request.customer_ref,
            sections={},
            citations=[],
            coverage=CustomerContextCoverage(
                requested=request.sections,
                returned=[],
                unavailable=request.sections,
            ),
            degraded_reasons=["not used by this regression"],
        )


def _required_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        pytest.skip(f"{name} is required for real-model Query Agent regression")
    return value


@pytest.mark.asyncio
async def test_real_model_queries_shanghai_customers_with_authoritative_evidence() -> None:
    executor = RecordingExecutor()
    agent = CRMQueryAgent(CRMReadToolRegistry(executor, EmptyCustomerContextReader()))

    result = await agent.run(
        CRMQueryAgentRequest(
            user_message="我在上海有哪些客户? 请先查询 CRM, 再根据查询结果回答。",
            allowed_tool_names=["query_customers"],
        ),
        AgentToolContext(
            db=Mock(),
            team_id=7,
            user_id=42,
            session_id=11,
            authorization="Bearer real-model-regression",
            permission_codes=frozenset({"customer:view:all"}),
        ),
        CRMQueryAgentModelConfig(
            api_host=_required_env("AI_API_URL"),
            api_key=_required_env("AI_API_KEY"),
            model=_required_env("AI_MODEL"),
            temperature=0.0,
            enable_thinking=False,
        ),
    )

    assert result.response.status == "ANSWERED"
    assert len(executor.calls) == 1
    assert len(result.query_results) == 1
    assert result.query_results[0].query_id == "qry_real_model_shanghai"
    assert result.trace.tool_call_count == 1
    assert result.trace.total_entity_count == 2
    assert set(result.response.evidence_refs) <= {
        "qry_real_model_shanghai",
        "eref_customer_shanghai_1",
        "eref_customer_shanghai_2",
    }
    assert result.response.evidence_refs
