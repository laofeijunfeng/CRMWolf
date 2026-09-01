import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TeamMemberSheet from '@/components/system-config/TeamMemberSheet.vue'
import RoleSheet from '@/components/system-config/RoleSheet.vue'
import ApprovalFlowSheet from '@/components/system-config/ApprovalFlowSheet.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'

const mocks = vi.hoisted(() => ({
  getTeamDetail: vi.fn(),
  getTeamMembers: vi.fn(),
  getRoles: vi.fn(),
  getApprovalFlows: vi.fn(),
}))

const { getTeamDetail, getTeamMembers, getRoles, getApprovalFlows } = mocks

vi.mock('@/api/team', () => ({
  teamApi: {
    getTeamDetail: mocks.getTeamDetail,
    getTeamMembers: mocks.getTeamMembers,
  },
}))

vi.mock('@/api/approvalFlow', () => ({
  default: {
    getApprovalFlows: mocks.getApprovalFlows,
  },
}))

vi.mock('@/api/role', () => ({
  default: {
    getRoles: mocks.getRoles,
  },
}))

vi.mock('@/api/user', () => ({
  default: {
    searchUsers: vi.fn(),
  },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: vi.fn(),
  confirmDelete: vi.fn(),
}))

vi.mock('@/api/permissions', () => ({
  default: {
    getAllPermissions: vi.fn(),
  },
}))

describe('settings embedded panels', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads team members when rendered by the page shell without a sheet open prop', async () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const userStore = useUserStore()
    teamStore.currentTeam = {
      id: 7,
      name: '演示团队',
      code: 'DEMO',
      owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    userStore.userInfo = {
      id: 42,
      name: '团队所有者',
      email: 'owner@example.com',
      status: 'active',
      created_at: null,
      updated_at: null,
    }
    getTeamDetail.mockResolvedValue(teamStore.currentTeam)
    getTeamMembers.mockResolvedValue([{
      id: 'member-1',
      name: '成员一',
      email: 'member@example.com',
      joined_at: '2026-01-01T00:00:00Z',
      roles: [],
    }])
    getRoles.mockResolvedValue([])

    const wrapper = mount(TeamMemberSheet, {
      props: { active: true, embedded: true },
      global: {
        stubs: {
          SheetHeader: { template: '<div><slot /></div>' },
          SheetTitle: { template: '<h2><slot /></h2>' },
          SheetDescription: { template: '<p><slot /></p>' },
          ScrollArea: { template: '<div><slot /></div>' },
          ListCard: { template: '<div><slot name="itemMain" v-for="item in items" :item="item" /></div>', props: ['items'] },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: { template: '<div><slot /></div>' },
          DialogTitle: { template: '<h2><slot /></h2>' },
          DialogDescription: { template: '<p><slot /></p>' },
          DialogFooter: { template: '<div><slot /></div>' },
          FormField: { template: '<div><slot :componentField="{}" /></div>' },
          FormControl: { template: '<div><slot /></div>' },
          FormItem: { template: '<div><slot /></div>' },
          FormLabel: { template: '<label><slot /></label>' },
          FormMessage: { template: '<span><slot /></span>' },
        },
      },
    })

    await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledWith(7))
    expect(wrapper.text()).toContain('成员一')
    wrapper.unmount()
  })

  it('loads roles when rendered by the page shell without a sheet open prop', async () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const userStore = useUserStore()
    teamStore.currentTeam = {
      id: 7,
      name: '演示团队',
      code: 'DEMO',
      owner_id: '42',
      created_at: '2026-01-01T00:00:00Z',
    }
    userStore.userInfo = {
      id: 42,
      name: '团队所有者',
      email: 'owner@example.com',
      status: 'active',
      created_at: null,
      updated_at: null,
    }
    getRoles.mockResolvedValue([{
      id: 1,
      code: 'ADMIN',
      name: '管理员',
      description: null,
      created_at: '2026-01-01T00:00:00Z',
    }])

    const wrapper = mount(RoleSheet, {
      props: { active: true, embedded: true },
      global: {
        stubs: {
          SheetHeader: { template: '<div><slot /></div>' },
          SheetTitle: { template: '<h2><slot /></h2>' },
          SheetDescription: { template: '<p><slot /></p>' },
          ScrollArea: { template: '<div><slot /></div>' },
          ListCard: { template: '<div><slot name="itemMain" v-for="item in items" :item="item" /></div>', props: ['items'] },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: { template: '<div><slot /></div>' },
          DialogTitle: { template: '<h2><slot /></h2>' },
          DialogDescription: { template: '<p><slot /></p>' },
          DialogFooter: { template: '<div><slot /></div>' },
          FormField: { template: '<div><slot :componentField="{}" /></div>' },
          FormControl: { template: '<div><slot /></div>' },
          FormItem: { template: '<div><slot /></div>' },
          FormLabel: { template: '<label><slot /></label>' },
          FormMessage: { template: '<span><slot /></span>' },
        },
      },
    })

    await vi.waitFor(() => expect(getRoles).toHaveBeenCalled())
    expect(wrapper.text()).toContain('管理员')
    wrapper.unmount()
  })
  it('does not mount SheetTitle outside DialogRoot in embedded approval flow mode', async () => {
    getApprovalFlows.mockResolvedValue([])

    const wrapper = mount(ApprovalFlowSheet, {
      props: { active: true, embedded: true },
      global: {
        stubs: {
          ScrollArea: { template: '<div><slot /></div>' },
          ListCard: { template: '<div />', props: ['items'] },
          Button: { template: '<button><slot /></button>' },
          Input: { template: '<input />' },
          Badge: { template: '<span><slot /></span>' },
          Select: { template: '<div><slot /></div>' },
          SelectContent: { template: '<div><slot /></div>' },
          SelectItem: { template: '<div><slot /></div>' },
          SelectTrigger: { template: '<button><slot /></button>' },
          SelectValue: { template: '<span><slot /></span>' },
          AmountText: { template: '<span />' },
          Empty: { template: '<div><slot /></div>' },
          EmptyHeader: { template: '<div><slot /></div>' },
          EmptyMedia: { template: '<div><slot /></div>' },
          EmptyTitle: { template: '<div><slot /></div>' },
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: { template: '<div><slot /></div>' },
          DialogTitle: { template: '<h2><slot /></h2>' },
          DialogDescription: { template: '<p><slot /></p>' },
          ApprovalFlowFormDialog: { template: '<div />' },
          ApprovalFlowAIDialog: { template: '<div />' },
        },
      },
    })

    await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalled())
    expect(wrapper.text()).not.toContain('审批流程管理')
    expect(wrapper.findComponent({ name: 'SheetTitle' }).exists()).toBe(false)
    wrapper.unmount()
  })

})
