from app.core.list_export import ListExportCatalog, ListExportField

PAYMENT_PLANS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="payment_plans",
    sheet_name="回款计划列表",
    fields=(
        ListExportField("plan_number", "计划编号", "text"),
        ListExportField("stage_name", "阶段名称", "text"),
        ListExportField("customer_name", "客户名称", "text"),
        ListExportField("contract_name", "合同名称", "text"),
        ListExportField("plan_amount", "计划金额", "currency"),
        ListExportField("due_date", "计划日期", "date"),
        ListExportField("status", "状态", "text"),
    ),
)
