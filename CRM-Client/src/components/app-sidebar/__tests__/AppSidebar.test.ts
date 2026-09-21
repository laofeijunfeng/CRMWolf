import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { GitBranch } from 'lucide-vue-next'
import { defineComponent, type Component, type PropType } from 'vue'
import AppSidebar from '@/components/app-sidebar/AppSidebar.vue'
import type { PermissionResponse } from '@/schemas/auth'
import { usePermissionStore, type PermissionLoadState } from '@/stores/permissions'

const route = vi.hoisted(() => ({ path: '/customers' }))
const router = vi.hoisted(() => ({ push: vi.fn() }))
const confirmationApiMocks = vi.hoisted(() => ({
  getPendingCount: vi.fn().mockResolvedValue(0),
  resolve: vi.fn(),
}))

vi.mock('vue-router', (): { useRoute: () => typeof route; useRouter: () => typeof router } => ({
  useRoute: (): typeof route => route,
  useRouter: (): typeof router => router,
}))
vi.mock('@/api/followUpTask', () => ({ followUpConfirmationApi: confirmationApiMocks }))
vi.mock('@/utils/logger', () => ({ logger: { warn: vi.fn() } }))

interface SidebarNavItem {
  label: string
  path: string
  icon: Component
  active: boolean
  badge?: number | string
  badgeDescription?: string
}

interface SidebarNavGroup {
  label: string
  items: SidebarNavItem[]
}

const NavMainStub = defineComponent({
  name: 'NavMain',
  props: {
    groups: {
      type: Array as PropType<SidebarNavGroup[]>,
      required: true,
    },
  },
  template: `
    <nav>
      <section v-for="group in groups" :key="group.label" :data-group="group.label">
        <h2>{{ group.label }}</h2>
        <a v-for="item in group.items" :key="item.path" :href="item.path">{{ item.label }}</a>
      </section>
    </nav>
  `,
})

const permission = (code: string): PermissionResponse => ({
  id: 1,
  code,
  name: code,
  resource: code.split(':')[0] ?? code,
  action: 'view',
})

const mountSidebar = (loadState: PermissionLoadState, codes: string[] = []): VueWrapper => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const permissionStore = usePermissionStore()
  permissionStore.loadState = loadState
  permissionStore.permissions = codes.map(permission)

  return mount(AppSidebar, {
    global: {
      plugins: [pinia],
      stubs: {
        NavMain: NavMainStub,
        NavUser: true,
        SettingsSidebar: true,
        Sidebar: { template: '<aside><slot /></aside>' },
        SidebarHeader: { template: '<header><slot /></header>' },
        SidebarContent: { template: '<main><slot /></main>' },
        SidebarFooter: { template: '<footer><slot /></footer>' },
        SidebarMenu: { template: '<div><slot /></div>' },
        SidebarMenuItem: { template: '<div><slot /></div>' },
        SidebarMenuButton: { template: '<button><slot /></button>' },
        SidebarRail: true,
      },
    },
  })
}

const groupsFor = (wrapper: VueWrapper): SidebarNavGroup[] => (
  wrapper.getComponent(NavMainStub).props('groups') as SidebarNavGroup[]
)
const groupLabels = (wrapper: VueWrapper): string[] => groupsFor(wrapper).map(group => group.label)
const items = (wrapper: VueWrapper, label: string): string[] => (
  groupsFor(wrapper).find(group => group.label === label)?.items.map(item => item.label) ?? []
)
const pathFor = (wrapper: VueWrapper, label: string): string | undefined => (
  groupsFor(wrapper).flatMap(group => group.items).find(item => item.label === label)?.path
)

const journeyPermissionCodes = [
  'customer:view:all',
  'customer:view:own',
  'opportunity:view:all',
  'opportunity:view:own',
] as const
const firstJourneyPermissionCode = journeyPermissionCodes[0]

const dashboardPermissionCode = 'sales_dashboard:view:own'

describe('AppSidebar business navigation', () => {
  let wrappers: VueWrapper[] = []

  beforeEach(() => {
    vi.clearAllMocks()
    route.path = '/customers'
  })

  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount())
    wrappers = []
  })

  it('groups sales work, transactions, finance, and dashboards in the required order', () => {
    const wrapper = mountSidebar('ready', [firstJourneyPermissionCode, dashboardPermissionCode])
    wrappers.push(wrapper)

    expect(groupLabels(wrapper)).toEqual(['销售工作', '交易管理', '财务管理', '数据看板'])
    expect(items(wrapper, '销售工作')).toEqual(['AI Agent', '线索管理', '客户管理', '客户追踪', '业务旅程'])
    expect(items(wrapper, '交易管理')).toEqual(['商机管理', '合同管理', '回款计划'])
    expect(items(wrapper, '财务管理')).toEqual(['回款管理', '发票管理'])
    expect(items(wrapper, '数据看板')).toEqual(['销售看板'])
    expect(pathFor(wrapper, '业务旅程')).toBe('/business-journeys')
    const journeyItem = groupsFor(wrapper).flatMap(group => group.items).find(item => item.label === '业务旅程')
    expect(journeyItem?.icon).toBe(GitBranch)
    expect(wrapper.text()).not.toContain('业务看板')
  })

  it.each(journeyPermissionCodes)('shows business journeys when ready with %s', (code) => {
    const wrapper = mountSidebar('ready', [code])
    wrappers.push(wrapper)

    expect(items(wrapper, '销售工作')).toContain('业务旅程')
  })

  it('hides business journeys when ready without customer or opportunity view permission', () => {
    const wrapper = mountSidebar('ready', [dashboardPermissionCode])
    wrappers.push(wrapper)

    expect(items(wrapper, '销售工作')).not.toContain('业务旅程')
  })

  it.each<PermissionLoadState>(['idle', 'loading'])('shows business journeys while permissions are %s', (loadState) => {
    const wrapper = mountSidebar(loadState)
    wrappers.push(wrapper)

    expect(items(wrapper, '销售工作')).toContain('业务旅程')
  })
  it('hides business journeys when permission loading fails', () => {
    const wrapper = mountSidebar('error', [firstJourneyPermissionCode])
    wrappers.push(wrapper)

    expect(items(wrapper, '销售工作')).not.toContain('业务旅程')
  })
})
