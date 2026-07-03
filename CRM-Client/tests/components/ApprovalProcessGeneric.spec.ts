/**
 * Task C2: ApprovalProcessGeneric 单元测试
 *
 * 覆盖 C-DSG-7 P0：
 * - 条2 驳回强制理由 / 同意可选（对称破缺）
 * - 条3 防双击（按钮 action pending 期间 :loading + :disabled）
 * - 条8 乐观锁冲突保留已输入驳回理由 + 重载 detail
 * 外加 C-DSG-4 五态：Loading / Empty（无审批单）/ Error / Success / Conflict。
 *
 * Mock 策略：mock `@/api/approvalGeneric` 整个模块（store action 内部走 Zod 校验
 * 后落入 currentApprovalDetail），用真实 Pinia store + storeToRefs 保证响应性
 * 与生产路径一致。ElMessage / ElMessageBox 用 vi.spyOn 监听文案。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

// ===== Mock approvalGeneric API：actions 为可监听 vi.fn；store 内部走 Zod =====
const api = vi.hoisted(() => ({
  submitApproval: vi.fn(),
  approveEntity: vi.fn(),
  cancelApproval: vi.fn(),
  getApprovalDetail: vi.fn(),
  bulkApprove: vi.fn()
}))

vi.mock('@/api/approvalGeneric', () => ({
  default: api,
  submitApproval: api.submitApproval,
  approveEntity: api.approveEntity,
  cancelApproval: api.cancelApproval,
  getApprovalDetail: api.getApprovalDetail,
  bulkApprove: api.bulkApprove
}))

// ===== Mock 权限 / user store（v-permission 指令依赖 usePermissionStore，
// 且 request.ts 拦截器引用 useUserStore，虽本测试不触发 axios 但仍需提供）=====
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: vi.fn(() => ({
    hasPermission: vi.fn(() => true),
    hasAnyPermission: vi.fn(() => true),
    hasAllPermissions: vi.fn(() => true)
  }))
}))
vi.mock('@/stores/user', () => ({
  useUserStore: vi.fn(() => ({ token: '', userInfo: null, permissions: [] as string[] }))
}))

import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import type { ApprovalDetail } from '@/schemas/approvalGeneric'

const baseDetail: ApprovalDetail = {
  id: 1,
  business_type: 'INVOICE',
  business_id: 1,
  contract_id: null,
  flow_id: 2,
  flow_name: '发票审批',
  current_node_id: 5,
  current_node_name: '财务审批',
  status: 'PENDING',
  submitter_id: 'u1',
  submitter_name: '张三',
  created_time: '2026-07-01T10:00:00',
  updated_time: '2026-07-01T10:00:00',
  flow_is_active: true,
  flow_disabled_warning: null,
  records: [
    {
      id: 1,
      approval_id: 1,
      node_id: 1,
      node_name: '提交',
      approver_id: 'u1',
      approver_name: '张三',
      approver_status: 'active',
      approver_status_display: '在职',
      action: 'SUBMIT',
      comment: null,
      created_time: '2026-07-01T10:00:00'
    }
  ]
}

const buildDetail = (overrides: Partial<ApprovalDetail>): ApprovalDetail =>
  ({ ...baseDetail, ...overrides })

const makeAxios404 = (): unknown => ({
  response: { status: 404, data: { detail: '审批流程不存在' } },
  message: 'Request failed with status code 404'
})

const makeAxios409 = (): unknown => ({
  response: { status: 409, data: { detail: '该审批已被处理，请刷新页面查看最新状态' } },
  message: 'Request failed with status code 409'
})

const makeAxios500 = (): unknown => ({
  response: { status: 500, data: { detail: '服务器错误' } },
  message: 'Request failed with status code 500'
})

const mountComp = (props: Record<string, unknown>) =>
  mount(ApprovalProcessGeneric, {
    props,
    global: {
      plugins: [ElementPlus],
      directives: {
        // no-op：始终保留元素（权限由 mock hasPermission=true 决定）
        permission: { mounted: () => undefined, updated: () => undefined }
      }
    }
  })

describe('ApprovalProcessGeneric', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.submitApproval.mockReset()
    api.approveEntity.mockReset()
    api.cancelApproval.mockReset()
    api.getApprovalDetail.mockReset()
    api.bulkApprove.mockReset()
    vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  })

  it('shows submit CTA empty state when no approval exists (404 → WolfEmpty)', async () => {
    api.getApprovalDetail.mockRejectedValue(makeAxios404())
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 1,
      canApprove: true,
      isSubmitter: true
    })
    await flushPromises()
    expect(w.text()).toContain('尚未提交审批')
    expect(w.find('[data-testid="submit-approval-btn"]').exists()).toBe(true)
  })

  it('shows approve/reject for approver when PENDING, not withdraw', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'PENDING' }))
    const w = mountComp({
      entityType: 'PAYMENT',
      entityId: 5,
      canApprove: true,
      isSubmitter: false
    })
    await flushPromises()
    expect(w.find('[data-testid="approve-btn"]').exists()).toBe(true)
    expect(w.find('[data-testid="reject-btn"]').exists()).toBe(true)
    expect(w.find('[data-testid="withdraw-btn"]').exists()).toBe(false)
  })

  it('shows withdraw for submitter when PENDING, not approve/reject', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'PENDING' }))
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 7,
      canApprove: false,
      isSubmitter: true
    })
    await flushPromises()
    expect(w.find('[data-testid="withdraw-btn"]').exists()).toBe(true)
    expect(w.find('[data-testid="approve-btn"]').exists()).toBe(false)
    expect(w.find('[data-testid="reject-btn"]').exists()).toBe(false)
  })

  it('reject requires reason (synchronous guard before action)', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'PENDING' }))
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 1,
      canApprove: true,
      isSubmitter: false
    })
    await flushPromises()

    // 打开驳回弹窗
    await w.find('[data-testid="reject-btn"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="reject-dialog"]').exists()).toBe(true)

    // 不填理由直接点确定 → 应触发 warning 且不调 approveEntity
    await w.find('[data-testid="reject-reason"]').setValue('')
    await w.find('[data-testid="reject-confirm-btn"]').trigger('click')
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledWith('请填写驳回理由，提交人将据此修改')
    expect(api.approveEntity).not.toHaveBeenCalled()
  })

  it('blocks double-submit: approve button disabled + loading while action pending', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'PENDING' }))
    // 用 deferred promise 控制挂起的 approve 请求
    let resolveApprove: (v: ApprovalDetail) => void = () => undefined
    api.approveEntity.mockReturnValue(
      new Promise<ApprovalDetail>((resolve) => {
        resolveApprove = resolve
      })
    )

    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 1,
      canApprove: true,
      isSubmitter: false
    })
    await flushPromises()

    const approveBtn = w.find('[data-testid="approve-btn"]')
    await approveBtn.trigger('click')
    await flushPromises()

    // action pending 期间按钮应 disabled + 带 loading 标识
    expect(approveBtn.attributes('disabled')).toBeDefined()
    expect(approveBtn.classes()).toContain('is-loading')

    // 完成 action 后恢复
    resolveApprove(buildDetail({ status: 'APPROVED' }))
    await flushPromises()
    expect(approveBtn.exists()).toBe(true)
  })

  it('optimistic-lock conflict preserves typed reject reason + reloads detail + warns', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'PENDING' }))
    api.approveEntity.mockRejectedValueOnce(makeAxios409())

    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 1,
      canApprove: true,
      isSubmitter: false
    })
    await flushPromises()

    // 打开驳回弹窗 + 输入理由
    await w.find('[data-testid="reject-btn"]').trigger('click')
    await flushPromises()
    await w.find('[data-testid="reject-reason"]').setValue('请补充材料')
    await w.find('[data-testid="reject-confirm-btn"]').trigger('click')
    await flushPromises()

    // C-DSG-7 条8：保留已输入理由（弹窗未关闭 + reason 未清空）
    expect(ElMessage.warning).toHaveBeenCalledWith('该审批已被他人处理，你的填写已保留')
    expect(api.approveEntity).toHaveBeenCalledWith(
      'INVOICE', 1, 'REJECT', '请补充材料', '2026-07-01T10:00:00'
    )
    // reload：getApprovalDetail 至少 2 次（初始 + 冲突重载）
    expect(api.getApprovalDetail).toHaveBeenCalledTimes(2)
    // 弹窗仍打开、理由仍在输入框
    expect(w.find('[data-testid="reject-dialog"]').exists()).toBe(true)
    const reasonInput = w.find('[data-testid="reject-reason"]')
    expect((reasonInput.element as HTMLTextAreaElement).value).toBe('请补充材料')
  })

  it('after conflict reload shows terminal-state notice when approval moved out of PENDING', async () => {
    api.getApprovalDetail
      .mockResolvedValueOnce(buildDetail({ status: 'PENDING' }))
      .mockResolvedValueOnce(buildDetail({ status: 'APPROVED' }))
    api.approveEntity.mockRejectedValueOnce(makeAxios409())

    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 1,
      canApprove: true,
      isSubmitter: false
    })
    await flushPromises()

    await w.find('[data-testid="reject-btn"]').trigger('click')
    await flushPromises()
    await w.find('[data-testid="reject-reason"]').setValue('请补充材料')
    await w.find('[data-testid="reject-confirm-btn"]').trigger('click')
    await flushPromises()

    // 重载后非 PENDING → 显示已由他人处理提示，禁用提交
    expect(w.text()).toContain('该审批已由他人处理，无需重复操作')
    expect(w.find('[data-testid="reject-confirm-btn"]').attributes('disabled')).toBeDefined()
  })

  it('shows ErrorState with reload CTA on non-404 load failure', async () => {
    api.getApprovalDetail.mockRejectedValue(makeAxios500())
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 1,
      canApprove: true,
      isSubmitter: false
    })
    await flushPromises()
    expect(w.text()).toContain('审批信息加载失败')
    expect(w.find('[data-testid="reload-detail-btn"]').exists()).toBe(true)
  })

  // ---------- C-DSG-7 条4：抽屉侧 REJECTED 态「修改并重新提交」CTA (Important #2) ----------

  it('shows 修改并重新提交 CTA for submitter when REJECTED + emits resubmit', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'REJECTED' }))
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 9,
      canApprove: false,
      isSubmitter: true
    })
    await flushPromises()
    const btn = w.find('[data-testid="resubmit-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('修改并重新提交')
    await btn.trigger('click')
    await flushPromises()
    expect(w.emitted('resubmit')).toBeTruthy()
    expect(w.emitted('resubmit')!.length).toBe(1)
  })

  it('hides resubmit CTA from non-submitter when REJECTED', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'REJECTED' }))
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 9,
      canApprove: false,
      isSubmitter: false
    })
    await flushPromises()
    expect(w.find('[data-testid="resubmit-btn"]').exists()).toBe(false)
  })

  it('hides resubmit CTA when status is not REJECTED', async () => {
    api.getApprovalDetail.mockResolvedValue(buildDetail({ status: 'APPROVED' }))
    const w = mountComp({
      entityType: 'INVOICE',
      entityId: 9,
      canApprove: false,
      isSubmitter: true
    })
    await flushPromises()
    expect(w.find('[data-testid="resubmit-btn"]').exists()).toBe(false)
  })
})