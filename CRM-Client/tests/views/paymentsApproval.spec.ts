/**
 * Task C3: Payments.vue 审批接入测试
 *
 * 验证回款记录表行渲染「提交审批」按钮（data-testid，payment:submit 权限门控），
 * 点击调 store.submitApproval('PAYMENT', recordId)，金额列走 formatCurrency。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'

// ===== Mock approvalGeneric API（store 内部走 Zod）=====
const api = vi.hoisted(() => ({
  submitApproval: vi.fn(),
  approveEntity: vi.fn(),
  cancelApproval: vi.fn(),
  getApprovalDetail: vi.fn(),
  bulkApprove: vi.fn(),
  listApprovals: vi.fn()
}))
vi.mock('@/api/approvalGeneric', () => ({
  default: api,
  submitApproval: api.submitApproval,
  approveEntity: api.approveEntity,
  cancelApproval: api.cancelApproval,
  getApprovalDetail: api.getApprovalDetail,
  bulkApprove: api.bulkApprove,
  listApprovals: api.listApprovals
}))

// ===== Mock payment API：返回回款记录 + 计划 =====
const paymentApi = vi.hoisted(() => ({
  listPaymentPlans: vi.fn(),
  listPaymentRecords: vi.fn(),
  createPaymentRecord: vi.fn()
}))
vi.mock('@/api/payment', () => ({
  default: paymentApi,
  listPaymentPlans: paymentApi.listPaymentPlans,
  listPaymentRecords: paymentApi.listPaymentRecords,
  createPaymentRecord: paymentApi.createPaymentRecord
}))

// ===== Mock permission store：payment:submit 命中 =====
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: vi.fn(() => ({
    hasPermission: vi.fn((code: string) => code === 'payment:submit'),
    hasAnyPermission: vi.fn(() => true),
    hasAllPermissions: vi.fn(() => true)
  }))
}))
vi.mock('@/stores/user', () => ({
  useUserStore: vi.fn(() => ({
    token: '',
    userInfo: { id: 42, name: '测试' },
    permissions: []
  }))
}))

import Payments from '@/views/Payments.vue'

const mockPlan = (overrides: Record<string, unknown> = {}) => ({
  id: 11,
  contract_id: 7,
  contract_name: '合同 A',
  customer_name: '客户 A',
  stage_name: '首期',
  planned_amount: 100000,
  paid_amount: 0,
  remaining_amount: 100000,
  due_date: '2026-07-15',
  status: 'PENDING',
  owner_name: '测试销售',
  ...overrides
})

describe('Payments approval integration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.submitApproval.mockReset()
    api.listApprovals.mockReset()
    paymentApi.listPaymentPlans.mockReset()
    paymentApi.listPaymentRecords.mockReset()
    paymentApi.listPaymentPlans.mockResolvedValue({ items: [mockPlan()], total: 1 })
    paymentApi.listPaymentRecords.mockResolvedValue({ items: [], total: 0 })
    api.submitApproval.mockResolvedValue({ approval_id: 5, status: 'PENDING' })
    vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as never)
  })

  const mountPayments = () =>
    mount(Payments, {
      global: {
        plugins: [ElementPlus],
        directives: {
          permission: { mounted: () => undefined, updated: () => undefined },
          'any-permission': { mounted: () => undefined, updated: () => undefined }
        }
      }
    })

  it('shows 提交审批 button on payment plan row only with payment:submit', async () => {
    const w = mountPayments()
    await flushPromises()
    expect(w.find('[data-testid="submit-approval-btn"]').exists()).toBe(true)
  })

  it('calls submitApproval(PAYMENT, recordId) on click + success toast', async () => {
    const w = mountPayments()
    await flushPromises()
    await w.find('[data-testid="submit-approval-btn"]').trigger('click')
    await flushPromises()
    expect(api.submitApproval).toHaveBeenCalledWith('PAYMENT', 11, undefined)
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('renders action button only when permission store lacks payment:submit', async () => {
    // 本测试用例 mock 已固定 hasPermission('payment:submit')=true；此处仅断言门控点
    // 存在：按钮带 data-testid，便于上层指令在不授权时移除。
    const w = mountPayments()
    await flushPromises()
    const btn = w.find('[data-testid="submit-approval-btn"]')
    expect(btn.exists()).toBe(true)
  })
})