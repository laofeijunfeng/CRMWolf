import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { Pagination, PaginationContent, PaginationItem } from '..'
import PaginationNext from '../PaginationNext.vue'
import PaginationPrevious from '../PaginationPrevious.vue'

const mountControl = (
  component: typeof PaginationNext,
  page: number,
  controlTemplate = '<Control />'
): VueWrapper => mount({
  components: { Pagination, PaginationContent, Control: component },
  template: `
    <Pagination :page="${page}" :items-per-page="10" :total="30">
      <PaginationContent>
        ${controlTemplate}
      </PaginationContent>
    </Pagination>
  `
})

describe('localized pagination controls', () => {
  it('renders Chinese accessible names for native previous and next buttons', () => {
    expect(mountControl(PaginationPrevious, 2).get('button').attributes('aria-label')).toBe('上一页')
    expect(mountControl(PaginationNext, 2).get('button').attributes('aria-label')).toBe('下一页')
  })

  it('renders a localized page number and preserves the active contract', () => {
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationItem },
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30">
          <PaginationContent>
            <PaginationItem :value="1" :is-active="true">1</PaginationItem>
          </PaginationContent>
        </Pagination>
      `
    })
    const button = wrapper.get('button')
    expect(button.attributes('aria-label')).toBe('第 1 页')
    expect(button.attributes('aria-current')).toBe('page')
    expect(button.attributes('type')).toBe('button')
  })

  it('supports asChild with a custom child and emits one page update', async () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationNext },
      setup: () => ({ update }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent>
            <PaginationNext as-child>
              <a href="#next">下一页链接</a>
            </PaginationNext>
          </PaginationContent>
        </Pagination>
      `
    })
    const link = wrapper.get('a')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(link.attributes('aria-label')).toBe('下一页')
    expect(link.attributes('type')).toBeUndefined()
    await link.trigger('click')
    expect(update).toHaveBeenCalledTimes(1)
    expect(update).toHaveBeenCalledWith(2)
  })

  it('preserves disabled behavior for native and asChild controls', async () => {
    const nativeUpdate = vi.fn()
    const nativeWrapper = mount({
      components: { Pagination, PaginationContent, PaginationPrevious },
      setup: () => ({ nativeUpdate }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="nativeUpdate">
          <PaginationContent><PaginationPrevious /></PaginationContent>
        </Pagination>
      `
    })
    expect(nativeWrapper.get('button').attributes('disabled')).toBeDefined()
    await nativeWrapper.get('button').trigger('click')
    expect(nativeUpdate).not.toHaveBeenCalled()

    const childUpdate = vi.fn()
    const childWrapper = mount({
      components: { Pagination, PaginationContent, PaginationNext },
      setup: () => ({ childUpdate }),
      template: `
        <Pagination :page="3" :items-per-page="10" :total="30" @update:page="childUpdate">
          <PaginationContent>
            <PaginationNext as-child><a href="#next">下一页链接</a></PaginationNext>
          </PaginationContent>
        </Pagination>
      `
    })
    expect(childWrapper.get('a').attributes('aria-disabled')).toBe('true')
    await childWrapper.get('a').trigger('click')
    expect(childUpdate).not.toHaveBeenCalled()
  })
})
