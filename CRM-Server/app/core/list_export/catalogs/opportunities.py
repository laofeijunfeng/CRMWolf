from app.core.list_export import ListExportCatalog, ListExportField

OPPORTUNITIES_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="opportunities",
    sheet_name="商机列表",
    fields=(
        ListExportField("public_id", "业务 ID", "text"),
        ListExportField("opportunity_name", "商机名称", "text"),
        ListExportField("owner", "负责人", "text"),
        ListExportField("customer_name", "客户名称", "text"),
        ListExportField("product_name", "产品", "text"),
        ListExportField("total_amount", "预计金额", "currency"),
        ListExportField("user_count", "用户数", "number"),
        ListExportField("license_type", "授权模式", "text"),
        ListExportField("purchase_type", "采购类型", "text"),
        ListExportField("expected_closing_date", "预计成交日期", "date"),
        ListExportField("stage", "销售阶段", "text"),
        ListExportField("win_probability", "赢率", "number"),
        ListExportField("status", "状态", "text"),
        ListExportField("approval_phase", "审批", "text"),
        ListExportField("created_time", "创建时间", "datetime"),
    ),
)
