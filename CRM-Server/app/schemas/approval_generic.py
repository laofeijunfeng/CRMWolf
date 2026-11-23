"""通用审批 API 端点请求/响应 Schema\uff08Task A6\uff09。

与 `app/schemas/approval.py` 解耦\uff1a旧 schema 仍服务 `/contracts/{contract_id}/...`
合同专用端点\uff08含 ApprovalDetailResponse 等完整响应模型\uff09\uff0c本模块仅定义通用端点
`/v1/approvals/{entity_type}/{entity_id}/...` 所需的轻量请求体。
`ApprovalActionRequest`\uff08action/comment/updated_time\uff09复用既有
`schemas.approval.ApprovalActionRequest`\uff0c避免重复定义与 enum 行为分叉。

设计要点\uff1a
- submit 仅需 comment\uff08可选\uff09
- approve 复用 schemas.approval.ApprovalActionRequest\uff08ApprovalActionEnum + 乐观锁 updated_time\uff09
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.approval import ApprovalRecordResponse
from app.schemas.contract import ContractChangeItem, ContractFinancialSnapshotResponse


class ApprovalSubmitRequest(BaseModel):
    """通用审批提交请求。"""
    comment: str | None = Field(
        None,
        description="提交说明\uff0c提交时填写的说明信息\uff08可选\uff09",
    )


class GenericApprovalSubmitResponse(BaseModel):
    """通用审批提交响应。"""
    approval_id: int = Field(..., description="新建审批实例 ID")
    status: str = Field(..., description="审批状态\uff1aPENDING/APPROVED/REJECTED/CANCELLED")


class ApprovalCustomerInfoResponse(BaseModel):
    """审批关联客户/公司基础信息。"""

    id: str = Field(..., description="客户对外ID")
    public_id: str | None = Field(None, description="客户对外ID")
    account_name: str = Field(..., description="客户公司名称")
    industry: str | None = Field(None, description="所属行业")
    city: str | None = Field(None, description="所在城市")
    company_scale: str | None = Field(None, description="公司规模")
    source: str | None = Field(None, description="客户来源")
    status: int | None = Field(None, description="客户状态")
    owner_id: str | None = Field(None, description="客户负责人ID")


# ============================================================================
# Task C3:通用审批列表端点 GET /v1/approvals 响应模型
# ============================================================================
# 对齐前端 `schemas/approvalGeneric.ts` 的 ApprovalListItemSchema / ApprovalListResponseSchema:
#   - items: 审批实例行(含按 business_type 内存 join 出的 application_number /
#     entity_name / entity_amount 三摘要字段,由 CRUD 层批量预取避免 N+1)
#   - overdue_hours: 后端 SQL/Python 计算(now - created_time,单位小时),
#     仅 PENDING 行有意义;SUBMITTED/PROCESSED tab 也回传,前端按需展示
#   - pending_count: 不论请求哪个 tab,后端都附当前用户「待我审批」总数,供侧边栏徽章
# ============================================================================


class ApprovalListItemResponse(BaseModel):
    """通用审批列表项\uff08GET /v1/approvals items 元素\uff09。"""

    id: int = Field(..., description="审批实例ID")
    business_type: str = Field(
        ...,
        description="业务单据类型\uff1aCONTRACT / PAYMENT / INVOICE / INVOICE_REISSUE / LICENSE / OPPORTUNITY",
    )
    business_id: int = Field(..., description="业务单据ID")
    business_public_id: str | None = Field(None, description="业务单据对外ID\uff1b商机审批返回商机对外ID")
    original_invoice_application_id: int | None = Field(None, description="原发票申请ID\uff1b仅发票重开审批返回")
    application_number: str = Field(
        ...,
        description="单号\uff08合同 contract_number / 发票 application_number / 回款合成 PAY-{id}\uff09",
    )
    entity_name: str | None = Field(
        None,
        description="客户/实体摘要\uff08合同 contract_name / 发票 invoice_title_text\uff1b回款暂为 None\uff09",
    )
    entity_amount: float | None = Field(
        None,
        description="单据金额\uff08合同 total_amount / 发票 invoice_amount / 回款 actual_amount\uff09",
    )
    actual_payer_name: str | None = Field(None, description="实际付款方名称\uff0c仅回款审批返回")
    license_status: str | None = Field(None, description="License 申请状态\uff0c仅 License 审批返回")
    customer_info: ApprovalCustomerInfoResponse | None = Field(None, description="关联客户/公司基础信息")
    has_attachment: bool | None = Field(False, description="是否存在可预览/下载附件")
    contract_file_path: str | None = Field(None, description="合同附件路径\uff0c仅 CONTRACT 审批返回")
    contract_file_name: str | None = Field(None, description="合同附件原始文件名\uff0c仅 CONTRACT 审批返回")
    contract_file_size: int | None = Field(None, description="合同附件大小\uff0c仅 CONTRACT 审批返回")
    contract_file_mime_type: str | None = Field(None, description="合同附件 MIME 类型\uff0c仅 CONTRACT 审批返回")
    invoice_file_path: str | None = Field(None, description="发票文件路径\uff0c仅 INVOICE 审批返回")
    invoice_number: str | None = Field(None, description="发票号码\uff0c仅 INVOICE 审批返回")
    issued_time: datetime | None = Field(None, description="发票开具时间\uff0c仅 INVOICE 审批返回")
    change_items: list[ContractChangeItem] | None = None
    reason: str | None = None
    attachment_name: str | None = None
    attachment_size: int | None = None
    attachment_mime_type: str | None = None
    submitter_id: str = Field(..., description="提交人系统用户ID")
    submitter_name: str | None = Field(None, description="提交人姓名")
    status: str = Field(..., description="审批状态\uff1aPENDING / APPROVED / REJECTED / CANCELLED")
    created_time: str = Field(..., description="提交时间 ISO8601")
    updated_time: str = Field(..., description="最后更新时间 ISO8601")
    overdue_hours: int | None = Field(
        None,
        description="超时小时数\uff08now - created_time\uff09\uff0c仅 PENDING 行有意义",
    )
    cc_node_name: str | None = Field(None, description="最近一次抄送当前用户的节点名称")
    cc_time: str | None = Field(None, description="最近一次抄送当前用户的时间 ISO8601")


class ApprovalInvoiceBillingSnapshotResponse(BaseModel):
    """Original invoice snapshot disclosed for a same-team reissue approval."""

    invoice_type: str | None = None
    invoice_title_type: str | None = None
    invoice_title_text: str | None = None
    invoice_taxpayer_id: str | None = None
    invoice_address: str | None = None
    invoice_phone: str | None = None
    invoice_bank_name: str | None = None
    invoice_bank_account: str | None = None
    invoice_amount: float | None = None


class ApprovalEntityDetailResponse(BaseModel):
    """Typed change fields while preserving existing business detail fields."""

    model_config = ConfigDict(extra="allow")

    contract_id: int | None = None
    contract_name: str | None = None
    change_items: list[ContractChangeItem] | None = None
    reason: str | None = None
    attachment_name: str | None = None
    attachment_size: int | None = None
    attachment_mime_type: str | None = None
    financial_snapshot: ContractFinancialSnapshotResponse | None = None
    invoice_type: str | None = None
    invoice_title_type: str | None = None
    invoice_title_text: str | None = None
    invoice_taxpayer_id: str | None = None
    invoice_address: str | None = None
    invoice_phone: str | None = None
    invoice_bank_name: str | None = None
    invoice_bank_account: str | None = None
    invoice_amount: float | None = None
    remark: str | None = None
    original_invoice_application_number: str | None = None
    original_invoice: ApprovalInvoiceBillingSnapshotResponse | None = None


class GenericApprovalDetailResponse(ApprovalListItemResponse):
    contract_id: int | None = None
    flow_id: int
    flow_name: str | None = None
    current_node_id: int | None = None
    current_node_name: str | None = None
    created_time: datetime
    updated_time: datetime
    flow_is_active: bool | None = None
    flow_disabled_warning: str | None = None
    entity_detail: ApprovalEntityDetailResponse
    records: list[ApprovalRecordResponse]


class ApprovalCcDeliveryResponse(BaseModel):
    id: int
    node_id: int
    node_name: str | None = None
    created_time: datetime


class ApprovalCcDetailResponse(GenericApprovalDetailResponse):
    cc_deliveries: list[ApprovalCcDeliveryResponse]


class ApprovalGenericListResponse(BaseModel):
    """通用审批列表响应\uff08GET /v1/approvals\uff09。"""

    items: list[ApprovalListItemResponse] = Field(..., description="审批列表项")
    total: int = Field(..., ge=0, description="当前 tab 过滤后的总数")
    pending_count: int = Field(
        ...,
        ge=0,
        description="当前用户的「待我审批」总数\uff0c任意 tab 响应都携带\uff0c供侧边栏徽章",
    )
