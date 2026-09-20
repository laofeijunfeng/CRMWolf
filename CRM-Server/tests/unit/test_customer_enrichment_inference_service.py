from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentDecision,
    CustomerEnrichmentInferenceResult,
)
from app.services.customer_enrichment_context_service import CustomerEnrichmentContextService
from app.services.customer_enrichment_inference_service import (
    CustomerEnrichmentInferenceError,
    CustomerEnrichmentInferenceService,
)
from app.services.customer_enrichment_plan import (
    ACTIVE_CUSTOMER_ENRICHMENT_PLAN,
    CustomerEnrichmentFieldRegistry,
)


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def options(self, *args):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _ContextDb:
    def __init__(self):
        self.customer = SimpleNamespace(
            id=101,
            team_id=2,
            account_name="星云研发科技",
            city="上海",
            company_scale="51-200人",
            source="线上注册",
            industry="finance",
            version=4,
            source_lead_id=None,
            product_links=[SimpleNamespace(product=SimpleNamespace(public_id="prd_hifox", name="Hifox"))],
        )
        self.contact = SimpleNamespace(
            customer_id=101,
            team_id=2,
            is_primary=1,
            name="张三",
            mobile="13800138000",
            email="secret@example.com",
            position="研发负责人",
        )
        self.activities = [
            SimpleNamespace(
                customer_id=101,
                team_id=2,
                activity_kind="电话",
                source_content=("客户主营软件研发和 AI Coding。" * 40) + str(index),
                summary=None,
                occurred_at=index,
                id=index,
            )
            for index in range(7)
        ]

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Customer":
            return _Query([self.customer])
        if name == "Contact":
            return _Query([self.contact])
        if name == "CustomerActivity":
            return _Query(list(reversed(self.activities)))
        return _Query([])


class _Runtime:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def ainvoke_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _industries():
    primary = SimpleNamespace(code="internet", name="互联网", level=1, parent=None, is_active=1)
    secondary = SimpleNamespace(
        code="internet_saas",
        name="SaaS公司",
        level=2,
        parent=primary,
        is_active=1,
    )
    other = SimpleNamespace(code="other", name="其他", level=1, parent=None, is_active=1)
    return [primary, secondary, other]


def test_active_plan_is_frozen_and_versioned():
    assert ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version == "customer-initial-v1"
    assert ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields == ("industry",)
    assert ACTIVE_CUSTOMER_ENRICHMENT_PLAN.backfill_enabled is True
    with pytest.raises(Exception):
        ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version = "changed"


def test_industry_handler_exposes_customer_column_for_atomic_write():
    from app.models.customer import Customer

    assert CustomerEnrichmentFieldRegistry().get("industry").customer_column is Customer.industry


def test_context_is_bounded_and_does_not_include_contact_pii(monkeypatch):
    monkeypatch.setattr(
        "app.services.customer_enrichment_context_service.industry_crud.get_all_active",
        lambda db: _industries(),
    )
    db = _ContextDb()
    db.activities[-1].source_content = "张三的手机号13800138000，邮箱secret@example.com，客户主营软件研发。"
    payload = CustomerEnrichmentContextService().build(
        db, team_id=2, customer_id=101, fields=("industry",)
    )
    assert payload["customer"] == {
        "account_name": "星云研发科技",
        "city": "上海",
        "company_scale": "51-200人",
        "source": "线上注册",
        "industry": "finance",
        "version": 4,
    }
    assert payload["products"] == [{"public_id": "prd_hifox", "name": "Hifox"}]
    assert payload["primary_contact"] == {"position": "研发负责人"}
    assert len(payload["recent_activities"]) == 5
    assert all(len(item["text"]) <= 500 for item in payload["recent_activities"])
    serialized = str(payload)
    assert "张三" not in serialized
    assert "13800138000" not in serialized
    assert "secret@example.com" not in serialized
    catalog = payload["catalogs"]["industry"]
    assert {item["code"] for item in catalog} == {"internet", "internet_saas", "other"}
    saas = next(item for item in catalog if item["code"] == "internet_saas")
    assert saas["parent_code"] == "internet"
    assert saas["parent_name"] == "互联网"


@pytest.mark.asyncio
async def test_inference_calls_structured_runtime_once_and_validates_code(monkeypatch):
    runtime = _Runtime(
        CustomerEnrichmentInferenceResult(
            decisions=[
                CustomerEnrichmentDecision(
                    field="industry",
                    value="internet_saas",
                    reason="客户主营软件研发",
                )
            ]
        )
    )
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_config",
        lambda db, team_id: SimpleNamespace(api_host="https://ai", model_name="model", temperature=0.7),
    )
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_decrypted_api_key",
        lambda db, team_id: "key",
    )
    service = CustomerEnrichmentInferenceService(runtime=runtime)
    context = {"catalogs": {"industry": [
        {"code": "internet_saas", "name": "SaaS公司", "level": 2, "parent_code": "internet", "parent_name": "互联网"},
        {"code": "other", "name": "其他", "level": 1, "parent_code": None, "parent_name": None},
    ]}}
    result = await service.infer(object(), team_id=2, context=context, requested_fields=("industry",))
    assert result.decisions[0].value == "internet_saas"
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["structured_output_strategy"] == "tool"
    assert runtime.calls[0]["temperature"] == 0.1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        CustomerEnrichmentInferenceResult(decisions=[CustomerEnrichmentDecision(field="unknown", value="x", reason="x")]),
        CustomerEnrichmentInferenceResult(decisions=[
            CustomerEnrichmentDecision(field="industry", value="other", reason="x"),
            CustomerEnrichmentDecision(field="industry", value="internet_saas", reason="y"),
        ]),
        CustomerEnrichmentInferenceResult(decisions=[CustomerEnrichmentDecision(field="industry", value="missing", reason="x")]),
    ],
)
async def test_inference_rejects_unknown_duplicate_or_invalid_decisions(monkeypatch, result):
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_config",
        lambda db, team_id: SimpleNamespace(api_host="https://ai", model_name="model", temperature=0.1),
    )
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_decrypted_api_key",
        lambda db, team_id: "key",
    )
    service = CustomerEnrichmentInferenceService(runtime=_Runtime(result))
    context = {"catalogs": {"industry": [
        {"code": "internet_saas", "name": "SaaS公司", "level": 2, "parent_code": "internet", "parent_name": "互联网"},
        {"code": "other", "name": "其他", "level": 1, "parent_code": None, "parent_name": None},
    ]}}
    with pytest.raises(CustomerEnrichmentInferenceError):
        await service.infer(object(), team_id=2, context=context, requested_fields=("industry",))


@pytest.mark.asyncio
async def test_missing_ai_config_is_retryable_and_never_returns_other(monkeypatch):
    monkeypatch.setattr(
        "app.services.customer_enrichment_inference_service.ai_config_crud.get_config",
        lambda db, team_id: None,
    )
    service = CustomerEnrichmentInferenceService(runtime=_Runtime(None))
    with pytest.raises(CustomerEnrichmentInferenceError) as exc:
        await service.infer(
            object(),
            team_id=2,
            context={"catalogs": {"industry": []}},
            requested_fields=("industry",),
        )
    assert exc.value.retryable is True
