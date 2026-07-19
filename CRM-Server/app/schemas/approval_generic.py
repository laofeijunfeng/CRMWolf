"""通用审批 API 端点请求/响应 Schema（Task A6）。

与 `app/schemas/approval.py` 解耦：旧 schema 仍服务 `/contracts/{contract_id}/...`
合同专用端点（含 ApprovalDetailResponse 等完整响应模型），本模块仅定义通用端点
`/v1/approvals/{entity_type}/{entity_id}/...` 所需的轻量请求体。
`ApprovalActionRequest`（action/comment/updated_time）复用既有
`schemas.approval.ApprovalActionRequest`，避免重复定义与 enum 行为分叉。

设计要点：
- submit 仅需 comment（可选）
- approve 复用 schemas.approval.ApprovalActionRequest（ApprovalActionEnum + 乐观锁 updated_time）
"""
from typing import Optional, List

from pydantic import BaseModel, Field


class ApprovalSubmitRequest(BaseModel):
    """通用审批提交请求。"""
    comment: Optional[str] = Field(
        None,
        description="提交说明，提交时填写的说明信息（可选）",
    )


class GenericApprovalSubmitResponse(BaseModel):
    """通用审批提交响应。"""
    approval_id: int = Field(..., description="新建审批实例 ID")
    status: str = Field(..., description="审批状态：PENDING/APPROVED/REJECTED/CANCELLED")


class ApprovalCustomerInfoResponse(BaseModel):
    """审批关联客户/公司基础信息。"""

    id: int = Field(..., description="客户ID")
    account_name: str = Field(..., description="客户公司名称")
    industry: Optional[str] = Field(None, description="所属行业")
    city: Optional[str] = Field(None, description="所在城市")
    company_scale: Optional[str] = Field(None, description="公司规模")
    source: Optional[str] = Field(None, description="客户来源")
    status: Optional[int] = Field(None, description="客户状态")
    owner_id: Optional[str] = Field(None, description="客户负责人ID")


# ============================================================================
# Task C3：通用审批列表端点 GET /v1/approvals 响应模型
# ============================================================================
# 对齐前端 `schemas/approvalGeneric.ts` 的 ApprovalListItemSchema / ApprovalListResponseSchema：
#   - items: 审批实例行（含按 business_type 内存 join 出的 application_number /
#     entity_name / entity_amount 三摘要字段，由 CRUD 层批量预取避免 N+1）
#   - overdue_hours: 后端 SQL/Python 计算（now - created_time，单位小时），
#     仅 PENDING 行有意义；SUBMITTED/PROCESSED tab 也回传，前端按需展示
#   - pending_count: 不论请求哪个 tab，后端都附当前用户「待我审批」总数，供侧边栏徽章
# ============================================================================


class ApprovalListItemResponse(BaseModel):
    """通用审批列表项（GET /v1/approvals items 元素）。"""

    id: int = Field(..., description="审批实例ID")
    business_type: str = Field(..., description="业务单据类型：CONTRACT / PAYMENT / INVOICE / LICENSE / OPPORTUNITY")
    business_id: int = Field(..., description="业务单据ID")
    application_number: str = Field(..., description="单号（合同 contract_number / 发票 application_number / 回款合成 PAY-{id}）")
    entity_name: Optional[str] = Field(None, description="客户/实体摘要（合同 contract_name / 发票 invoice_title_text；回款暂为 None）")
    entity_amount: Optional[float] = Field(None, description="单据金额（合同 total_amount / 发票 invoice_amount / 回款 actual_amount）")
    actual_payer_name: Optional[str] = Field(None, description="实际付款方名称，仅回款审批返回")
    license_status: Optional[str] = Field(None, description="License 申请状态，仅 License 审批返回")
    customer_info: Optional[ApprovalCustomerInfoResponse] = Field(None, description="关联客户/公司基础信息")
    submitter_id: str = Field(..., description="提交人系统用户ID")
    submitter_name: Optional[str] = Field(None, description="提交人姓名")
    status: str = Field(..., description="审批状态：PENDING / APPROVED / REJECTED / CANCELLED")
    created_time: str = Field(..., description="提交时间 ISO8601")
    updated_time: str = Field(..., description="最后更新时间 ISO8601")
    overdue_hours: Optional[int] = Field(None, description="超时小时数（now - created_time），仅 PENDING 行有意义")


class ApprovalGenericListResponse(BaseModel):
    """通用审批列表响应（GET /v1/approvals）。"""

    items: List[ApprovalListItemResponse] = Field(..., description="审批列表项")
    total: int = Field(..., ge=0, description="当前 tab 过滤后的总数")
    pending_count: int = Field(..., ge=0, description="当前用户的「待我审批」总数，任意 tab 响应都携带，供侧边栏徽章")
