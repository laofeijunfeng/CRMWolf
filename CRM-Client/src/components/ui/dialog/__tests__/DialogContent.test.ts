import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '..'

const getCloseButton = (): HTMLButtonElement => {
  const close = document.body.querySelector<HTMLButtonElement>('[aria-label="关闭"]')
  if (close === null) throw new Error('Dialog close button not found')
  return close
}

afterEach(() => {
  document.body.innerHTML = ''
})

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
  it('follows compact shadcn-vue close control placement with an accessible name', async () => {
    const wrapper = mountOpenDialog()
    await nextTick()
    const close = getCloseButton()
    expect(close.classList.contains('right-4')).toBe(true)
    expect(close.classList.contains('top-4')).toBe(true)
    wrapper.unmount()
  })

  it('keeps the native dialog close behavior', async () => {
    const wrapper = mountOpenDialog()
    await nextTick()
    getCloseButton().click()
    await nextTick()
    expect((wrapper.vm as unknown as { open: boolean }).open).toBe(false)
    wrapper.unmount()
  })
})

describe('DialogContent size', () => {
  const mountSized = (attrs: string): VueWrapper => mount({
    components: { Dialog, DialogContent, DialogTitle },
    template: `<Dialog :open="true"><DialogContent ${attrs}><DialogTitle>t</DialogTitle></DialogContent></Dialog>`,
    attachTo: document.body
  })
  const contentClasses = (): DOMTokenList => {
    const el = document.body.querySelector('[role="dialog"]')
    if (el === null) throw new Error('Dialog content not found')
    return el.classList
  }

  it('defaults to the md width tier and honours an explicit size', async () => {
    const md = mountSized('')
    await nextTick()
    expect(contentClasses().contains('max-w-[var(--dialog-w-md)]')).toBe(true)
    md.unmount()
    document.body.innerHTML = ''

    const lg = mountSized('size="lg"')
    await nextTick()
    expect(contentClasses().contains('max-w-[var(--dialog-w-lg)]')).toBe(true)
    expect(contentClasses().contains('max-w-[var(--dialog-w-md)]')).toBe(false)
    lg.unmount()
  })

  it('lets an explicit max-w-none override the tier (maximized preview)', async () => {
    const w = mountSized('size="full" class="max-w-none"')
    await nextTick()
    expect(contentClasses().contains('max-w-none')).toBe(true)
    expect(contentClasses().contains('max-w-[var(--dialog-w-full)]')).toBe(false)
    w.unmount()
  })
})
