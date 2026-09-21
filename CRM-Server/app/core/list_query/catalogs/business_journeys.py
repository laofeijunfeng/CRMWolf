from __future__ import annotations

from sqlalchemy import func

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import person_field, text_search_predicate
from app.models.customer import Customer
from app.models.deal_journey import CustomerDealJourney
from app.models.opportunity import Opportunity
from app.models.product import Product


def _derived_stage_predicate(condition, field, context, parsed_value):  # noqa: ARG001
    """Advertise derived-stage operators; the query service applies them in Python."""
    return None


BUSINESS_JOURNEYS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="business_journeys",
    fields=[
        ListQueryField(
            key="journey_name",
            type="text",
            expression=CustomerDealJourney.name,
        ),
        ListQueryField(
            key="customer_name",
            type="text",
            expression=Customer.account_name,
        ),
        ListQueryField(
            key="stage",
            type="enum",
            allowed_ops=("eq", "neq", "in", "not_in"),
            predicate_builder=_derived_stage_predicate,
        ),
        person_field(
            "owner_id",
            func.coalesce(Opportunity.owner_id, Customer.owner_id),
        ),
        ListQueryField(
            key="amount",
            type="number",
            expression=func.coalesce(
                Opportunity.actual_amount,
                Opportunity.total_amount,
                0,
            ),
        ),
        ListQueryField(
            key="purchase_type",
            type="enum",
            expression=Opportunity.purchase_type,
        ),
        ListQueryField(
            key="product_name",
            type="text",
            expression=Product.name,
        ),
        ListQueryField(
            key="last_event_at",
            type="date",
            expression=CustomerDealJourney.last_event_at,
        ),
        ListQueryField(
            key="started_at",
            type="date",
            expression=CustomerDealJourney.started_at,
        ),
        ListQueryField(
            key="created_time",
            type="date",
            expression=Opportunity.created_time,
        ),
        ListQueryField(
            key="expected_closing_date",
            type="date",
            expression=Opportunity.expected_closing_date,
            date_kind="date",
        ),
        ListQueryField(
            key="status",
            type="enum",
            expression=CustomerDealJourney.status,
        ),
    ],
    search_predicate=text_search_predicate(
        CustomerDealJourney.name,
        Opportunity.opportunity_name,
        Product.name,
        include_customer_identity_terms=True,
    ),
)


__all__ = ["BUSINESS_JOURNEYS_LIST_QUERY_CATALOG"]
