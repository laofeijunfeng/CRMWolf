import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DataTableExportDialog from '../DataTableExportDialog.vue'
import type { DataTableExportDialogField } from '../DataTableExportDialog.vue'

const fields: DataTableExportDialogField[] = [
  { fieldKey: 'name', key: 'name', label: '名称', source: 'column', visible: true },
  { fieldKey: 'owner', key: 'owner', label: '负责人', source: 'column', visible: false },
  { fieldKey: 'public_id', key: 'public_id', label: '业务 ID', source: 'export-only', visible: false },
]

const mounted: VueWrapper[] = []

function mountDialog(
  exportHandler: (fieldKeys: string[]) => Promise<void>,
  total = 76
): VueWrapper {
  const wrapper = mount(DataTableExportDialog, {
    props: { fields, total, title: '客户列表', exportHandler },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  return wrapper
}

async function openDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.get('button').trigger('click')
  await flushPromises()
}

function dialogField(key: string): Element | undefined {
  return Array.from(document.body.querySelectorAll('.data-table-export-field'))
    .find((node) => node.getAttribute('data-field-key') === key)
}

async function toggleField(key: string): Promise<void> {
  const checkbox = dialogField(key)?.querySelector('[role="checkbox"]')
  if (checkbox === undefined || !(checkbox instanceof HTMLElement)) {
    throw new Error(`export field not rendered: ${key}`)
  }
  checkbox.click()
  await flushPromises()
}

function selectedKeys(): string[] {
  return Array.from(document.body.querySelectorAll('.data-table-export-field'))
    .filter((node) => node.querySelector('[role="checkbox"]')?.getAttribute('data-state') === 'checked')
    .map((node) => node.getAttribute('data-field-key') as string)
}

async function clickDialogButton(testId: string): Promise<void> {
  const button = document.body.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)
  if (button === null) throw new Error(`dialog button not found: ${testId}`)
  button.click()
  await flushPromises()
}

describe('DataTableExportDialog', () => {
  afterEach(() => {
    while (mounted.length > 0) mounted.pop()?.unmount()
  })

  it('selects visible fields by default and leaves hidden and export-only unchecked', async () => {
    const wrapper = mountDialog(vi.fn(async () => undefined))
    await openDialog(wrapper)

    expect(selectedKeys()).toEqual(['name'])
    expect(dialogField('owner')).toBeDefined()
    expect(dialogField('public_id')).toBeDefined()
  })

  it('passes public_id first and closes only after the handler resolves', async () => {
    let resolveHandler: (() => void) | undefined
    const exportHandler = vi.fn(() => new Promise<void>((resolve) => { resolveHandler = resolve }))
    const wrapper = mountDialog(exportHandler)
    await openDialog(wrapper)

    await toggleField('public_id')
    await clickDialogButton('data-table-export-submit')
    expect(exportHandler).toHaveBeenCalledTimes(1)
    expect(exportHandler).toHaveBeenCalledWith(['public_id', 'name'])

    resolveHandler?.()
    await flushPromises()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
  })

  it('blocks duplicate submissions while the handler is pending', async () => {
    const exportHandler = vi.fn(() => new Promise<void>(() => undefined))
    const wrapper = mountDialog(exportHandler)
    await openDialog(wrapper)

    await clickDialogButton('data-table-export-submit')
    await clickDialogButton('data-table-export-submit')
    expect(exportHandler).toHaveBeenCalledTimes(1)
  })

  it('keeps the dialog and selections when the handler rejects', async () => {
    const exportHandler = vi.fn(() => Promise.reject(new Error('boom')))
    const wrapper = mountDialog(exportHandler)
    await openDialog(wrapper)

    await toggleField('owner')
    await clickDialogButton('data-table-export-submit')

    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
    expect(selectedKeys()).toEqual(['name', 'owner'])
  })

  it('disables submit when the filtered total is zero', async () => {
    const wrapper = mountDialog(vi.fn(async () => undefined), 0)
    await openDialog(wrapper)

    const submit = document.body.querySelector<HTMLButtonElement>('[data-testid="data-table-export-submit"]')
    expect(submit?.disabled).toBe(true)
  })

  it('discards temporary selections after close and reopen', async () => {
    const wrapper = mountDialog(vi.fn(async () => undefined))
    await openDialog(wrapper)

    await toggleField('public_id')
    await clickDialogButton('data-table-export-cancel')
    await openDialog(wrapper)

    expect(selectedKeys()).toEqual(['name'])
  })
})
