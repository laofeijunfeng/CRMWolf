import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { getSettingsNavigationItem, SETTINGS_NAVIGATION } from './settingsNavigation'

describe('settings navigation registry', () => {
  it('keeps one canonical route per settings module', () => {
    const paths = SETTINGS_NAVIGATION.map(item => item.path)
    expect(new Set(paths).size).toBe(paths.length)
    expect(getSettingsNavigationItem('procurement')?.path).toBe('/settings/procurement-methods')
  })

  it('keeps account settings available without team permissions', () => {
    const account = getSettingsNavigationItem('account')
    expect(account?.scope).toBe('personal')
    expect(account?.requiredAnyPermissions).toEqual([])
  })

  it('allows automation permissions to enter the new approval workflow page', () => {
    const item = getSettingsNavigationItem('approval-flows-new')

    expect(item?.requiredAnyPermissions).toEqual(expect.arrayContaining([
      'automation:read',
      'automation:create',
      'automation:edit',
    ]))
  })
  it('registers canonical products entry with explicit permission and no owner bypass', () => {
    const item = getSettingsNavigationItem('products')
    expect(item).toMatchObject({
      path: '/settings/products',
      requiredAnyPermissions: ['product:view'],
      scope: 'team',
      requiresTeam: true,
      allowOwnerBypass: false,
    })
  })
  it('registers Agent run log after AI config in the integration group', () => {
    const item = getSettingsNavigationItem('agent-run-log')
    const ids = SETTINGS_NAVIGATION.map(entry => entry.id)
    expect(item).toMatchObject({
      path: '/settings/agent-run-log',
      group: 'integration',
      scope: 'team',
      requiresTeam: true,
      requiredAnyPermissions: ['ai:read', 'ai:manage', 'system:config'],
    })
    expect(item?.legacyComponentKey).toBeUndefined()
    expect(ids.indexOf('agent-run-log')).toBe(ids.indexOf('ai') + 1)
  })

  it('does not host settings modules through SettingsModulePage', () => {
    const routerSource = readFileSync(resolve(process.cwd(), 'src/router/index.ts'), 'utf8')
    expect(routerSource).not.toContain('SettingsModulePage')
    expect(routerSource).toContain('SettingsMembersPage')
    expect(routerSource).toContain('SettingsProductsPage')
    expect(routerSource).toContain('SettingsAIPage')
  })

  it('keeps separate AI and products settings routes', () => {
    const routerSource = readFileSync(resolve(process.cwd(), 'src/router/index.ts'), 'utf8')
    expect(routerSource).toContain('SettingsAIPage')
    expect(routerSource).toContain('SettingsProductsPage')
    expect(getSettingsNavigationItem('ai')?.id).toBe('ai')
    expect(getSettingsNavigationItem('products')?.id).toBe('products')
    expect(getSettingsNavigationItem('ai')?.path).not.toBe(getSettingsNavigationItem('products')?.path)
  })
})
