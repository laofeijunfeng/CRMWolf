import { describe, expect, it } from 'vitest'
import { getSettingsNavigationItem, getVisibleSettingsNavigation } from '@/settingsNavigation'

describe('SettingsSidebar navigation contract', () => {
  it('filters inaccessible modules while keeping account settings available', () => {
    const visible = getVisibleSettingsNavigation(item => item.id === 'account' || item.id === 'roles')
    expect(visible.map(item => item.label)).toEqual(['账户设置', '角色管理'])
    expect(getSettingsNavigationItem('account')?.scope).toBe('personal')
  })

  it('exposes every settings module to the team owner policy', () => {
    const visible = getVisibleSettingsNavigation(() => true)
    expect(visible).toHaveLength(10)
  })
})
