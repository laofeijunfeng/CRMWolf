from enum import Enum


class ApprovalPhase(str, Enum):
    """
    审批流程状态（数据库直接映射）

    所有业务单据的审批流程状态统一使用此枚举。

    状态说明：
    - DRAFT: 草稿/待提交审批，单据已创建但未提交审批
    - PENDING_REVIEW: 待审批，单据已提交审批，等待审批流转
    - APPROVED: 审批通过，审批流程已完成，单据可继续后续业务流程
    - REJECTED: 审批拒绝，审批流程已拒绝，用户可修改后重新提交

    与原有 status 字段的职责分离：
    - ApprovalPhase: 专注审批流程状态，由 ApprovalTransactionManager 和 Approval Engine 管理
    - 原有 status: 保留业务语义（Contract.status 表示合同生命周期，
                  Payment.confirmation_status 表示回款确认状态等）
    """

    DRAFT = "draft"           # 草稿/待提交审批
    PENDING_REVIEW = "pending_review"  # 待审批（整个审批流程中）
    APPROVED = "approved"     # 审批通过
    REJECTED = "rejected"     # 审批拒绝

    @classmethod
    def from_approval_status(cls, approval_status: str) -> "ApprovalPhase":
        """
        从 Approval.status 映射到 ApprovalPhase

        Args:
            approval_status: Approval.status 字段值（PENDING/APPROVED/REJECTED）

        Returns:
            ApprovalPhase: 对应的审批流程状态

        Examples:
            >>> ApprovalPhase.from_approval_status('PENDING')
            ApprovalPhase.PENDING_REVIEW
            >>> ApprovalPhase.from_approval_status('APPROVED')
            ApprovalPhase.APPROVED
        """
        from app.models.approval import ApprovalStatus

        mapping = {
            ApprovalStatus.PENDING: cls.PENDING_REVIEW,
            ApprovalStatus.APPROVED: cls.APPROVED,
            ApprovalStatus.REJECTED: cls.REJECTED,
        }
        return mapping.get(approval_status, cls.DRAFT)