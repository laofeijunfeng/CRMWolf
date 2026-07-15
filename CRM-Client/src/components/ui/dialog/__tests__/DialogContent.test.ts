import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '..'

const getCloseButton = (): HTMLButtonElement => {
  const close = document.body.querySelector<HTMLButtonElement>('[aria-label="关闭"]')
  if (close === null) throw new Error('Dialog close button not found')
  return close
}

const mountOpenDialog = (): VueWrapper => mount({
  components: { Dialog, DialogContent, DialogDescription, DialogTitle },
  setup: () => ({ open: ref(true) }),
  template: `
    <Dialog v-model:open="open">
      <DialogContent>
        <DialogTitle>测试弹窗</DialogTitle>
        <DialogDescription>测试说明</DialogDescription>
      </DialogContent>
    </Dialog>
  `,
  attachTo: document.body
})

describe('DialogContent close control', () => {
  it('provides a 44px close target with an accessible name', async () => {
    const wrapper = mountOpenDialog()
    await nextTick()
    const close = getCloseButton()
    expect(close.classList.contains('size-11')).toBe(true)
    expect(close.classList.contains('right-2')).toBe(true)
    expect(close.classList.contains('top-2')).toBe(true)
    wrapper.unmount()
  })

  it('keeps the native dialog close behavior', async () => {
    const wrapper = mountOpenDialog()
    await nextTick()
    getCloseButton().click()
    await nextTick()
    expect(wrapper.vm.open).toBe(false)
    wrapper.unmount()
  })
})
