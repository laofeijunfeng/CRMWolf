"""Shared LangChain runtime helpers for CRM AI Agent."""
from __future__ import annotations

from typing import Literal, Optional, TypeVar

from pydantic import BaseModel, ValidationError

try:
    from langchain.agents import create_agent
except Exception:  # pragma: no cover - optional production dependency
    create_agent = None  # type: ignore[assignment]

try:
    from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
except Exception:  # pragma: no cover - optional production dependency
    ProviderStrategy = None  # type: ignore[assignment]
    ToolStrategy = None  # type: ignore[assignment]

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional production dependency
    ChatOpenAI = None  # type: ignore[assignment]


StructuredResultT = TypeVar("StructuredResultT", bound=BaseModel)
StructuredOutputStrategy = Literal["auto", "provider", "tool"]


class AgentLangChainStructuredOutputError(Exception):
    """Raised when LangChain structured output cannot be called or validated."""


class AgentLangChainRuntime:
    """Small harness around LangChain structured-output agent calls."""

    def __init__(self, agent_factory=None, chat_model_factory=None) -> None:
        self.agent_factory = create_agent if agent_factory is None else agent_factory
        self.chat_model_factory = ChatOpenAI if chat_model_factory is None else chat_model_factory

    async def ainvoke_structured(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredResultT],
        structured_output_strategy: StructuredOutputStrategy = "auto",
        middleware: Optional[list[object]] = None,
        tools: Optional[list[object]] = None,
        error_prefix: str,
    ) -> Optional[StructuredResultT]:
        if self.agent_factory is None or self.chat_model_factory is None:
            return None

        try:
            chat_model = self.chat_model_factory(
                model=model,
                api_key=api_key,
                base_url=api_host,
                temperature=temperature,
            )
            agent = self.agent_factory(
                model=chat_model,
                tools=tools or [],
                system_prompt=system_prompt,
                response_format=self._response_format(response_model, structured_output_strategy),
                middleware=middleware or [],
            )
            response = await agent.ainvoke({"messages": [{"role": "user", "content": user_prompt}]})
        except Exception as exc:
            raise RuntimeError(
                f"{error_prefix} 调用失败：{exc.__class__.__name__}: {_safe_error_message(exc)}"
            ) from exc

        structured_response = response.get("structured_response") if isinstance(response, dict) else None
        if isinstance(structured_response, response_model):
            return structured_response
        if structured_response is not None:
            try:
                return response_model.model_validate(structured_response)
            except ValidationError as exc:
                raise AgentLangChainStructuredOutputError(f"{error_prefix} 结果无效：{str(exc)}") from exc
        raise AgentLangChainStructuredOutputError(f"{error_prefix} 未返回结构化结果。")

    @staticmethod
    def _response_format(
        response_model: type[StructuredResultT],
        strategy: StructuredOutputStrategy,
    ) -> object:
        if strategy == "provider":
            if ProviderStrategy is None:
                return response_model
            return ProviderStrategy(response_model)
        if strategy == "tool":
            if ToolStrategy is None:
                return response_model
            return ToolStrategy(response_model)
        return response_model


def _safe_error_message(exc: BaseException, limit: int = 240) -> str:
    message = str(exc).strip()
    if not message:
        return "-"
    if len(message) <= limit:
        return message
    return f"{message[:limit]}..."


agent_langchain_runtime = AgentLangChainRuntime()
