"""Behavioral tests for the ephemeral CRM Query Agent module."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import APIConnectionError

from app.services.agent.query import (
    CRMFilter,
    CRMQueryAgent,
    CRMQueryAgentExecutionError,
    CRMQueryAgentLimits,
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


class StubExecutor:
    def __init__(self, results: list[CRMQueryResult], *, delay_seconds: float = 0) -> None:
        self._results = iter(results)
        self.delay_seconds = delay_seconds
        self.calls: list[CRMQuerySpec] = []

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryResult:
        self.calls.append(spec)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return next(self._results)


class StubCustomerContextReader:
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
            degraded_reasons=["no context"],
        )


class FakeChatModel:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class ParallelEmptyToolCallModel(BaseChatModel):
    """Scripted model that emits duplicate tool calls in one real agent step."""

    invocation_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "parallel-empty-tool-call-model"

    def bind_tools(self, tools: object, **kwargs: object) -> ParallelEmptyToolCallModel:
        return self

    def _generate(
        self,
        messages: object,
        stop: list[str] | None = None,
        run_manager: object = None,
        **kwargs: object,
    ) -> ChatResult:
        self.invocation_count += 1
        if self.invocation_count > 1:
            raise AssertionError("authoritative EMPTY must terminate before another model call")
        calls = [
            {
                "name": "query_customers",
                "args": _query_payload(),
                "id": f"call_{index}",
                "type": "tool_call",
            }
            for index in range(2)
        ]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])


AgentBehavior = Callable[[dict[str, object], dict[str, object]], Awaitable[dict[str, object]]]


class CapturingAgentFactory:
    def __init__(self, behavior: AgentBehavior) -> None:
        self.behavior = behavior
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object):
        self.calls.append(kwargs)
        behavior = self.behavior

        class FakeAgent:
            async def ainvoke(
                self,
                payload: dict[str, object],
                config: dict[str, object] | None = None,
            ) -> dict[str, object]:
                return await behavior(payload, {**kwargs, "invoke_config": config})

        return FakeAgent()


def _context() -> AgentToolContext:
    return AgentToolContext(
        db=Mock(),
        team_id=7,
        user_id=42,
        session_id=11,
        authorization="Bearer server-token",
        permission_codes=frozenset({"customer:view:all"}),
    )


def test_query_agent_limits_default_to_bounded_model_retries() -> None:
    assert CRMQueryAgentLimits().model_retry_attempts == 2


def _model_config() -> CRMQueryAgentModelConfig:
    return CRMQueryAgentModelConfig(
        api_host="https://ai.example.com/v1",
        api_key="test-key",
        model="test-model",
        temperature=0.1,
    )


def _query_payload(*, page_size: int = 20) -> dict[str, object]:
    return {
        "resource": "customer",
        "projection": ["public_id", "account_name", "city"],
        "filters": [{"field": "city", "operator": "eq", "value": "上海"}],
        "sorts": [{"field": "last_modified_time", "direction": "desc"}],
        "metrics": [],
        "group_by": [],
        "scope": "accessible",
        "page_size": page_size,
        "cursor": None,
    }


def _query_result(query_id: str, *, start: int = 1, count: int = 1) -> CRMQueryResult:
    refs = [
        EntityRef(
            ref_id=f"eref_customer_{index}",
            resource="customer",
            public_id=f"cus_{index:032d}",
            display_name=f"客户 {index}",
        )
        for index in range(start, start + count)
    ]
    return CRMQueryResult(
        query_id=query_id,
        resource="customer",
        status="SUCCESS" if refs else "EMPTY",
        rows=[{"public_id": ref.public_id, "account_name": ref.display_name} for ref in refs],
        entity_refs=refs,
        total=count,
        applied_filters=[],
        applied_sorts=[],
    )


def _agent(
    executor: StubExecutor,
    behavior: AgentBehavior,
    *,
    limits: CRMQueryAgentLimits | None = None,
) -> tuple[CRMQueryAgent, CapturingAgentFactory]:
    factory = CapturingAgentFactory(behavior)
    registry = CRMReadToolRegistry(executor, StubCustomerContextReader())
    return (
        CRMQueryAgent(
            registry,
            agent_factory=factory,
            chat_model_factory=FakeChatModel,
            limits=limits,
        ),
        factory,
    )


@pytest.mark.asyncio
async def test_query_agent_classifies_exhausted_transient_model_transport_as_retryable() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        raise APIConnectionError(
            message="websocket disconnected",
            request=httpx.Request("POST", "https://ai.example.com/v1/chat/completions"),
        )

    agent, factory = _agent(StubExecutor([]), behavior)

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="上海有哪些客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "UPSTREAM_UNAVAILABLE"
    assert exc_info.value.error.retryable is True
    assert factory.calls[0]["model"].kwargs["max_retries"] == 2


@pytest.mark.asyncio
async def test_query_agent_uses_selected_read_tools_and_returns_authoritative_results() -> None:
    executor = StubExecutor([_query_result("qry_shanghai")])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        assert payload["messages"]
        tools = {tool.name: tool for tool in runtime["tools"]}
        tool_result = await tools["query_customers"].ainvoke(_query_payload())
        assert tool_result["query_id"] == "qry_shanghai"
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "找到 1 个上海客户。",
                "clarification_question": None,
                "evidence_refs": ["qry_shanghai", "eref_customer_1"],
            }
        }

    agent, factory = _agent(executor, behavior)
    result = await agent.run(
        CRMQueryAgentRequest(
            user_message="我在上海有哪些客户?",
            allowed_tool_names=["query_customers"],
        ),
        _context(),
        _model_config(),
    )

    assert result.response.answer == "找到 1 个上海客户。"
    assert result.query_results == [_query_result("qry_shanghai")]
    assert result.trace.tool_names == ["query_customers"]
    assert result.trace.tool_call_count == 1
    assert result.trace.total_entity_count == 1
    assert result.trace.stop_reason == "COMPLETED"
    assert set(factory.calls[0]) >= {
        "model",
        "tools",
        "system_prompt",
        "response_format",
        "middleware",
        "checkpointer",
        "store",
        "name",
    }
    assert factory.calls[0]["checkpointer"] is None
    assert factory.calls[0]["store"] is None
    assert [tool.name for tool in factory.calls[0]["tools"]] == ["query_customers"]


@pytest.mark.asyncio
async def test_query_agent_passes_canonical_previous_query_to_the_model() -> None:
    previous_query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city"],
        filters=[{"field": "city", "operator": "eq", "value": "上海"}],
        sorts=[{"field": "last_modified_time", "direction": "desc"}],
        scope="accessible",
        page_size=20,
    )

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        messages = payload["messages"]
        assert isinstance(messages, list)
        content = messages[0]["content"]
        assert isinstance(content, str)
        model_input = json.loads(content)
        assert model_input["user_message"] == "重点客户呢"
        assert model_input["previous_query"] == previous_query.model_dump(
            mode="json",
            exclude_none=True,
        )
        assert model_input["server_authoritative_entity_refs"] == []
        assert "默认继承 previous_query" in model_input["instruction"]
        return {
            "structured_response": {
                "status": "CLARIFICATION_REQUIRED",
                "answer": None,
                "clarification_question": "请确认重点客户的判断标准。",
                "evidence_refs": [],
            }
        }

    agent, _ = _agent(StubExecutor([]), behavior)
    result = await agent.run(
        CRMQueryAgentRequest(
            user_message="重点客户呢",
            previous_query=previous_query,
            allowed_tool_names=["query_customers"],
        ),
        _context(),
        _model_config(),
    )

    assert result.response.status == "CLARIFICATION_REQUIRED"


@pytest.mark.asyncio
async def test_query_agent_prompt_requires_minimal_selected_customer_activity_query() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        return {
            "structured_response": {
                "status": "CLARIFICATION_REQUIRED",
                "answer": None,
                "clarification_question": "测试结束",
                "evidence_refs": [],
            }
        }

    agent, factory = _agent(StubExecutor([]), behavior)
    await agent.run(
        CRMQueryAgentRequest(
            user_message="第一个客户最近跟进得怎么样",
            entity_refs=[
                EntityRef(
                    ref_id="eref_customer_1",
                    resource="customer",
                    public_id="cus_1",
                    display_name="上海测试客户",
                    result_set_id="rs_1",
                )
            ],
            allowed_tool_names=["query_customer_activities"],
        ),
        _context(),
        _model_config(),
    )

    prompt = factory.calls[0]["system_prompt"]
    assert "同一工具不得重复调用" in prompt
    assert "只调用一次 query_customer_activities" in prompt
    assert "不要同时调用 get_customer_context" in prompt


@pytest.mark.asyncio
async def test_query_agent_inherits_previous_filters_when_model_adds_a_follow_up_filter() -> None:
    previous_query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city", "status"],
        filters=[{"field": "city", "operator": "eq", "value": "上海"}],
        sorts=[{"field": "last_modified_time", "direction": "desc"}],
        scope="accessible",
        page_size=20,
    )
    executor = StubExecutor([_query_result("qry_priority_shanghai")])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool_result = await runtime["tools"][0].ainvoke(
            {
                "resource": "customer",
                "projection": ["public_id", "account_name", "city", "status"],
                "filters": [{"field": "status", "operator": "eq", "value": 0}],
                "sorts": [],
                "metrics": [],
                "group_by": [],
                "scope": "accessible",
                "page_size": 20,
                "cursor": None,
            }
        )
        assert tool_result["query_id"] == "qry_priority_shanghai"
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "找到上海范围内的重点客户。",
                "clarification_question": None,
                "evidence_refs": ["qry_priority_shanghai", "eref_customer_1"],
            }
        }

    agent, _ = _agent(executor, behavior)
    await agent.run(
        CRMQueryAgentRequest(
            user_message="重点客户呢",
            previous_query=previous_query,
            allowed_tool_names=["query_customers"],
        ),
        _context(),
        _model_config(),
    )

    assert [item.model_dump(mode="json") for item in executor.calls[0].filters] == [
        {"field": "city", "operator": "eq", "value": "上海"},
        {"field": "status", "operator": "eq", "value": 0},
    ]


@pytest.mark.asyncio
async def test_query_agent_does_not_duplicate_inherited_model_filter_objects() -> None:
    previous_query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city"],
        filters=[{"field": "city", "operator": "eq", "value": "上海"}],
        scope="accessible",
    )
    executor = StubExecutor([_query_result("qry_shanghai")])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool_result = await runtime["tools"][0].ainvoke(
            {
                "resource": "customer",
                "projection": ["public_id", "account_name", "city"],
                "filters": [CRMFilter(field="city", operator="eq", value="上海")],
                "sorts": [],
                "metrics": [],
                "group_by": [],
                "scope": "accessible",
                "page_size": 50,
                "cursor": None,
            }
        )
        assert tool_result["query_id"] == "qry_shanghai"
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "找到上海客户。",
                "clarification_question": None,
                "evidence_refs": ["qry_shanghai", "eref_customer_1"],
            }
        }

    agent, _ = _agent(executor, behavior)
    await agent.run(
        CRMQueryAgentRequest(
            user_message="上海客户呢",
            previous_query=previous_query,
            allowed_tool_names=["query_customers"],
        ),
        _context(),
        _model_config(),
    )

    assert [item.model_dump(mode="json") for item in executor.calls[0].filters] == [
        {"field": "city", "operator": "eq", "value": "上海"},
    ]


@pytest.mark.asyncio
async def test_query_agent_allows_clarification_without_calling_a_tool() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        return {
            "structured_response": {
                "status": "CLARIFICATION_REQUIRED",
                "answer": None,
                "clarification_question": "你想查询哪座城市的客户?",
                "evidence_refs": [],
            }
        }

    agent, _ = _agent(StubExecutor([]), behavior)
    result = await agent.run(
        CRMQueryAgentRequest(user_message="查一下客户", allowed_tool_names=["query_customers"]),
        _context(),
        _model_config(),
    )

    assert result.response.status == "CLARIFICATION_REQUIRED"
    assert result.trace.stop_reason == "CLARIFICATION_REQUIRED"
    assert result.trace.tool_call_count == 0


@pytest.mark.asyncio
async def test_query_agent_rejects_unregistered_dynamic_tool_before_model_call() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        raise AssertionError("model must not be called")

    agent, factory = _agent(StubExecutor([]), behavior)

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["delete_customer"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_INVALID"
    assert factory.calls == []


@pytest.mark.asyncio
async def test_query_agent_terminates_after_one_authoritative_empty_when_model_emits_parallel_calls() -> None:
    executor = StubExecutor(
        [
            _query_result("qry_empty_terminal", count=0),
            _query_result("qry_must_not_execute"),
        ],
        delay_seconds=0.01,
    )
    registry = CRMReadToolRegistry(executor, StubCustomerContextReader())
    model = ParallelEmptyToolCallModel()
    agent = CRMQueryAgent(
        registry,
        chat_model_factory=lambda **kwargs: model,
        limits=CRMQueryAgentLimits(max_tool_calls=1),
    )

    result = await agent.run(
        CRMQueryAgentRequest(user_message="查不存在的客户", allowed_tool_names=["query_customers"]),
        _context(),
        _model_config(),
    )

    assert result.response.status == "ANSWERED"
    assert result.response.answer == "当前权限范围内未找到符合条件的客户。"
    assert result.response.evidence_refs == ["qry_empty_terminal"]
    assert [item.query_id for item in result.query_results] == ["qry_empty_terminal"]
    assert len(executor.calls) == 1
    assert result.trace.tool_call_count == 1
    assert [call.status for call in result.trace.tool_calls] == ["SUCCESS"]
    assert model.invocation_count == 1


@pytest.mark.asyncio
async def test_query_agent_enforces_maximum_read_tool_calls() -> None:
    executor = StubExecutor([_query_result(f"qry_{index}") for index in range(1, 6)])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool = runtime["tools"][0]
        for _ in range(5):
            await tool.ainvoke(_query_payload())
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": ["qry_1"],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(max_tool_calls=4))

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_LIMIT_EXCEEDED"
    assert len(executor.calls) == 4


@pytest.mark.asyncio
async def test_query_agent_enforces_per_tool_timeout() -> None:
    executor = StubExecutor([_query_result("qry_slow")], delay_seconds=0.05)

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        await runtime["tools"][0].ainvoke(_query_payload())
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": [],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(tool_timeout_seconds=0.01))

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "UPSTREAM_TIMEOUT"
    assert exc_info.value.error.retryable is True


@pytest.mark.asyncio
async def test_query_agent_enforces_whole_turn_entity_limit() -> None:
    executor = StubExecutor(
        [
            _query_result("qry_1", start=1, count=40),
            _query_result("qry_2", start=41, count=40),
            _query_result("qry_3", start=81, count=40),
        ]
    )

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool = runtime["tools"][0]
        for _ in range(3):
            await tool.ainvoke(_query_payload(page_size=40))
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": ["qry_1"],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(max_total_entities=100))

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_query_agent_allows_only_one_invalid_query_correction() -> None:
    executor = StubExecutor([])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool = runtime["tools"][0]
        invalid_payload = {**_query_payload(), "resource": "contact"}
        first = await tool.ainvoke(invalid_payload)
        second = await tool.ainvoke(invalid_payload)
        assert first["error"]["code"] == "QUERY_INVALID"
        assert second["error"]["code"] == "QUERY_INVALID"
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": [],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(max_query_corrections=1))

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_INVALID"


@pytest.mark.asyncio
async def test_query_agent_preserves_terminal_tool_error_when_turn_times_out() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        result = await runtime["tools"][0].ainvoke(_query_payload(page_size=50))
        assert result["error"]["code"] == "QUERY_LIMIT_EXCEEDED"
        raise TimeoutError

    agent, _ = _agent(
        StubExecutor([_query_result("qry_over_budget", count=51)]),
        behavior,
        limits=CRMQueryAgentLimits(max_rows_per_tool=50),
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_query_agent_preserves_terminal_tool_error_when_model_fails() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        result = await runtime["tools"][0].ainvoke(_query_payload(page_size=50))
        assert result["error"]["code"] == "QUERY_LIMIT_EXCEEDED"
        raise RuntimeError("model failed after terminal tool error")

    agent, _ = _agent(
        StubExecutor([_query_result("qry_over_budget", count=51)]),
        behavior,
        limits=CRMQueryAgentLimits(max_rows_per_tool=50),
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_query_agent_rejects_answer_without_authoritative_tool_evidence() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "上海有 10 个客户。",
                "clarification_question": None,
                "evidence_refs": ["invented_query"],
            }
        }

    agent, _ = _agent(StubExecutor([]), behavior)

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="上海有多少客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_query_agent_rejects_unknown_evidence_even_with_authoritative_query_result() -> None:
    executor = StubExecutor([_query_result("qry_authoritative")])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        await runtime["tools"][0].ainvoke(_query_payload())
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "已找到客户。",
                "clarification_question": None,
                "evidence_refs": ["invented_query"],
            }
        }

    agent, _ = _agent(executor, behavior)
    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_query_agent_clamps_model_requested_page_size_to_tool_row_limit() -> None:
    executor = StubExecutor([_query_result("qry_clamped", count=50)])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        result = await runtime["tools"][0].ainvoke(_query_payload(page_size=51))
        assert "error" not in result
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": ["qry_clamped"],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(max_rows_per_tool=50))

    result = await agent.run(
        CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
        _context(),
        _model_config(),
    )

    assert result.response.status == "ANSWERED"
    assert [call.page_size for call in executor.calls] == [50]


def test_query_agent_default_turn_timeout_allows_tool_and_response_round_trip() -> None:
    assert CRMQueryAgentLimits().turn_timeout_seconds == 60


@pytest.mark.asyncio
async def test_query_agent_enforces_whole_turn_timeout() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {
            "structured_response": {
                "status": "CLARIFICATION_REQUIRED",
                "answer": None,
                "clarification_question": "请补充条件",
                "evidence_refs": [],
            }
        }

    agent, _ = _agent(
        StubExecutor([]),
        behavior,
        limits=CRMQueryAgentLimits(turn_timeout_seconds=0.01),
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "UPSTREAM_TIMEOUT"
    assert exc_info.value.error.retryable is True


@pytest.mark.asyncio
async def test_query_agent_fails_when_summary_times_out_after_authoritative_results() -> None:
    executor = StubExecutor([_query_result("qry_completed_week", count=2)])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool_result = await runtime["tools"][0].ainvoke(_query_payload())
        assert tool_result["query_id"] == "qry_completed_week"
        await asyncio.sleep(0.05)
        raise AssertionError("the summary should have timed out before a model response")

    agent, _ = _agent(
        executor,
        behavior,
        limits=CRMQueryAgentLimits(turn_timeout_seconds=0.01),
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="本周我做了什么", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "UPSTREAM_TIMEOUT"
    assert exc_info.value.error.retryable is True



@pytest.mark.asyncio
async def test_query_agent_collects_customer_context_and_validates_citations() -> None:
    from app.services.agent.query import CustomerContextCitation

    customer_ref = EntityRef(
        ref_id="eref_customer_context",
        resource="customer",
        public_id="cus_00000000000000000000000000000009",
        display_name="客户 9",
    )

    class ContextReader:
        async def read(
            self,
            request: CustomerContextRequest,
            context: AgentToolContext,
        ) -> CustomerContextResult:
            return CustomerContextResult(
                customer_ref=request.customer_ref,
                sections={"brief": {"summary": "客户正在推进续约"}},
                citations=[
                    CustomerContextCitation(
                        citation_id="cite_customer_9",
                        source="CUSTOMER_INTELLIGENCE",
                        source_ref="customer-brief:9",
                        label="客户简报",
                    )
                ],
                coverage=CustomerContextCoverage(
                    requested=request.sections,
                    returned=request.sections,
                    unavailable=[],
                ),
            )

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        result = await runtime["tools"][0].ainvoke(
            {
                "customer_ref": customer_ref.model_dump(mode="json"),
                "sections": ["brief"],
                "question": "这个客户目前是什么情况?",
                "evidence_limit": 6,
            }
        )
        assert result["citations"][0]["citation_id"] == "cite_customer_9"
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "客户正在推进续约。",
                "clarification_question": None,
                "evidence_refs": ["eref_customer_context", "cite_customer_9"],
            }
        }

    factory = CapturingAgentFactory(behavior)
    agent = CRMQueryAgent(
        CRMReadToolRegistry(StubExecutor([]), ContextReader()),
        agent_factory=factory,
        chat_model_factory=FakeChatModel,
    )
    result = await agent.run(
        CRMQueryAgentRequest(
            user_message="这个客户目前是什么情况?",
            allowed_tool_names=["get_customer_context"],
        ),
        _context(),
        _model_config(),
    )

    assert result.customer_context_results[0].customer_ref == customer_ref
    assert result.query_results == []
    assert result.trace.total_entity_count == 1


@pytest.mark.asyncio
async def test_query_agent_allows_only_one_structured_output_correction() -> None:
    from langchain.agents.structured_output import StructuredOutputValidationError, ToolStrategy
    from langchain_core.messages import AIMessage

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        strategy = runtime["response_format"]
        assert isinstance(strategy, ToolStrategy)
        handler = strategy.handle_errors
        assert callable(handler)
        error = StructuredOutputValidationError(
            "CRMQueryAgentResponse",
            ValueError("invalid response"),
            AIMessage(content=""),
        )
        assert "修正一次" in handler(error)
        handler(error)
        raise AssertionError("second correction must raise")

    agent, _ = _agent(
        StubExecutor([]),
        behavior,
        limits=CRMQueryAgentLimits(max_structured_output_corrections=1),
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_query_agent_passes_explicit_thinking_mode_to_model_transport() -> None:
    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        return {
            "structured_response": {
                "status": "CLARIFICATION_REQUIRED",
                "answer": None,
                "clarification_question": "请补充查询条件",
                "evidence_refs": [],
            }
        }

    agent, factory = _agent(StubExecutor([]), behavior)
    await agent.run(
        CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
        _context(),
        CRMQueryAgentModelConfig(
            api_host="https://ai.example.com/v1",
            api_key="test-key",
            model="thinking-model",
            temperature=0,
            enable_thinking=False,
        ),
    )

    model = factory.calls[0]["model"]
    assert isinstance(model, FakeChatModel)
    assert model.kwargs["extra_body"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_query_agent_stops_executing_tools_after_terminal_error() -> None:
    from app.services.agent.query import CRMQueryExecutionError, QueryError

    class PermissionDeniedExecutor:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryResult:
            self.calls += 1
            raise CRMQueryExecutionError(
                QueryError(
                    code="PERMISSION_DENIED",
                    message="permission denied",
                    retryable=False,
                )
            )

    executor = PermissionDeniedExecutor()

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool = runtime["tools"][0]
        first = await tool.ainvoke(_query_payload())
        second = await tool.ainvoke(_query_payload())
        assert first["error"]["code"] == "PERMISSION_DENIED"
        assert second["error"]["code"] == "PERMISSION_DENIED"
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": ["invented"],
            }
        }

    factory = CapturingAgentFactory(behavior)
    agent = CRMQueryAgent(
        CRMReadToolRegistry(executor, StubCustomerContextReader()),
        agent_factory=factory,
        chat_model_factory=FakeChatModel,
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "PERMISSION_DENIED"
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_query_agent_treats_reader_value_error_as_terminal_internal_error() -> None:
    customer_ref = EntityRef(
        ref_id="eref_customer_reader_error",
        resource="customer",
        public_id="cus_reader_error",
        display_name="异常客户",
    )

    class BrokenContextReader:
        async def read(
            self,
            request: CustomerContextRequest,
            context: AgentToolContext,
        ) -> CustomerContextResult:
            raise ValueError("internal reader invariant failed")

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        result = await runtime["tools"][0].ainvoke(
            {
                "customer_ref": customer_ref.model_dump(mode="json"),
                "sections": ["brief"],
                "question": None,
                "evidence_limit": 6,
            }
        )
        assert result["error"]["code"] == "INTERNAL_ERROR"
        return {
            "structured_response": {
                "status": "CLARIFICATION_REQUIRED",
                "answer": None,
                "clarification_question": "请稍后重试",
                "evidence_refs": [],
            }
        }

    agent = CRMQueryAgent(
        CRMReadToolRegistry(StubExecutor([]), BrokenContextReader()),
        agent_factory=CapturingAgentFactory(behavior),
        chat_model_factory=FakeChatModel,
    )

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="客户情况", allowed_tool_names=["get_customer_context"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_query_agent_counts_row_public_ids_when_entity_refs_are_missing() -> None:
    results = []
    for page in range(3):
        start = page * 40 + 1
        rows = [
            {"public_id": f"cus_row_{index}", "account_name": f"客户 {index}"}
            for index in range(start, start + 40)
        ]
        results.append(
            CRMQueryResult(
                query_id=f"qry_rows_{page + 1}",
                resource="customer",
                status="SUCCESS",
                rows=rows,
                entity_refs=[],
                total=40,
                applied_filters=[],
                applied_sorts=[],
            )
        )
    executor = StubExecutor(results)

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool = runtime["tools"][0]
        for _ in range(3):
            await tool.ainvoke(_query_payload(page_size=40))
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": ["qry_rows_1"],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(max_total_entities=100))

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_query_agent_trace_remains_valid_at_configured_maximum_tool_calls() -> None:
    executor = StubExecutor([_query_result(f"qry_{index}") for index in range(1, 21)])

    async def behavior(payload: dict[str, object], runtime: dict[str, object]) -> dict[str, object]:
        tool = runtime["tools"][0]
        for _ in range(21):
            await tool.ainvoke(_query_payload())
        return {
            "structured_response": {
                "status": "ANSWERED",
                "answer": "done",
                "clarification_question": None,
                "evidence_refs": ["qry_1"],
            }
        }

    agent, _ = _agent(executor, behavior, limits=CRMQueryAgentLimits(max_tool_calls=20))

    with pytest.raises(CRMQueryAgentExecutionError) as exc_info:
        await agent.run(
            CRMQueryAgentRequest(user_message="查客户", allowed_tool_names=["query_customers"]),
            _context(),
            _model_config(),
        )

    assert exc_info.value.error.code == "QUERY_LIMIT_EXCEEDED"
    assert exc_info.value.trace is not None
    assert exc_info.value.trace.tool_call_count == 21
    assert len(exc_info.value.trace.tool_calls) == 21
    assert len(executor.calls) == 20
