from app.core.list_export.catalog import ListExportCatalog
from app.core.list_export.catalogs.approvals import APPROVALS_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.contracts import CONTRACTS_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.customers import CUSTOMERS_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.follow_up_tasks import FOLLOW_UP_TASKS_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.invoices import INVOICES_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.leads import LEADS_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.opportunities import OPPORTUNITIES_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.payment_plans import PAYMENT_PLANS_LIST_EXPORT_CATALOG
from app.core.list_export.catalogs.payment_records import PAYMENT_RECORDS_LIST_EXPORT_CATALOG

LIST_EXPORT_CATALOGS: dict[str, ListExportCatalog] = {
    "approvals": APPROVALS_LIST_EXPORT_CATALOG,
    "contracts": CONTRACTS_LIST_EXPORT_CATALOG,
    "customers": CUSTOMERS_LIST_EXPORT_CATALOG,
    "follow_up_tasks": FOLLOW_UP_TASKS_LIST_EXPORT_CATALOG,
    "invoices": INVOICES_LIST_EXPORT_CATALOG,
    "leads": LEADS_LIST_EXPORT_CATALOG,
    "opportunities": OPPORTUNITIES_LIST_EXPORT_CATALOG,
    "payment_plans": PAYMENT_PLANS_LIST_EXPORT_CATALOG,
    "payment_records": PAYMENT_RECORDS_LIST_EXPORT_CATALOG,
}

__all__ = [
    "APPROVALS_LIST_EXPORT_CATALOG",
    "CONTRACTS_LIST_EXPORT_CATALOG",
    "CUSTOMERS_LIST_EXPORT_CATALOG",
    "FOLLOW_UP_TASKS_LIST_EXPORT_CATALOG",
    "INVOICES_LIST_EXPORT_CATALOG",
    "LEADS_LIST_EXPORT_CATALOG",
    "LIST_EXPORT_CATALOGS",
    "OPPORTUNITIES_LIST_EXPORT_CATALOG",
    "PAYMENT_PLANS_LIST_EXPORT_CATALOG",
    "PAYMENT_RECORDS_LIST_EXPORT_CATALOG",
]
