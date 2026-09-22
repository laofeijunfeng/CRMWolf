from app.core.list_export import ListExportCatalog, ListExportField

CONTRACTS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="contracts",
    sheet_name="合同列表",
    fields=(
        ListExportField("contract_number", "合同编号", "text"),
        ListExportField("contract_name", "合同名称", "text"),
        ListExportField("customer_name", "客户名称", "text"),
        ListExportField("opportunity_name", "商机名称", "text"),
        ListExportField("total_amount", "合同金额", "currency"),
        ListExportField("license_type", "授权模式", "text"),
        ListExportField("purchase_type", "采购类型", "text"),
        ListExportField("subscription_years", "采购年限", "number"),
        ListExportField("license_authorized_users", "授权数量", "number"),
        ListExportField("standard_unit_price", "客单价", "currency"),
        ListExportField("license_expiry_date", "授权时间", "date"),
        ListExportField("signing_date", "签署日期", "date"),
        ListExportField("created_time", "创建时间", "datetime"),
        ListExportField("owner", "负责人", "text"),
    ),
)
