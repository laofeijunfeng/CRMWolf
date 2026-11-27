import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentUIProcessBlock from '@/components/agent-ui/AgentUIProcessBlock.vue'
import type { ProcessBlock } from '@/components/agent-ui/agentUIProcess'

const makeBlock = (overrides: Partial<ProcessBlock> = {}): ProcessBlock => ({
  id: 'proc_1',
  type: 'process',
  title: '执行过程',
  items: [
    { key: 'classify', title: '判断活动类型', status: 'COMPLETED' },
    {
      key: 'organize',
      title: '整理活动内容',
      status: 'RUNNING',
      description: '正在抽取客户沟通要点与后续待办。',
    },
  ],
  ...overrides,
})

describe('AgentUIProcessBlock', () => {
  it('auto-opens while running and auto-collapses once finished when user has not toggled', async () => {
    const wrapper = mount(AgentUIProcessBlock, {
      props: { block: makeBlock(), running: true, episodeKey: 'ep-1' },
    })
    const headerTrigger = wrapper.get('button')
    expect(headerTrigger.attributes('aria-expanded')).toBe('true')

    await wrapper.setProps({
      running: false,
      block: makeBlock({
        items: [
          { key: 'classify', title: '判断活动类型', status: 'COMPLETED' },
          { key: 'organize', title: '整理活动内容', status: 'COMPLETED' },
        ],
      }),
    })

    expect(headerTrigger.attributes('aria-expanded')).toBe('false')
  })

  it('respects user manual override within an episode and resets when episodeKey changes', async () => {
    const wrapper = mount(AgentUIProcessBlock, {
      props: { block: makeBlock(), running: true, episodeKey: 'ep-1' },
    })
    const headerTrigger = wrapper.get('button')
    expect(headerTrigger.attributes('aria-expanded')).toBe('true')

    // User manually collapses while running; subsequent step updates must not re-open it.
    await headerTrigger.trigger('click')
    expect(headerTrigger.attributes('aria-expanded')).toBe('false')

    await wrapper.setProps({
      block: makeBlock({
        items: [
          { key: 'classify', title: '判断活动类型', status: 'COMPLETED' },
          { key: 'organize', title: '整理活动内容', status: 'COMPLETED' },
          { key: 'evaluate', title: '评估记录质量', status: 'RUNNING' },
        ],
      }),
    })
    expect(headerTrigger.attributes('aria-expanded')).toBe('false')

    // User manually expands while running; finishing must not force-collapse it.
    await headerTrigger.trigger('click')
    expect(headerTrigger.attributes('aria-expanded')).toBe('true')

    await wrapper.setProps({ running: false })
    expect(headerTrigger.attributes('aria-expanded')).toBe('true')

    // New episode resets user override back to automatic policy.
    await wrapper.setProps({ episodeKey: 'ep-2', running: false })
    expect(headerTrigger.attributes('aria-expanded')).toBe('false')

    await wrapper.setProps({ episodeKey: 'ep-3', running: true })
    expect(headerTrigger.attributes('aria-expanded')).toBe('true')
  })

  it('applies text-shimmer only to RUNNING step titles and toggles per-step description disclosure', async () => {
    const wrapper = mount(AgentUIProcessBlock, {
      props: { block: makeBlock(), running: true, episodeKey: 'ep-1' },
    })

    const rows = wrapper.findAll('ol > li')
    expect(rows).toHaveLength(2)

    // Step without description is static text (no nested button) and not shimmering.
    const staticRow = rows[0]!
    expect(staticRow.find('button').exists()).toBe(false)
    expect(staticRow.find('.text-shimmer').exists()).toBe(false)

    // Step with description has shimmering title when RUNNING and nested collapsible trigger.
    const detailRow = rows[1]!
    const shimmer = detailRow.find('.text-shimmer')
    expect(shimmer.exists()).toBe(true)
    expect(shimmer.text()).toBe('整理活动内容')

    const stepTrigger = detailRow.get('button')
    expect(stepTrigger.attributes('aria-expanded')).toBe('false')
    const detailPanel = detailRow.get('p').element.closest('[data-state]')
    expect(detailPanel?.getAttribute('data-state')).toBe('closed')

    await stepTrigger.trigger('click')
    expect(stepTrigger.attributes('aria-expanded')).toBe('true')
    expect(detailPanel?.getAttribute('data-state')).toBe('open')
    expect(detailRow.text()).toContain('正在抽取客户沟通要点与后续待办。')
  })
})
