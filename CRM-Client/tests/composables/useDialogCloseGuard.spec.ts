import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'

function createHost(initialDirty = true) {
  const emittedOpen: boolean[] = []
  let guard: ReturnType<typeof useDialogCloseGuard> | undefined
  const host = defineComponent({
    setup() {
      guard = useDialogCloseGuard({
        isDirty: ref(initialDirty),
        submitting: ref(false),
        emitOpen: (open) => emittedOpen.push(open),
      })
      return () => h('div')
    },
  })

  const wrapper = mount(host)
  if (guard === undefined) throw new Error('close guard was not initialized')
  return { wrapper, guard, emittedOpen }
}

describe('useDialogCloseGuard', () => {
  it('blocks a dirty close and confirms discard only after explicit action', async () => {
    const { wrapper, guard, emittedOpen } = createHost()

    guard.requestClose()
    await nextTick()

    expect(guard.showConfirmDialog.value).toBe(true)
    expect(emittedOpen).toEqual([])

    guard.continueEditing()
    expect(guard.showConfirmDialog.value).toBe(false)
    expect(emittedOpen).toEqual([])

    guard.requestClose()
    guard.confirmDiscard()
    await nextTick()

    expect(emittedOpen).toEqual([false])
    expect(guard.showConfirmDialog.value).toBe(false)
    wrapper.unmount()
  })

  it('reopens the controlled dialog when the parent tries to close dirty input directly', async () => {
    const { wrapper, guard, emittedOpen } = createHost()

    expect(guard.handleParentClose()).toBe(true)
    await nextTick()

    expect(emittedOpen).toEqual([true])
    expect(guard.showConfirmDialog.value).toBe(true)
    wrapper.unmount()
  })

  it('treats confirmation Escape or overlay dismissal as continue editing', async () => {
    const { wrapper, guard, emittedOpen } = createHost()

    guard.requestClose()
    expect(guard.showConfirmDialog.value).toBe(true)

    guard.handleConfirmOpenChange(false)
    await nextTick()

    expect(guard.showConfirmDialog.value).toBe(false)
    expect(emittedOpen).toEqual([])
    wrapper.unmount()
  })

  it('ignores a stale open after an approved close until the parent opens again', async () => {
    const { wrapper, guard, emittedOpen } = createHost(false)

    guard.approveClose()
    guard.handleParentClose()
    guard.handleOpenChange(true)
    await nextTick()

    expect(emittedOpen).toEqual([])

    guard.reset()
    guard.handleOpenChange(true)
    await nextTick()

    expect(emittedOpen).toEqual([true])
    wrapper.unmount()
  })
})
