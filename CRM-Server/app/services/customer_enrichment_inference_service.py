from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime, agent_model_enable_thinking
from app.services.customer_enrichment_contracts import CustomerEnrichmentInferenceResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.services.customer_enrichment_plan import CustomerEnrichmentFieldRegistry


class CustomerEnrichmentInferenceError(Exception):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class CustomerEnrichmentInferenceService:
    def __init__(
        self,
        *,
        runtime: AgentLangChainRuntime | None = None,
        registry: CustomerEnrichmentFieldRegistry | None = None,
    ) -> None:
        if registry is None:
            from app.services.customer_enrichment_plan import CustomerEnrichmentFieldRegistry

            registry = CustomerEnrichmentFieldRegistry()
        self.runtime = runtime or AgentLangChainRuntime()
        self.registry = registry

    async def infer(
        self,
        db: Session,
        team_id: int,
        context: dict[str, object],
        requested_fields: tuple[str, ...],
    ) -> CustomerEnrichmentInferenceResult:
        try:
            config = ai_config_crud.get_config(db, team_id)
            if config is None:
                raise CustomerEnrichmentInferenceError("AI 配置未设置")
            api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
            if not api_key:
                raise CustomerEnrichmentInferenceError("AI API Key 未设置")

            catalogs = _requested_catalogs(context, requested_fields)
            self.registry.validate_catalogs(requested_fields, catalogs)
            result = await self.runtime.ainvoke_structured(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                temperature=0.1,
                enable_thinking=agent_model_enable_thinking(config.model_name),
                system_prompt=_system_prompt(requested_fields),
                user_prompt=_user_prompt(context, requested_fields),
                response_model=CustomerEnrichmentInferenceResult,
                structured_output_strategy="tool",
                error_prefix="客户初始补全 structured output",
            )
            if result is None:
                raise CustomerEnrichmentInferenceError("客户初始补全模型不可用")
            self.registry.validate(result.decisions, requested_fields, catalogs)
            return result
        except CustomerEnrichmentInferenceError:
            raise
        except Exception as exc:
            raise CustomerEnrichmentInferenceError(f"客户初始补全推断失败: {exc}") from exc


def _requested_catalogs(
    context: dict[str, object],
    requested_fields: Sequence[str],
) -> dict[str, list[dict[str, object]]]:
    raw_catalogs = context.get("catalogs")
    if not isinstance(raw_catalogs, dict):
        raise CustomerEnrichmentInferenceError("客户补全目录缺失")

    catalogs: dict[str, list[dict[str, object]]] = {}
    for field in requested_fields:
        raw_catalog = raw_catalogs.get(field)
        if not isinstance(raw_catalog, list):
            raise CustomerEnrichmentInferenceError(f"客户补全字段目录缺失: {field}")
        if not all(isinstance(item, dict) for item in raw_catalog):
            raise CustomerEnrichmentInferenceError(f"客户补全字段目录无效: {field}")
        catalogs[field] = raw_catalog
    return catalogs


def _system_prompt(requested_fields: Sequence[str]) -> str:
    field_list = ", ".join(requested_fields)
    return f"""你是 CRM 客户初始主数据补全模型。

本次只允许返回这些字段：{field_list}。
规则：
- 每个 requested field 必须且只能出现一次，不得遗漏或重复。
- industry 必须从输入提供的启用行业目录中选择精确 code，禁止输出名称或自由文本。
- 业务信息不足、无法判断行业时，返回目录中的 other code。
- 不得返回未注册字段。
- 不得返回 confidence、置信度或推理过程。
- reason 只写简短业务依据，不包含 chain-of-thought。
"""


def _user_prompt(context: dict[str, object], requested_fields: Sequence[str]) -> str:
    payload = {
        "requested_fields": list(requested_fields),
        "context": context,
    }
    return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
