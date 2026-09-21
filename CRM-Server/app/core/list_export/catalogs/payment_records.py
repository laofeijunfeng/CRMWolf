from app.core.list_export import ListExportCatalog, ListExportField

PAYMENT_RECORDS_LIST_EXPORT_CATALOG = ListExportCatalog(
    resource="payment_records",
    sheet_name="回款记录列表",
    fields=(
        ListExportField("record_number", "回款编号", "text"),
        ListExportField("customer_name", "客户名称", "text"),
        ListExportField("actual_payer_name", "实际付款方", "text"),
        ListExportField("invoice_title_text", "发票抬头", "text"),
        ListExportField("contract_name", "合同名称", "text"),
        ListExportField("actual_amount", "回款金额", "currency"),
        ListExportField("owner_name", "负责人", "text"),
        ListExportField("commission_member_name", "团队成员", "text"),
        ListExportField("payment_date", "回款日期", "date"),
        ListExportField("confirmation_status", "状态", "text"),
        ListExportField("created_time", "创建时间", "datetime"),
    ),
)
