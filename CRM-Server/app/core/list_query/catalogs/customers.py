from __future__ import annotations

from sqlalchemy import select

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import (
    collaborators_name_expression,
    collaborators_predicate,
    customer_license_status_expression,
    person_field,
    source_field,
    text_search_predicate,
    user_name_expression,
)
from app.core.list_query.types import JoinSpec, SortCondition
from app.models.customer import Contact, Customer, CustomerProduct
from app.models.procurement import ProcurementMethod
from app.models.product import Product
from app.services.customer_derived_status import (
    CustomerDerivedStatus,
    derived_status_expression,
    derived_status_predicate,
)


def _customer_product_name_expression():
    return (
        select(Product.name)
        .join(CustomerProduct, CustomerProduct.product_id == Product.id)
        .where(CustomerProduct.customer_id == Customer.id, CustomerProduct.team_id == Customer.team_id)
        .order_by(CustomerProduct.product_id)
        .limit(1)
        .scalar_subquery()
    )
def _primary_contact_expression(column):
    return (
        select(column)
        .where(
            Contact.customer_id == Customer.id,
            Contact.team_id == Customer.team_id,
            Contact.is_primary == 1,
        )
        .order_by(Contact.id.asc())
        .limit(1)
        .scalar_subquery()
    )


CUSTOMERS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="customers",
    fields=[
        ListQueryField(key="account_name", type="text", expression=Customer.account_name),
        ListQueryField(key="primary_contact_name", type="text", expression=_primary_contact_expression(Contact.name)),
        ListQueryField(key="primary_contact_mobile", type="text", expression=_primary_contact_expression(Contact.mobile)),
        person_field("owner_id", Customer.owner_id),
        ListQueryField(
            key="collaborators",
            type="text",
            expression_builder=lambda _ctx: collaborators_name_expression(),
            predicate_builder=collaborators_predicate,
        ),
        ListQueryField(
            key="city",
            type="text",
            expression=Customer.city,
            allowed_ops=["eq", "neq", "contains", "not_contains", "in", "is_empty", "is_not_empty"],
        ),
        ListQueryField(key="company_scale", type="enum", expression=Customer.company_scale),
        ListQueryField(
            key="status",
            type="enum",
            enum_type=CustomerDerivedStatus,
            enum_persist="value",
            expression_builder=lambda _ctx: derived_status_expression(),
            predicate_builder=derived_status_predicate,
            allowed_ops=["eq", "neq", "in", "not_in"],
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
        ListQueryField(key="product_name", type="text", expression=_customer_product_name_expression()),
        source_field(filter_column=Customer.source_id, sort_column=Customer.source),
        ListQueryField(
            key="creator",
            type="text",
            expression=user_name_expression(Customer.creator_id),
        ),
        ListQueryField(key="created_time", type="date", expression=Customer.created_time),
        ListQueryField(
            key="last_modified_time",
            type="date",
            expression=Customer.last_modified_time,
        ),
        ListQueryField(key="returned_time", type="date", expression=Customer.returned_time),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
    search_predicate=text_search_predicate(
        _customer_product_name_expression(),
        include_customer_identity_terms=True,
    ),
)
