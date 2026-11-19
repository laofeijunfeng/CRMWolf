import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'

const confirmDiscardChanges = vi.hoisted(() => vi.fn<(kind?: 'close' | 'leave') => Promise<boolean>>())
vi.mock('@/utils/confirmDialog', () => ({ confirmDiscardChanges }))

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
  beforeEach(() => {
    confirmDiscardChanges.mockReset()
  })

  it('closes dirty input only after the discard confirmation resolves true', async () => {
    const { wrapper, guard, emittedOpen } = createHost()

    confirmDiscardChanges.mockResolvedValueOnce(false)
    guard.requestClose()
    await flushPromises()
    expect(confirmDiscardChanges).toHaveBeenCalledWith('close')
    expect(emittedOpen).toEqual([])

    confirmDiscardChanges.mockResolvedValueOnce(true)
    guard.requestClose()
    await flushPromises()
    expect(emittedOpen).toEqual([false])
    wrapper.unmount()
  })

  it('asks once while a confirmation is already open', async () => {
    const { wrapper, guard, emittedOpen } = createHost()
    let resolve: (value: boolean) => void = () => {}
    confirmDiscardChanges.mockReturnValueOnce(new Promise<boolean>((r) => { resolve = r }))

    guard.requestClose()
    guard.handleOpenChange(false)
    guard.requestClose()
    expect(confirmDiscardChanges).toHaveBeenCalledTimes(1)

    resolve(false)
    await flushPromises()
    expect(emittedOpen).toEqual([])
    wrapper.unmount()
  })

  it('reopens the controlled dialog when the parent tries to close dirty input directly', async () => {
    const { wrapper, guard, emittedOpen } = createHost()
    confirmDiscardChanges.mockResolvedValueOnce(false)

    expect(guard.handleParentClose()).toBe(true)
    await flushPromises()

    expect(emittedOpen).toEqual([true])
    expect(confirmDiscardChanges).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('closes clean input without asking', async () => {
    const { wrapper, guard, emittedOpen } = createHost(false)

    guard.requestClose()
    await flushPromises()

    expect(confirmDiscardChanges).not.toHaveBeenCalled()
    expect(emittedOpen).toEqual([false])
    wrapper.unmount()
  })

  it('ignores a stale open after an approved close until the parent opens again', async () => {
    const { wrapper, guard, emittedOpen } = createHost(false)

    guard.approveClose()
    guard.handleParentClose()
    guard.handleParentClose()
    guard.handleOpenChange(true)
    await flushPromises()

    expect(emittedOpen).toEqual([])

    guard.reset()
    guard.handleOpenChange(true)
    await flushPromises()

    expect(emittedOpen).toEqual([true])
    wrapper.unmount()
  })
})
