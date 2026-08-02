"""LLM-backed customer fact extraction.

The extractor is intentionally read-only: it turns a customer intelligence event
and the unified customer context into candidate facts. Deterministic graph nodes
decide whether and how those candidates are persisted.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.ai_service import ai_service
from app.services.customer_fact_service import CustomerFactType

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

FactExtractionAction: TypeAlias = Literal["upsert", "review", "ignore"]


class CustomerFactExtractionError(Exception):
    """Raised when customer fact extraction cannot call or validate AI output."""


class ExtractedCustomerFact(BaseModel):
    fact_type: CustomerFactType = Field(..., description="客户事实类型")
    subject: str | None = Field(None, max_length=120, description="事实主体，例如 POC、预算、审批、竞品、关键人")
    content: str = Field(..., min_length=1, max_length=800, description="可沉淀的客户事实")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="事实可靠度")
    action: FactExtractionAction = Field("upsert", description="upsert=可直接沉淀，review=需人工复核，ignore=不沉淀")
    evidence_quote: str | None = Field(None, max_length=300, description="来自触发事件或证据的短引用")
    reason: str = Field("", max_length=300, description="为什么提炼该事实")

    @field_validator("subject", "evidence_quote", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("reason")
    @classmethod
    def _clean_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("content")
    @classmethod
    def _clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("事实内容不能为空")
        return cleaned


class CustomerFactExtractionResult(BaseModel):
    summary: str = Field("", max_length=500, description="本次抽取概况")
    facts: list[ExtractedCustomerFact] = Field(default_factory=list, max_length=12)


class CustomerFactExtractionService:
    def __init__(
        self,
        *,
        runtime: AgentLangChainRuntime | None = None,
        ai_client=ai_service,
    ) -> None:
        self.runtime = runtime or AgentLangChainRuntime()
        self.ai_client = ai_client

    async def extract(
        self,
        db: Session,
        *,
        team_id: int,
        event: JsonObject,
        customer_context: JsonObject,
        customer_memory: JsonObject | None = None,
        current_date: date | None = None,
    ) -> CustomerFactExtractionResult:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise CustomerFactExtractionError("AI 配置未设置，无法提炼客户事实。")
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise CustomerFactExtractionError("AI API Key 未设置，无法提炼客户事实。")

        prompt_date = current_date or date.today()
        user_prompt = _build_user_prompt(
            event=event,
            customer_context=customer_context,
            customer_memory=customer_memory or {},
        )
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                temperature=min(float(config.temperature or 0.1), 0.2),
                system_prompt=_system_prompt(prompt_date),
                user_prompt=user_prompt,
                response_model=CustomerFactExtractionResult,
                structured_output_strategy="tool",
                error_prefix="客户事实提炼 structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            raise CustomerFactExtractionError(str(exc)) from exc
        except Exception:
            result = None
        if result is not None:
            return result

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=[
                {"role": "system", "content": _system_prompt(prompt_date)},
                {"role": "user", "content": user_prompt},
            ],
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=max(int(config.max_tokens or 1024), 1200),
            response_format={"type": "json_object"},
        )
        try:
            return CustomerFactExtractionResult.model_validate(json.loads(_clean_json(raw)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise CustomerFactExtractionError(f"客户事实提炼结果无效：{str(exc)}") from exc


def _system_prompt(current_date: date) -> str:
    return f"""你是 CRM 客户智能档案的事实提炼 Agent。

当前日期：{current_date.isoformat()}

任务：从本次触发事件、强业务上下文、语义证据和客户长期记忆中提炼可复用的客户事实。

原则：
- 只能提炼有明确依据的事实，不要编造。
- MySQL strong_context 是强事实；semantic_evidence 只是辅助证据。
- 不要把合同、商机、回款等系统字段改写成强事实；只沉淀客户别名、客户需求、风险、预算、阶段状态、关键人态度、竞品、下一步、偏好、摘要。
- 如果证据明确表达客户的简称、别称、集团简称、机构简称或常用内部叫法，输出 fact_type=alias；subject 和 content 均使用该称呼本身，不要包含系统 ID 或代码。
- 同一个 subject 下只输出当前最有价值的一条事实。
- confidence >= 0.75 且证据清楚时 action=upsert；0.55 到 0.75 或存在冲突时 action=review；低于 0.55 或无业务价值时 action=ignore。
- 输出必须符合结构化 schema，不要输出 Markdown 或解释文字。"""


def _build_user_prompt(
    *,
    event: JsonObject,
    customer_context: JsonObject,
    customer_memory: JsonObject,
) -> str:
    return (
        "【触发事件】\n"
        f"{_json_dump(event)}\n\n"
        "【统一客户上下文】\n"
        f"{_json_dump(customer_context)}\n\n"
        "【LangGraph Store 客户记忆】\n"
        f"{_json_dump(customer_memory)}"
    )


def _json_dump(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _clean_json(raw: str) -> str:
    content = raw.strip()
    if content.startswith("```json"):
        content = content[7:].strip()
    elif content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end >= start:
        return content[start:end + 1]
    return content


customer_fact_extraction_service = CustomerFactExtractionService()
