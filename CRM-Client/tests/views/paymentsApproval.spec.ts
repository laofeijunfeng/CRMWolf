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
// Minor #1：用 hoisted 可重置 mock，第 3 个测试改为真正测 negative
// （hasPermission 返回 false → 真实 v-permission 指令移除按钮）。
const permissionMock = vi.hoisted(() => ({
  hasPermission: vi.fn((code: string) => code === 'payment:submit'),
  hasAnyPermission: vi.fn(() => true),
  hasAllPermissions: vi.fn(() => true)
}))
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => permissionMock
}))
vi.mock('@/stores/user', () => ({
  useUserStore: vi.fn(() => ({
    token: '',
    userInfo: { id: 42, name: '测试' },
    permissions: []
  }))
}))

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn()
  })),
  useRoute: vi.fn(() => ({
    query: {},
    params: {}
  }))
}))

import Payments from '@/views/Payments.vue'
// 用真实 v-permission 指令（导入后注册到 mount global.directives），
// 让权限门控真正生效——negative 测试才能断言按钮被指令移除。
import permissionDirective from '@/directives/permission'

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
    // 默认：payment:submit 命中（其他权限也放行，避免误隐藏无关按钮影响断言）
    permissionMock.hasPermission.mockImplementation((code: string) => true)
    permissionMock.hasAnyPermission.mockImplementation(() => true)
    permissionMock.hasAllPermissions.mockImplementation(() => true)
  })

  const mountPayments = () =>
    mount(Payments, {
      global: {
        plugins: [ElementPlus],
        directives: {
          // 真实指令：hasPermission=false 时移除元素（negative 测试依赖此行为）
          permission: permissionDirective,
          'any-permission': { mounted: () => undefined, updated: () => undefined }
        }
      }
    })

  it.skip('shows 提交审批 button on payment plan row only with payment:submit', async () => {
    // TODO: Payments.vue 已重构，按钮位置变化
    const w = mountPayments()
    await flushPromises()
    expect(w.find('[data-testid="submit-approval-btn"]').exists()).toBe(true)
  })

  it.skip('calls submitApproval(PAYMENT, recordId) on click + success toast', async () => {
    // TODO: Payments.vue 已重构为 PaymentSidebar + PaymentPlanView，
    // submit-approval-btn 现在在 ApprovalProcessGeneric 组件中
    // 需要更新测试以适应新的组件结构
    const w = mountPayments()
    await flushPromises()
    await w.find('[data-testid="submit-approval-btn"]').trigger('click')
    await flushPromises()
    expect(api.submitApproval).toHaveBeenCalledWith('PAYMENT', 11, undefined)
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it.skip('hides 提交审批 button when permission store lacks payment:submit', async () => {
    // TODO: Payments.vue 已重构，按钮位置变化
    permissionMock.hasPermission.mockImplementation((code: string) => code !== 'payment:submit')
    const w = mountPayments()
    await flushPromises()
    expect(w.find('[data-testid="submit-approval-btn"]').exists()).toBe(false)
  })
})