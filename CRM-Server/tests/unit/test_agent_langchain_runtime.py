"""CRM AI Agent LangChain runtime tests."""

import pytest
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from pydantic import BaseModel

from app.services.agent import langchain_runtime
from app.services.agent.langchain_runtime import (
    AgentLangChainRuntime,
    AgentLangChainStructuredOutputError,
)


class SampleStructuredResult(BaseModel):
    value: str
    score: int


class FakeChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_langchain_runtime_returns_none_when_dependency_unavailable(monkeypatch):
    monkeypatch.setattr(langchain_runtime, "create_agent", None)
    monkeypatch.setattr(langchain_runtime, "ChatOpenAI", None)

    runtime = AgentLangChainRuntime()

    result = await runtime.ainvoke_structured(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        temperature=0.1,
        system_prompt="system",
        user_prompt="user",
        response_model=SampleStructuredResult,
        error_prefix="测试",
    )

    assert result is None


@pytest.mark.asyncio
async def test_langchain_runtime_validates_dict_structured_response():
    class FakeAgent:
        async def ainvoke(self, payload):
            assert payload == {"messages": [{"role": "user", "content": "user"}]}
            return {"structured_response": {"value": "ok", "score": 90}}

    calls = {}

    def fake_agent_factory(**kwargs):
        calls.update(kwargs)
        return FakeAgent()

    runtime = AgentLangChainRuntime(
        agent_factory=fake_agent_factory,
        chat_model_factory=FakeChatModel,
    )

    result = await runtime.ainvoke_structured(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        temperature=0.1,
        system_prompt="system",
        user_prompt="user",
        response_model=SampleStructuredResult,
        tools=["tool"],
        middleware=["middleware"],
        error_prefix="测试",
    )

    assert result == SampleStructuredResult(value="ok", score=90)
    assert isinstance(calls["model"], FakeChatModel)
    assert calls["tools"] == ["tool"]
    assert calls["system_prompt"] == "system"
    assert calls["response_format"] is SampleStructuredResult
    assert calls["middleware"] == ["middleware"]


@pytest.mark.asyncio
async def test_langchain_runtime_supports_explicit_tool_structured_output_strategy():
    class FakeAgent:
        async def ainvoke(self, payload):
            return {"structured_response": {"value": "ok", "score": 90}}

    calls = {}

    def fake_agent_factory(**kwargs):
        calls.update(kwargs)
        return FakeAgent()

    runtime = AgentLangChainRuntime(
        agent_factory=fake_agent_factory,
        chat_model_factory=FakeChatModel,
    )

    result = await runtime.ainvoke_structured(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        temperature=0.1,
        system_prompt="system",
        user_prompt="user",
        response_model=SampleStructuredResult,
        structured_output_strategy="tool",
        error_prefix="测试",
    )

    assert result == SampleStructuredResult(value="ok", score=90)
    assert isinstance(calls["response_format"], ToolStrategy)


@pytest.mark.asyncio
async def test_langchain_runtime_supports_explicit_provider_structured_output_strategy():
    class FakeAgent:
        async def ainvoke(self, payload):
            return {"structured_response": {"value": "ok", "score": 90}}

    calls = {}

    def fake_agent_factory(**kwargs):
        calls.update(kwargs)
        return FakeAgent()

    runtime = AgentLangChainRuntime(
        agent_factory=fake_agent_factory,
        chat_model_factory=FakeChatModel,
    )

    await runtime.ainvoke_structured(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        temperature=0.1,
        system_prompt="system",
        user_prompt="user",
        response_model=SampleStructuredResult,
        structured_output_strategy="provider",
        error_prefix="测试",
    )

    assert isinstance(calls["response_format"], ProviderStrategy)


@pytest.mark.asyncio
async def test_langchain_runtime_raises_when_structured_response_invalid():
    class FakeAgent:
        async def ainvoke(self, payload):
            return {"structured_response": {"value": "ok", "score": "bad"}}

    runtime = AgentLangChainRuntime(
        agent_factory=lambda **kwargs: FakeAgent(),
        chat_model_factory=FakeChatModel,
    )

    with pytest.raises(AgentLangChainStructuredOutputError, match="测试 结果无效"):
        await runtime.ainvoke_structured(
            api_host="https://ai.example.com/v1",
            api_key="test-key",
            model="test-model",
            temperature=0.1,
            system_prompt="system",
            user_prompt="user",
            response_model=SampleStructuredResult,
            error_prefix="测试",
        )


@pytest.mark.asyncio
async def test_langchain_runtime_wraps_agent_invoke_failure():
    class FakeAgent:
        async def ainvoke(self, payload):
            raise TimeoutError("timeout")

    runtime = AgentLangChainRuntime(
        agent_factory=lambda **kwargs: FakeAgent(),
        chat_model_factory=FakeChatModel,
    )

    with pytest.raises(RuntimeError, match="测试 调用失败：TimeoutError: timeout"):
        await runtime.ainvoke_structured(
            api_host="https://ai.example.com/v1",
            api_key="test-key",
            model="test-model",
            temperature=0.1,
            system_prompt="system",
            user_prompt="user",
            response_model=SampleStructuredResult,
            error_prefix="测试",
        )
