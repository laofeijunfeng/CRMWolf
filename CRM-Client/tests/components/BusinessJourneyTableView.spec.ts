import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BusinessJourneyTableView from '@/components/business-journey/BusinessJourneyTableView.vue'

describe('BusinessJourneyTableView layout', () => {
  it('renders the standard list-page table height', () => {
    const wrapper = mount(BusinessJourneyTableView, {
      props: {
        fields: [],
        data: [],
        total: 0,
        page: 1,
        pageSize: 20,
        filters: [],
        sorts: [],
        columns: [],
        search: '',
        displayMode: 'table',
      },
    })

    const card = wrapper.get('.data-table-card')
    const content = wrapper.get('.data-table-content')

    expect((card.element as HTMLElement).style.height).toBe('calc(100vh - 121px)')
    expect(card.classes()).toContain('data-table-card--fill')
    expect(content.classes()).toContain('data-table-content--contained')
  })
})
