from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import (
    case_order,
    keyword_predicate,
    payment_approval_status_expression,
    payment_invoice_title_expression,
    payment_owner_name_expression,
)
from app.core.list_query.types import SortCondition
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentRecord

PAYMENT_RECORDS_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="payment_records",
    fields=[
        ListQueryField(
            key="keyword",
            type="text",
            predicate_builder=keyword_predicate(
                PaymentRecord.record_number,
                PaymentPlan.stage_name,
                Contract.contract_name,
                Customer.account_name,
                PaymentRecord.actual_payer_name,
                payment_owner_name_expression(),
                PaymentRecord.commission_member_name,
                payment_invoice_title_expression(),
            ),
        ),
        ListQueryField(key="record_number", type="text", expression=PaymentRecord.record_number),
        ListQueryField(key="customer_name", type="text", expression=Customer.account_name),
        ListQueryField(key="actual_payer_name", type="text", expression=PaymentRecord.actual_payer_name),
        ListQueryField(
            key="invoice_title_text",
            type="text",
            expression=payment_invoice_title_expression(),
        ),
        ListQueryField(key="contract_name", type="text", expression=Contract.contract_name),
        ListQueryField(key="actual_amount", type="number", expression=PaymentRecord.actual_amount),
        ListQueryField(
            key="owner_name",
            type="text",
            expression=payment_owner_name_expression(),
        ),
        ListQueryField(key="commission_member_name", type="text", expression=PaymentRecord.commission_member_name),
        ListQueryField(key="payment_date", type="date", expression=PaymentRecord.payment_date, date_kind="date"),
        ListQueryField(
            key="confirmation_status",
            type="enum",
            expression=PaymentRecord.confirmation_status,
            sort_expression=case_order(
                PaymentRecord.confirmation_status,
                [
                    PaymentConfirmationStatus.PENDING,
                    PaymentConfirmationStatus.CONFIRMED,
                    PaymentConfirmationStatus.DISPUTED,
                ],
            ),
        ),
        ListQueryField(key="created_time", type="date", expression=PaymentRecord.created_time),
        ListQueryField(
            key="approval_status",
            type="enum",
            expression_builder=payment_approval_status_expression,
        ),
    ],
    default_sorts=[SortCondition(field="payment_date", direction="desc")],
)
