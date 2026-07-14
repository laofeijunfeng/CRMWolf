import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { Pagination, PaginationContent } from '..'
import PaginationNext from '../PaginationNext.vue'
import PaginationPrevious from '../PaginationPrevious.vue'

const mountControl = (component: typeof PaginationNext, page: number): VueWrapper => mount({
  components: { Pagination, PaginationContent, Control: component },
  template: `
    <Pagination :page="${page}" :items-per-page="10" :total="30">
      <PaginationContent>
        <Control />
      </PaginationContent>
    </Pagination>
  `
})

describe('localized pagination controls', () => {
  it('renders a Chinese accessible name for the previous button', () => {
    const wrapper = mountControl(PaginationPrevious, 2)
    expect(wrapper.get('button').attributes('aria-label')).toBe('上一页')
  })

  it('renders a Chinese accessible name for the next button', () => {
    const wrapper = mountControl(PaginationNext, 2)
    expect(wrapper.get('button').attributes('aria-label')).toBe('下一页')
  })
})
