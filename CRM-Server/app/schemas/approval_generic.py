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
