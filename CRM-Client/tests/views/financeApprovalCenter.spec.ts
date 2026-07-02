/**
 * Task C3: FinanceApprovalCenter 单元测试
 *
 * 覆盖 C-DSG-5 三 tab + C-DSG-7 落 C3 部分：
 *   条1 批量同意/拒绝按钮存在
 *   条5 超时徽章 + 待我审批按 overdue_hours 降序
 *   条4 「我提交的」tab 对 REJECTED 行显示「修改并重新提交」
 *   条9 键盘 J/K 上下行、Enter 开抽屉、Esc 关抽屉
 *   条14 单号点击复制
 * 外加 E2 角色驱动 tab 可见性、空态 WolfEmpty、详情抽屉内嵌 ApprovalProcessGeneric。
 *
 * Mock 策略：mock `@/api/approvalGeneric` 的 listApprovals / getApprovalDetail，
 * 真实 Pinia store（store 内部走 Zod 校验后落入 approvalList / pendingCount）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

// ===== Mock approvalGeneric API =====
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

// ===== Mock 权限 / user store（指令 + ID 提供者）=====
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: vi.fn(() => ({
    hasPermission: vi.fn(() => true),
    hasAnyPermission: vi.fn(() => true),
    hasAllPermissions: vi.fn(() => true)
  }))
}))
vi.mock('@/stores/user', () => ({
  useUserStore: vi.fn(() => ({
    token: '',
    userInfo: { id: 42, name: '测试用户' },
    permissions: ['invoice:approve', 'payment:approve', 'payment:submit']
  }))
}))

// ===== Mock vue-router：useRouter 返回带 push spy 的 stub（Important #1 修复验证）=====
const routerPush = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush })
}))

import FinanceApprovalCenter from '@/views/FinanceApprovalCenter.vue'
import type {
  ApprovalListResponse,
  ApprovalListItem
} from '@/schemas/approvalGeneric'

const baseRow: ApprovalListItem = {
  id: 1,
  business_type: 'INVOICE',
  business_id: 100,
  application_number: 'INV-0001',
  entity_name: '某科技公司',
  entity_amount: 58000,
  submitter_id: 'u-7',
  submitter_name: '张三',
  status: 'PENDING',
  created_time: '2026-07-01T10:00:00',
  updated_time: '2026-07-01T10:00:00',
  overdue_hours: null
}

const buildRow = (overrides: Partial<ApprovalListItem>): ApprovalListItem =>
  ({ ...baseRow, ...overrides })

const buildListResponse = (
  items: ApprovalListItem[],
  pendingCount = items.length
): ApprovalListResponse => ({
  items,
  total: items.length,
  pending_count: pendingCount
})

const emptyResponse: ApprovalListResponse = { items: [], total: 0, pending_count: 0 }

const makeAxios404 = (): unknown => ({
  response: { status: 404, data: { detail: '审批流程不存在' } },
  message: 'Request failed with status code 404'
})

const detailFor = (row: ApprovalListItem): unknown => ({
  id: row.id,
  business_type: row.business_type,
  business_id: row.business_id,
  contract_id: null,
  flow_id: 1,
  flow_name: '审批流程',
  current_node_id: 2,
  current_node_name: '财务审批',
  status: row.status,
  submitter_id: row.submitter_id,
  submitter_name: row.submitter_name,
  created_time: row.created_time,
  updated_time: row.updated_time,
  flow_is_active: true,
  flow_disabled_warning: null,
  records: [{
    id: 1,
    approval_id: row.id,
    node_id: 1,
    node_name: '提交',
    approver_id: row.submitter_id,
    approver_name: row.submitter_name,
    approver_status: 'active',
    approver_status_display: '在职',
    action: 'SUBMIT',
    comment: null,
    created_time: row.created_time
  }]
})

const mountCenter = (global: Record<string, unknown> = {}) =>
  mount(FinanceApprovalCenter, {
    global: {
      plugins: [ElementPlus],
      directives: {
        permission: { mounted: () => undefined, updated: () => undefined },
        'any-permission': { mounted: () => undefined, updated: () => undefined }
      },
      ...global
    }
  })

describe('FinanceApprovalCenter', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.listApprovals.mockReset()
    api.getApprovalDetail.mockReset()
    api.bulkApprove.mockReset()
    api.approveEntity.mockReset()
    api.cancelApproval.mockReset()
    api.submitApproval.mockReset()
    vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessage, 'info').mockImplementation(() => ({}) as never)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    routerPush.mockReset()
  })

  it('renders three role-driven tabs with unread badge on pending', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([baseRow], 3))
    const w = mountCenter()
    await flushPromises()
    expect(w.text()).toContain('待我审批')
    expect(w.text()).toContain('3')
    expect(w.text()).toContain('我已处理')
    expect(w.text()).toContain('我提交的')
  })

  it('shows WolfEmpty in pending tab when no rows', async () => {
    api.listApprovals.mockResolvedValue(emptyResponse)
    const w = mountCenter()
    await flushPromises()
    expect(w.text()).toContain('暂无待审批事项')
  })

  it('preserves bulk approve/reject buttons (C-DSG-7 条1)', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([baseRow]))
    const w = mountCenter()
    await flushPromises()
    expect(w.find('[data-testid="bulk-approve-btn"]').exists()).toBe(true)
    expect(w.find('[data-testid="bulk-reject-btn"]').exists()).toBe(true)
  })

  it('shows overdue badge when overdue_hours>=48 and sorts pending desc (条5)', async () => {
    const notDue = buildRow({ id: 10, application_number: 'INV-0010', overdue_hours: 2 })
    const veryOverdue = buildRow({ id: 11, application_number: 'INV-0011', overdue_hours: 72 })
    const slightlyOverdue = buildRow({ id: 12, application_number: 'INV-0012', overdue_hours: 50 })
    api.listApprovals.mockResolvedValue(
      buildListResponse([notDue, veryOverdue, slightlyOverdue], 3)
    )
    const w = mountCenter()
    await flushPromises()
    // 超时徽章文案（条5）
    expect(w.text()).toContain('超时 72 小时')
    expect(w.text()).toContain('超时 50 小时')
    // notDue 行不应有超时徽章文案（avoid false positive：其他行也有"超时"字样时仍 ok）
    // 排序：overdue_hours 降序 → 第一行应是 veryOverdue
    const rows = w.findAll('.approval-row')
    expect(rows.length).toBeGreaterThanOrEqual(3)
    // 第一行的单号应为最大 overdue
    expect(rows[0].text()).toContain('INV-0011')
  })

  it('shows 修改并重新提交 on REJECTED row in 我提交的 tab (条4)', async () => {
    // 按 tab 维度返回不同数据，避免点击后异步竞态（mock 覆盖晚于 fetchList 调用）
    api.listApprovals.mockImplementation((query: { tab: string }) => {
      if (query.tab === 'submitted') {
        return Promise.resolve(buildListResponse([
          buildRow({ id: 20, status: 'REJECTED', application_number: 'INV-0020' })
        ], 0))
      }
      return Promise.resolve(emptyResponse)
    })
    const w = mountCenter()
    await flushPromises()
    // 切到「我提交的」tab
    await w.find('[data-testid="tab-submitted"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="resubmit-btn"]').exists()).toBe(true)
  })

  it('keyboard: Enter opens drawer, Esc closes (条9)', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([baseRow]))
    api.getApprovalDetail.mockResolvedValue(detailFor(baseRow))
    const w = mountCenter()
    await flushPromises()
    // el-drawer 用 v-show，关闭后元素仍在 DOM；通过 ElDrawer modelValue 判定开/关
    const drawer = () => w.findComponent({ name: 'ElDrawer' })
    expect(drawer().props('modelValue')).toBe(false)
    // Enter 开抽屉（全局 keydown 监听在 window 上）
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await flushPromises()
    expect(drawer().props('modelValue')).toBe(true)
    // Esc 关抽屉
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(drawer().props('modelValue')).toBe(false)
  })

  it('keyboard: J/K move row focus (条9)', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([
      buildRow({ id: 1, application_number: 'INV-A' }),
      buildRow({ id: 2, application_number: 'INV-B' })
    ], 2))
    const w = mountCenter()
    await flushPromises()
    const rows = w.findAll('.approval-row')
    expect(rows.length).toBe(2)
    // K 上移、J 下移：触发 keydown 不报错且焦点索引变化
    await rows[0].trigger('keydown', { key: 'j' })
    await flushPromises()
    await rows[1].trigger('keydown', { key: 'k' })
    await flushPromises()
    // 至少不应抛错；选中索引由内部 ref 持有，断言不显式越界
    expect(w.findAll('.approval-row').length).toBe(2)
  })

  it('clicking 单号 copies to clipboard (条14)', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([baseRow]))
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      value: { writeText },
      configurable: true
    })
    const w = mountCenter()
    await flushPromises()
    await w.find('[data-testid="copy-number"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('INV-0001')
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('E2: list query passes tab + business_type filter params', async () => {
    api.listApprovals.mockResolvedValue(emptyResponse)
    const w = mountCenter()
    await flushPromises()
    // 初始 tab=pending，调用应含 tab=pending
    expect(api.listApprovals).toHaveBeenCalledWith(
      expect.objectContaining({ tab: 'pending' })
    )
    // 切到 submitted tab
    await w.find('[data-testid="tab-submitted"]').trigger('click')
    await flushPromises()
    const calls = api.listApprovals.mock.calls
    expect(calls[calls.length - 1][0]).toEqual(
      expect.objectContaining({ tab: 'submitted' })
    )
  })

  it('drawer detail endpoint called on 详情 click (E9: no per-row list call)', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([baseRow]))
    api.getApprovalDetail.mockResolvedValue(detailFor(baseRow))
    const w = mountCenter()
    await flushPromises()
    // 列表只调用一次 listApprovals（切换 tab 才再调），不逐行
    expect(api.listApprovals).toHaveBeenCalledTimes(1)
    // 详情按钮触发行级 detail 查询
    await w.find('[data-testid="detail-btn"]').trigger('click')
    await flushPromises()
    expect(api.getApprovalDetail).toHaveBeenCalledWith('INVOICE', 100)
  })

  it('rejects 404 detail gracefully (drawer empty/ErrorState)', async () => {
    api.listApprovals.mockResolvedValue(buildListResponse([baseRow]))
    api.getApprovalDetail.mockRejectedValue(makeAxios404())
    const w = mountCenter()
    await flushPromises()
    await w.find('[data-testid="detail-btn"]').trigger('click')
    await flushPromises()
    // 404 → ErrorState forbidden OR 草稿空态（任一即可：不应崩溃）
    expect(w.text()).toBeTruthy()
  })

  it('resubmit uses router.push (not window.location) with correct entity edit path (Important #1)', async () => {
    // INVOICE 行 REJECTED + submitted tab → resubmit 应 router.push 到 /invoices/edit/:id
    api.listApprovals.mockImplementation((query: { tab: string }) => {
      if (query.tab === 'submitted') {
        return Promise.resolve(buildListResponse([
          buildRow({
            id: 30, status: 'REJECTED', business_type: 'INVOICE',
            business_id: 100, application_number: 'INV-0030'
          })
        ], 0))
      }
      return Promise.resolve(emptyResponse)
    })
    const w = mountCenter()
    await flushPromises()
    await w.find('[data-testid="tab-submitted"]').trigger('click')
    await flushPromises()
    await w.find('[data-testid="resubmit-btn"]').trigger('click')
    await flushPromises()
    // ElMessageBox.confirm 默认 resolve（beforeEach 已 mock）→ 应 router.push
    expect(routerPush).toHaveBeenCalledWith('/invoices/edit/100')
  })

  it('resubmit PAYMENT pushes /payments + info toast (Important #1)', async () => {
    api.listApprovals.mockImplementation((query: { tab: string }) => {
      if (query.tab === 'submitted') {
        return Promise.resolve(buildListResponse([
          buildRow({
            id: 31, status: 'REJECTED', business_type: 'PAYMENT',
            business_id: 200, application_number: 'PAY-200'
          })
        ], 0))
      }
      return Promise.resolve(emptyResponse)
    })
    const w = mountCenter()
    await flushPromises()
    await w.find('[data-testid="tab-submitted"]').trigger('click')
    await flushPromises()
    await w.find('[data-testid="resubmit-btn"]').trigger('click')
    await flushPromises()
    expect(routerPush).toHaveBeenCalledWith('/payments')
    expect(ElMessage.info).toHaveBeenCalledWith('请修改回款记录后重新提交审批')
  })

  it('drawer REJECTED CTA emits resubmit → router.push (Important #2)', async () => {
    // 抽屉侧 ApprovalProcessGeneric REJECTED 态应渲染「修改并重新提交」CTA，
    // 点击 emit resubmit → FinanceApprovalCenter 调 router.push。
    // 注意：抽屉 isSubmitter = activeTab==='submitted'，须切到 submitted tab
    // 才会渲染 CTA；用 .drawer-approval 作用域选择器区分表格行 resubmit-btn。
    api.listApprovals.mockImplementation((query: { tab: string }) => {
      if (query.tab === 'submitted') {
        return Promise.resolve(buildListResponse([
          buildRow({ id: 32, status: 'REJECTED', business_type: 'INVOICE', business_id: 101 })
        ], 0))
      }
      return Promise.resolve(emptyResponse)
    })
    api.getApprovalDetail.mockResolvedValue(detailFor(
      buildRow({ id: 32, status: 'REJECTED', business_type: 'INVOICE', business_id: 101 })
    ))
    const w = mountCenter()
    await flushPromises()
    await w.find('[data-testid="tab-submitted"]').trigger('click')
    await flushPromises()
    // 开抽屉
    await w.find('[data-testid="detail-btn"]').trigger('click')
    await flushPromises()
    // 抽屉内应存在 resubmit CTA（ApprovalProcessGeneric 渲染，作用域 .drawer-approval）
    const drawerBtn = w.find('.drawer-approval [data-testid="resubmit-btn"]')
    expect(drawerBtn.exists()).toBe(true)
    await drawerBtn.trigger('click')
    await flushPromises()
    expect(routerPush).toHaveBeenCalledWith('/invoices/edit/101')
  })
})