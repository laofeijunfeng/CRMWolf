"""Non-blocking content quality checks for customer profile projections.

Contract validation answers: *can this projection be published safely?*
Quality linting answers: *is the generated narrative worth reviewing?*
The latter must never turn a readable customer profile into a failed Agent run.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CustomerProfileQualitySeverity = Literal["WARNING"]


class CustomerProfileQualityIssue(BaseModel):
    """A diagnostic for generated content, not a user-facing profile field."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: CustomerProfileQualitySeverity = "WARNING"
    path: str
    message: str


class CustomerProfileQualityReport(BaseModel):
    """Stable report carried by the run audit and the published version."""

    model_config = ConfigDict(extra="forbid")

    issues: list[CustomerProfileQualityIssue] = Field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(self.issues)

    def as_json(self) -> dict[str, object]:
        return self.model_dump(mode="json")


# These roles describe what the customer record says. They are deliberately
# not sales guidance even when the customer's wording contains "建议".
_CUSTOMER_EXPRESSION_ROLES = frozenset(
    {
        "customer_expression",
        "customer_requirement",
        "customer_commitment",
        "customer_constraint",
        "recorded_fact",
        "follow_up_record",
    }
)
_TEXT_KEYS = frozenset({"content", "statement", "change", "overview", "note", "summary"})
_SALES_GUIDANCE_PATTERN = re.compile(
    r"(?:建议销售|建议跟进|建议联系|建议优先|优先联系|下一步建议|销售(?:应|应该|需要)|需要销售)"
)


class CustomerProfileProjectionQualityLinter:
    """Find likely sales guidance without rejecting customer-recorded wording."""

    def lint(self, sections: object) -> CustomerProfileQualityReport:
        issues: list[CustomerProfileQualityIssue] = []
        self._walk(sections, path="sections", statement_role=None, issues=issues)
        return CustomerProfileQualityReport(issues=issues)

    def _walk(
        self,
        value: object,
        *,
        path: str,
        statement_role: str | None,
        issues: list[CustomerProfileQualityIssue],
    ) -> None:
        if isinstance(value, dict):
            current_role = statement_role
            raw_role = value.get("statement_role")
            if isinstance(raw_role, str) and raw_role.strip():
                current_role = raw_role.strip().lower()
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}"
                if key_text in _TEXT_KEYS and isinstance(child, str):
                    self._check_text(
                        child,
                        path=child_path,
                        statement_role=current_role,
                        issues=issues,
                    )
                self._walk(
                    child,
                    path=child_path,
                    statement_role=current_role,
                    issues=issues,
                )
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                self._walk(
                    child,
                    path=f"{path}[{index}]",
                    statement_role=statement_role,
                    issues=issues,
                )

    def _check_text(
        self,
        text: str,
        *,
        path: str,
        statement_role: str | None,
        issues: list[CustomerProfileQualityIssue],
    ) -> None:
        if statement_role in _CUSTOMER_EXPRESSION_ROLES:
            return
        # A common and valid customer statement is "客户建议先……". The
        # subject is the customer, not the seller; do not turn it into a warning.
        if "客户建议" in text or "对方建议" in text:
            return
        if _SALES_GUIDANCE_PATTERN.search(text):
            issues.append(
                CustomerProfileQualityIssue(
                    code="PROFILE_NARRATIVE_SALES_GUIDANCE_SUSPECTED",
                    path=path,
                    message="该段叙事可能包含面向销售的指导表达",
                )
            )


customer_profile_projection_quality_linter = CustomerProfileProjectionQualityLinter()
