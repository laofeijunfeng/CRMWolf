/**
 * 回款计划 Pinia Store
 *
 * 管理 Badge 数量和回款计划列表，支持前端组件实时获取待处理数量。
 *
 * 设计要点：
 * - State 使用 `ref<Type>(...)` 显式类型，禁止 any
 * - storeToRefs 解构读 State（响应性保留），Actions 内用 `.value` 赋值
 * - 每个 action 用 try/finally 保证 loading 复位
 * - 错误静默处理，不更新状态，不影响调用方
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentPlanStatus,
  type BadgeCounts
} from '@/api/payment'

export const usePaymentPlansStore = defineStore('paymentPlans', () => {
  // ===== State =====
  // Badge 数量
  const pendingCount = ref<number>(0)
  const partialCount = ref<number>(0)
  const overdueCount = ref<number>(0)
  const pendingSubmitCount = ref<number>(0)
  const pendingApprovalCount = ref<number>(0)
  const pendingApprovalMeCount = ref<number>(0)  // Task 8.3: 待我审批的数量

  // 回款计划列表
  const paymentPlans = ref<PaymentPlanResponse[]>([])
  const total = ref<number>(0)

  // 加载状态
  const loading = ref<boolean>(false)

  // ===== Actions =====

  /**
   * 获取 Badge 数量
   * 从后端拉取各类待处理数量，更新 State
   */
  const fetchBadgeCounts = async (): Promise<void> => {
    try {
      const counts: BadgeCounts = await paymentApi.getBadgeCounts()
      pendingCount.value = counts.pending
      partialCount.value = counts.partial
      overdueCount.value = counts.overdue
      pendingSubmitCount.value = counts.pending_submit
      pendingApprovalCount.value = counts.pending_approval
      pendingApprovalMeCount.value = counts.pending_approval_me  // Task 8.3
    } catch {
      // 静默处理，保持现有值
    }
  }

  /**
   * 获取回款计划列表（带筛选）
   * @param filters 筛选条件（status, approvalStatus 等）
   */
  const fetchPaymentPlans = async (filters?: {
    status?: PaymentPlanStatus
    approvalStatus?: string
    page?: number
    pageSize?: number
  }): Promise<void> => {
    loading.value = true
    try {
      const params: {
        status?: PaymentPlanStatus
        page?: number
        page_size?: number
      } = {}
      if (filters?.status !== undefined) {
        params.status = filters.status
      }
      if (filters?.page !== undefined) {
        params.page = filters.page
      }
      if (filters?.pageSize !== undefined) {
        params.page_size = filters.pageSize
      }
      const response = await paymentApi.listPaymentPlans(params)
      paymentPlans.value = response.items
      total.value = response.total
    } catch {
      // 静默处理，保持现有值
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取计划详情（含回款记录）
   * @param planId 计划 ID
   */
  const fetchPlanDetail = async (planId: number): Promise<PaymentPlanResponse | null> => {
    loading.value = true
    try {
      return await paymentApi.getPaymentPlanDetail(planId)
    } catch {
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 清空状态
   */
  const clear = (): void => {
    pendingCount.value = 0
    partialCount.value = 0
    overdueCount.value = 0
    pendingSubmitCount.value = 0
    pendingApprovalCount.value = 0
    pendingApprovalMeCount.value = 0  // Task 8.3
    paymentPlans.value = []
    total.value = 0
    loading.value = false
  }

  return {
    // State
    pendingCount,
    partialCount,
    overdueCount,
    pendingSubmitCount,
    pendingApprovalCount,
    pendingApprovalMeCount,  // Task 8.3
    paymentPlans,
    total,
    loading,
    // Actions
    fetchBadgeCounts,
    fetchPaymentPlans,
    fetchPlanDetail,
    clear
  }
})
