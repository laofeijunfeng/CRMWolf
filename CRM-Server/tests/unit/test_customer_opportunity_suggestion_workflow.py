"""Opportunity-suggestion Agent Workflow parity seam tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.agent.principal import AgentPrincipal
from app.services.agent.tools.base import AgentToolResult
from app.services.agent.workflow.contracts import (
    WorkflowOpportunitySuggestionStart,
    WorkflowRuntimeContext,
    WorkflowSupplement,
    WorkflowTurnInput,
)
from app.services.agent.workflow.execution import CRMWorkflowEffectExecutor
from app.services.agent.workflow.planning import (
    CRMWorkflowPlanner,
    WorkflowPlanningError,
    WorkflowPlanningNeedsInput,
)
from app.services.agent.workflow.resources import (
    OpportunityStageCandidate,
    OpportunityStageResolution,
    OpportunityStageTransitionStep,
    ProcurementMethodResolution,
    WorkflowCustomerCandidate,
)


class _Query:
    def __init__(self, value: object) -> None:
        self.value = value

    def filter(self, *args: object, **kwargs: object) -> _Query:
        return self

    def one_or_none(self) -> object:
        return self.value


class _DB:
    def __init__(self, values: dict[type[object], object]) -> None:
        self.values = values

    def query(self, model: type[object]) -> _Query:
        return _Query(self.values.get(model))


class _CustomerResolver:
    async def validate_cached(self, *, customer_id: str, authorization: str) -> object:
        return SimpleNamespace(
            status="RESOLVED",
            customer=WorkflowCustomerCandidate(customer_id=customer_id, customer_name="上海星云科技有限公司"),
        )


class _ProcurementResolver:
    async def resolve(self, **kwargs: object) -> ProcurementMethodResolution:
        return ProcurementMethodResolution(status="RESOLVED", method_id=7, method_name="默认采购方式")


class _StageResolver:
    def __init__(self, resolution: OpportunityStageResolution) -> None:
        self.resolution = resolution

    async def resolve(self, **kwargs: object) -> OpportunityStageResolution:
        return self.resolution


def _request(action: str, *, supplements: list[WorkflowSupplement] | None = None) -> WorkflowTurnInput:
    return WorkflowTurnInput(
        workflow_id="wf_" + "1" * 32,
        start=WorkflowOpportunitySuggestionStart(
            kind="opportunity_suggestion",
            action=action,
            job_public_id="cosj_test",
        ),
        principal=AgentPrincipal(team_id=1, user_id=2, session_id=3),
        supplements=supplements or [],
    )


def _db(
    *,
    decision: str = "CREATE_OPPORTUNITY",
    payload: dict[str, object] | None = None,
    status: str = "COMPLETED",
) -> _DB:
    job = SimpleNamespace(
        team_id=1,
        public_id="cosj_test",
        status=status,
        activity_id=22,
        activity_revision=3,
        result_json={
            "decision": decision,
            "suggestion": {
                "related_object_id": "opp_existing" if decision == "MOVE_OPPORTUNITY_STAGE" else None,
                "execution_payload": payload or {},
            },
        },
    )
    activity = SimpleNamespace(
        id=22,
        team_id=1,
        activity_revision=3,
        submission_source="AGENT",
        customer_id=33,
    )
    customer = SimpleNamespace(
        id=33,
        team_id=1,
        public_id="cus_33",
        account_name="上海星云科技有限公司",
    )
    return _DB({CustomerOpportunitySuggestionJob: job, CustomerActivity: activity, Customer: customer})


def _runtime(db: _DB) -> WorkflowRuntimeContext:
    return WorkflowRuntimeContext(db=db, authorization="Bearer test")


@pytest.mark.asyncio
async def test_create_suggestion_uses_signed_payload_without_semantic_parser() -> None:
    planner = CRMWorkflowPlanner(
        customer_resolver=_CustomerResolver(),
        opportunity_procurement_method_resolver=_ProcurementResolver(),
    )
    plan = await planner.plan(
        _request("CREATE_OPPORTUNITY"),
        workflow_id="wf_" + "1" * 32,
        runtime=_runtime(
            _db(
                payload={
                    "total_amount": 100000,
                    "user_count": 20,
                    "license_type": "SUBSCRIPTION",
                    "subscription_years": 2,
                    "purchase_type": "NEW",
                    "expected_closing_date": "2026-09-30",
                }
            )
        ),
    )

    assert plan.execution_authorization == "RESUME_AUTHORIZED"
    assert plan.commands[0].tool_name == "create_opportunity"
    assert plan.commands[0].payload["opportunity"] == {
        "customer_id": "cus_33",
        "total_amount": 100000.0,
        "user_count": 20,
        "license_type": "SUBSCRIPTION",
        "purchase_type": "NEW",
        "expected_closing_date": "2026-09-30",
        "procurement_method_id": 7,
        "subscription_years": 2,
    }


@pytest.mark.asyncio
async def test_create_suggestion_returns_embedded_form_then_executes_after_supplement() -> None:
    planner = CRMWorkflowPlanner(
        customer_resolver=_CustomerResolver(),
        opportunity_procurement_method_resolver=_ProcurementResolver(),
    )
    db = _db(payload={"purchase_type": "NEW"})
    request = _request("CREATE_OPPORTUNITY")

    with pytest.raises(WorkflowPlanningNeedsInput) as paused:
        await planner.plan(request, workflow_id=request.workflow_id, runtime=_runtime(db))
    assert paused.value.interaction.interaction_type == "form"
    assert paused.value.interaction.business_action == "collect_opportunity_fields"

    supplemented = request.model_copy(
        update={
            "supplements": [
                WorkflowSupplement(
                    content="已补充商机信息",
                    source="agent_ui",
                    metadata={
                        "business_action": "collect_opportunity_fields",
                        "form_values": {
                            "total_amount": 100000,
                            "user_count": 20,
                            "license_type": "PERPETUAL",
                            "purchase_type": "NEW",
                            "expected_closing_date": "2026-09-30",
                        },
                    },
                )
            ]
        }
    )
    plan = await planner.plan(supplemented, workflow_id=request.workflow_id, runtime=_runtime(db))
    assert plan.execution_authorization == "RESUME_AUTHORIZED"
    assert plan.commands[0].tool_name == "create_opportunity"


@pytest.mark.asyncio
async def test_suggestion_cancel_is_terminal_and_has_no_command() -> None:
    planner = CRMWorkflowPlanner(customer_resolver=_CustomerResolver())
    plan = await planner.plan(
        _request("CANCEL"),
        workflow_id="wf_" + "1" * 32,
        runtime=_runtime(_db()),
    )
    assert plan.terminal_outcome == "CANCELLED"
    assert plan.commands == []


@pytest.mark.asyncio
async def test_move_suggestion_uses_authoritative_stage_resolution() -> None:
    stage_resolver = _StageResolver(
        OpportunityStageResolution(
            status="RESOLVED",
            opportunity=OpportunityStageCandidate("opp_existing", "星云商机", "需求确认"),
            target_stage=OpportunityStageTransitionStep(12, "商务谈判"),
            steps=(OpportunityStageTransitionStep(12, "商务谈判"),),
        )
    )
    planner = CRMWorkflowPlanner(
        customer_resolver=_CustomerResolver(),
        opportunity_stage_resolver=stage_resolver,
    )
    plan = await planner.plan(
        _request("MOVE_OPPORTUNITY_STAGE"),
        workflow_id="wf_" + "1" * 32,
        runtime=_runtime(_db(decision="MOVE_OPPORTUNITY_STAGE", payload={"stage_template_id": 12})),
    )
    assert plan.execution_authorization == "RESUME_AUTHORIZED"
    assert plan.commands[0].payload == {
        "opportunity_id": "opp_existing",
        "stage_template_id": 12,
    }


@pytest.mark.asyncio
async def test_move_suggestion_stale_resolution_is_ignored_without_write_command() -> None:
    planner = CRMWorkflowPlanner(
        customer_resolver=_CustomerResolver(),
        opportunity_stage_resolver=_StageResolver(OpportunityStageResolution(status="NOT_FOUND")),
    )
    plan = await planner.plan(
        _request("MOVE_OPPORTUNITY_STAGE"),
        workflow_id="wf_" + "1" * 32,
        runtime=_runtime(_db(decision="MOVE_OPPORTUNITY_STAGE", payload={"stage_template_id": 12})),
    )
    assert plan.terminal_outcome == "SKIPPED"
    assert plan.commands == []


class _ToolRegistry:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        name: str,
        context: object,
        payload: dict[str, object],
        *,
        policy: object,
    ) -> AgentToolResult:
        self.calls.append({"name": name, "payload": payload, "policy": policy})
        return AgentToolResult(tool_name=name, success=True, data={"public_id": "opp_new"})


@pytest.mark.asyncio
async def test_suggestion_resume_plan_carries_user_confirmation_to_write_guardrail() -> None:
    planner = CRMWorkflowPlanner(
        customer_resolver=_CustomerResolver(),
        opportunity_procurement_method_resolver=_ProcurementResolver(),
    )
    request = _request("CREATE_OPPORTUNITY")
    plan = await planner.plan(
        request,
        workflow_id=request.workflow_id,
        runtime=_runtime(
            _db(
                payload={
                    "total_amount": 100000,
                    "user_count": 20,
                    "license_type": "PERPETUAL",
                    "purchase_type": "NEW",
                    "expected_closing_date": "2026-09-30",
                }
            )
        ),
    )
    registry = _ToolRegistry()
    result = await CRMWorkflowEffectExecutor(tool_registry=registry).execute(
        plan,
        workflow_id=request.workflow_id,
        request=request,
        runtime=_runtime(_DB({})),
    )
    assert result.success is True
    assert registry.calls[0]["name"] == "create_opportunity"
    policy = registry.calls[0]["policy"]
    assert policy.hitl_decision == "approve"
    assert policy.authorization_source == "workflow_suggestion_user_confirmed"


@pytest.mark.asyncio
async def test_deleted_source_activity_cannot_resume_suggestion() -> None:
    planner = CRMWorkflowPlanner(customer_resolver=_CustomerResolver())
    db = _db(payload={"total_amount": 1})
    db.values[CustomerActivity] = None
    with pytest.raises(Exception) as exc_info:
        await planner.plan(
            _request("CREATE_OPPORTUNITY"),
            workflow_id="wf_" + "1" * 32,
            runtime=_runtime(db),
        )
    assert getattr(exc_info.value, "code", None) == "WORKFLOW_SUGGESTION_SOURCE_DELETED"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["SKIPPED", "EXHAUSTED"])
async def test_terminal_suggestion_job_cannot_resume_crm_write(status: str) -> None:
    planner = CRMWorkflowPlanner(customer_resolver=_CustomerResolver())

    with pytest.raises(WorkflowPlanningError) as exc_info:
        await planner.plan(
            _request("CREATE_OPPORTUNITY"),
            workflow_id="wf_" + "1" * 32,
            runtime=_runtime(_db(status=status)),
        )

    assert exc_info.value.code == "WORKFLOW_SUGGESTION_NOT_READY"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("activity_revision", "submission_source"),
    [(4, "AGENT"), (3, "FORM")],
)
async def test_suggestion_resume_rejects_stale_or_non_agent_source(
    activity_revision: int,
    submission_source: str,
) -> None:
    planner = CRMWorkflowPlanner(customer_resolver=_CustomerResolver())
    db = _db()
    db.values[CustomerActivity].activity_revision = activity_revision
    db.values[CustomerActivity].submission_source = submission_source

    with pytest.raises(WorkflowPlanningError) as exc_info:
        await planner.plan(
            _request("CREATE_OPPORTUNITY"),
            workflow_id="wf_" + "1" * 32,
            runtime=_runtime(db),
        )

    assert exc_info.value.code == "WORKFLOW_SUGGESTION_SOURCE_STALE"
