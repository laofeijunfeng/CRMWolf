import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { Pagination, PaginationContent, PaginationItem } from '..'
import PaginationNext from '../PaginationNext.vue'
import PaginationPrevious from '../PaginationPrevious.vue'

const clickEvent = (): MouseEvent => new MouseEvent('click', {
  bubbles: true,
  cancelable: true
})

describe('pagination rendered-element contracts', () => {
  it('renders localized native buttons and native disabled state', async () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationPrevious },
      setup: () => ({ update }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent><PaginationPrevious /></PaginationContent>
        </Pagination>
      `
    })
    const button = wrapper.get('button')
    expect(button.attributes('aria-label')).toBe('上一页')
    expect(button.attributes('type')).toBe('button')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    expect(update).not.toHaveBeenCalled()
  })

  it('renders a localized active page and does not emit a redundant update', async () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationItem },
      setup: () => ({ update }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent>
            <PaginationItem :value="1" :is-active="true">1</PaginationItem>
          </PaginationContent>
        </Pagination>
      `
    })
    const button = wrapper.get('button')
    expect(button.attributes('aria-label')).toBe('第 1 页')
    expect(button.attributes('aria-current')).toBe('page')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    expect(update).not.toHaveBeenCalled()
  })

  it.each([-1, 0, 4])('disables out-of-range page value %s', async value => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationItem },
      setup: () => ({ update, value }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent><PaginationItem :value="value">{{ value }}</PaginationItem></PaginationContent>
        </Pagination>
      `
    })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.get('button').trigger('click')
    expect(update).not.toHaveBeenCalled()
  })

  it('respects root disabled for a valid page item', async () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationItem },
      setup: () => ({ update }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" disabled @update:page="update">
          <PaginationContent><PaginationItem :value="2">2</PaginationItem></PaginationContent>
        </Pagination>
      `
    })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.get('button').trigger('click')
    expect(update).not.toHaveBeenCalled()
  })

  it('supports enabled asChild anchors with one update and no disabled attrs', () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationNext },
      setup: () => ({ update }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent>
            <PaginationNext as-child><a href="#next">下一页链接</a></PaginationNext>
          </PaginationContent>
        </Pagination>
      `
    })
    const link = wrapper.get('a')
    expect(link.attributes('aria-disabled')).toBeUndefined()
    expect(link.attributes('tabindex')).toBeUndefined()
    const event = clickEvent()
    link.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(update).toHaveBeenCalledTimes(1)
    expect(update).toHaveBeenCalledWith(2)
  })

  it('prevents disabled asChild anchor navigation and removes it from tab order', () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationNext },
      setup: () => ({ update }),
      template: `
        <Pagination :page="3" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent>
            <PaginationNext as-child><a href="#next">下一页链接</a></PaginationNext>
          </PaginationContent>
        </Pagination>
      `
    })
    const link = wrapper.get('a')
    expect(link.attributes('aria-disabled')).toBe('true')
    expect(link.attributes('tabindex')).toBe('-1')
    const event = clickEvent()
    link.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(update).not.toHaveBeenCalled()
  })

  it('applies the same disabled contract to as="a" without a native disabled attribute', () => {
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationPrevious },
      setup: () => ({ update }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="update">
          <PaginationContent><PaginationPrevious as="a" href="#previous" /></PaginationContent>
        </Pagination>
      `
    })
    const link = wrapper.get('a')
    expect(link.attributes('disabled')).toBeUndefined()
    expect(link.attributes('aria-disabled')).toBe('true')
    expect(link.attributes('tabindex')).toBe('-1')
    const event = clickEvent()
    link.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(update).not.toHaveBeenCalled()
  })
})
