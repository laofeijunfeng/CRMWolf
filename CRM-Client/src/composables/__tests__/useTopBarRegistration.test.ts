import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { useHeaderStore } from '@/stores/header'
import { useTopBarRegistration } from '../useTopBarRegistration'

describe('useTopBarRegistration', () => {
  it('clears registered TopBar actions on unmount', () => {
    setActivePinia(createPinia())
    const headerStore = useHeaderStore()
    const Host = defineComponent({
      name: 'TopBarHost',
      setup() {
        useTopBarRegistration({
          actions: () => [{
            id: 'invite-member',
            label: '邀请成员',
            handler: (): void => undefined,
          }],
        })
        return (): null => null
      },
    })

    const wrapper = mount(Host)
    expect(headerStore.actions.some((action) => action.id === 'invite-member')).toBe(true)

    wrapper.unmount()
    expect(headerStore.actions).toEqual([])
  })

  it('clears registered TopBar tabs on unmount without calling full clear', () => {
    setActivePinia(createPinia())
    const headerStore = useHeaderStore()
    headerStore.setBack(true, '/settings/procurement-methods')
    const Host = defineComponent({
      name: 'TopBarTabsHost',
      setup() {
        useTopBarRegistration({
          tabs: () => [{ key: 'all', label: '全部' }],
        })
        return (): null => null
      },
    })

    const wrapper = mount(Host)
    expect(headerStore.tabs).not.toBeNull()

    wrapper.unmount()
    expect(headerStore.tabs).toBeNull()
    expect(headerStore.showBack).toBe(true)
    expect(headerStore.backRoute).toBe('/settings/procurement-methods')
  })
})
