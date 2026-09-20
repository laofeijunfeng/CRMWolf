from __future__ import annotations

import re

from app.crud.industry import industry_crud
from app.crud.product_intent import product_intent_payload
from app.models.customer import Contact, Customer, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.lead import Lead, LeadFollowUp
from app.services.customer_enrichment_inference_service import CustomerEnrichmentInferenceError
from app.services.customer_enrichment_plan import CustomerEnrichmentFieldRegistry
from sqlalchemy.orm import joinedload


class CustomerEnrichmentContextService:
    def __init__(self, *, registry: CustomerEnrichmentFieldRegistry | None = None) -> None:
        self.registry = registry or CustomerEnrichmentFieldRegistry()

    def build(
        self,
        db,
        team_id: int,
        customer_id: int,
        fields: tuple[str, ...],
    ) -> dict[str, object]:
        customer = (
            db.query(Customer)
            .options(joinedload(Customer.product_links).joinedload(CustomerProduct.product))
            .filter(Customer.id == customer_id, Customer.team_id == team_id)
            .first()
        )
        if customer is None:
            raise CustomerEnrichmentInferenceError("客户不存在")

        primary_contact = (
            db.query(Contact)
            .filter(
                Contact.customer_id == customer.id,
                Contact.team_id == team_id,
                Contact.is_primary == 1,
            )
            .order_by(Contact.id.asc())
            .first()
        )
        activities = (
            db.query(CustomerActivity)
            .filter(
                CustomerActivity.customer_id == customer.id,
                CustomerActivity.team_id == team_id,
            )
            .order_by(CustomerActivity.occurred_at.desc(), CustomerActivity.id.desc())
            .limit(5)
            .all()
        )

        contact_pii = tuple(
            value
            for value in (
                getattr(primary_contact, "name", None),
                getattr(primary_contact, "mobile", None),
                getattr(primary_contact, "email", None),
            )
            if isinstance(value, str) and value
        )
        source_lead, source_follow_ups = self._source_lead_context(
            db,
            team_id=team_id,
            source_lead_id=getattr(customer, "source_lead_id", None),
            contact_pii=contact_pii,
        )
        products = product_intent_payload(getattr(customer, "product_links", None))["products"]
        return {
            "customer": {
                "account_name": customer.account_name,
                "city": customer.city,
                "company_scale": customer.company_scale,
                "source": customer.source,
                "version": customer.version,
            },
            "products": products,
            "primary_contact": (
                {"position": primary_contact.position}
                if primary_contact is not None
                else None
            ),
            "recent_activities": [self._activity_payload(item, contact_pii) for item in activities],
            "source_lead": source_lead,
            "recent_lead_follow_ups": source_follow_ups,
            "catalogs": self.registry.catalogs(db, team_id, fields),
        }

    @staticmethod
    def _activity_payload(
        activity: CustomerActivity,
        contact_pii: tuple[str, ...],
    ) -> dict[str, object]:
        summary = getattr(activity, "summary", None)
        source_content = getattr(activity, "source_content", None)
        text = summary if isinstance(summary, str) and summary.strip() else source_content
        return {
            "kind": getattr(activity, "activity_kind", None),
            "text": _sanitize_text(text, contact_pii)[:500],
        }

    @staticmethod
    def _source_lead_context(
        db,
        *,
        team_id: int,
        source_lead_id: int | None,
        contact_pii: tuple[str, ...],
    ) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
        if source_lead_id is None:
            return None, []
        lead = (
            db.query(Lead)
            .filter(Lead.id == source_lead_id, Lead.team_id == team_id)
            .first()
        )
        if lead is None:
            return None, []
        lead_pii = contact_pii + tuple(
            value
            for value in (
                getattr(lead, "contact_name", None),
                getattr(lead, "contact_phone", None),
            )
            if isinstance(value, str) and value
        )
        follow_ups = (
            db.query(LeadFollowUp)
            .filter(LeadFollowUp.lead_id == lead.id, LeadFollowUp.team_id == team_id)
            .order_by(LeadFollowUp.created_time.desc(), LeadFollowUp.id.desc())
            .limit(5)
            .all()
        )
        return (
            {
                "lead_name": lead.lead_name,
                "city": lead.city,
                "company_scale": lead.company_scale,
                "source": lead.source,
            },
            [
                {
                    "method": _enum_value(getattr(item, "method", None)),
                    "text": _sanitize_text(getattr(item, "content", None), lead_pii)[:500],
                }
                for item in follow_ups
            ],
        )


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _sanitize_text(value: object, sensitive_values: tuple[str, ...]) -> str:
    text = str(value or "")
    for sensitive in sensitive_values:
        text = text.replace(sensitive, "[已脱敏]")
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[已脱敏]", text)
    return re.sub(
        r"(?i)(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])",
        "[已脱敏]",
        text,
    )
