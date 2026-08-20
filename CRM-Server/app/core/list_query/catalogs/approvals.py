from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import (
    approval_application_number_expression,
    approval_entity_amount_expression,
    approval_entity_name_expression,
    approval_overdue_hours_expression,
)
from app.core.list_query.types import SortCondition
from app.models.approval import Approval

APPROVALS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="approvals",
    fields=[
        ListQueryField(
            key="application_number",
            type="text",
            expression=approval_application_number_expression(),
        ),
        ListQueryField(key="business_type", type="enum", expression=Approval.business_type),
        ListQueryField(
            key="entity_name",
            type="text",
            expression=approval_entity_name_expression(),
        ),
        ListQueryField(
            key="entity_amount",
            type="number",
            expression=approval_entity_amount_expression(),
        ),
        ListQueryField(key="submitter_name", type="text", expression=Approval.submitter_name),
        ListQueryField(key="created_time", type="date", expression=Approval.created_time),
        ListQueryField(key="status", type="enum", expression=Approval.status),
        ListQueryField(
            key="overdue_hours",
            type="number",
            expression_builder=approval_overdue_hours_expression,
        ),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
)
