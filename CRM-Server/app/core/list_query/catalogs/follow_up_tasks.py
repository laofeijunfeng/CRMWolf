from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import (
    follow_up_content_expression,
    follow_up_customer_name_expression,
    follow_up_status_label_expression,
)
from app.core.list_query.types import SortCondition
from app.models.sales_commitment import FollowUpTask

FOLLOW_UP_TASKS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="follow_up_tasks",
    fields=[
        ListQueryField(
            key="customer_name",
            type="text",
            expression=follow_up_customer_name_expression(),
        ),
        ListQueryField(
            key="tracking_content",
            type="text",
            expression=follow_up_content_expression(),
        ),
        ListQueryField(
            key="status_label",
            type="enum",
            expression=follow_up_status_label_expression(),
        ),
        ListQueryField(
            key="tracking_time",
            type="date",
            expression=FollowUpTask.due_at,
        ),
    ],
    default_sorts=[SortCondition(field="tracking_time", direction="asc")],
)
