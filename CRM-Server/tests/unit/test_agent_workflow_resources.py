"""Authoritative Workflow planning resource resolution behavior."""

from __future__ import annotations

import pytest

from app.services.agent.query import EntityRef
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.workflow.resources import (
    CRMCustomerMemberResolver,
    CRMFollowUpTaskResolver,
    CRMOpportunityProcurementMethodResolver,
    CRMOpportunityStageResolver,
    CRMWorkflowCustomerResolver,
    WorkflowResourceResolutionError,
)


class FakeCRMAPIClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def request(
        self,
        method: str,
        path: str,
        authorization: str,
        **kwargs: object,
    ) -> object:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                "kwargs": kwargs,
            }
        )
        return self.response


async def test_workflow_customer_resolver_uses_authoritative_identity_resolution_api() -> None:
    api_client = FakeCRMAPIClient(
        {
            "decision": "auto_select",
            "items": [
                {
                    "id": "cus_fanya_001",
                    "account_name": "广州凡亚信息科技有限公司",
                    "city": "广州",
                    "match": {
                        "score": 0.99,
                        "source": "generated_match_term",
                        "reason": "客户简称匹配",
                    },
                }
            ],
            "related_customers": [],
            "metadata": {"identity_decision": "auto_select"},
        }
    )
    resolver = CRMWorkflowCustomerResolver(api_client=api_client)

    resolution = await resolver.resolve(
        explicit_customer_name="凡亚信息",
        context_customer=EntityRef(
            ref_id="eref_customer_old",
            resource="customer",
            public_id="cus_old",
            display_name="旧页面客户",
        ),
        selected_customer_id=None,
        authorization="Bearer signed-token",
    )

    assert resolution.status == "RESOLVED"
    assert resolution.customer is not None
    assert resolution.customer.customer_id == "cus_fanya_001"
    assert api_client.calls == [
        {
            "method": "GET",
            "path": "/v1/customers/identity-resolution",
            "authorization": "Bearer signed-token",
            "kwargs": {"params": {"query": "凡亚信息", "limit": 10}},
        }
    ]


async def test_workflow_customer_resolver_uses_page_context_without_identity_api_when_text_has_no_customer() -> None:
    api_client = FakeCRMAPIClient({"unexpected": True})
    resolver = CRMWorkflowCustomerResolver(api_client=api_client)

    resolution = await resolver.resolve(
        explicit_customer_name=None,
        context_customer=EntityRef(
            ref_id="eref_customer_context",
            resource="customer",
            public_id="cus_context_001",
            display_name="上海星云科技有限公司",
        ),
        selected_customer_id=None,
        authorization="Bearer signed-token",
    )

    assert resolution.status == "RESOLVED"
    assert resolution.customer is not None
    assert resolution.customer.customer_id == "cus_context_001"
    assert api_client.calls == []


async def test_workflow_customer_resolver_requires_selection_for_ambiguous_identity() -> None:
    api_client = FakeCRMAPIClient(
        {
            "decision": "requires_confirmation",
            "items": [
                {
                    "id": "cus_fanya_guangzhou",
                    "account_name": "广州凡亚信息科技有限公司",
                    "city": "广州",
                    "match": {"score": 0.94},
                },
                {
                    "id": "cus_fanya_shenzhen",
                    "account_name": "深圳凡亚信息科技有限公司",
                    "city": "深圳",
                    "match": {"score": 0.92},
                },
            ],
            "related_customers": [],
            "metadata": {"identity_decision": "requires_confirmation"},
        }
    )
    resolver = CRMWorkflowCustomerResolver(api_client=api_client)

    resolution = await resolver.resolve(
        explicit_customer_name="凡亚信息",
        context_customer=None,
        selected_customer_id=None,
        authorization="Bearer signed-token",
    )

    assert resolution.status == "SELECTION_REQUIRED"
    assert [candidate.customer_id for candidate in resolution.candidates] == [
        "cus_fanya_guangzhou",
        "cus_fanya_shenzhen",
    ]


async def test_workflow_customer_resolver_revalidates_signed_selection_against_current_candidates() -> None:
    payload = {
        "decision": "requires_confirmation",
        "items": [
            {
                "id": "cus_fanya_guangzhou",
                "account_name": "广州凡亚信息科技有限公司",
                "city": "广州",
                "match": {"score": 0.94},
            },
            {
                "id": "cus_fanya_shenzhen",
                "account_name": "深圳凡亚信息科技有限公司",
                "city": "深圳",
                "match": {"score": 0.92},
            },
        ],
        "related_customers": [],
        "metadata": {"identity_decision": "requires_confirmation"},
    }
    resolver = CRMWorkflowCustomerResolver(api_client=FakeCRMAPIClient(payload))

    selected = await resolver.resolve(
        explicit_customer_name="凡亚信息",
        context_customer=None,
        selected_customer_id="cus_fanya_shenzhen",
        authorization="Bearer signed-token",
    )
    stale = await resolver.resolve(
        explicit_customer_name="凡亚信息",
        context_customer=None,
        selected_customer_id="cus_removed",
        authorization="Bearer signed-token",
    )

    assert selected.status == "RESOLVED"
    assert selected.customer is not None
    assert selected.customer.customer_id == "cus_fanya_shenzhen"
    assert stale.status == "SELECTION_REQUIRED"
    assert [candidate.customer_id for candidate in stale.candidates] == [
        "cus_fanya_guangzhou",
        "cus_fanya_shenzhen",
    ]


@pytest.mark.parametrize("decision", ["no_match", "semantic_related_only"])
async def test_workflow_customer_resolver_never_binds_non_identity_results(decision: str) -> None:
    resolver = CRMWorkflowCustomerResolver(
        api_client=FakeCRMAPIClient(
            {
                "decision": decision,
                "items": [],
                "related_customers": [
                    {
                        "id": "cus_semantic_only",
                        "account_name": "语义相关但未形成身份匹配的客户",
                        "city": "上海",
                        "match": {"score": 0.99, "source": "customer_knowledge"},
                    }
                ],
                "metadata": {"identity_decision": decision},
            }
        )
    )

    resolution = await resolver.resolve(
        explicit_customer_name="凡亚信息",
        context_customer=None,
        selected_customer_id=None,
        authorization="Bearer signed-token",
    )

    assert resolution.status == "NOT_FOUND"
    assert resolution.customer is None


async def test_workflow_customer_resolver_maps_server_failure_to_retryable_error() -> None:
    class FailingCRMAPIClient:
        async def request(self, *args: object, **kwargs: object) -> object:
            raise CRMAPIClientError("upstream failed", status_code=503)

    resolver = CRMWorkflowCustomerResolver(api_client=FailingCRMAPIClient())

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            explicit_customer_name="凡亚信息",
            context_customer=None,
            selected_customer_id=None,
            authorization="Bearer signed-token",
        )

    assert exc_info.value.retryable is True
    assert exc_info.value.message == "客户信息暂时无法读取。"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "decision": "auto_select",
            "items": [{"id": "17", "account_name": "内部主键泄漏", "city": None, "match": {}}],
            "related_customers": [],
            "metadata": {},
        },
        {
            "decision": "auto_select",
            "items": [{"id": "cus_valid", "account_name": "客户", "city": None, "match": {}}],
            "related_customers": [],
            "metadata": {},
            "unexpected": True,
        },
    ],
)
async def test_workflow_customer_resolver_fails_closed_on_invalid_identity_contract(payload: object) -> None:
    resolver = CRMWorkflowCustomerResolver(api_client=FakeCRMAPIClient(payload))

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            explicit_customer_name="凡亚信息",
            context_customer=None,
            selected_customer_id=None,
            authorization="Bearer signed-token",
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "客户查询结果无效。"


async def test_customer_member_resolver_reads_authorized_candidates_and_resolves_exact_name() -> None:
    api_client = FakeCRMAPIClient(
        [
            {
                "id": "9",
                "name": "张三",
                "avatar_url": None,
                "roles": ["presales"],
                "already_member": False,
            },
            {
                "id": "10",
                "name": "李四",
                "avatar_url": None,
                "roles": ["sales"],
                "already_member": False,
            },
        ]
    )
    resolver = CRMCustomerMemberResolver(api_client=api_client)

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        user_name=" 张 三 ",
        authorization="Bearer signed-token",
    )

    assert resolution.status == "RESOLVED"
    assert resolution.user_id == "9"
    assert resolution.user_name == "张三"
    assert api_client.calls == [
        {
            "method": "GET",
            "path": "/v1/customers/cus_shanghai_001/member-candidates",
            "authorization": "Bearer signed-token",
            "kwargs": {},
        }
    ]


async def test_customer_member_resolver_requires_signed_selection_for_duplicate_names() -> None:
    api_client = FakeCRMAPIClient(
        [
            {
                "id": "9",
                "name": "张三",
                "avatar_url": None,
                "roles": ["sales"],
                "already_member": False,
            },
            {
                "id": "10",
                "name": "张三",
                "avatar_url": None,
                "roles": ["presales"],
                "already_member": False,
            },
        ]
    )
    resolver = CRMCustomerMemberResolver(api_client=api_client)

    ambiguous = await resolver.resolve(
        customer_id="cus_shanghai_001",
        user_name="张三",
        authorization="Bearer signed-token",
    )
    selected = await resolver.resolve(
        customer_id="cus_shanghai_001",
        user_name="张三",
        authorization="Bearer signed-token",
        selected_user_id="10",
    )

    assert ambiguous.status == "AMBIGUOUS"
    assert [candidate.user_id for candidate in ambiguous.candidates] == ["9", "10"]
    assert selected.status == "RESOLVED"
    assert selected.user_id == "10"


async def test_customer_member_resolver_fails_closed_on_invalid_api_contract() -> None:
    resolver = CRMCustomerMemberResolver(
        api_client=FakeCRMAPIClient(
            [
                {
                    "id": 9,
                    "name": "张三",
                    "roles": [],
                    "already_member": False,
                }
            ]
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            customer_id="cus_shanghai_001",
            user_name="张三",
            authorization="Bearer signed-token",
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "客户成员候选人数据无效。"


class RoutedFakeCRMAPIClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def request(
        self,
        method: str,
        path: str,
        authorization: str,
        **kwargs: object,
    ) -> object:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                "kwargs": kwargs,
            }
        )
        return self.responses[path]


async def test_opportunity_procurement_resolver_uses_only_active_authorized_customer_default() -> None:
    api_client = RoutedFakeCRMAPIClient(
        {
            "/v1/customers/cus_shanghai_001/default-procurement-method": {
                "procurement_method_id": 8,
                "code": "PUBLIC_BIDDING",
                "name": "公开招标",
                "description": None,
            },
            "/v1/procurement-methods/options": [
                {"id": 8, "code": "PUBLIC_BIDDING", "name": "公开招标"},
                {"id": 9, "code": "DIRECT_PURCHASE", "name": "直接采购"},
            ],
        }
    )
    resolver = CRMOpportunityProcurementMethodResolver(api_client=api_client)

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
    )

    assert resolution.status == "RESOLVED"
    assert resolution.method_id == 8
    assert resolution.method_name == "公开招标"
    assert [call["path"] for call in api_client.calls] == [
        "/v1/customers/cus_shanghai_001/default-procurement-method",
        "/v1/procurement-methods/options",
    ]


async def test_opportunity_procurement_resolver_requires_selection_and_revalidates_signed_id() -> None:
    api_client = RoutedFakeCRMAPIClient(
        {
            "/v1/customers/cus_shanghai_001/default-procurement-method": {
                "procurement_method_id": None,
                "message": "客户未设置默认采购方式",
            },
            "/v1/procurement-methods/options": [
                {"id": 8, "code": "PUBLIC_BIDDING", "name": "公开招标"},
                {"id": 9, "code": "DIRECT_PURCHASE", "name": "直接采购"},
            ],
        }
    )
    resolver = CRMOpportunityProcurementMethodResolver(api_client=api_client)

    unresolved = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
    )
    selected = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        selected_method_id=9,
    )
    stale = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        selected_method_id=99,
    )

    assert unresolved.status == "SELECTION_REQUIRED"
    assert [candidate.method_id for candidate in unresolved.candidates] == [8, 9]
    assert selected.status == "RESOLVED"
    assert selected.method_id == 9
    assert selected.method_name == "直接采购"
    assert stale.status == "NOT_FOUND"


async def test_opportunity_procurement_resolver_fails_closed_on_invalid_contract() -> None:
    resolver = CRMOpportunityProcurementMethodResolver(
        api_client=RoutedFakeCRMAPIClient(
            {
                "/v1/customers/cus_shanghai_001/default-procurement-method": {
                    "procurement_method_id": None,
                    "message": "客户未设置默认采购方式",
                },
                "/v1/procurement-methods/options": [{"id": "8", "code": "PUBLIC_BIDDING", "name": "公开招标"}],
            }
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            customer_id="cus_shanghai_001",
            authorization="Bearer signed-token",
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "商机采购方式数据无效。"


def opportunity_item(
    *,
    opportunity_id: str,
    name: str,
    customer_id: str = "cus_shanghai_001",
    status: int = 0,
    approval_phase: str = "approved",
    current_stage_name: str | None = "需求确认",
) -> dict[str, object]:
    return {
        "id": opportunity_id,
        "public_id": opportunity_id,
        "opportunity_name": name,
        "customer_id": customer_id,
        "status": status,
        "approval_phase": approval_phase,
        "stage": ({"stage_name": current_stage_name} if current_stage_name is not None else None),
    }


def opportunity_page(*items: dict[str, object]) -> dict[str, object]:
    return {
        "items": list(items),
        "total": len(items),
        "page": 1,
        "page_size": 100,
        "total_pages": 1 if items else 0,
    }


def procurement_stages(
    *,
    current_stage_id: int | None = 11,
) -> list[dict[str, object]]:
    return [
        {
            "id": 11,
            "stage_name": "需求确认",
            "win_probability": 20,
            "sort_order": 1,
            "is_current": current_stage_id == 11,
            "is_default_start": True,
            "can_skip": False,
        },
        {
            "id": 12,
            "stage_name": "方案评估",
            "win_probability": 40,
            "sort_order": 2,
            "is_current": current_stage_id == 12,
            "is_default_start": False,
            "can_skip": False,
        },
        {
            "id": 13,
            "stage_name": "商务谈判",
            "win_probability": 70,
            "sort_order": 3,
            "is_current": current_stage_id == 13,
            "is_default_start": False,
            "can_skip": False,
        },
    ]


class OpportunityStageFakeCRMAPIClient:
    def __init__(
        self,
        *,
        opportunities: object,
        stages_by_opportunity: dict[str, object],
    ) -> None:
        self.opportunities = opportunities
        self.stages_by_opportunity = stages_by_opportunity
        self.calls: list[dict[str, object]] = []

    async def request(
        self,
        method: str,
        path: str,
        authorization: str,
        **kwargs: object,
    ) -> object:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                "kwargs": kwargs,
            }
        )
        if path == "/v1/opportunities/":
            return self.opportunities
        prefix = "/v1/opportunities/"
        suffix = "/procurement-stages"
        if path.startswith(prefix) and path.endswith(suffix):
            opportunity_id = path[len(prefix) : -len(suffix)]
            return self.stages_by_opportunity[opportunity_id]
        raise AssertionError(f"unexpected CRM API path: {path}")


class PaginatedOpportunityStageFakeCRMAPIClient:
    def __init__(self, *, pages_by_skip: dict[int, object]) -> None:
        self.pages_by_skip = pages_by_skip

    async def request(
        self,
        method: str,
        path: str,
        authorization: str,
        **kwargs: object,
    ) -> object:
        assert method == "GET"
        assert path == "/v1/opportunities/"
        assert authorization == "Bearer signed-token"
        params = kwargs.get("params")
        assert isinstance(params, dict)
        skip = params.get("skip", 0)
        assert isinstance(skip, int)
        return self.pages_by_skip[skip]


async def test_opportunity_stage_resolver_does_not_replace_unknown_explicit_id_with_only_candidate() -> None:
    api_client = OpportunityStageFakeCRMAPIClient(
        opportunities=opportunity_page(
            opportunity_item(
                opportunity_id="opp_authoritative",
                name="权威商机",
            )
        ),
        stages_by_opportunity={},
    )
    resolver = CRMOpportunityStageResolver(api_client=api_client)

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id="opp_model_forged",
        opportunity_reference_text=None,
        target_stage_name="方案评估",
    )

    assert resolution.status == "NOT_FOUND"
    assert len(api_client.calls) == 1


async def test_opportunity_stage_resolver_fails_closed_on_incomplete_pagination() -> None:
    first_page_items = [
        opportunity_item(opportunity_id=f"opp_{index:03d}", name=f"商机 {index}")
        for index in range(100)
    ]
    resolver = CRMOpportunityStageResolver(
        api_client=PaginatedOpportunityStageFakeCRMAPIClient(
            pages_by_skip={
                0: {
                    "items": first_page_items,
                    "total": 101,
                    "page": 1,
                    "page_size": 100,
                    "total_pages": 2,
                },
                100: {
                    "items": [],
                    "total": 101,
                    "page": 2,
                    "page_size": 100,
                    "total_pages": 2,
                },
            }
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            customer_id="cus_shanghai_001",
            authorization="Bearer signed-token",
            opportunity_id=None,
            opportunity_reference_text=None,
            target_stage_name=None,
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "商机列表数据无效。"


async def test_opportunity_stage_resolver_resolves_unique_next_stage() -> None:
    api_client = OpportunityStageFakeCRMAPIClient(
        opportunities=opportunity_page(
            opportunity_item(
                opportunity_id="opp_shanghai_001",
                name="星云企业版采购",
            )
        ),
        stages_by_opportunity={"opp_shanghai_001": procurement_stages()},
    )
    resolver = CRMOpportunityStageResolver(api_client=api_client)

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text="星云企业版采购",
        target_stage_name=None,
    )

    assert resolution.status == "RESOLVED"
    assert resolution.opportunity is not None
    assert resolution.opportunity.opportunity_id == "opp_shanghai_001"
    assert resolution.target_stage is not None
    assert resolution.target_stage.stage_template_id == 12
    assert [step.stage_template_id for step in resolution.steps] == [12]
    assert api_client.calls == [
        {
            "method": "GET",
            "path": "/v1/opportunities/",
            "authorization": "Bearer signed-token",
            "kwargs": {
                "params": {
                    "customer_id": "cus_shanghai_001",
                    "status": 0,
                    "limit": 100,
                }
            },
        },
        {
            "method": "GET",
            "path": "/v1/opportunities/opp_shanghai_001/procurement-stages",
            "authorization": "Bearer signed-token",
            "kwargs": {},
        },
    ]


async def test_opportunity_stage_resolver_expands_all_intermediate_steps() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(
                opportunity_item(
                    opportunity_id="opp_shanghai_001",
                    name="星云企业版采购",
                )
            ),
            stages_by_opportunity={"opp_shanghai_001": procurement_stages()},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text="星云企业版采购",
        target_stage_name="商务谈判",
    )

    assert resolution.status == "RESOLVED"
    assert [step.stage_template_id for step in resolution.steps] == [12, 13]
    assert [step.stage_name for step in resolution.steps] == ["方案评估", "商务谈判"]


async def test_opportunity_stage_resolver_requires_opportunity_selection() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(
                opportunity_item(opportunity_id="opp_001", name="星云企业版采购"),
                opportunity_item(opportunity_id="opp_002", name="星云私有化采购"),
            ),
            stages_by_opportunity={},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name="方案评估",
    )

    assert resolution.status == "OPPORTUNITY_SELECTION_REQUIRED"
    assert [candidate.opportunity_id for candidate in resolution.opportunity_candidates] == [
        "opp_001",
        "opp_002",
    ]


async def test_opportunity_stage_resolver_revalidates_canonical_opportunity_selection() -> None:
    api_client = OpportunityStageFakeCRMAPIClient(
        opportunities=opportunity_page(
            opportunity_item(opportunity_id="opp_001", name="星云企业版采购"),
            opportunity_item(opportunity_id="opp_002", name="星云私有化采购"),
        ),
        stages_by_opportunity={"opp_002": procurement_stages()},
    )
    resolver = CRMOpportunityStageResolver(api_client=api_client)

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id="opp_model_forged",
        opportunity_reference_text="星云企业版采购",
        target_stage_name="方案评估",
        selected_opportunity_id="opp_002",
    )

    assert resolution.status == "RESOLVED"
    assert resolution.opportunity is not None
    assert resolution.opportunity.opportunity_id == "opp_002"
    assert api_client.calls[-1]["path"] == "/v1/opportunities/opp_002/procurement-stages"


async def test_opportunity_stage_resolver_rejects_stale_canonical_opportunity_selection() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(
                opportunity_item(opportunity_id="opp_001", name="星云企业版采购"),
                opportunity_item(opportunity_id="opp_002", name="星云私有化采购"),
            ),
            stages_by_opportunity={},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name="方案评估",
        selected_opportunity_id="opp_stale",
    )

    assert resolution.status == "OPPORTUNITY_SELECTION_REQUIRED"
    assert [candidate.opportunity_id for candidate in resolution.opportunity_candidates] == [
        "opp_001",
        "opp_002",
    ]


async def test_opportunity_stage_resolver_requires_selection_for_ambiguous_stage_name() -> None:
    stages = procurement_stages()
    stages[1]["stage_name"] = "方案初评"
    stages[2]["stage_name"] = "方案终评"
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(opportunity_item(opportunity_id="opp_001", name="星云企业版采购")),
            stages_by_opportunity={"opp_001": stages},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name="方案",
    )

    assert resolution.status == "STAGE_SELECTION_REQUIRED"
    assert resolution.opportunity is not None
    assert [candidate.stage_template_id for candidate in resolution.stage_candidates] == [12, 13]


async def test_opportunity_stage_resolver_revalidates_canonical_stage_selection() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(opportunity_item(opportunity_id="opp_001", name="星云企业版采购")),
            stages_by_opportunity={"opp_001": procurement_stages()},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name="模型伪造阶段",
        selected_stage_id=13,
    )

    assert resolution.status == "RESOLVED"
    assert [step.stage_template_id for step in resolution.steps] == [12, 13]


async def test_opportunity_stage_resolver_rejects_stale_canonical_stage_selection() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(opportunity_item(opportunity_id="opp_001", name="星云企业版采购")),
            stages_by_opportunity={"opp_001": procurement_stages()},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name=None,
        selected_stage_id=99,
    )

    assert resolution.status == "STAGE_SELECTION_REQUIRED"
    assert [candidate.stage_template_id for candidate in resolution.stage_candidates] == [12, 13]


@pytest.mark.parametrize("target_stage_name", ["需求确认", "需求"])
async def test_opportunity_stage_resolver_does_not_move_to_current_or_previous_stage(
    target_stage_name: str,
) -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(
                opportunity_item(
                    opportunity_id="opp_001",
                    name="星云企业版采购",
                    current_stage_name="方案评估",
                )
            ),
            stages_by_opportunity={"opp_001": procurement_stages(current_stage_id=12)},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name=target_stage_name,
    )

    assert resolution.status == "NOT_FOUND"
    assert resolution.steps == ()


async def test_opportunity_stage_resolver_starts_from_authoritative_default_stage() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(
                opportunity_item(
                    opportunity_id="opp_001",
                    name="星云企业版采购",
                    current_stage_name=None,
                )
            ),
            stages_by_opportunity={"opp_001": procurement_stages(current_stage_id=None)},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name="方案评估",
    )

    assert resolution.status == "RESOLVED"
    assert [step.stage_template_id for step in resolution.steps] == [11, 12]


async def test_opportunity_stage_resolver_filters_non_authoritative_list_items() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(
                opportunity_item(opportunity_id="opp_valid", name="有效商机"),
                opportunity_item(
                    opportunity_id="opp_other_customer",
                    name="其他客户商机",
                    customer_id="cus_other",
                ),
                opportunity_item(
                    opportunity_id="opp_won",
                    name="已赢单商机",
                    status=1,
                ),
                opportunity_item(
                    opportunity_id="opp_draft",
                    name="草稿商机",
                    approval_phase="draft",
                ),
            ),
            stages_by_opportunity={"opp_valid": procurement_stages()},
        )
    )

    resolution = await resolver.resolve(
        customer_id="cus_shanghai_001",
        authorization="Bearer signed-token",
        opportunity_id=None,
        opportunity_reference_text=None,
        target_stage_name=None,
    )

    assert resolution.status == "RESOLVED"
    assert resolution.opportunity is not None
    assert resolution.opportunity.opportunity_id == "opp_valid"


async def test_opportunity_stage_resolver_fails_closed_on_invalid_list_contract() -> None:
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities={
                "items": [
                    opportunity_item(
                        opportunity_id="opp_001",
                        name="星云企业版采购",
                        status=True,
                    )
                ],
                "total": 1,
                "page": 1,
                "page_size": 100,
                "total_pages": 1,
            },
            stages_by_opportunity={},
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            customer_id="cus_shanghai_001",
            authorization="Bearer signed-token",
            opportunity_id=None,
            opportunity_reference_text=None,
            target_stage_name=None,
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "商机列表数据无效。"


async def test_opportunity_stage_resolver_fails_closed_on_invalid_stage_contract() -> None:
    invalid_stages = procurement_stages()
    invalid_stages[1]["id"] = "12"
    resolver = CRMOpportunityStageResolver(
        api_client=OpportunityStageFakeCRMAPIClient(
            opportunities=opportunity_page(opportunity_item(opportunity_id="opp_001", name="星云企业版采购")),
            stages_by_opportunity={"opp_001": invalid_stages},
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            customer_id="cus_shanghai_001",
            authorization="Bearer signed-token",
            opportunity_id=None,
            opportunity_reference_text=None,
            target_stage_name=None,
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "商机采购阶段数据无效。"


FOLLOW_UP_TASK_ID_1 = "fut_00000000000000000000000000000001"
FOLLOW_UP_TASK_ID_2 = "fut_00000000000000000000000000000002"


def follow_up_task_item(
    task_id: str,
    *,
    owner_id: object = "2",
    status: object = "open",
    title: object = "确认预算审批",
    customer_id: str = "cus_shanghai_001",
) -> dict[str, object]:
    return {
        "id": task_id,
        "public_id": task_id,
        "customer": {
            "id": customer_id,
            "public_id": customer_id,
            "name": "上海星云科技有限公司",
            "account_name": "上海星云科技有限公司",
        },
        "owner_id": owner_id,
        "title": title,
        "status": status,
        "due_at": "2026-08-26T10:00:00",
    }


class FollowUpTaskFakeCRMAPIClient:
    def __init__(
        self,
        *,
        details: dict[str, object] | None = None,
        pages: dict[int, object] | None = None,
    ) -> None:
        self.details = details or {}
        self.pages = pages or {}
        self.calls: list[dict[str, object]] = []

    async def request(
        self,
        method: str,
        path: str,
        authorization: str,
        **kwargs: object,
    ) -> object:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                "kwargs": kwargs,
            }
        )
        if path == "/v1/follow-up-tasks":
            params = kwargs["params"]
            assert isinstance(params, dict)
            response = self.pages[int(params["skip"])]
        else:
            response = self.details[path]
        if isinstance(response, Exception):
            raise response
        return response


async def test_follow_up_task_resolver_reads_explicit_task_from_authoritative_detail() -> None:
    api_client = FollowUpTaskFakeCRMAPIClient(
        details={
            f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_1}": follow_up_task_item(
                FOLLOW_UP_TASK_ID_1
            )
        }
    )
    resolver = CRMFollowUpTaskResolver(api_client=api_client)

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
        task_id=FOLLOW_UP_TASK_ID_1,
    )

    assert resolution.status == "RESOLVED"
    assert resolution.task is not None
    assert resolution.task.task_id == FOLLOW_UP_TASK_ID_1
    assert resolution.task.customer_id == "cus_shanghai_001"
    assert api_client.calls == [
        {
            "method": "GET",
            "path": f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_1}",
            "authorization": "Bearer signed-token",
            "kwargs": {},
        }
    ]


@pytest.mark.parametrize(
    ("owner_id", "status"),
    [
        ("9", "open"),
        ("2", "completed"),
        ("2", "cancelled"),
    ],
)
async def test_follow_up_task_resolver_hides_non_updatable_detail(
    owner_id: str,
    status: str,
) -> None:
    resolver = CRMFollowUpTaskResolver(
        api_client=FollowUpTaskFakeCRMAPIClient(
            details={
                f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_1}": follow_up_task_item(
                    FOLLOW_UP_TASK_ID_1,
                    owner_id=owner_id,
                    status=status,
                )
            }
        )
    )

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
        task_id=FOLLOW_UP_TASK_ID_1,
    )

    assert resolution.status == "NOT_FOUND"
    assert resolution.task is None


@pytest.mark.parametrize("status_code", [403, 404])
async def test_follow_up_task_resolver_does_not_disclose_forbidden_or_missing_detail(
    status_code: int,
) -> None:
    resolver = CRMFollowUpTaskResolver(
        api_client=FollowUpTaskFakeCRMAPIClient(
            details={
                f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_1}": CRMAPIClientError(
                    "not visible",
                    status_code=status_code,
                )
            }
        )
    )

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
        task_id=FOLLOW_UP_TASK_ID_1,
    )

    assert resolution.status == "NOT_FOUND"


async def test_follow_up_task_resolver_requires_selection_for_multiple_authorized_open_tasks() -> None:
    api_client = FollowUpTaskFakeCRMAPIClient(
        pages={
            0: {
                "items": [
                    follow_up_task_item(FOLLOW_UP_TASK_ID_1, title="确认合同条款"),
                    follow_up_task_item(FOLLOW_UP_TASK_ID_2, title="确认预算审批"),
                ],
                "total": 2,
            }
        }
    )
    resolver = CRMFollowUpTaskResolver(api_client=api_client)

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
    )

    assert resolution.status == "SELECTION_REQUIRED"
    assert [candidate.task_id for candidate in resolution.candidates] == [
        FOLLOW_UP_TASK_ID_1,
        FOLLOW_UP_TASK_ID_2,
    ]
    assert api_client.calls[0]["kwargs"] == {
        "params": {
            "status": "open",
            "owner_scope": "mine",
            "skip": 0,
            "limit": 100,
        }
    }


async def test_follow_up_task_resolver_reloads_server_signed_selection_from_detail() -> None:
    api_client = FollowUpTaskFakeCRMAPIClient(
        details={
            f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_2}": follow_up_task_item(
                FOLLOW_UP_TASK_ID_2
            )
        }
    )
    resolver = CRMFollowUpTaskResolver(api_client=api_client)

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
        selected_task_id=FOLLOW_UP_TASK_ID_2,
    )

    assert resolution.status == "RESOLVED"
    assert resolution.task is not None
    assert resolution.task.task_id == FOLLOW_UP_TASK_ID_2
    assert [call["path"] for call in api_client.calls] == [
        f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_2}"
    ]


@pytest.mark.parametrize(
    "pages",
    [
        {
            0: {"items": [follow_up_task_item(FOLLOW_UP_TASK_ID_1)], "total": 2},
            1: {"items": [follow_up_task_item(FOLLOW_UP_TASK_ID_2)], "total": 3},
        },
        {
            0: {"items": [follow_up_task_item(FOLLOW_UP_TASK_ID_1)], "total": 2},
            1: {"items": [], "total": 2},
        },
        {
            0: {"items": [follow_up_task_item(FOLLOW_UP_TASK_ID_1)], "total": 2},
            1: {"items": [follow_up_task_item(FOLLOW_UP_TASK_ID_1)], "total": 2},
        },
    ],
    ids=["total-changed", "empty-before-total", "duplicate-public-id"],
)
async def test_follow_up_task_resolver_fails_closed_on_inconsistent_pagination(
    pages: dict[int, object],
) -> None:
    resolver = CRMFollowUpTaskResolver(
        api_client=FollowUpTaskFakeCRMAPIClient(pages=pages)
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            authorization="Bearer signed-token",
            user_id=2,
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "跟进任务列表数据无效。"


async def test_follow_up_task_resolver_fails_closed_on_invalid_detail_contract() -> None:
    resolver = CRMFollowUpTaskResolver(
        api_client=FollowUpTaskFakeCRMAPIClient(
            details={
                f"/v1/follow-up-tasks/{FOLLOW_UP_TASK_ID_1}": follow_up_task_item(
                    FOLLOW_UP_TASK_ID_1,
                    owner_id=2,
                )
            }
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            authorization="Bearer signed-token",
            user_id=2,
            task_id=FOLLOW_UP_TASK_ID_1,
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "跟进任务数据无效。"


async def test_follow_up_task_resolver_fails_closed_on_invalid_list_contract() -> None:
    resolver = CRMFollowUpTaskResolver(
        api_client=FollowUpTaskFakeCRMAPIClient(
            pages={
                0: {
                    "items": [
                        follow_up_task_item(
                            "fut_not-a-real-public-id",
                        )
                    ],
                    "total": 1,
                }
            }
        )
    )

    with pytest.raises(WorkflowResourceResolutionError) as exc_info:
        await resolver.resolve(
            authorization="Bearer signed-token",
            user_id=2,
        )

    assert exc_info.value.retryable is False
    assert exc_info.value.message == "跟进任务列表数据无效。"

async def test_follow_up_confirmation_case_resolver_reads_only_authoritative_owned_case() -> None:
    from app.services.agent.workflow.resources import CRMFollowUpTaskConfirmationCaseResolver

    api_client = FakeCRMAPIClient(
        {
            "id": "fuc_00000000000000000000000000000001",
            "public_id": "fuc_00000000000000000000000000000001",
            "status": "PENDING",
            "owner_id": "2",
            "question_text": "跟进任务是否已经完成?",
            "suggested_action": "COMPLETE",
            "customer": {
                "id": "cus_shanghai_001",
                "public_id": "cus_shanghai_001",
                "name": "上海客户",
                "account_name": "上海客户",
            },
            "task": {
                "id": "fut_00000000000000000000000000000001",
                "public_id": "fut_00000000000000000000000000000001",
                "title": "技术评估",
                "status": "open",
            },
            "expires_at": "2026-08-24T09:00:00",
        }
    )
    resolver = CRMFollowUpTaskConfirmationCaseResolver(api_client=api_client)

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
        case_id="fuc_00000000000000000000000000000001",
    )

    assert resolution.status == "RESOLVED"
    assert resolution.case is not None
    assert resolution.case.status == "PENDING"
    assert resolution.case.suggested_action == "COMPLETE"
    assert resolution.case.customer_id == "cus_shanghai_001"
    assert resolution.case.task_id == "fut_00000000000000000000000000000001"
    assert api_client.calls == [
        {
            "method": "GET",
            "path": (
                "/v1/follow-up-tasks/confirmation-cases/"
                "fuc_00000000000000000000000000000001"
            ),
            "authorization": "Bearer signed-token",
            "kwargs": {},
        }
    ]


async def test_follow_up_confirmation_case_resolver_fails_closed_on_owner_mismatch() -> None:
    from app.services.agent.workflow.resources import CRMFollowUpTaskConfirmationCaseResolver

    resolver = CRMFollowUpTaskConfirmationCaseResolver(
        api_client=FakeCRMAPIClient(
            {
                "id": "fuc_00000000000000000000000000000001",
                "public_id": "fuc_00000000000000000000000000000001",
                "status": "PENDING",
                "owner_id": "99",
                "question_text": "跟进任务是否已经完成?",
                "suggested_action": "COMPLETE",
                "customer": {
                    "id": "cus_shanghai_001",
                    "public_id": "cus_shanghai_001",
                },
                "task": {
                    "id": "fut_00000000000000000000000000000001",
                    "public_id": "fut_00000000000000000000000000000001",
                },
                "expires_at": None,
            }
        )
    )

    resolution = await resolver.resolve(
        authorization="Bearer signed-token",
        user_id=2,
        case_id="fuc_00000000000000000000000000000001",
    )

    assert resolution.status == "NOT_FOUND"
    assert resolution.case is None
