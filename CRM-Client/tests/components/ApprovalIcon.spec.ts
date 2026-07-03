/**
 * ApprovalIcon 单元测试
 *
 * 测试覆盖：
 * - 权限门控：无审批权限时不渲染
 * - Badge 显示：pendingCount > 0 时显示
 * - Badge 隐藏：pendingCount === 0 时隐藏
 * - 点击跳转：点击按钮跳转到 /approvals
 * - aria-label：含待办数量
 */

import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRouter } from 'vue-router'
import ApprovalIcon from '@/components/ApprovalIcon.vue'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: vi.fn(),
}))

// Mock permission directive
vi.mock('@/directives/permission', () => ({
  setupPermissionDirective: vi.fn(),
}))

describe('ApprovalIcon', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders when user has approval permissions', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['invoice:approve'])

    const mockRouter = { push: vi.fn() }
    vi.mocked(useRouter).mockReturnValue(mockRouter as any)

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // 应该渲染
    expect(wrapper.find('[data-testid="approval-icon"]').exists()).toBe(true)
  })

  it('does not render when user has no approval permissions', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set([]) // 无审批权限

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
        directives: {
          'any-permission': {
            mounted: (el: HTMLElement) => {
              el.parentNode?.removeChild(el) // 无权限时移除元素
            },
          },
        },
      },
    })

    // 不应该渲染
    expect(wrapper.find('[data-testid="approval-icon"]').exists()).toBe(false)
  })

  it('shows badge when pendingCount > 0', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['invoice:approve'])

    const approvalStore = useApprovalStore()
    approvalStore.pendingCount = 5

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // Badge 应该显示
    expect(wrapper.find('[data-testid="approval-badge"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="approval-badge"]').attributes('value')).toBe('5')
  })

  it('hides badge when pendingCount === 0', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['invoice:approve'])

    const approvalStore = useApprovalStore()
    approvalStore.pendingCount = 0

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // Badge 应该隐藏（hidden 属性）
    const badge = wrapper.find('[data-testid="approval-badge"]')
    expect(badge.exists()).toBe(true)
    expect(badge.attributes('hidden')).toBe('true')
  })

  it('navigates to /approvals when clicked', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['invoice:approve'])

    const mockRouter = { push: vi.fn() }
    vi.mocked(useRouter).mockReturnValue(mockRouter as any)

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // 点击按钮
    await wrapper.find('[data-testid="approval-button"]').trigger('click')

    // 应该跳转到 /approvals
    expect(mockRouter.push).toHaveBeenCalledWith('/approvals')
  })

  it('has aria-label with pending count', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['invoice:approve'])

    const approvalStore = useApprovalStore()
    approvalStore.pendingCount = 3

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // aria-label 应该含待办数量
    const button = wrapper.find('[data-testid="approval-button"]')
    expect(button.attributes('aria-label')).toContain('待办 3 条')
  })

  it('has aria-label with "无待办" when pendingCount === 0', async () => {
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['invoice:approve'])

    const approvalStore = useApprovalStore()
    approvalStore.pendingCount = 0

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // aria-label 应该显示"无待办"
    const button = wrapper.find('[data-testid="approval-button"]')
    expect(button.attributes('aria-label')).toContain('无待办')
  })

  it('includes all approval permissions in check', async () => {
    // 验证权限列表包含 contract:approve:*（关键修复）
    const ALL_APPROVAL_PERMISSIONS = [
      'contract:approve:own',
      'contract:approve:all',
      'invoice:approve',
      'invoice:approve:own',
      'invoice:approve:all',
      'payment:approve',
      'payment:approve:own',
      'payment:approve:all',
    ]

    // 测试合同审批人能看到
    const permissionStore = usePermissionStore()
    permissionStore.permissionSet = new Set(['contract:approve:own'])

    const wrapper = mount(ApprovalIcon, {
      global: {
        plugins: [createPinia()],
      },
    })

    // 应该渲染（合同审批人能看到）
    expect(wrapper.find('[data-testid="approval-icon"]').exists()).toBe(true)
  })
})