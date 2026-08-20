from __future__ import annotations

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.catalogs.common import (
    invoice_effective_status_expression,
    invoice_keyword_predicate,
    related_name_expression,
    user_name_expression,
)
from app.core.list_query.types import SortCondition
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import InvoiceApplication

INVOICES_LIST_QUERY_CATALOG = ListQueryCatalog(
    name="invoices",
    fields=[
        ListQueryField(
            key="keyword",
            type="text",
            predicate_builder=invoice_keyword_predicate,
        ),
        ListQueryField(key="application_number", type="text", expression=InvoiceApplication.application_number),
        ListQueryField(
            key="customer_name",
            type="text",
            expression=related_name_expression(
                Customer,
                InvoiceApplication.customer_id,
                Customer.account_name,
                team_id_expression=InvoiceApplication.team_id,
            ),
        ),
        ListQueryField(
            key="contract_name",
            type="text",
            expression=related_name_expression(
                Contract,
                InvoiceApplication.contract_id,
                Contract.contract_name,
                team_id_expression=InvoiceApplication.team_id,
            ),
        ),
        ListQueryField(key="invoice_type", type="enum", expression=InvoiceApplication.invoice_type),
        ListQueryField(key="invoice_amount", type="number", expression=InvoiceApplication.invoice_amount),
        ListQueryField(key="invoice_title_text", type="text", expression=InvoiceApplication.invoice_title_text),
        ListQueryField(key="status", type="enum", expression=InvoiceApplication.status),
        ListQueryField(
            key="invoice_effective_status",
            type="enum",
            expression_builder=invoice_effective_status_expression,
        ),
        ListQueryField(
            key="applicant_name",
            type="text",
            expression=user_name_expression(InvoiceApplication.applicant_id),
        ),
        ListQueryField(key="created_time", type="date", expression=InvoiceApplication.created_time),
        ListQueryField(key="issued_time", type="date", expression=InvoiceApplication.issued_time),
    ],
    default_sorts=[SortCondition(field="created_time", direction="desc")],
)
