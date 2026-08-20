from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import (
    collaborators_name_expression,
    collaborators_predicate,
    customer_license_status_expression,
    person_field,
    source_field,
    user_name_expression,
)
from app.core.list_query.types import JoinSpec, SortCondition
from app.models.customer import Customer, CustomerStatus
from app.models.procurement import ProcurementMethod

CUSTOMERS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="customers",
    fields=[
        ListQueryField(key="account_name", type="text", expression=Customer.account_name),
        person_field("owner_id", Customer.owner_id),
        ListQueryField(
            key="collaborators",
            type="text",
            expression_builder=lambda _ctx: collaborators_name_expression(),
            predicate_builder=collaborators_predicate,
        ),
        ListQueryField(key="city", type="text", expression=Customer.city),
        ListQueryField(key="company_scale", type="enum", expression=Customer.company_scale),
        ListQueryField(
            key="status",
            type="enum",
            expression=Customer.status,
            enum_type=CustomerStatus,
            enum_persist="value",
        ),
        ListQueryField(
            key="license_status",
            type="enum",
            expression_builder=customer_license_status_expression,
        ),
        ListQueryField(
            key="license_expiry_date",
            type="date",
            expression=Customer.license_expiry_date,
            date_kind="date",
        ),
        ListQueryField(
            key="default_procurement_method",
            type="text",
            expression=ProcurementMethod.name,
            joins=[
                JoinSpec(
                    key="default_procurement_method",
                    target=ProcurementMethod,
                    onclause=Customer.default_procurement_method_id == ProcurementMethod.id,
                    isouter=True,
                )
            ],
        ),
        ListQueryField(key="industry", type="enum", expression=Customer.industry),
        source_field(filter_column=Customer.source_id, sort_column=Customer.source),
        ListQueryField(
            key="creator",
            type="text",
            expression=user_name_expression(Customer.creator_id),
        ),
        ListQueryField(key="created_time", type="date", expression=Customer.created_time),
        ListQueryField(key="returned_time", type="date", expression=Customer.returned_time),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
)
