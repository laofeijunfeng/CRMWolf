from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import person_field, related_name_expression
from app.core.list_query.types import SortCondition
from app.models.customer import Customer
from app.models.opportunity import Opportunity

OPPORTUNITIES_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="opportunities",
    fields=[
        ListQueryField(key="opportunity_name", type="text", expression=Opportunity.opportunity_name),
        person_field("owner_id", Opportunity.owner_id),
        ListQueryField(
            key="customer_name",
            type="text",
            expression=related_name_expression(
                Customer,
                Opportunity.customer_id,
                Customer.account_name,
                team_id_expression=Opportunity.team_id,
            ),
        ),
        ListQueryField(key="total_amount", type="number", expression=Opportunity.total_amount),
        ListQueryField(key="user_count", type="number", expression=Opportunity.user_count),
        ListQueryField(key="license_type", type="enum", expression=Opportunity.license_type),
        ListQueryField(key="purchase_type", type="enum", expression=Opportunity.purchase_type),
        ListQueryField(
            key="expected_closing_date",
            type="date",
            expression=Opportunity.expected_closing_date,
            date_kind="date",
        ),
        ListQueryField(key="stage_name", type="text", expression=Opportunity.current_stage_name),
        ListQueryField(key="win_probability", type="number", expression=Opportunity.win_probability),
        ListQueryField(key="status", type="enum", expression=Opportunity.status),
        ListQueryField(key="approval_phase", type="enum", expression=Opportunity.approval_phase),
        ListQueryField(key="created_time", type="date", expression=Opportunity.created_time),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
)
