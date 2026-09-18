import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { useSettingsUnsavedLeave, type SettingsUnsavedLeaveGuard } from '../useSettingsUnsavedLeave'

const LeaveGuardRoot = defineComponent({
  name: 'LeaveGuardRoot',
  template: '<router-view />',
})

const mountGuardedApp = async (options: {
  isDirty: () => boolean
  isSubmitting: () => boolean
}): Promise<{
  leave: SettingsUnsavedLeaveGuard
  router: Router
  wrapper: VueWrapper
}> => {
  let leave: SettingsUnsavedLeaveGuard | undefined

  const GuardedPage = defineComponent({
    name: 'GuardedPage',
    setup() {
      leave = useSettingsUnsavedLeave(options)
      return (): null => null
    },
  })

  const ElsewherePage = defineComponent({
    name: 'ElsewherePage',
    setup() {
      return (): null => null
    },
  })

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'guarded', component: GuardedPage },
      { path: '/elsewhere', name: 'elsewhere', component: ElsewherePage },
    ],
  })

  await router.push('/')
  await router.isReady()

  const wrapper = mount(LeaveGuardRoot, {
    global: {
      plugins: [router],
    },
  })

  if (leave === undefined) {
    wrapper.unmount()
    throw new Error('useSettingsUnsavedLeave did not initialize on the stub page')
  }

  return {
    leave,
    router,
    wrapper,
  }
}

describe('useSettingsUnsavedLeave', () => {
  it('blocks dirty navigation until confirmLeave', async () => {
    const { leave, router, wrapper } = await mountGuardedApp({
      isDirty: (): boolean => true,
      isSubmitting: (): boolean => false,
    })

    await router.push('/elsewhere')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/')
    expect(leave.showLeaveConfirm.value).toBe(true)
    expect(leave.pendingPath.value).toBe('/elsewhere')

    leave.confirmLeave()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/elsewhere')
    expect(leave.showLeaveConfirm.value).toBe(false)

    wrapper.unmount()
  })
})
