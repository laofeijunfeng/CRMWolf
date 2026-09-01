"""Validation boundary for customer profile projection drafts.

The Agent may propose prose, but it cannot decide whether a draft is safe to
publish.  This validator keeps evidence attribution, scope metadata and the
product boundary (recorded information, not sales advice) deterministic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.customer_profile import CustomerProfileSections

if TYPE_CHECKING:
    from app.services.customer_profile_projection_service import CustomerProfileProjectionDraft


class CustomerProfileProjectionValidationError(ValueError):
    """A draft cannot be published as a customer profile projection."""

    code = "PROFILE_SCHEMA_INVALID"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


_FORBIDDEN_ADVICE_KEYS = frozenset(
    {
        "recommendation",
        "recommendations",
        "suggestion",
        "suggestions",
        "suggested_action",
        "recommended_action",
        "recommended_next_step",
        "sales_advice",
        "sales_guidance",
        "contact_recommendation",
        "contact_timing_recommendation",
    }
)
_ALLOWED_SCOPE_TYPES = frozenset({"customer", "journey", "opportunity"})
_FORBIDDEN_STATEMENT_ROLES = frozenset({"sales_guidance", "sales_advice", "recommendation"})


class CustomerProfileProjectionValidator:
    """Validate a draft without changing or enriching its content."""

    def validate_draft(self, draft: CustomerProfileProjectionDraft) -> CustomerProfileSections:
        try:
            sections = CustomerProfileSections.model_validate(draft.sections)
        except Exception as exc:  # Pydantic's detailed error must not cross the API boundary.
            raise CustomerProfileProjectionValidationError("客户档案段落结构无效") from exc

        evidence_registry = self._evidence_registry(draft.evidence_refs)
        if not evidence_registry and self._contains_evidence_refs(sections.model_dump(mode="python")):
            raise CustomerProfileProjectionValidationError(
                "档案包含证据引用，但证据索引为空"  # noqa: RUF001
            )
        self._validate_value(sections.model_dump(mode="python"), evidence_registry, path="sections")
        self._validate_watermarks(draft.source_watermark)
        for name in ("fact_watermark", "journey_watermark", "task_watermark", "commitment_watermark"):
            if int(getattr(draft, name, 0)) < 0:
                raise CustomerProfileProjectionValidationError(f"{name} 不能为负数")
        return sections

    def _evidence_registry(self, evidence_refs: object) -> set[str]:
        if not isinstance(evidence_refs, list):
            raise CustomerProfileProjectionValidationError("档案证据索引必须是数组")
        registry: set[str] = set()
        for index, item in enumerate(evidence_refs):
            if not isinstance(item, dict):
                raise CustomerProfileProjectionValidationError(f"证据索引第 {index + 1} 项不是对象")
            key = item.get("evidence_key") or item.get("evidence_id") or item.get("id")
            if not isinstance(key, str) or not key.strip():
                raise CustomerProfileProjectionValidationError(f"证据索引第 {index + 1} 项缺少引用标识")
            normalized = key.strip()
            if normalized in registry:
                raise CustomerProfileProjectionValidationError(f"证据引用重复: {normalized}")
            registry.add(normalized)
        return registry

    def _validate_value(self, value: object, evidence_registry: set[str], *, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                if key_text.lower() in _FORBIDDEN_ADVICE_KEYS:
                    raise CustomerProfileProjectionValidationError(
                        f"档案不得包含销售建议字段: {path}.{key_text}",
                        code="PROFILE_SALES_GUIDANCE_FORBIDDEN",
                    )
                if key_text == "evidence_refs":
                    self._validate_evidence_refs(child, evidence_registry, path=f"{path}.{key_text}")
                if (
                    key_text == "statement_role"
                    and isinstance(child, str)
                    and child.strip().lower() in _FORBIDDEN_STATEMENT_ROLES
                ):
                    raise CustomerProfileProjectionValidationError(
                        f"档案不得包含销售指导角色: {path}.{key_text}",
                        code="PROFILE_SALES_GUIDANCE_FORBIDDEN",
                    )
                if key_text == "scope_type" and child not in _ALLOWED_SCOPE_TYPES:
                    raise CustomerProfileProjectionValidationError(f"不支持的档案作用域: {child}")
                if key_text == "scope_id" and child is None:
                    raise CustomerProfileProjectionValidationError(f"{path}.scope_id 不能为空")
                self._validate_value(child, evidence_registry, path=f"{path}.{key_text}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self._validate_value(child, evidence_registry, path=f"{path}[{index}]")

    def _validate_evidence_refs(self, value: object, evidence_registry: set[str], *, path: str) -> None:
        if not isinstance(value, list):
            raise CustomerProfileProjectionValidationError(f"{path} 必须是数组")
        for index, ref in enumerate(value):
            if not isinstance(ref, str) or not ref.strip():
                raise CustomerProfileProjectionValidationError(f"{path}[{index}] 不是有效引用")
            if ref not in evidence_registry:
                raise CustomerProfileProjectionValidationError(f"证据引用不存在: {ref}")

    def _contains_evidence_refs(self, value: object) -> bool:
        if isinstance(value, dict):
            return any(key == "evidence_refs" or self._contains_evidence_refs(child) for key, child in value.items())
        if isinstance(value, list):
            return any(self._contains_evidence_refs(child) for child in value)
        return False

    def _validate_watermarks(self, value: object) -> None:
        if not isinstance(value, dict):
            raise CustomerProfileProjectionValidationError("档案来源水位必须是对象")
        for key, item in value.items():
            if isinstance(item, bool):
                raise CustomerProfileProjectionValidationError(f"来源水位 {key} 类型无效")
            if isinstance(item, int) and item < 0:
                raise CustomerProfileProjectionValidationError(f"来源水位 {key} 不能为负数")


customer_profile_projection_validator = CustomerProfileProjectionValidator()
