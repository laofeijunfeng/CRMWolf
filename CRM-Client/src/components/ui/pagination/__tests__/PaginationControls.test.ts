import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { Pagination, PaginationContent, PaginationItem } from '..'
import PaginationNext from '../PaginationNext.vue'
import PaginationPrevious from '../PaginationPrevious.vue'

const clickEvent = (): MouseEvent => new MouseEvent('click', { bubbles: true, cancelable: true })

describe('controlled pagination element contracts', () => {
  it('renders native type=button controls that do not submit forms', async () => {
    const submit = vi.fn()
    const update = vi.fn()
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationItem, PaginationNext, PaginationPrevious },
      setup: () => ({ submit, update }),
      template: `
        <form @submit.prevent="submit">
          <Pagination :page="2" :items-per-page="10" :total="30" @update:page="update">
            <PaginationContent>
              <PaginationPrevious />
              <PaginationItem :value="3">3</PaginationItem>
              <PaginationNext />
            </PaginationContent>
          </Pagination>
        </form>
      `
    })
    for (const button of wrapper.findAll('button')) {
      expect(button.attributes('type')).toBe('button')
      await button.trigger('click')
    }
    expect(submit).not.toHaveBeenCalled()
  })

  it('derives current, selected, and disabled state from the root page', async () => {
    const Host = defineComponent({
      components: { Pagination, PaginationContent, PaginationItem },
      setup: () => ({ page: ref(1) }),
      template: `
        <Pagination v-model:page="page" :items-per-page="10" :total="30">
          <PaginationContent>
            <PaginationItem :value="1" data-testid="page-1">1</PaginationItem>
            <PaginationItem :value="2" data-testid="page-2">2</PaginationItem>
          </PaginationContent>
        </Pagination>
      `
    })
    const wrapper = mount(Host)
    expect(wrapper.get('[data-testid="page-1"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('[data-testid="page-1"]').attributes('data-selected')).toBe('true')
    expect(wrapper.get('[data-testid="page-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="page-2"]').attributes('aria-current')).toBeUndefined()

    await wrapper.get('[data-testid="page-2"]').trigger('click')
    expect(wrapper.get('[data-testid="page-1"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.get('[data-testid="page-2"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('[data-testid="page-2"]').attributes('disabled')).toBeDefined()
  })

  it.each([-1, 0, 4])('disables out-of-range item %s without updates', async value => {
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

  it('prevents critical attr overrides while forwarding safe attrs', () => {
    const wrapper = mount({
      components: { Pagination, PaginationContent, PaginationItem },
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30">
          <PaginationContent>
            <PaginationItem
              :value="1"
              id="safe-id"
              data-testid="current-page"
              type="submit"
              :disabled="false"
              aria-disabled="false"
              tabindex="0"
              aria-current="false"
            >1</PaginationItem>
          </PaginationContent>
        </Pagination>
      `
    })
    const button = wrapper.get('[data-testid="current-page"]')
    expect(button.attributes('id')).toBe('safe-id')
    expect(button.attributes('type')).toBe('button')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-disabled')).toBeUndefined()
    expect(button.attributes('tabindex')).toBeUndefined()
    expect(button.attributes('aria-current')).toBe('page')
  })

  it('supports a controlled anchor branch without asChild merging', () => {
    const enabledUpdate = vi.fn()
    const enabledWrapper = mount({
      components: { Pagination, PaginationContent, PaginationNext },
      setup: () => ({ enabledUpdate }),
      template: `
        <Pagination :page="1" :items-per-page="10" :total="30" @update:page="enabledUpdate">
          <PaginationContent><PaginationNext as="a" href="#next" data-testid="next-link" /></PaginationContent>
        </Pagination>
      `
    })
    const enabledLink = enabledWrapper.get('[data-testid="next-link"]')
    const enabledEvent = clickEvent()
    enabledLink.element.dispatchEvent(enabledEvent)
    expect(enabledEvent.defaultPrevented).toBe(false)
    expect(enabledUpdate).toHaveBeenCalledTimes(1)

    const disabledUpdate = vi.fn()
    const disabledWrapper = mount({
      components: { Pagination, PaginationContent, PaginationNext },
      setup: () => ({ disabledUpdate }),
      template: `
        <Pagination :page="3" :items-per-page="10" :total="30" @update:page="disabledUpdate">
          <PaginationContent><PaginationNext as="a" href="#next" data-testid="next-link" /></PaginationContent>
        </Pagination>
      `
    })
    const disabledLink = disabledWrapper.get('[data-testid="next-link"]')
    expect(disabledLink.attributes('aria-disabled')).toBe('true')
    expect(disabledLink.attributes('tabindex')).toBe('-1')
    const disabledEvent = clickEvent()
    disabledLink.element.dispatchEvent(disabledEvent)
    expect(disabledEvent.defaultPrevented).toBe(true)
    expect(disabledUpdate).not.toHaveBeenCalled()
  })
})
