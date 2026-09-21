from app.core.list_export import ListExportCatalog, ListExportField

CUSTOMERS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="customers",
    sheet_name="客户列表",
    fields=(
        ListExportField("public_id", "业务 ID", "text"),
        ListExportField("account_name", "客户名称", "text"),
        ListExportField("owner", "负责人", "text"),
        ListExportField("collaborators", "协作者", "text"),
        ListExportField("city", "城市", "text"),
        ListExportField("company_scale", "规模", "text"),
        ListExportField("status", "状态", "text"),
        ListExportField("license_status", "授权状态", "text"),
        ListExportField("license_expiry_date", "授权到期", "date"),
        ListExportField("default_procurement_method", "默认采购方式", "text"),
        ListExportField("industry", "行业", "text"),
        ListExportField("source", "来源", "text"),
        ListExportField("product_name", "产品", "text"),
        ListExportField("creator", "创建人", "text"),
        ListExportField("created_time", "创建时间", "datetime"),
    ),
)
