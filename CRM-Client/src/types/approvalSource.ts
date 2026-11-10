/**
 * 从审批详情下钻打开主体详情时携带的来源审批上下文。
 * 主体详情 Sheet 收到该上下文即进入只读查看模式。
 */
export interface ApprovalSourceContext {
  /** 审批类型名称，如「回款审批」 */
  approvalLabel: string
  /** 来源审批单编号，如 PAY-20261108-019 */
  applicationNumber: string
}
