from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.services.agent.orchestrator.contracts import RootRuntimeContext
from app.services.agent.query import semantic_intent as semantic_intent_module
from app.services.agent.query.agent import CRMQueryAgentModelConfig
from app.services.agent.query.semantic_intent import (
    CRMQuerySemanticIntent,
    LLMQuerySemanticIntentResolver,
    QuerySemanticIntentInvalidError,
    QuerySemanticIntentUnavailableError,
    QueryTemporalIntent,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


class FakeStructuredModel:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[object] = []

    def with_structured_output(self, response_model: type[BaseModel], *, method: str):
        assert response_model is CRMQuerySemanticIntent
        assert method == "function_calling"
        return self

    async def ainvoke(self, messages: object) -> object:
        self.calls.append(messages)
        return self.result


class FakeModelFactory:
    def __init__(self, result: object) -> None:
        self.model = FakeStructuredModel(result)
        self.kwargs: dict[str, object] | None = None

    def __call__(self, **kwargs: object) -> FakeStructuredModel:
        self.kwargs = kwargs
        return self.model


def _config() -> CRMQueryAgentModelConfig:
    return CRMQueryAgentModelConfig(
        api_host="https://ai.example.com/v1",
        api_key="key",
        model="test-model",
        temperature=0.7,
    )


@pytest.mark.asyncio
async def test_resolver_uses_llm_semantics_for_natural_language_without_keyword_table() -> None:
    factory = FakeModelFactory(
        {
            "scope": "global_work",
            "resource": "follow_up_tasks",
            "temporal": {"kind": "custom", "start_at": "2026-09-01", "end_at": "2026-09-15"},
            "confidence": 0.94,
        }
    )
    resolver = LLMQuerySemanticIntentResolver(chat_model_factory=factory)

    result = await resolver.resolve(
        "接下来半个月我有哪些必须处理的事情?",
        model_config=_config(),
        runtime=RootRuntimeContext(),
    )

    assert result == CRMQuerySemanticIntent(
        scope="global_work",
        resource="follow_up_tasks",
        temporal=QueryTemporalIntent(kind="custom", start_at="2026-09-01", end_at="2026-09-15"),
        confidence=0.94,
    )
    assert factory.kwargs is not None
    assert factory.kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_resolver_preserves_customer_alias_and_does_not_confuse_customer_scope_with_global_work() -> None:
    factory = FakeModelFactory(
        {
            "scope": "customer_scoped",
            "resource": "follow_up_tasks",
            "customer_text": "凡亚信息",
            "temporal": {"kind": "next_week"},
            "confidence": 0.99,
        }
    )
    resolver = LLMQuerySemanticIntentResolver(chat_model_factory=factory)

    result = await resolver.resolve(
        "凡亚信息下个工作周期有哪些需要继续跟进的事项?",
        model_config=_config(),
        runtime=RootRuntimeContext(),
    )

    assert result.scope == "customer_scoped"
    assert result.customer_text == "凡亚信息"
    assert result.resource == "follow_up_tasks"
    assert result.temporal.kind == "next_week"


def test_customer_deployment_query_is_a_supported_customer_scoped_resource() -> None:
    intent = CRMQuerySemanticIntent(
        scope="customer_scoped",
        resource="deployment_info",
        customer_text="深圳矽递科技股份有限公司",
        confidence=0.99,
    )

    assert intent.resource == "deployment_info"


def test_standard_temporal_intent_discards_model_supplied_boundaries() -> None:
    intent = CRMQuerySemanticIntent(
        scope="global_work",
        resource="follow_up_tasks",
        temporal={
            "kind": "this_week",
            "end_at": "2026-09-07T00:00:00",
        },
        confidence=0.99,
    )

    assert intent.temporal.kind == "this_week"
    assert intent.temporal.start_at is None
    assert intent.temporal.end_at is None


@pytest.mark.asyncio
async def test_unspecified_semantic_time_is_not_silently_treated_as_this_week() -> None:
    factory = FakeModelFactory({"scope": "global_work", "resource": "follow_up_tasks", "confidence": 0.8})
    resolver = LLMQuerySemanticIntentResolver(chat_model_factory=factory)

    result = await resolver.resolve("以后我要做什么", model_config=_config(), runtime=RootRuntimeContext())

    assert result.temporal.kind == "unspecified"


@pytest.mark.asyncio
async def test_resolver_default_budget_matches_provider_latency_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    budgets: list[float] = []

    class RecordingTimeout:
        def __init__(self, timeout: float) -> None:
            budgets.append(timeout)

        async def __aenter__(self) -> RecordingTimeout:
            return self

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            return False

    monkeypatch.setattr(semantic_intent_module.asyncio, "timeout", RecordingTimeout)
    resolver = LLMQuerySemanticIntentResolver(chat_model_factory=FakeModelFactory({
        "scope": "global_work",
        "resource": "follow_up_tasks",
        "confidence": 0.95,
    }))

    await resolver.resolve("查询我接下来要做什么", model_config=_config(), runtime=RootRuntimeContext())

    assert budgets == [30.0]


class RaisingModelFactory:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def __call__(self, **kwargs: object) -> object:
        raise self.error


class RaisingStructuredModel(FakeStructuredModel):
    def with_structured_output(self, response_model: type[BaseModel], *, method: str):
        raise RuntimeError("structured output unavailable")


class RaisingInvokeModel(FakeStructuredModel):
    async def ainvoke(self, messages: object) -> object:
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_resolver_normalizes_model_factory_failure() -> None:
    resolver = LLMQuerySemanticIntentResolver(
        chat_model_factory=RaisingModelFactory(RuntimeError("provider unavailable")),
    )

    with pytest.raises(QuerySemanticIntentUnavailableError):
        await resolver.resolve("这周有哪些事情要做", model_config=_config(), runtime=RootRuntimeContext())


@pytest.mark.asyncio
async def test_resolver_normalizes_structured_output_failure() -> None:
    resolver = LLMQuerySemanticIntentResolver(
        chat_model_factory=lambda **kwargs: RaisingStructuredModel({}),
    )

    with pytest.raises(QuerySemanticIntentUnavailableError):
        await resolver.resolve("这周有哪些事情要做", model_config=_config(), runtime=RootRuntimeContext())


@pytest.mark.asyncio
async def test_resolver_normalizes_provider_invoke_failure() -> None:
    resolver = LLMQuerySemanticIntentResolver(
        chat_model_factory=lambda **kwargs: RaisingInvokeModel({}),
    )

    with pytest.raises(QuerySemanticIntentUnavailableError):
        await resolver.resolve("这周有哪些事情要做", model_config=_config(), runtime=RootRuntimeContext())


@pytest.mark.asyncio
async def test_resolver_rejects_invalid_structured_output() -> None:
    resolver = LLMQuerySemanticIntentResolver(
        chat_model_factory=lambda **kwargs: FakeStructuredModel(
            {"scope": "global_work", "resource": "not_a_resource", "confidence": 1}
        ),
    )

    with pytest.raises(QuerySemanticIntentInvalidError):
        await resolver.resolve("这周有哪些事情要做", model_config=_config(), runtime=RootRuntimeContext())
