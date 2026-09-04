import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ConfirmDialog from '@/components/crmwolf/ConfirmDialog.vue'
import { createConfirmDialog } from '@/utils/confirmDialogImpl'

describe('ConfirmDialog', () => {
  it('resolves true when the confirm action is clicked', async () => {
    const wrapper = mount(ConfirmDialog, { attachTo: document.body })
    const resultPromise = createConfirmDialog({
      title: '确认完成',
      message: '确认完成这条客户追踪吗？',
      confirmText: '确定',
      cancelText: '取消',
      variant: 'default',
    })
    await flushPromises()

    const buttons = Array.from(document.querySelectorAll('button'))
    expect(buttons.map((button) => button.textContent)).toContain('确定')
    const confirmButton = buttons.find((button) => button.textContent === '确定')
    expect(confirmButton).toBeDefined()
    confirmButton?.click()
    await flushPromises()

    await expect(resultPromise).resolves.toBe(true)
    wrapper.unmount()
  })
})
