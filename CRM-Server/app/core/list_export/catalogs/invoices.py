from app.core.list_export import ListExportCatalog, ListExportField

INVOICES_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="invoices",
    sheet_name="发票申请列表",
    fields=(
        ListExportField("application_number", "申请单号", "text"),
        ListExportField("customer_name", "客户名称", "text"),
        ListExportField("contract_name", "合同名称", "text"),
        ListExportField("invoice_type", "发票类型", "text"),
        ListExportField("invoice_amount", "开票金额", "currency"),
        ListExportField("invoice_title_text", "开票抬头", "text"),
        ListExportField("status", "状态", "text"),
        ListExportField("invoice_effective_status", "发票状态", "text"),
        ListExportField("applicant_name", "申请人", "text"),
        ListExportField("created_time", "创建时间", "datetime"),
    ),
)
