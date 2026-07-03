/**
 * Task C4: ApprovalNotificationCenter 单元测试
 *
 * 覆盖：
 * - 铃铛渲染 pendingCount（来自 store.fetchList tab=pending 响应）
 * - 超时项高亮（overdue_hours >= 48 加 nc-overdue 类，引用 $wolf-warning token）
 * - E10 轮询优化：
 *   1) document.hidden 时暂停轮询（visibilitychange → 不发请求）
 *   2) 恢复前台立即拉一次
 *   3) 请求失败指数退避 60→120→240→300(封顶)，成功后重置回 60s
 * - 无审批权限（invoice:approve / payment:approve 均无）时铃铛不渲染
 *   （v-any-permission 指令在 mounted 阶段移除根元素）
 * - 点击下拉项直跳 /finance/approvals
 *
 * Mock 策略：mock `@/api/approvalGeneric` listApprovals 控制响应；用真实 Pinia
 * store（fetchList 内部走 Zod 校验 → 同步更新 pendingCount/approvalList）；
 * mock 权限 store 控制 hasAnyPermission；注册内联 any-permission 指令复用
 * 真实移除逻辑。vue-router useRouter mock push断言跳转目标。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

// ===== Mock approvalGeneric API：仅 listApprovals 被 store.fetchList 调用 =====
const api = vi.hoisted(() => ({
  listApprovals: vi.fn()
}))
vi.mock('@/api/approvalGeneric', () => ({
  default: api,
  listApprovals: api.listApprovals
}))

// ===== Mock 权限 store：hasAnyPermission 可按测试重置（default true）=====
const permissionMock = vi.hoisted(() => ({
  hasPermission: vi.fn(() => true),
  hasAnyPermission: vi.fn(() => true),
  hasAllPermissions: vi.fn(() => true)
}))
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => permissionMock
}))

// ===== Mock user store（request 拦截器引用，虽本测试不触发 axios）=====
vi.mock('@/stores/user', () => ({
  useUserStore: vi.fn(() => ({
    token: '',
    userInfo: { id: 42, name: '测试' },
    permissions: [] as string[]
  }))
}))

// ===== Mock vue-router useRouter：捕获 push 目标 =====
const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => routerMock
}))

import { usePermissionStore } from '@/stores/permissions'
import ApprovalNotificationCenter from '@/components/ApprovalNotificationCenter.vue'
import type { ApprovalListItem, ApprovalListResponse } from '@/schemas/approvalGeneric'

// ===== 构造列表项工厂 =====
const buildItem = (overrides: Partial<ApprovalListItem> = {}): ApprovalListItem => ({
  id: 1,
  business_type: 'INVOICE',
  business_id: 100,
  application_number: 'INV-2026-001',
  entity_name: '发票 001',
  entity_amount: 12000,
  submitter_id: 'u1',
  submitter_name: '张三',
  status: 'PENDING',
  created_time: '2026-07-01T10:00:00',
  updated_time: '2026-07-01T10:00:00',
  overdue_hours: null,
  ...overrides
})

const buildResponse = (
  items: ApprovalListItem[],
  pendingCount: number
): ApprovalListResponse => ({
  items,
  total: items.length,
  pending_count: pendingCount
})

// ===== 内联 any-permission 指令：复用真实移除逻辑（依赖 mocked 权限 store）=====
const anyPermissionDirective = {
  mounted(el: HTMLElement, binding: { value: string[] }) {
    if (!binding.value || !Array.isArray(binding.value)) return
    if (!usePermissionStore().hasAnyPermission(binding.value)) {
      el.parentNode?.removeChild(el)
    }
  },
  updated(el: HTMLElement, binding: { value: string[] }) {
    if (!binding.value || !Array.isArray(binding.value)) return
    if (!usePermissionStore().hasAnyPermission(binding.value)) {
      el.parentNode?.removeChild(el)
    }
  }
}

const mountBell = (props: Record<string, unknown> = {}) =>
  mount(ApprovalNotificationCenter, {
    props: { pollIntervalMs: 60_000, maxBackoffMs: 300_000, listLimit: 8, ...props },
    global: {
      plugins: [ElementPlus],
      directives: { 'any-permission': anyPermissionDirective }
    }
  })

const setHidden = (hidden: boolean): void => {
  Object.defineProperty(document, 'hidden', {
    value: hidden,
    configurable: true
  })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('ApprovalNotificationCenter', () => {
  let wrapper: VueWrapper | null = null

  beforeEach(() => {
    setActivePinia(createPinia())
    api.listApprovals.mockReset()
    routerMock.push.mockReset()
    permissionMock.hasAnyPermission.mockImplementation(() => true)
    permissionMock.hasPermission.mockImplementation(() => true)
    permissionMock.hasAllPermissions.mockImplementation(() => true)
    setHidden(false)
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.useRealTimers()
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
  })

  it('renders bell badge with pendingCount from store.fetchList(pending)', async () => {
    api.listApprovals.mockResolvedValue(
      buildResponse([buildItem({ id: 1 }), buildItem({ id: 2 })], 2)
    )
    wrapper = mountBell()
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledWith(
      expect.objectContaining({ tab: 'pending', page: 1, page_size: 8 })
    )
    expect(wrapper.find('[data-testid="approval-bell-badge"]').text()).toContain('2')
  })

  it('highlights overdue item (overdue_hours >= 48) with nc-overdue class', async () => {
    api.listApprovals.mockResolvedValue(
      buildResponse(
        [
          buildItem({ id: 1, overdue_hours: 72, application_number: 'INV-OLD' }),
          buildItem({ id: 2, overdue_hours: 5, application_number: 'INV-NEW' })
        ],
        2
      )
    )
    wrapper = mountBell()
    await flushPromises()
    // el-dropdown 内容 teleport 到 document.body，需展开后查 DOM
    await wrapper.find('[data-testid="approval-bell-badge"]').trigger('click')
    await flushPromises()
    const overdue = document.body.querySelector('[data-testid="approval-bell-item-1"]')
    const fresh = document.body.querySelector('[data-testid="approval-bell-item-2"]')
    expect(overdue?.classList.contains('nc-overdue')).toBe(true)
    expect(fresh?.classList.contains('nc-overdue')).toBe(false)
  })

  it('E10: pauses polling when document.hidden and resumes with immediate fetch', async () => {
    vi.useFakeTimers()
    api.listApprovals.mockResolvedValue(buildResponse([], 0))
    wrapper = mountBell()
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(1)

    // 切到后台 → 暂停轮询
    setHidden(true)
    await vi.advanceTimersByTimeAsync(120_000)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(1)

    // 切回前台 → 立即拉一次
    setHidden(false)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(2)
  })

  it('E10: exponential backoff on failure (60→120→240→300 cap) and reset on success', async () => {
    vi.useFakeTimers()
    // 失败 → 失败 → 失败 → 成功 → 再成功
    api.listApprovals
      .mockRejectedValueOnce(new Error('boom'))
      .mockRejectedValueOnce(new Error('boom'))
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(buildResponse([], 0))
      .mockResolvedValueOnce(buildResponse([], 0))

    wrapper = mountBell()
    await flushPromises() // call 1 (reject) → 退避 120s
    expect(api.listApprovals).toHaveBeenCalledTimes(1)

    // 60s 后不应触发（next 在 120s）
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(1)

    // 再 60s（共 120s）→ call 2 (reject) → 退避 240s
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(2)

    // 240s 后 → call 3 (reject) → 退避封顶 300s（480 截到 300）
    await vi.advanceTimersByTimeAsync(240_000)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(3)

    // 300s 后 → call 4 (success) → 重置退避回 60s
    await vi.advanceTimersByTimeAsync(300_000)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(4)

    // 60s 后 → call 5 (success)
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(api.listApprovals).toHaveBeenCalledTimes(5)
  })

  it('hides bell when user lacks both invoice:approve and payment:approve', async () => {
    permissionMock.hasAnyPermission.mockImplementation(() => false)
    api.listApprovals.mockResolvedValue(buildResponse([], 0))
    wrapper = mountBell()
    await flushPromises()
    expect(wrapper.find('[data-testid="approval-bell"]').exists()).toBe(false)
  })

  it('navigates to FinanceApprovalCenter on item click', async () => {
    const item = buildItem({ id: 7, business_type: 'PAYMENT', business_id: 55 })
    api.listApprovals.mockResolvedValue(buildResponse([item], 1))
    wrapper = mountBell()
    await flushPromises()
    await wrapper.find('[data-testid="approval-bell-badge"]').trigger('click')
    await flushPromises()
    const itemEl = document.body.querySelector(
      '[data-testid="approval-bell-item-7"]'
    ) as HTMLElement
    expect(itemEl).not.toBeNull()
    itemEl.click()
    expect(routerMock.push).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/finance/approvals' })
    )
  })
})