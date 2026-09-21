from app.core.list_export import ListExportCatalog, ListExportField

APPROVALS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="approvals",
    sheet_name="审批列表",
    fields=(
        ListExportField("application_number", "单号", "text"),
        ListExportField("business_type", "类型", "text"),
        ListExportField("entity_name", "实体", "text"),
        ListExportField("entity_amount", "金额", "currency"),
        ListExportField("submitter_name", "提交人", "text"),
        ListExportField("created_time", "提交时间", "datetime"),
        ListExportField("status", "状态", "text"),
        ListExportField("overdue_hours", "超时", "number"),
    ),
)
