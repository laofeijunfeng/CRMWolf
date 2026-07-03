/**
 * 通用审批 API 封装
 *
 * 对接后端 `app/api/approvals.py` 通用端点（Task A6）：
 *   POST /v1/approvals/{entity_type}/{entity_id}/submit
 *   POST /v1/approvals/{entity_type}/{entity_id}/approve
 *   POST /v1/approvals/{entity_type}/{entity_id}/cancel
 *   GET  /v1/approvals/{entity_type}/{entity_id}/detail
 *   POST /v1/approvals/bulk-approve
 *
 * 设计要点：
 * - 复用 `@/utils/request` 实例（baseURL 由实例统一注入，禁止硬编码）
 * - 响应类型由 Zod schema 派生，具体校验在 store 层执行（参见
 *   `src/stores/approval.ts`），此处仅声明返回类型
 * - path 参数 `entityType/entity_id` 由调用方传入，后端 `is_valid_business_type`
 *   负责校验非法值（→ 400）
 *
 * eslint-disable crmwolf/require-zod-schema：本规则检测 `request.xxx(...)` 的
 * 直接父节点须为 `.parse()` 调用，但 `await request.xxx(...)` 的父节点是
 * AwaitExpression，规则与 async/await 在结构上不兼容（既有 src/api/approval.ts
 * 同样携带此 warn 债务）。Zod 边界校验统一在 store 层
 * （src/stores/approval.ts 的 *.parse）执行，本层仅声明返回类型。
 */

/* eslint-disable crmwolf/require-zod-schema */

import request from '@/utils/request'
import {
  type EntityType,
  type ApprovalAction,
  type ApprovalDetail,
  type ApprovalSubmitResponse,
  type MessageResponse,
  type BulkApproveResponse,
  type ApprovalListResponse,
  type ApprovalListQuery
} from '@/schemas/approvalGeneric'

// 乐观锁时间戳映射：{ str(business_id): iso8601 }，键为 id 字符串形式
export type UpdatedTimesMap = Record<string, string>

/**
 * 提交审批（通用）
 * @returns GenericApprovalSubmitResponse：{ approval_id, status }
 *   PAYMENT/INVOICE 未匹配流程时后端直通返回 approval_id=0, status=APPROVED
 */
function submitApproval(
  entityType: EntityType,
  entityId: number,
  comment?: string
): Promise<ApprovalSubmitResponse> {
  return request.post<ApprovalSubmitResponse>(
    `/v1/approvals/${entityType}/${entityId}/submit`,
    comment === undefined ? {} : { comment }
  )
}

/**
 * 审批通过/拒绝（通用）。后端返回最新审批详情（_serialize_generic_approval）。
 * @param updatedTime iso8601，乐观锁时间戳；不传则不带乐观锁检测
 */
function approveEntity(
  entityType: EntityType,
  entityId: number,
  action: ApprovalAction,
  comment: string,
  updatedTime?: string
): Promise<ApprovalDetail> {
  const body: {
    action: ApprovalAction
    comment: string
    updated_time?: string
  } = { action, comment }
  if (updatedTime !== undefined) {
    body.updated_time = updatedTime
  }
  return request.post<ApprovalDetail>(
    `/v1/approvals/${entityType}/${entityId}/approve`,
    body
  )
}

/**
 * 撤回审批（通用）。仅提交人本人可撤回，且仅限 PENDING 状态。
 */
function cancelApproval(
  entityType: EntityType,
  entityId: number
): Promise<MessageResponse> {
  return request.post<MessageResponse>(
    `/v1/approvals/${entityType}/${entityId}/cancel`,
    {}
  )
}

/**
 * 获取审批详情（通用）。后端按 entity_type+entity_id 取最新一条审批实例。
 */
function getApprovalDetail(
  entityType: EntityType,
  entityId: number
): Promise<ApprovalDetail> {
  return request.get<ApprovalDetail>(
    `/v1/approvals/${entityType}/${entityId}/detail`
  )
}

/**
 * 批量审批（E6：逐条独立事务，部分成功汇总）。
 * @param updatedTimes 可选乐观锁字典：{ str(id): iso8601 }，未提供 id 的条目不带锁
 */
function bulkApprove(
  entityType: EntityType,
  ids: number[],
  action: ApprovalAction,
  comment: string,
  updatedTimes?: UpdatedTimesMap
): Promise<BulkApproveResponse> {
  const body: {
    entity_type: EntityType
    ids: number[]
    action: ApprovalAction
    comment: string
    updated_times?: UpdatedTimesMap
  } = { entity_type: entityType, ids, action, comment }
  if (updatedTimes !== undefined) {
    body.updated_times = updatedTimes
  }
  return request.post<BulkApproveResponse>('/v1/approvals/bulk-approve', body)
}

/**
 * FinanceApprovalCenter 列表查询（Task C3 / E2 越权过滤）。
 *
 * 后端按 tab 严格按角色过滤，team_id 由依赖注入携带（前端不传、不缓存）：
 *   submitted → submitter_id == current_user
 *   pending   → current_node.approve_role IN (user_roles) AND status=PENDING
 *   processed → records.approver_id == current_user
 * business_type 为可选维度过滤（INVOICE / PAYMENT / CONTRACT）。
 *
 * 注：后端 `GET /v1/approvals` 通用列表端点为 Task C3 前端调用所预期；若尚未
 * 提供，前端照常传正确参数，后端过滤能力缺失由 Task C3 报告标注（不前端伪造过滤）。
 */
function listApprovals(query: ApprovalListQuery): Promise<ApprovalListResponse> {
  return request.get<ApprovalListResponse>('/v1/approvals', { params: query })
}

const approvalGenericApi = {
  submitApproval,
  approveEntity,
  cancelApproval,
  getApprovalDetail,
  bulkApprove,
  listApprovals
}

export default approvalGenericApi
export {
  submitApproval,
  approveEntity,
  cancelApproval,
  getApprovalDetail,
  bulkApprove,
  listApprovals
}