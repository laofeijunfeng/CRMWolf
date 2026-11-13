import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import ChartBucketDialog from '../ChartBucketDialog.vue'
import ChartCardFrame from '../ChartCardFrame.vue'
import ChartPageShell from '../ChartPageShell.vue'

const wrappers: VueWrapper[] = []

function button(testId: string): HTMLButtonElement {
  const element = document.body.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)
  if (element === null) throw new Error(`Missing button: ${testId}`)
  return element
}

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
})

describe('ChartBucketDialog', () => {
  it('renders state slots and emits retry for initial errors', async () => {
    const wrapper = mount(ChartBucketDialog, {
      props: { open: true, title: 'Bucket details', description: 'Matching items', loading: true, testIdPrefix: 'bucket' },
      slots: { loading: '<p>Loading rows</p>', error: '<p>Failed rows</p>', empty: '<p>No rows</p>', items: '<p>Rows</p>' },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()
    expect(document.body.querySelector('[role="status"]')?.textContent).toBe('Loading rows')
    expect(document.body.textContent).not.toContain('Rows')

    await wrapper.setProps({ loading: false, error: 'Request failed' })
    expect(document.body.querySelector('[role="alert"]')?.textContent).toContain('Failed rows')
    button('bucket-retry').click()
    await nextTick()
    expect(wrapper.emitted('retry')).toEqual([[]])

    await wrapper.setProps({ error: null })
    expect(document.body.textContent).toContain('No rows')
    expect(document.body.querySelector('[data-testid="bucket-retry"]')).toBeNull()
  })

  it('retains items during pagination and disables load-more until loading finishes', async () => {
    const wrapper = mount(ChartBucketDialog, {
      props: { open: true, title: 'Bucket details', description: 'Matching items', hasItems: true, hasMore: true, testIdPrefix: 'bucket' },
      slots: { items: '<p>First row</p>', loading: '<p>Initial loading</p>', empty: '<p>Empty</p>' },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()
    button('bucket-load-more').click()
    await nextTick()
    expect(wrapper.emitted('load-more')).toEqual([[]])

    await wrapper.setProps({ loading: true })
    expect(document.body.textContent).toContain('First row')
    expect(document.body.textContent).not.toContain('Initial loading')
    expect(button('bucket-load-more').disabled).toBe(true)
    button('bucket-load-more').click()
    expect(wrapper.emitted('load-more')).toHaveLength(1)

    await wrapper.setProps({ loading: false, hasMore: false })
    expect(document.body.querySelector('[data-testid="bucket-load-more"]')).toBeNull()
  })

  it('requests controlled close and follows external open changes', async () => {
    const wrapper = mount(ChartBucketDialog, {
      props: { open: true, title: 'Bucket details', description: 'Matching items' },
      slots: { default: '<p>Custom body</p>', footer: '<p>Custom footer</p>' },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()
    expect(document.body.textContent).toContain('Custom body')
    expect(document.body.textContent).toContain('Custom footer')
    const close = document.body.querySelector<HTMLButtonElement>('[aria-label="关闭"]')
    if (close === null) throw new Error('Missing close button')
    close.click()
    await nextTick()
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    expect(wrapper.props('open')).toBe(true)

    await wrapper.setProps({ open: false })
    await nextTick()
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
  })

  it('returns focus to the external bucket action when Escape closes the dialog', async () => {
    const wrapper = mount({
      components: { ChartBucketDialog },
      setup: () => ({ open: ref(false) }),
      template: `<button type="button" data-testid="opener" @click="open = true">Open bucket</button>
        <ChartBucketDialog v-model:open="open" title="Bucket details" description="Matching items" />`,
    }, { attachTo: document.body })
    wrappers.push(wrapper)
    const opener = button('opener')
    opener.focus()
    opener.click()
    await nextTick()
    await nextTick()
    const close = document.body.querySelector<HTMLButtonElement>('[aria-label="关闭"]')
    if (close === null) throw new Error('Missing close button')
    close.focus()
    close.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    await nextTick()
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(opener)
  })

  it('resets local slot state when resetKey changes without closing the controlled dialog', async () => {
    const Editor = defineComponent({
      setup: () => ({ value: ref('') }),
      template: '<input aria-label="Local search" v-model="value" />',
    })
    const wrapper = mount(ChartBucketDialog, {
      props: { open: true, title: 'Bucket details', description: 'Matching items', resetKey: 'first' },
      slots: { default: Editor },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()
    const input = document.body.querySelector<HTMLInputElement>('input')
    if (input === null) throw new Error('Missing local search')
    input.value = 'stale search'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()

    await wrapper.setProps({ resetKey: 'second' })
    expect(document.body.querySelector<HTMLInputElement>('input')?.value).toBe('')
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('shows pagination errors while retaining loaded items', async () => {
    const wrapper = mount(ChartBucketDialog, {
      props: { open: true, title: 'Bucket details', description: 'Matching items', hasItems: true, hasMore: true, error: 'Page failed', testIdPrefix: 'bucket' },
      slots: { items: '<p>Loaded row</p>' },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await nextTick()
    expect(document.body.textContent).toContain('Loaded row')
    expect(document.body.querySelector('[role="alert"]')?.textContent).toContain('Page failed')
  })
})

describe('Chart page frames', () => {
  it('selects only the requested page-state slot and preserves ready-state slots', async () => {
    const wrapper = mount(ChartPageShell, {
      props: { state: 'loading', ariaLabel: 'Analysis' },
      slots: {
        loading: '<p>Loading</p>', error: '<p>Failed</p>', empty: '<p>Empty</p>',
        summary: '<h2>Summary</h2>', default: '<p>Chart</p>', 'inline-error': '<p>Refresh failed</p>',
        overlays: '<p>Overlay</p>',
      },
    })
    expect(wrapper.text()).toBe('LoadingOverlay')
    expect(wrapper.attributes('aria-label')).toBe('Analysis')
    await wrapper.setProps({ state: 'error' })
    expect(wrapper.text()).toBe('FailedOverlay')
    await wrapper.setProps({ state: 'empty' })
    expect(wrapper.text()).toBe('EmptyOverlay')
    await wrapper.setProps({ state: 'ready' })
    expect(wrapper.text()).toBe('SummaryRefresh failedChartOverlay')
    wrapper.unmount()
  })

  it('preserves card identity and renders direct default, legend and footer content', () => {
    const wrapper = mount(ChartCardFrame, {
      props: { cardKey: 'distribution', title: 'Distribution', description: 'Current scope', wide: true, testIdPrefix: 'analysis-card' },
      slots: { default: '<article>Chart content</article>', legend: '<p>Legend</p>', footer: '<p>Footnote</p>' },
    })
    expect(wrapper.attributes('data-testid')).toBe('analysis-card-distribution')
    expect(wrapper.text()).toBe('DistributionCurrent scopeChart contentLegendFootnote')
    wrapper.unmount()
  })
})
