from app.core.list_export import ListExportCatalog, ListExportField

LEADS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="leads",
    sheet_name="线索列表",
    fields=(
        ListExportField("public_id", "业务 ID", "text"),
        ListExportField("lead_name", "线索名称", "text"),
        ListExportField("owner", "负责人", "text"),
        ListExportField("contact_name", "联系人", "text"),
        ListExportField("contact_phone", "联系电话", "text"),
        ListExportField("source", "来源", "text"),
        ListExportField("product_name", "产品", "text"),
        ListExportField("city", "城市", "text"),
        ListExportField("company_scale", "规模", "text"),
        ListExportField("status", "状态", "text"),
        ListExportField("created_time", "创建时间", "datetime"),
    ),
)
