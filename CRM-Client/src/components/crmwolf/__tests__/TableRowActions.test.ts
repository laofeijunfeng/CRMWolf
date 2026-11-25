import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DesktopTableRowActions from '../DesktopTableRowActions.vue'
import TableRowActions from '../TableRowActions.vue'
import type { ActionConfig } from '../tableRowActionTypes'

const mountedWrappers: VueWrapper[] = []

const disabledReason = '该商机已有合同，请先处理合同后再标记输单'

function track(wrapper: VueWrapper): VueWrapper {
  mountedWrappers.push(wrapper)
  return wrapper
}

afterEach(() => {
  mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})

describe('table row action disabled reasons', () => {
  it('keeps a desktop disabled loss item readable and non-executable', async () => {
    const handler = vi.fn()
    const action: ActionConfig = {
      id: 'lose',
      label: '输单',
      handler,
      disabled: true,
      disabledReason,
      destructive: true
    }
    const wrapper = track(mount(DesktopTableRowActions, {
      props: {
        row: { id: 1 },
        actions: {
          primaryActions: [{ label: '编辑', handler: vi.fn(), desktopPrimary: true }],
          secondaryActions: [action]
        }
      },
      attachTo: document.body
    }))

    await wrapper.get('[aria-label="更多操作"]').trigger('click')
    await flushPromises()

    const item = Array.from(document.querySelectorAll('[role="menuitem"]'))
      .find((element) => element.textContent?.includes('输单') === true)
    expect(item).toBeDefined()
    expect(item?.textContent).toContain(disabledReason)
    expect(item?.getAttribute('aria-disabled')).toBe('true')
    expect(item?.hasAttribute('data-disabled')).toBe(false)

    item?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    item?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await flushPromises()

    expect(handler).not.toHaveBeenCalled()
  })

  it('keeps a mobile disabled loss item readable and non-executable', async () => {
    const handler = vi.fn()
    const wrapper = track(mount(TableRowActions, {
      props: {
        row: { id: 1 },
        primaryActions: [{ label: '编辑', handler: vi.fn() }],
        secondaryActions: [{
          id: 'lose',
          label: '输单',
          handler,
          disabled: true,
          disabledReason,
          destructive: true
        }]
      },
      attachTo: document.body
    }))

    await wrapper.get('[aria-label="更多操作"]').trigger('click')
    await flushPromises()

    const item = Array.from(document.querySelectorAll('[role="menuitem"]'))
      .find((element) => element.textContent?.includes('输单') === true)
    expect(item).toBeDefined()
    expect(item?.textContent).toContain(disabledReason)
    expect(item?.getAttribute('aria-disabled')).toBe('true')
    expect(item?.hasAttribute('data-disabled')).toBe(false)

    item?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    item?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await flushPromises()

    expect(handler).not.toHaveBeenCalled()
  })
})
