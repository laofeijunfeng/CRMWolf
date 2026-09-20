import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import BusinessJourneyBoardView from '@/components/business-journey/BusinessJourneyBoardView.vue'

const journeyPublicId = `djy_${'a'.repeat(32)}`
const board = {
  columns: [{
    key: 'active_progress' as const,
    title: '积极推进',
    description: '持续推进中的旅程',
    count: 1,
    amount: 168000,
    cards: [{
      public_id: journeyPublicId,
      journey_name: '华东续约旅程',
      customer_id: `cus_${'c'.repeat(32)}`,
      customer_name: '示例科技',
      owner: { id: '7', name: '王小明', avatar_url: null },
      status: 'ACTIVE',
      current_board_stage: 'active_progress' as const,
      started_at: '2026-09-01T09:00:00',
      closed_at: null,
      last_event_at: '2026-09-10T12:00:00',
      last_event_summary: '完成方案确认',
      amount: 168000,
      primary_opportunity: {
        public_id: `opp_${'b'.repeat(32)}`,
        opportunity_name: '华东续约商机',
        amount: 168000,
        actual_amount: null,
        status: 1,
        current_stage_name: '方案确认',
        win_probability: 70,
        expected_closing_date: '2026-10-31',
      },
      contract_summary: { count: 1, signed_count: 0, amount: 168000 },
      payment_summary: {
        plan_count: 1,
        record_count: 0,
        planned_amount: 168000,
        paid_amount: 0,
        remaining_amount: 168000,
      },
      invoice_summary: {
        application_count: 0,
        issued_count: 0,
        applied_amount: 0,
        issued_amount: 0,
      },
    }],
  }],
  summary: {
    total_count: 1,
    total_amount: 168000,
    active_count: 1,
    completed_count: 0,
    lost_count: 0,
  },
  truncated: false,
}


function mountBoard(props: Record<string, unknown> = {}) {
  return mount(BusinessJourneyBoardView, {
    props: {
      board,
      loading: false,
      errorMessage: '',
      ...props,
    },
  })
}

describe('BusinessJourneyBoardView', () => {
  it('preserves stage palette classes and age tones', () => {
    vi.setSystemTime(new Date('2026-09-21T12:00:00'))
    const wrapper = mountBoard()

    expect(wrapper.get('.business-board-column').classes()).toContain('business-board-stage--blue')
    expect(wrapper.get('.journey-age').text()).toBe('11天')
    expect(wrapper.get('.journey-age').classes()).toEqual(expect.arrayContaining([
      'bg-yellow-50',
      'text-yellow-700',
      'border-yellow-100',
    ]))
    vi.useRealTimers()
  })

  it('renders the unchanged initial skeleton', () => {
    const wrapper = mountBoard({ board: null, loading: true })

    expect(wrapper.get('[aria-label="旅程看板加载中"]').findAll('.business-board-column')).toHaveLength(5)
  })

  it('shows stale refresh state without replacing the successful board', () => {
    const wrapper = mountBoard({
      loading: true,
      errorMessage: '旅程看板刷新失败，当前显示上次成功加载的数据',
    })

    expect(wrapper.text()).toContain('旅程看板刷新失败，当前显示上次成功加载的数据')
    expect(wrapper.text()).toContain('正在刷新，当前显示上次成功加载的数据')
    expect(wrapper.find('.journey-card').exists()).toBe(true)
  })

  it('shows a blocking error only when no board data exists', async () => {
    const wrapper = mountBoard({
      board: null,
      errorMessage: '旅程看板加载失败，请重试',
    })

    expect(wrapper.get('.business-board-blocking-error').text()).toContain('旅程看板加载失败，请重试')
    await wrapper.get('.business-board-blocking-error button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('emits public journey identity from pointer and keyboard row clicks', async () => {
    const wrapper = mountBoard()
    const card = wrapper.get('.journey-card')
    const payload = {
      customerId: board.columns[0].cards[0].customer_id,
      journeyPublicId,
    }
    expect(card.attributes('aria-label')).toBe('查看业务旅程：华东续约旅程')


    await card.trigger('click')
    await card.trigger('keydown', { key: 'Enter' })
    await card.trigger('keydown', { key: ' ' })

    expect(wrapper.emitted('row-click')).toEqual([[payload], [payload], [payload]])
  })
})
