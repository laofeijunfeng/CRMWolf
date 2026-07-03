"""通用审批 API 端点请求/响应 Schema（Task A6）。

与 `app/schemas/approval.py` 解耦：旧 schema 仍服务 `/contracts/{contract_id}/...`
合同专用端点（含 ApprovalDetailResponse 等完整响应模型），本模块仅定义通用端点
`/v1/approvals/{entity_type}/{entity_id}/...` 与 `/v1/approvals/bulk-approve` 所需
的轻量请求体。`ApprovalActionRequest`（action/comment/updated_time）复用既有
`schemas.approval.ApprovalActionRequest`，避免重复定义与 enum 行为分叉。

设计要点：
- submit 仅需 comment（可选）
- approve 复用 schemas.approval.ApprovalActionRequest（ApprovalActionEnum + 乐观锁 updated_time）
- bulk-approve 自定 BulkApproveRequest：{entity_type, ids, action, comment, updated_times?}
  其中 updated_times 为 {str(id): iso8601} 字典，按 id 注入每条 approve 的乐观锁值
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.approval import ApprovalActionRequest, ApprovalActionEnum


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


class BulkApproveRequest(BaseModel):
    """批量审批请求（E6：逐条独立事务，部分成功汇总）。"""
    entity_type: str = Field(
        ...,
        description="业务单据类型：CONTRACT / PAYMENT / INVOICE",
    )
    ids: List[int] = Field(
        ...,
        min_length=1,
        description="业务单据 ID 列表，至少 1 条",
    )
    action: ApprovalActionEnum = Field(
        ...,
        description="审批动作：APPROVE / REJECT",
    )
    comment: Optional[str] = Field(
        None,
        description="审批意见，对全部条目统一应用",
    )
    updated_times: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "乐观锁时间戳字典：{str(business_id): iso8601 updated_time}。"
            "键为 business_id 的字符串形式，对齐 JSON 对象键语义。"
            "未提供该 id 的条目则不带乐观锁检测。"
        ),
    )


class BulkApproveFailedItem(BaseModel):
    """批量审批中失败的单条记录。"""
    id: int = Field(..., description="业务单据 ID")
    reason: str = Field(..., description="失败原因（如：已被他人处理 / 审批不存在 / 角色不匹配）")


class BulkApproveResponse(BaseModel):
    """批量审批汇总响应。"""
    success_count: int = Field(..., description="成功审批的条数")
    failed: List[BulkApproveFailedItem] = Field(
        ...,
        description="失败条目列表，含失败原因",
    )


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
    business_type: str = Field(..., description="业务单据类型：CONTRACT / PAYMENT / INVOICE")
    business_id: int = Field(..., description="业务单据ID")
    application_number: str = Field(..., description="单号（合同 contract_number / 发票 application_number / 回款合成 PAY-{id}）")
    entity_name: Optional[str] = Field(None, description="客户/实体摘要（合同 contract_name / 发票 invoice_title_text；回款暂为 None）")
    entity_amount: Optional[float] = Field(None, description="单据金额（合同 total_amount / 发票 invoice_amount / 回款 actual_amount）")
    submitter_id: str = Field(..., description="提交人飞书用户ID")
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
