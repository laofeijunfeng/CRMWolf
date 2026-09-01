"""Publication policy for customer-profile projections.

The policy is the pure decision seam between a generated draft and the
persistence module.  It combines hard contract validation with non-blocking
content diagnostics, while keeping both implementations independently focused.
The Agent may call it for preflight; the publication module calls it again after
partial-section merging, so the final decision is always based on the exact
content that will be persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.customer_profile_projection_quality import (
    CustomerProfileQualityReport,
    customer_profile_projection_quality_linter,
)
from app.services.customer_profile_projection_validator import (
    CustomerProfileProjectionValidationError,
    customer_profile_projection_validator,
)

if TYPE_CHECKING:
    from app.schemas.customer_profile import CustomerProfileSections
    from app.services.customer_profile_projection_service import CustomerProfileProjectionDraft


@dataclass(frozen=True)
class CustomerProfileProjectionAssessment:
    """Validated sections and diagnostics for one exact draft."""

    sections: CustomerProfileSections
    quality_report: CustomerProfileQualityReport


class CustomerProfileProjectionPolicy:
    """Evaluate profile content without performing database or Agent side effects."""

    def assess(self, draft: CustomerProfileProjectionDraft) -> CustomerProfileProjectionAssessment:
        try:
            sections = customer_profile_projection_validator.validate_draft(draft)
        except CustomerProfileProjectionValidationError:
            raise
        quality_report = customer_profile_projection_quality_linter.lint(
            sections.model_dump(mode="python")
        )
        return CustomerProfileProjectionAssessment(
            sections=sections,
            quality_report=quality_report,
        )


customer_profile_projection_policy = CustomerProfileProjectionPolicy()
