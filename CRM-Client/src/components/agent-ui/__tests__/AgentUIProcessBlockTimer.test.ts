import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AgentUIProcessBlock from '../AgentUIProcessBlock.vue'
import type { ProcessBlock } from '../agentUIProcess'

const block: ProcessBlock = {
  id: 'live-process',
  type: 'process',
  title: '执行过程',
  items: [{ key: 'understand', title: '理解业务操作', status: 'RUNNING' }],
}

const STARTED_AT = '2026-11-28T08:00:00.000Z'

describe('AgentUIProcessBlock 运行计时', () => {
  let wrapper: VueWrapper | null = null

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(Date.parse(STARTED_AT) + 4_200))
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  const elapsedText = (): string => wrapper?.get('[data-agent-ui-elapsed]').text() ?? ''

  it('运行中按秒推进等宽经过时间，运行结束后停止并移除', async () => {
    wrapper = mount(AgentUIProcessBlock, { props: { block, running: true, stepStartedAt: STARTED_AT } })

    const elapsed = wrapper.get('[data-agent-ui-elapsed]')
    expect(elapsed.classes()).toContain('tabular-nums')
    expect(elapsedText()).toBe('4s')

    await vi.advanceTimersByTimeAsync(1_000)
    expect(elapsedText()).toBe('5s')
    await vi.advanceTimersByTimeAsync(1_000)
    expect(elapsedText()).toBe('6s')

    await wrapper.setProps({ running: false })
    expect(wrapper.find('[data-agent-ui-elapsed]').exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(3_000)
    expect(wrapper.find('[data-agent-ui-elapsed]').exists()).toBe(false)
  })

  it('卸载时清除运行计时器', () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval')
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval')
    wrapper = mount(AgentUIProcessBlock, { props: { block, running: true, stepStartedAt: STARTED_AT } })
    // jsdom 的 requestAnimationFrame 也走 setInterval；只看每秒一次的经过时间计时器。
    const tickerIds = setIntervalSpy.mock.calls.flatMap((call, index): unknown[] => {
      const id: unknown = setIntervalSpy.mock.results[index]?.value
      return call[1] === 1_000 ? [id] : []
    })
    expect(tickerIds).toHaveLength(1)

    wrapper.unmount()
    wrapper = null
    const clearedIds = clearIntervalSpy.mock.calls.map(([id]) => id)
    expect(clearedIds).toContain(tickerIds[0])
  })
})
