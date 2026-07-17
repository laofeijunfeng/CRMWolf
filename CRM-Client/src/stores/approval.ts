/**
 * 通用审批 Pinia Store
 *
 * 持有当前审批详情 `currentApprovalDetail`，封装通用审批 API 调用并在
 * 响应上执行 Zod 校验。供 C2/C3 审批组件与 FinanceApprovalCenter 调用。
 *
 * 设计要点：
 * - State 使用 `ref<Type>(...)` 显式类型，禁止 any；初始详情为 null
 * - storeToRefs 解构读 State（响应性保留），Actions 内用 `.value` 赋值
 * - 每个 action 用 try/finally 保证 loading 复位；Zod 校验失败时错误自然向上抛
 *   （不吞错、不污染 detail），调用方自行 try/catch 处理
 * - cancel 成功后清空 currentApprovalDetail（单据已回 DRAFT，详情失效）
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import approvalGenericApi, {
  type UpdatedTimesMap
} from '@/api/approvalGeneric'
import {
  ApprovalDetailSchema,
  ApprovalSubmitResponseSchema,
  MessageResponseSchema,
  BulkApproveResponseSchema,
  ApprovalListResponseSchema,
  type EntityType,
  type ApprovalAction,
  type ApprovalDetail,
  type ApprovalSubmitResponse,
  type MessageResponse,
  type BulkApproveResponse,
  type ApprovalListResponse,
  type ApprovalListQuery,
  type ApprovalListItem
} from '@/schemas/approvalGeneric'

export const useApprovalStore = defineStore('approvalGeneric', () => {
  // ===== State =====
  const currentApprovalDetail = ref<ApprovalDetail | null>(null)
  const loading = ref<boolean>(false)
  // FinanceApprovalCenter 列表（Task C3）
  const approvalList = ref<ApprovalListItem[]>([])
  const approvalListTotal = ref<number>(0)
  // 待我审批待办数（侧边栏徽章 + 待我审批 tab 徽章）
  const pendingCount = ref<number>(0)

  // ===== Actions =====

  /**
   * 拉取并校验审批详情，落入 currentApprovalDetail。
   * Zod 校验失败抛错，detail 不被污染。
   */
  const fetchDetail = async (entityType: EntityType, entityId: number): Promise<ApprovalDetail> => {
    loading.value = true
    try {
      const raw = await approvalGenericApi.getApprovalDetail(entityType, entityId)
      const parsed = ApprovalDetailSchema.parse(raw)
      currentApprovalDetail.value = parsed
      return parsed
    } finally {
      loading.value = false
    }
  }

  /**
   * 提交审批。返回 { approval_id, status }。
   */
  const submitEntity = async (
    entityType: EntityType,
    entityId: number,
    comment?: string
  ): Promise<ApprovalSubmitResponse> => {
    loading.value = true
    try {
      const raw = await approvalGenericApi.submitApproval(entityType, entityId, comment)
      return ApprovalSubmitResponseSchema.parse(raw)
    } finally {
      loading.value = false
    }
  }

  /**
   * 审批通过/拒绝。后端返回最新审批详情；Zod 校验后落入 currentApprovalDetail。
   * @param updatedTime iso8601 乐观锁时间戳（可选）
   */
  const approveEntity = async (
    entityType: EntityType,
    entityId: number,
    action: ApprovalAction,
    comment: string,
    updatedTime?: string
  ): Promise<ApprovalDetail> => {
    loading.value = true
    try {
      const raw = await approvalGenericApi.approveEntity(
        entityType, entityId, action, comment, updatedTime
      )
      const parsed = ApprovalDetailSchema.parse(raw)
      currentApprovalDetail.value = parsed
      return parsed
    } finally {
      loading.value = false
    }
  }

  /**
   * 撤回审批。成功后清空 currentApprovalDetail（单据已回 DRAFT，旧详情失效）。
   */
  const cancelEntity = async (
    entityType: EntityType,
    entityId: number
  ): Promise<MessageResponse> => {
    loading.value = true
    try {
      const raw = await approvalGenericApi.cancelApproval(entityType, entityId)
      const parsed = MessageResponseSchema.parse(raw)
      currentApprovalDetail.value = null
      return parsed
    } finally {
      loading.value = false
    }
  }

  /**
   * 批量审批（E6：逐条独立事务，部分成功汇总）。
   * @param updatedTimes 可选乐观锁字典 { str(id): iso8601 }
   */
  const bulkApprove = async (
    entityType: EntityType,
    ids: number[],
    action: ApprovalAction,
    comment: string,
    updatedTimes?: UpdatedTimesMap
  ): Promise<BulkApproveResponse> => {
    loading.value = true
    try {
      const raw = await approvalGenericApi.bulkApprove(
        entityType, ids, action, comment, updatedTimes
      )
      return BulkApproveResponseSchema.parse(raw)
    } finally {
      loading.value = false
    }
  }

  /** 清空当前审批详情（离开审批页时调用） */
  const clearDetail = (): void => {
    currentApprovalDetail.value = null
  }

  /**
   * 拉取 FinanceApprovalCenter 列表（Task C3 / E2 越权过滤）。
   * 后端按 tab+business_type 严格按角色过滤；Zod 校验后落入 approvalList。
   * 同步更新 pendingCount（来自响应的 pending_count，供侧边栏徽章用）。
   * tab==='pending' 查询时 pending_count 直接用 total；其他 tab 也回写最新
   * 待办数（后端在任意 tab 响应中带 pending_count）。
   */
  const fetchList = async (query: ApprovalListQuery): Promise<ApprovalListResponse> => {
    loading.value = true
    try {
      const raw = await approvalGenericApi.listApprovals(query)
      const parsed = ApprovalListResponseSchema.parse(raw)
      approvalList.value = parsed.items
      approvalListTotal.value = parsed.total
      pendingCount.value = parsed.pending_count
      return parsed
    } finally {
      loading.value = false
    }
  }

  /** 清空列表（离开审批中心时调用） */
  const clearList = (): void => {
    approvalList.value = []
    approvalListTotal.value = 0
  }

  return {
    currentApprovalDetail,
    loading,
    approvalList,
    approvalListTotal,
    pendingCount,
    fetchDetail,
    submitEntity,
    approveEntity,
    cancelEntity,
    bulkApprove,
    clearDetail,
    fetchList,
    clearList
  }
})