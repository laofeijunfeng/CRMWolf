import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { ref, type Ref } from 'vue'

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
