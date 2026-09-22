from app.core.list_export import ListExportCatalog, ListExportField

FOLLOW_UP_TASKS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="follow_up_tasks",
    sheet_name="客户追踪列表",
    fields=(
        ListExportField("public_id", "业务 ID", "text"),
        ListExportField("customer_name", "客户", "text"),
        ListExportField("tracking_content", "追踪内容", "text"),
        ListExportField("status_label", "状态", "text"),
        ListExportField("tracking_time", "跟进时效", "datetime"),
    ),
)
