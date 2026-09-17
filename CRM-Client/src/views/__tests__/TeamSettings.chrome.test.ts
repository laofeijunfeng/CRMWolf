import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TeamSettings from '@/views/TeamSettings.vue'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'

vi.mock('@/api/team', () => ({
  teamApi: { getTeamDetail: vi.fn(), updateTeam: vi.fn(), regenerateInviteCode: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: (): { meta: { title: string } } => ({ meta: { title: '团队信息与安全' } }),
}))

describe('TeamSettings chrome', () => {
  it('does not render a duplicate settings heading or max-width shell', () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'ready'
    teamStore.currentTeam = { id: 1, name: '演示', code: 'DEMO', owner_id: '1', created_at: '2026-01-01T00:00:00Z' }
    const wrapper = mount(TeamSettings, { global: { stubs: { ErrorState: true, Card: { template: '<div><slot /></div>' }, CardHeader: true, CardTitle: true, CardDescription: true, CardContent: true, Button: true, Input: true, Label: true, Skeleton: true } } })
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('系统设置')
    expect(wrapper.html()).not.toContain('max-w-6xl')
    wrapper.unmount()
  })
})
