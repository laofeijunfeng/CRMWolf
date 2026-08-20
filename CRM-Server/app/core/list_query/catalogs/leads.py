from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import person_field, source_field
from app.core.list_query.types import SortCondition
from app.models.lead import CompanyScale, Lead, LeadStatus

LEADS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="leads",
    fields=[
        ListQueryField(key="lead_name", type="text", expression=Lead.lead_name),
        person_field("owner_id", Lead.owner_id),
        ListQueryField(key="contact_name", type="text", expression=Lead.contact_name),
        ListQueryField(key="contact_phone", type="text", expression=Lead.contact_phone),
        source_field(filter_column=Lead.source_id, sort_column=Lead.source),
        ListQueryField(key="city", type="text", expression=Lead.city),
        ListQueryField(
            key="company_scale",
            type="enum",
            expression=Lead.company_scale,
            enum_type=CompanyScale,
            enum_persist="name",
        ),
        ListQueryField(
            key="status",
            type="enum",
            expression=Lead.status,
            enum_type=LeadStatus,
            enum_persist="name",
        ),
        ListQueryField(
            key="created_time",
            type="date",
            expression=Lead.created_time,
            date_semantics="exclusive",
        ),
        ListQueryField(
            key="last_modified_time",
            type="date",
            expression=Lead.last_modified_time,
            date_semantics="exclusive",
        ),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
)
