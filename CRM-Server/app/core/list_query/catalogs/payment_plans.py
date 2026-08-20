from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import case_order, keyword_predicate
from app.core.list_query.types import SortCondition
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentPlanStatus

PAYMENT_PLANS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="payment_plans",
    fields=[
        ListQueryField(
            key="keyword",
            type="text",
            predicate_builder=keyword_predicate(
                PaymentPlan.stage_name,
                Contract.contract_name,
                Customer.account_name,
                Opportunity.opportunity_name,
            ),
        ),
        ListQueryField(key="plan_number", type="text", expression=PaymentPlan.plan_number),
        ListQueryField(key="stage_name", type="text", expression=PaymentPlan.stage_name),
        ListQueryField(key="customer_name", type="text", expression=Customer.account_name),
        ListQueryField(key="contract_name", type="text", expression=Contract.contract_name),
        ListQueryField(key="planned_amount", type="number", expression=PaymentPlan.planned_amount),
        ListQueryField(key="due_date", type="date", expression=PaymentPlan.due_date, date_kind="date"),
        ListQueryField(
            key="status",
            type="enum",
            expression=PaymentPlan.status,
            sort_expression=case_order(
                PaymentPlan.status,
                [
                    PaymentPlanStatus.PENDING,
                    PaymentPlanStatus.PARTIAL,
                    PaymentPlanStatus.COMPLETED,
                    PaymentPlanStatus.OVERDUE,
                ],
            ),
        ),
    ],
    default_sorts=[SortCondition(field="due_date", direction="asc")],
)
