from __future__ import annotations

from sqlalchemy import func

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import latest_official_issued_license, person_field, related_name_expression
from app.core.list_query.types import SortCondition
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.license_application import LicenseApplication
from app.models.opportunity import Opportunity

CONTRACTS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="contracts",
    fields=[
        ListQueryField(key="contract_number", type="text", expression=Contract.contract_number),
        ListQueryField(key="contract_name", type="text", expression=Contract.contract_name),
        ListQueryField(
            key="customer_name",
            type="text",
            expression=related_name_expression(
                Customer,
                Contract.customer_id,
                Customer.account_name,
                team_id_expression=Contract.team_id,
            ),
        ),
        ListQueryField(
            key="opportunity_name",
            type="text",
            expression=related_name_expression(
                Opportunity,
                Contract.opportunity_id,
                Opportunity.opportunity_name,
                team_id_expression=Contract.team_id,
            ),
        ),
        ListQueryField(key="total_amount", type="number", expression=Contract.total_amount),
        ListQueryField(key="license_type", type="enum", expression=Contract.license_type),
        ListQueryField(
            key="purchase_type",
            type="enum",
            expression=related_name_expression(
                Opportunity,
                Contract.opportunity_id,
                Opportunity.purchase_type,
                team_id_expression=Contract.team_id,
            ),
        ),
        ListQueryField(key="subscription_years", type="number", expression=Contract.subscription_years),
        ListQueryField(
            key="license_authorized_users",
            type="number",
            expression=func.coalesce(
                latest_official_issued_license(LicenseApplication.authorized_users),
                Contract.user_count,
            ),
        ),
        ListQueryField(key="standard_unit_price", type="number", expression=Contract.standard_unit_price),
        ListQueryField(
            key="license_expiry_date",
            type="date",
            expression=latest_official_issued_license(LicenseApplication.expiry_date),
            date_kind="date",
        ),
        ListQueryField(key="status", type="enum", expression=Contract.status),
        ListQueryField(key="signing_date", type="date", expression=Contract.signing_date, date_kind="date"),
        ListQueryField(key="effective_date", type="date", expression=Contract.effective_date, date_kind="date"),
        ListQueryField(key="expiry_date", type="date", expression=Contract.expiry_date, date_kind="date"),
        ListQueryField(key="created_time", type="date", expression=Contract.created_time),
        person_field("owner_id", Contract.owner_id),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
)
