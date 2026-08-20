from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.list_query.catalog import ListQueryCatalog

from app.core.list_query.catalogs.approvals import APPROVALS_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.contracts import CONTRACTS_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.customers import CUSTOMERS_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.follow_up_tasks import FOLLOW_UP_TASKS_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.invoices import INVOICES_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.leads import LEADS_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.opportunities import OPPORTUNITIES_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.payment_plans import PAYMENT_PLANS_LIST_QUERY_CATALOG
from app.core.list_query.catalogs.payment_records import PAYMENT_RECORDS_LIST_QUERY_CATALOG

LIST_QUERY_CATALOGS: dict[str, ListQueryCatalog] = {
    "approvals": APPROVALS_LIST_QUERY_CATALOG,
    "contracts": CONTRACTS_LIST_QUERY_CATALOG,
    "customers": CUSTOMERS_LIST_QUERY_CATALOG,
    "follow_up_tasks": FOLLOW_UP_TASKS_LIST_QUERY_CATALOG,
    "invoices": INVOICES_LIST_QUERY_CATALOG,
    "leads": LEADS_LIST_QUERY_CATALOG,
    "opportunities": OPPORTUNITIES_LIST_QUERY_CATALOG,
    "payment_plans": PAYMENT_PLANS_LIST_QUERY_CATALOG,
    "payment_records": PAYMENT_RECORDS_LIST_QUERY_CATALOG,
}

__all__ = [
    "APPROVALS_LIST_QUERY_CATALOG",
    "CONTRACTS_LIST_QUERY_CATALOG",
    "CUSTOMERS_LIST_QUERY_CATALOG",
    "FOLLOW_UP_TASKS_LIST_QUERY_CATALOG",
    "INVOICES_LIST_QUERY_CATALOG",
    "LEADS_LIST_QUERY_CATALOG",
    "LIST_QUERY_CATALOGS",
    "OPPORTUNITIES_LIST_QUERY_CATALOG",
    "PAYMENT_PLANS_LIST_QUERY_CATALOG",
    "PAYMENT_RECORDS_LIST_QUERY_CATALOG",
]
