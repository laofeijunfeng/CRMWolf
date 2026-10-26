import { mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import JourneyStyleBoardView, { type JourneyBoardColumn } from '../JourneyStyleBoardView.vue'

const columns: JourneyBoardColumn[] = [
  {
    key: 'following',
    label: '跟进中',
    tone: 'info',
    countLabel: '2',
    cards: [
      { id: 'cus_1', context: '方案沟通', title: '星河科技', owner: '王敏' },
      { id: 'cus_2', context: '', title: '  ', owner: '' },
    ],
  },
  {
    key: 'lost',
    label: '已流失',
    tone: 'danger',
    countLabel: '0',
    cards: [],
  },
]

function mountBoard(props: Record<string, unknown> = {}): VueWrapper {
  return mount(JourneyStyleBoardView, {
    props: {
      columns,
      loading: false,
      refreshing: false,
      stale: false,
      error: null,
      ...props,
    },
  })
}

describe('JourneyStyleBoardView', () => {
  it('shows only the stage line, name, and owner, and keeps an empty column', async () => {
    const wrapper = mountBoard()
    const following = wrapper.get('[data-column-key="following"]')
    const card = following.get('[role="button"]')

    expect(following.text()).toContain('跟进中')
    expect(following.text()).toContain('2')
    expect(following.text()).not.toContain('信息')
    expect(card.text()).toContain('方案沟通')
    expect(card.text()).toContain('星河科技')
    expect(card.text()).toContain('王敏')
    expect(following.text()).not.toContain('查看全部')
    expect(following.text()).not.toContain('选择状态')
    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.get('[data-column-key="lost"]').text()).toContain('暂无记录')

    const blank = following.findAll('[role="button"]')[1]
    expect(blank).toBeDefined()
    expect(blank?.text()).toContain('-')
    expect(blank?.text()).not.toContain('行业')

    await card.trigger('keydown', { key: 'Enter' })
    await card.trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('activate-card')).toEqual([
      [{ id: 'cus_1', columnKey: 'following' }],
      [{ id: 'cus_1', columnKey: 'following' }],
    ])
  })

  it('shows the last successful cards when refresh fails and retries', async () => {
    const wrapper = mountBoard({
      stale: true,
      error: new Error('刷新失败'),
    })

    expect(wrapper.text()).toContain('星河科技')
    expect(wrapper.text()).toContain('数据已过期')
    await wrapper.get('[data-testid="board-inline-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('blocks the first load until retry and shows a skeleton while loading', async () => {
    const loading = mountBoard({ columns: null, loading: true })
    expect(loading.find('[data-testid="board-skeleton"]').exists()).toBe(true)
    loading.unmount()

    const failed = mountBoard({
      columns: null,
      loading: false,
      error: new Error('看板加载失败'),
    })
    expect(failed.text()).toContain('看板加载失败')
    expect(failed.find('[data-column-key="following"]').exists()).toBe(false)
    await failed.get('[data-testid="board-blocking-retry"]').trigger('click')
    expect(failed.emitted('retry')).toHaveLength(1)
  })
})
