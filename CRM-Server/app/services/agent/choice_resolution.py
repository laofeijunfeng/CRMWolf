"""Reusable user-facing choice projection and resume resolution."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Optional, TypedDict

from app.services.agent.types import JSONDict, coerce_json_value


class AgentChoice(TypedDict, total=False):
    label: str
    value: str
    metadata: JSONDict


@dataclass(frozen=True)
class ChoiceResourceSpec:
    resource_type: str
    id_field: str
    id_metadata_key: str
    title_fields: tuple[str, ...]
    detail_fields: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ChoiceResolution:
    selected: Mapping[str, object] | None
    confidence: float
    reason: str
    ambiguous: bool = False


CUSTOMER_SPEC = ChoiceResourceSpec(
    resource_type="customer",
    id_field="id",
    id_metadata_key="selected_customer_id",
    title_fields=("account_name", "customer_name", "name"),
)
OPPORTUNITY_SPEC = ChoiceResourceSpec(
    resource_type="opportunity",
    id_field="id",
    id_metadata_key="selected_opportunity_id",
    title_fields=("opportunity_name", "name"),
    detail_fields=(
        ("current_stage_name", "当前阶段"),
        ("target_stage_name", "目标阶段"),
        ("purchase_type_name", "采购类型"),
        ("purchase_type_label", "采购类型"),
        ("expected_closing_date", "预计成交"),
        ("procurement_method_name", "采购方式"),
        ("procurement_method_label", "采购方式"),
        ("total_amount", "金额"),
    ),
)
CONTRACT_SPEC = ChoiceResourceSpec(
    resource_type="contract",
    id_field="id",
    id_metadata_key="selected_contract_id",
    title_fields=("contract_name", "contract_number", "name"),
    detail_fields=(("customer_name", "客户"), ("total_amount", "金额"), ("sign_date", "签约日期")),
)
PAYMENT_PLAN_SPEC = ChoiceResourceSpec(
    resource_type="payment_plan",
    id_field="id",
    id_metadata_key="selected_payment_plan_id",
    title_fields=("stage_name", "plan_name", "contract_name", "name"),
    detail_fields=(("contract_name", "合同"), ("receivable_amount", "应收"), ("remaining_amount", "剩余"), ("planned_date", "计划日期")),
)

BUSINESS_SPECS: dict[str, ChoiceResourceSpec] = {
    "opportunities": OPPORTUNITY_SPEC,
    "contracts": CONTRACT_SPEC,
    "payment_plans": PAYMENT_PLAN_SPEC,
}

_CHINESE_ORDINALS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def project_choices(spec: ChoiceResourceSpec, candidates: list[Mapping[str, object]]) -> list[AgentChoice]:
    choices: list[AgentChoice] = []
    for index, candidate in enumerate(candidates, start=1):
        label = choice_label(spec, candidate, index=index)
        metadata = choice_metadata(spec, candidate, index=index)
        choices.append({"label": label, "value": str(index), "metadata": metadata})
    return choices


def project_business_choices(event: Mapping[str, object]) -> list[AgentChoice]:
    choices: list[AgentChoice] = []
    for collection_key, spec in BUSINESS_SPECS.items():
        raw_candidates = event.get(collection_key)
        if not isinstance(raw_candidates, list):
            continue
        candidates = [item for item in raw_candidates if isinstance(item, Mapping)]
        choices.extend(project_choices(spec, candidates))
    return choices


def choice_label(spec: ChoiceResourceSpec, candidate: Mapping[str, object], *, index: int) -> str:
    title = _first_text(candidate, spec.title_fields) or f"{_fallback_resource_name(spec.resource_type)} {index}"
    details: list[str] = []
    for field, display_name in spec.detail_fields:
        value = _safe_display_text(candidate.get(field))
        if value:
            details.append(f"{display_name}：{value}")
    if not details:
        return title
    return f"{title}（{'，'.join(details)}）"


def choice_metadata(spec: ChoiceResourceSpec, candidate: Mapping[str, object], *, index: int) -> JSONDict:
    metadata: JSONDict = {
        "resource_type": spec.resource_type,
        "choice_index": index,
    }
    candidate_id = candidate.get(spec.id_field)
    if isinstance(candidate_id, int) and candidate_id > 0:
        metadata[spec.id_metadata_key] = candidate_id
        metadata["resource_id"] = candidate_id
    elif isinstance(candidate_id, str) and candidate_id.strip():
        metadata[spec.id_metadata_key] = candidate_id.strip()
        metadata["resource_id"] = candidate_id.strip()
    return metadata


def resolve_choice(
    content: str,
    *,
    metadata: Mapping[str, object],
    spec: ChoiceResourceSpec,
    candidates: list[Mapping[str, object]],
) -> ChoiceResolution:
    """Resolve only deterministic interaction-protocol choices.

    Business semantic matching is handled by the LangGraph resource-resolution
    subgraph so it can use model ranking, confidence gates, and shared fallback
    policy across CRM resource types.
    """

    selected_by_metadata = _resolve_by_metadata(metadata, spec, candidates)
    if selected_by_metadata is not None:
        return ChoiceResolution(selected=selected_by_metadata, confidence=1.0, reason="structured_metadata")

    selected_by_ordinal = _resolve_by_ordinal(content, candidates)
    if selected_by_ordinal is not None:
        return ChoiceResolution(selected=selected_by_ordinal, confidence=0.96, reason="ordinal")

    normalized = _normalize(content)
    if not normalized:
        return ChoiceResolution(selected=None, confidence=0.0, reason="empty")

    for index, candidate in enumerate(candidates, start=1):
        label = choice_label(spec, candidate, index=index)
        if normalized == _normalize(label):
            return ChoiceResolution(selected=candidate, confidence=0.98, reason="exact_choice_label")
    return ChoiceResolution(selected=None, confidence=0.0, reason="semantic_required")


def append_structured_form_values(content: str, metadata: Mapping[str, object]) -> str:
    form_values = metadata.get("form_values")
    if not isinstance(form_values, Mapping):
        return content
    hidden_parts: list[str] = []
    for key, value in form_values.items():
        if not isinstance(key, str) or not key or value in (None, ""):
            continue
        hidden_parts.append(f"{key}={value}")
    if not hidden_parts:
        return content
    return f"{content}，系统表单值：{';'.join(hidden_parts)}"


def _resolve_by_metadata(
    metadata: Mapping[str, object],
    spec: ChoiceResourceSpec,
    candidates: list[Mapping[str, object]],
) -> Mapping[str, object] | None:
    expected_type = metadata.get("resource_type")
    if isinstance(expected_type, str) and expected_type and expected_type != spec.resource_type:
        return None
    resource_id = metadata.get(spec.id_metadata_key) or metadata.get("resource_id")
    if resource_id is not None:
        for candidate in candidates:
            if _same_identifier(candidate.get(spec.id_field), resource_id):
                return candidate
    choice_index = metadata.get("choice_index")
    index = _positive_int(choice_index)
    if index is not None and 1 <= index <= len(candidates):
        return candidates[index - 1]
    return None


def _resolve_by_ordinal(content: str, candidates: list[Mapping[str, object]]) -> Mapping[str, object] | None:
    index = _ordinal_index(content)
    if index is not None and 1 <= index <= len(candidates):
        return candidates[index - 1]
    return None


def _first_text(candidate: Mapping[str, object], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = _safe_display_text(candidate.get(field))
        if value:
            return value
    return None


def _safe_display_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text if text else None
    return None


def _fallback_resource_name(resource_type: str) -> str:
    labels = {
        "customer": "客户",
        "opportunity": "商机",
        "contract": "合同",
        "payment_plan": "回款计划",
    }
    return labels.get(resource_type, "业务对象")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _ordinal_index(content: str) -> int | None:
    normalized = _normalize(content)
    digit_match = re.fullmatch(r"(?:第)?(\d+)(?:个|项|条|号)?", normalized)
    if digit_match:
        return _positive_int(digit_match.group(1))
    chinese_match = re.fullmatch(r"(?:第)?([一二两三四五六七八九十])(?:个|项|条|号)?", normalized)
    if chinese_match:
        return _CHINESE_ORDINALS.get(chinese_match.group(1))
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _same_identifier(left: object, right: object) -> bool:
    left_value = coerce_json_value(left)
    right_value = coerce_json_value(right)
    return isinstance(left_value, (str, int)) and isinstance(right_value, (str, int)) and str(left_value) == str(right_value)
