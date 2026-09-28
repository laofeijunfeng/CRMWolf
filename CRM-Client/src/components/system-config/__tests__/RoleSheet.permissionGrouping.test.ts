import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import type { Ref, VNode } from 'vue'
import type { PermissionResponse } from '@/schemas/role'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getRoles: vi.fn(),
  getRole: vi.fn(),
  getAllPermissions: vi.fn(),
}))

vi.mock('@/api/role', () => ({
  default: {
    getRoles: mocks.getRoles,
    getRole: mocks.getRole,
    createRole: vi.fn(),
    updateRole: vi.fn(),
    deleteRole: vi.fn(),
    updateRolePermissions: vi.fn(),
  },
}))

vi.mock('@/api/permissions', () => ({
  default: { getAllPermissions: mocks.getAllPermissions },
}))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: (): { hasPermission: () => boolean; hasAnyPermission: () => boolean } => ({
    hasPermission: (): boolean => true,
    hasAnyPermission: (): boolean => true,
  }),
}))

vi.mock('@/composables/useSettingsAccess', async () => {
  const { ref } = await import('vue')
  return { useSettingsAccess: (): { isOwner: Ref<boolean> } => ({ isOwner: ref(true) }) }
})

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn() } }))

// Mock factories run before static imports, so Vue is loaded inside this factory.
vi.mock('@/components/crmwolf', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    ListCard: defineComponent({
      name: 'ListCard',
      props: { items: { type: Array, default: () => [] } },
      setup(props, { slots }): () => VNode {
        return () => h('div', (props.items as Record<string, unknown>[]).map(item => h('section', {
          key: String(item['id']),
        }, [
          slots['itemMain']?.({ item }),
          slots['itemActions']?.({ item }),
        ])))
      },
    }),
  }
})

import RoleSheet from '@/components/system-config/RoleSheet.vue'

const role = {
  id: 1,
  code: 'FINANCE',
  name: '财务人员',
  description: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const permissionResponse = (id: number, code: string, resource: string, name: string, action: string): PermissionResponse => ({
  id, code, resource, name, action,
  scope: null,
  description: null,
  is_active: true,
  created_at: '2026-09-28T00:00:00Z',
  updated_at: '2026-09-28T00:00:00Z',
})

const DialogStub = defineComponent({
  props: { open: Boolean },
  setup(props, { slots }): () => VNode | null {
    return () => props.open ? h('div', { role: 'dialog' }, slots['default']?.()) : null
  },
})

const SlotStub = defineComponent({
  setup: (_, { slots }): (() => VNode) => () => h('div', slots['default']?.()),
})

describe('RoleSheet permission grouping', () => {
  beforeEach(() => {
    mocks.getRoles.mockReset().mockResolvedValue([role])
    mocks.getRole.mockReset().mockResolvedValue({ ...role, permissions: [] })
    mocks.getAllPermissions.mockReset().mockResolvedValue([
      permissionResponse(1, 'payment:approve', 'payment', '审批回款', 'approve'),
      permissionResponse(2, 'payment:plan:export', 'payment_plan', '导出回款计划', 'export'),
      permissionResponse(3, 'payment:record:export', 'payment_record', '导出回款记录', 'export'),
    ])
  })

  it('shows payment record export inside one payment group', async () => {
    const wrapper = mount(RoleSheet, {
      props: { embedded: true, active: true },
      global: {
        stubs: {
          ScrollArea: SlotStub,
          Dialog: DialogStub,
          DialogContent: SlotStub,
          DialogHeader: SlotStub,
          DialogTitle: SlotStub,
          DialogDescription: SlotStub,
          DialogFooter: SlotStub,
          Button: {
            emits: ['click'],
            template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
          },
          Checkbox: { template: '<input type="checkbox">' },
          Label: { template: '<label><slot /></label>' },
          Badge: { template: '<span><slot /></span>' },
        },
      },
    })
    await vi.waitFor(() => expect(mocks.getRoles).toHaveBeenCalled())
    const permissionButton = wrapper.findAll('button').find(button => button.text().includes('权限'))
    if (permissionButton === undefined) throw new Error('RoleSheet permission action not rendered')
    await permissionButton.trigger('click')
    await flushPromises()
    const groupHeadings = wrapper.findAll('.font-semibold').map(item => item.text())
    expect(groupHeadings.filter(heading => heading === '回款')).toHaveLength(1)
    expect(groupHeadings).not.toContain('回款计划')
    expect(groupHeadings).not.toContain('回款记录')
    expect(wrapper.text()).toContain('导出回款记录')
    expect(wrapper.text()).toContain('payment:record:export')
    wrapper.unmount()
  })
})
