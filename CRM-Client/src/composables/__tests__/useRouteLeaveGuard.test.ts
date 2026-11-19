import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useRouteLeaveGuard, type RouteLeaveGuard, type RouteLeaveGuardOptions } from '../useRouteLeaveGuard'

const confirmDiscardChanges = vi.hoisted(() => vi.fn<(kind?: 'close' | 'leave') => Promise<boolean>>())
vi.mock('@/utils/confirmDialog', () => ({ confirmDiscardChanges }))

const mountGuardedApp = async (options: RouteLeaveGuardOptions): Promise<{
  leave: RouteLeaveGuard
  router: Router
  wrapper: VueWrapper
}> => {
  let leave: RouteLeaveGuard | undefined
  const GuardedPage = defineComponent({
    setup() {
      leave = useRouteLeaveGuard(options)
      return (): null => null
    },
  })
  const ElsewherePage = defineComponent({ setup: () => (): null => null })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: GuardedPage },
      { path: '/elsewhere', component: ElsewherePage },
      { path: '/other', component: ElsewherePage },
    ],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(defineComponent({ template: '<router-view />' }), { global: { plugins: [router] } })
  if (leave === undefined) throw new Error('useRouteLeaveGuard did not initialize')
  return { leave, router, wrapper }
}

describe('useRouteLeaveGuard', () => {
  beforeEach(() => {
    confirmDiscardChanges.mockReset()
  })

  it('stays on the page when the leave confirmation is cancelled', async () => {
    confirmDiscardChanges.mockResolvedValueOnce(false)
    const { router, wrapper } = await mountGuardedApp({ isDirty: () => true, isSubmitting: () => false })

    await router.push('/elsewhere')
    await flushPromises()

    expect(confirmDiscardChanges).toHaveBeenCalledWith('leave')
    expect(router.currentRoute.value.path).toBe('/')
    wrapper.unmount()
  })

  it('leaves after the discard is confirmed', async () => {
    confirmDiscardChanges.mockResolvedValueOnce(true)
    const { router, wrapper } = await mountGuardedApp({ isDirty: () => true, isSubmitting: () => false })

    await router.push('/elsewhere')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/elsewhere')
    wrapper.unmount()
  })

  it('shares one confirmation across overlapping navigations', async () => {
    let resolve: ((value: boolean) => void) | undefined
    confirmDiscardChanges.mockReturnValueOnce(new Promise<boolean>((r) => { resolve = r }))
    const { router, wrapper } = await mountGuardedApp({ isDirty: () => true, isSubmitting: () => false })

    void router.push('/elsewhere')
    await flushPromises()
    void router.push('/other')
    await flushPromises()
    expect(confirmDiscardChanges).toHaveBeenCalledTimes(1)

    resolve?.(true)
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/other')
    wrapper.unmount()
  })

  it('skips confirmation when clean or submitting', async () => {
    let dirty = false
    let submitting = false
    const { router, wrapper } = await mountGuardedApp({ isDirty: () => dirty, isSubmitting: () => submitting })

    await router.push('/elsewhere')
    await router.push('/')
    dirty = true
    submitting = true
    await router.push('/elsewhere')
    await flushPromises()

    expect(confirmDiscardChanges).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/elsewhere')
    wrapper.unmount()
  })

  it('lets one navigation through after allowNextNavigation', async () => {
    const { leave, router, wrapper } = await mountGuardedApp({ isDirty: () => true, isSubmitting: () => false })

    leave.allowNextNavigation()
    await router.push('/elsewhere')
    await flushPromises()

    expect(confirmDiscardChanges).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/elsewhere')
    wrapper.unmount()
  })
})
