import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { ref, type Ref } from 'vue'
import { readFileSync } from 'node:fs'

interface UserInfoMock { id: number; name: string; avatar_url?: string }

const route = vi.hoisted(() => ({ path: '/customers' }))
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), go: vi.fn(), back: vi.fn() }))
const userStore = vi.hoisted<{ userInfo?: Ref<UserInfoMock>; isLoggedIn: ReturnType<typeof vi.fn>; fetchUserInfo: ReturnType<typeof vi.fn>; logout: ReturnType<typeof vi.fn> }>(() => ({
  userInfo: undefined,
  isLoggedIn: vi.fn(() => true),
  fetchUserInfo: vi.fn(),
  logout: vi.fn(),
}))
const teamStore = vi.hoisted<{ currentTeam?: Ref<null>; teams?: Ref<unknown[]>; hasAnyTeam: ReturnType<typeof vi.fn>; fetchUserTeams: ReturnType<typeof vi.fn>; switchTeam: ReturnType<typeof vi.fn> }>(() => ({
  currentTeam: undefined,
  teams: undefined,
  hasAnyTeam: vi.fn(() => true),
  fetchUserTeams: vi.fn(),
  switchTeam: vi.fn(),
}))
const permissionStore = vi.hoisted(() => ({
  initialized: true,
  fetchPermissions: vi.fn(),
  hasAnyPermission: vi.fn(() => true),
}))

vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => router }))
vi.mock('@/stores/user', () => ({ useUserStore: () => userStore }))
vi.mock('@/stores/team', () => ({ useTeamStore: () => teamStore }))
vi.mock('@/stores/permissions', () => ({ usePermissionStore: () => permissionStore }))
vi.mock('@/stores/pageTitle', () => ({ usePageTitleStore: () => ({ title: ref(''), tabs: [], activeTab: '', hasTabs: false }) }))
vi.mock('@/stores/header', () => ({ useHeaderStore: () => ({ tabs: [], activeTab: '', hasTabs: false, leftAction: null, showBack: false, backRoute: null, actions: [], hasActions: false, setActiveTab: vi.fn() }) }))
vi.mock('@/utils/logger', () => ({ logger: { error: vi.fn() } }))
vi.mock('@/utils/confirmDialog', () => ({ confirmLogout: vi.fn() }))

import AppLayout from '@/AppLayout.vue'

describe('AppLayout user menu', () => {
  let wrapper: VueWrapper | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    userStore.userInfo = ref({ id: 1, name: '王小明' })
    teamStore.currentTeam = ref(null)
    teamStore.teams = ref([])
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    document.body.innerHTML = ''
  })

  it('opens the account menu by click, not hover', async () => {
    wrapper = mount(AppLayout, {
      global: {
        stubs: {
          ApprovalIcon: true,
          BottomNav: true,
          TopBarTabs: true,
          'router-view': true,
        },
      },
    })

    if (wrapper === null) throw new Error('AppLayout 未挂载')
    const trigger = wrapper.get('button[aria-label="用户设置"]')
    await trigger.trigger('mouseenter')
    expect(document.body.querySelector('[role="menuitem"][aria-label="账户设置"]')).toBeNull()

    await trigger.trigger('click')
    expect(document.body.querySelector('[role="menuitem"][aria-label="账户设置"]')).not.toBeNull()

    const accountItem = document.body.querySelector('[role="menuitem"][aria-label="账户设置"]') as HTMLElement
    accountItem.click()
    expect(router.push).toHaveBeenCalledWith('/account')
  })
})

describe('AppLayout sidebar visibility CSS contract', () => {
  it('does not override Tailwind responsive hidden classes globally', () => {
    const globalStyles = readFileSync('src/styles/global.scss', 'utf-8')
    const sidebarSource = readFileSync('src/components/ui/sidebar/Sidebar.vue', 'utf-8')

    expect(globalStyles).not.toMatch(/\.hidden\s*\{\s*display:\s*none\s*!important/)
    expect(sidebarSource).toContain('hidden md:block')
    expect(sidebarSource).toContain('hidden h-svh w-[var(--sidebar-width)]')
    expect(sidebarSource).toContain('md:flex')
  })

  it('keeps route content inside the app shell scroll container', () => {
    const appLayoutSource = readFileSync('src/AppLayout.vue', 'utf-8')
    const agentChatSource = readFileSync('src/components/agent/CRMAgentChat.vue', 'utf-8')
    const messageScrollerSource = readFileSync('src/components/ui/message-scroller/MessageScroller.vue', 'utf-8')
    const appDrawerSource = readFileSync('src/components/ui/app-drawer/AppDrawer.vue', 'utf-8')

    expect(appLayoutSource).toContain(':class="mainContentClass"')
    expect(appLayoutSource).toContain(':class="mainViewClass"')
    expect(appLayoutSource).not.toContain('<BottomNav')
    expect(appLayoutSource).not.toContain("from '@/components/crmwolf/BottomNav.vue'")
    expect(appLayoutSource).toMatch(/\.main-content\s*\{[^}]*overflow:\s*hidden/s)
    expect(appLayoutSource).toContain("'main-content--contained': route.name === 'AgentChat' || route.path.startsWith('/agent')")
    expect(appLayoutSource).toMatch(/\.main-content--contained\s*\{[^}]*height:\s*calc\(100svh - 1rem\)/s)
    expect(appLayoutSource).toMatch(/\.main-content--contained\s*\{[^}]*min-height:\s*0/s)
    expect(appLayoutSource).toMatch(/\.main-view\s*\{[^}]*overflow:\s*auto/s)
    expect(appLayoutSource).toContain("'main-view--contained': route.name === 'AgentChat' || route.path.startsWith('/agent')")
    expect(appLayoutSource).toMatch(/\.main-view--contained\s*\{[^}]*height:\s*100%/s)
    expect(appLayoutSource).toMatch(/\.main-view--contained\s*\{[^}]*max-height:\s*100%/s)
    expect(appLayoutSource).toMatch(/\.main-view--contained\s*\{[^}]*overflow:\s*hidden/s)
    expect(appLayoutSource).toContain(':deep(.agent-chat)')
    expect(agentChatSource).toContain('height: 100%;\n  max-height: 100%;\n  min-height: 0;')
    expect(agentChatSource).toContain('max-height: 100%;\n  min-height: 0;\n  overflow: hidden;')
    expect(messageScrollerSource).toContain('message-scroller h-full min-h-0')
    expect(messageScrollerSource).toMatch(/data-reka-scroll-area-viewport[\s\S]*overflow-y:\s*auto/)
    expect(appDrawerSource).toMatch(/\.app-drawer\s*\{[^}]*max-height:\s*min\(80svh, 720px\)/s)
    expect(appDrawerSource).toMatch(/\.app-drawer__content\s*\{[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\)/s)
    expect(appDrawerSource).toMatch(/\.app-drawer__body\s*\{[^}]*overflow-y:\s*auto/s)
    expect(agentChatSource).not.toContain('height: calc(100dvh - $wolf-topbar-height-v2)')
    expect(agentChatSource).not.toContain('height: calc(100dvh - $wolf-topbar-height-mobile-v2 - $wolf-bottom-nav-height-v2)')
  })

  it('uses the shadcn sidebar sheet instead of the old mobile bottom navigation', () => {
    const appLayoutSource = readFileSync('src/AppLayout.vue', 'utf-8')
    const sidebarSource = readFileSync('src/components/ui/sidebar/Sidebar.vue', 'utf-8')
    const sidebarProviderSource = readFileSync('src/components/ui/sidebar/SidebarProvider.vue', 'utf-8')

    expect(sidebarProviderSource).toContain('useMediaQuery("(max-width: 767px)")')
    expect(sidebarSource).toContain('<Sheet v-else-if="isMobile"')
    expect(appLayoutSource).toContain('<SidebarTrigger class="sidebar-trigger" />')
    expect(appLayoutSource).not.toContain('sidebar-trigger-desktop')
    expect(appLayoutSource).not.toContain('height: calc(100dvh - $wolf-bottom-nav-height-v2)')
  })

  it('keeps the desktop sidebar uncontrolled when no open prop is passed', () => {
    const sidebarProviderSource = readFileSync('src/components/ui/sidebar/SidebarProvider.vue', 'utf-8')

    expect(sidebarProviderSource).toContain('open: undefined')
    expect(sidebarProviderSource).toContain('passive: (props.open === undefined) as false')
  })

  it('keeps dashboard navigation visible while permissions are still loading', () => {
    const appSidebarSource = readFileSync('src/components/app-sidebar/AppSidebar.vue', 'utf-8')

    expect(appSidebarSource).toContain('const shouldShowDashboardGroup = computed(() => {')
    expect(appSidebarSource).toContain('return !permissionStore.initialized || canViewSalesDashboard.value')
    expect(appSidebarSource).toContain('...(shouldShowDashboardGroup.value')
  })

  it('keeps the top bar aligned with the white main workspace surface', () => {
    const appLayoutSource = readFileSync('src/AppLayout.vue', 'utf-8')

    expect(appLayoutSource).toContain('<Separator orientation="vertical" class="sidebar-trigger-separator" />')
    expect(appLayoutSource).toContain("import { Separator } from '@/components/ui/separator'")
    expect(appLayoutSource).toMatch(/\.top-bar\s*\{[^}]*background:\s*\$wolf-bg-card-v2/s)
    expect(appLayoutSource).toMatch(/\.top-bar\s*\{[^}]*box-shadow:\s*none/s)
    expect(appLayoutSource).toMatch(/\.top-bar\s*\{[^}]*border-bottom:\s*1px solid \$wolf-border-default-v2/s)
    expect(appLayoutSource).toMatch(/\.sidebar-trigger-separator\s*\{[^}]*height:\s*16px/s)
  })

  it('uses the official Tailwind blue tokens for the shadcn sidebar emphasis', () => {
    const baseStyles = readFileSync('src/styles/base.css', 'utf-8')
    const variablesSource = readFileSync('src/styles/variables-v2.scss', 'utf-8')

    expect(variablesSource).toContain('$wolf-bg-sidebar-v2: #F8FAFC')
    expect(variablesSource).toContain('$wolf-bg-page-v2: #FFFFFF')
    expect(variablesSource).toContain('$wolf-primary-v2: #2563EB')
    expect(baseStyles).toContain('--sidebar-background: 210 40% 98%;')
    expect(baseStyles).toContain('--sidebar-primary: 221.2 83.2% 53.3%;')
    expect(baseStyles).toContain('--sidebar-accent: 210 40% 96.1%;')
    expect(baseStyles).toContain('--sidebar-active: 214.3 100% 96.9%;')
    expect(baseStyles).toContain('--sidebar-border: 214.3 31.8% 91.4%;')
    expect(baseStyles).toContain('--ring: 221.2 83.2% 53.3%;')
    expect(baseStyles).not.toContain('--primary: 222.2 47.4% 11.2%;')
  })

  it('does not keep old full-viewport page shell heights inside the sidebar layout', () => {
    const systemConfigSource = readFileSync('src/views/SystemConfig.vue', 'utf-8')
    const customerEditSource = readFileSync('src/views/CustomerEdit.vue', 'utf-8')
    const salesDashboardSource = readFileSync('src/views/SalesDashboard.vue', 'utf-8')

    expect(systemConfigSource).not.toContain('min-height: calc(100vh - 56px)')
    expect(customerEditSource).not.toContain('min-height: calc(100vh - 56px)')
    expect(salesDashboardSource).not.toContain('min-height: calc(100vh - $wolf-topbar-height-v2)')
    expect(salesDashboardSource).not.toContain('min-height: calc($wolf-viewport-height-mobile-v2 - $wolf-topbar-height-mobile-v2)')
    expect(salesDashboardSource).not.toContain('padding-bottom: calc($wolf-bottom-nav-height-v2 + $wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2)')
    expect(salesDashboardSource).toMatch(/\.sales-dashboard-page\s*\{[^}]*min-height:\s*0/s)
  })
})
