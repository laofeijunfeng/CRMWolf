"""审批业务单据类型枚举（防幻觉：禁止推断，必须查本文件）"""

class BusinessType:
    CONTRACT = "CONTRACT"
    PAYMENT = "PAYMENT"
    INVOICE = "INVOICE"
    LICENSE = "LICENSE"

ALL_BUSINESS_TYPES = [BusinessType.CONTRACT, BusinessType.PAYMENT, BusinessType.INVOICE, BusinessType.LICENSE]

BUSINESS_TYPE_DISPLAY_NAMES = {
    BusinessType.CONTRACT: "合同",
    BusinessType.PAYMENT: "回款登记",
    BusinessType.INVOICE: "发票申请",
    BusinessType.LICENSE: "License申请",
}

def is_valid_business_type(business_type: str) -> bool:
    return business_type in ALL_BUSINESS_TYPES