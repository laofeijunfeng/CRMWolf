import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref, watch } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const listTurns = vi.hoisted(() => vi.fn())
const getTurn = vi.hoisted(() => vi.fn())
const handleApiError = vi.hoisted(() => vi.fn())
const toastSuccess = vi.hoisted(() => vi.fn())
const toastError = vi.hoisted(() => vi.fn())
const copyText = vi.hoisted(() => vi.fn())
const accessState = vi.hoisted(() => ({
  allowed: { value: true },
  unavailable: { value: false },
  pending: { value: false },
}))

vi.mock('@/api/agentRunLog', () => ({ agentRunLogApi: { listTurns, getTurn } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: () => undefined }))
vi.mock('@/composables/useSettingsAccess', () => {
  const allowed = ref(true)
  const unavailable = ref(false)
  const pending = ref(false)
  accessState.allowed = allowed
  accessState.unavailable = unavailable
  accessState.pending = pending
  return {
    useSettingsAccess: () => ({
      canAccess: () => allowed.value,
      permissionsUnavailable: unavailable,
      permissionsPending: pending,
    }),
  }
})
vi.mock('@/components/crmwolf', () => ({
  DataTable: defineComponent({
    name: 'DataTable',
    props: { fields: null, data: null, page: null, pageSize: null, total: null, rowKey: null, detailColumnKey: null, emptyReason: null, loadError: null, loading: null, search: null, rowInteractive: Boolean },
    emits: ['update:page', 'update:page-size', 'row-click', 'retry', 'filter-reset'],
    setup: (props, { emit, slots }) => () => h('section', { 'data-testid': 'run-log-table' }, [
      slots.tableTools?.(),
      props.data.length === 0 && props.emptyReason === 'filtered'
        ? h('button', { onClick: () => emit('filter-reset') }, '清除筛选') : null,
      props.loadError ? h('button', { onClick: () => emit('retry') }, '重试') : null,
      h('table', [h('tbody', props.data.map((row: { turn_id: string; user_text: string }, index: number) =>
        h('tr', { key: row.turn_id }, [h('td', [
          h('button', { 'aria-label': `查看${row.user_text}`, onClick: () => emit('row-click', row, index) }, row.user_text),
        ])]),
      ))]),
      h('div', { 'data-testid': 'mobile-cards' }, props.data.map((row: { turn_id: string }, index: number) =>
        h('div', { key: row.turn_id }, slots['mobile-card']?.({ row, index })),
      )),
      h('button', { onClick: () => emit('update:page', 2) }, '第 2 页'),
      h('button', { onClick: () => { emit('update:page-size', 50); emit('update:page', 1) } }, '50 条/页'),
    ]),
  }),
  DataTableSearch: defineComponent({
    name: 'DataTableSearch',
    props: ['modelValue'],
    emits: ['update:modelValue', 'search', 'clear'],
    setup: (props, { emit }) => {
      const draft = ref(props.modelValue)
      watch(() => props.modelValue, (value) => { draft.value = value })
      return () => h('form', { role: 'search', onSubmit: (event: Event) => {
        event.preventDefault()
        emit('update:modelValue', draft.value.trim())
        emit('search', draft.value.trim())
      } }, [
        h('input', { 'aria-label': '搜索日志', value: draft.value, onInput: (event: Event) => {
          draft.value = (event.target as HTMLInputElement).value
        } }),
        h('button', { type: 'submit' }, '搜索'),
        h('button', { type: 'button', onClick: () => { draft.value = ''; emit('update:modelValue', ''); emit('clear') } }, '清空搜索'),
      ])
    },
  }),
  SelectField: defineComponent({
    name: 'SelectField',
    props: ['modelValue', 'options', 'label'],
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('label', [props.label,
      h('select', { value: props.modelValue, onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value) },
        props.options.map((option: { value: string; label: string }) => h('option', { value: option.value }, option.label))),
    ]),
  }),
}))
vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'Sheet',
    props: ['open'],
    emits: ['update:open'],
    setup: (props, { emit, slots }) => () => props.open ? h('div', { role: 'dialog' }, [
      h('button', { 'aria-label': '关闭', onClick: () => emit('update:open', false) }, '关闭'),
      slots.default?.(),
    ]) : null,
  }),
  SheetHeader: defineComponent({ name: 'SheetHeader', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  SheetTitle: defineComponent({ name: 'SheetTitle', setup: (_, { slots }) => () => h('h2', slots.default?.()) }),
  SheetDescription: defineComponent({ name: 'SheetDescription', setup: (_, { slots }) => () => h('p', slots.default?.()) }),
}))
vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({ name: 'DetailSheetContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

import AgentRunLogSettings from '@/views/AgentRunLogSettings.vue'

const listItem = {
  turn_id: 'turn_blocked', user_id: 2, user_name: '销售李', user_text: '记双汇跟进',
  outcome: 'blocked_unwritten' as const, summary: '质量 52 分，拦住写入。',
  quality_score: 52, customer_name: '双汇', model: 'test-model', created_time: '2026-09-17T10:00:00',
}
const fullLog = '{\n  "turn_id": "turn_blocked",\n  "messages": [\n    {"role": "user", "content": "记双汇跟进；全文不是六步摘要"}\n  ]\n}'
const detail = { ...listItem, log: fullLog, steps: [
  { kind: 'model' as const, title: '判成「记跟进」', detail: 'route = WORKFLOW', tone: 'done' as const },
  { kind: 'code' as const, title: '匹配到客户「双汇」', detail: 'checkpoint 已有客户绑定', tone: 'done' as const },
  { kind: 'code' as const, title: '质量 52 分，拦住', detail: '阈值 60。', tone: 'blocked' as const },
  { kind: 'interaction' as const, title: '只问了一个补充问题', detail: '下一步由谁做什么', tone: 'blocked' as const },
  { kind: 'api' as const, title: '没有调创建', detail: 'create_customer_activity 未调用', tone: 'skipped' as const },
  { kind: 'background' as const, title: '没有整理 / 评分任务', detail: 'Agent 路径不创建 AIJob', tone: 'skipped' as const },
] }

function deferred<T>() {
  let resolve!: (value: T) => void
  return { promise: new Promise<T>((done) => { resolve = done }), resolve }
}

describe('AgentRunLogSettings', () => {
  beforeEach(() => {
    listTurns.mockReset()
    getTurn.mockReset()
    handleApiError.mockReset()
    toastSuccess.mockReset()
    toastError.mockReset()
    copyText.mockReset().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copyText } })
    accessState.allowed.value = true
    accessState.unavailable.value = false
    accessState.pending.value = false
    listTurns.mockResolvedValue({ items: [listItem], total: 60, page: 1, page_size: 20, total_pages: 3 })
    getTurn.mockResolvedValue(detail)
  })

  it('retains only committed search and outcome across server page and page-size changes', async () => {
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    expect(listTurns).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })

    await wrapper.get('input[aria-label="搜索日志"]').setValue(' 双汇 ')
    expect(listTurns).toHaveBeenCalledTimes(1)
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(listTurns).toHaveBeenLastCalledWith({ page: 1, page_size: 20, q: '双汇' })

    await wrapper.get('select').setValue('failed')
    await flushPromises()
    expect(listTurns).toHaveBeenLastCalledWith({ page: 1, page_size: 20, q: '双汇', outcome: 'failed' })

    await wrapper.get('input[aria-label="搜索日志"]').setValue('未提交草稿')
    await wrapper.findAll('button').find((button) => button.text() === '第 2 页')?.trigger('click')
    await flushPromises()
    expect(listTurns).toHaveBeenLastCalledWith({ page: 2, page_size: 20, q: '双汇', outcome: 'failed' })

    await wrapper.findAll('button').find((button) => button.text() === '50 条/页')?.trigger('click')
    await flushPromises()
    expect(listTurns).toHaveBeenLastCalledWith({ page: 1, page_size: 50, q: '双汇', outcome: 'failed' })
    expect(wrapper.getComponent({ name: 'DataTable' }).props()).toMatchObject({ rowKey: 'turn_id', rowInteractive: true, detailColumnKey: 'user_text', pageSize: 50, total: 60 })
    expect(wrapper.getComponent({ name: 'DataTable' }).props('fields').every((field: { filter: boolean; sort: boolean; filterDisabledReason: string; sortDisabledReason: string }) =>
      field.filter === false && field.sort === false && Boolean(field.filterDisabledReason) && Boolean(field.sortDisabledReason))).toBe(true)
  })

  it('renders localized outcomes and readable time in mobile cards', async () => {
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    const mobileCard = wrapper.get('[data-testid="mobile-cards"]')
    expect(mobileCard.text()).toContain('拦住未写')
    expect(mobileCard.text()).toContain('销售李')
    expect(mobileCard.text()).not.toContain('blocked_unwritten')
    expect(mobileCard.text()).not.toContain('2026-09-17T10:00:00')
  })

  it('opens a keyboard-accessible row detail and presents the exact complete log for selection and copying', async () => {
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    await wrapper.get('button[aria-label="查看记双汇跟进"]').trigger('click')
    await flushPromises()

    expect(getTurn).toHaveBeenCalledWith('turn_blocked')
    const pre = wrapper.get('[role="dialog"] pre')
    expect(pre.text()).toBe(fullLog)
    expect(pre.classes()).toContain('select-text')
    expect(pre.classes()).toContain('whitespace-pre-wrap')
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('判成「记跟进」')
    await wrapper.get('[role="dialog"] button[aria-label="复制完整日志"]').trigger('click')
    await flushPromises()
    expect(copyText).toHaveBeenCalledWith(fullLog)
    expect(toastSuccess).toHaveBeenCalled()

    copyText.mockRejectedValueOnce(new Error('denied'))
    await wrapper.get('[role="dialog"] button[aria-label="复制完整日志"]').trigger('click')
    await flushPromises()
    expect(toastError).toHaveBeenCalled()
  })

  it('ignores older detail responses after switching rows or closing the sheet', async () => {
    const first = deferred<typeof detail>()
    const second = deferred<typeof detail>()
    getTurn.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise)
    listTurns.mockResolvedValue({ items: [listItem, { ...listItem, turn_id: 'turn_two', user_text: '第二条' }], total: 2, page: 1, page_size: 20, total_pages: 1 })
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    await wrapper.get('button[aria-label="查看记双汇跟进"]').trigger('click')
    await wrapper.get('button[aria-label="查看第二条"]').trigger('click')
    first.resolve(detail)
    await flushPromises()
    expect(wrapper.find('[role="dialog"] pre').exists()).toBe(false)
    second.resolve({ ...detail, turn_id: 'turn_two', log: '第二条完整记录' })
    await flushPromises()
    expect(wrapper.get('[role="dialog"] pre').text()).toBe('第二条完整记录')
    await wrapper.get('[role="dialog"] button[aria-label="关闭"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('does not reopen a closed sheet when its detail request finishes later', async () => {
    const pending = deferred<typeof detail>()
    getTurn.mockReturnValueOnce(pending.promise)
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    await wrapper.get('button[aria-label="查看记双汇跟进"]').trigger('click')
    await wrapper.get('[role="dialog"] button[aria-label="关闭"]').trigger('click')
    pending.resolve(detail)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('keeps retry in the table and reloads the same server query after an error', async () => {
    listTurns.mockRejectedValueOnce(new Error('network'))
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    expect(wrapper.getComponent({ name: 'DataTable' }).props('loadError')).toMatchObject({ title: 'Agent 运行日志加载失败' })
    await wrapper.findAll('button').find((button) => button.text() === '重试')?.trigger('click')
    await flushPromises()
    expect(listTurns).toHaveBeenCalledTimes(2)
    expect(listTurns).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
    expect(wrapper.text()).toContain('记双汇跟进')
  })

  it('does not leave old rows accessible after a different server query fails', async () => {
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    expect(wrapper.find('button[aria-label="查看记双汇跟进"]').exists()).toBe(true)

    listTurns.mockRejectedValueOnce(new Error('network'))
    await wrapper.get('input[aria-label="搜索日志"]').setValue('不存在')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('button[aria-label="查看记双汇跟进"]').exists()).toBe(false)
    expect(wrapper.getComponent({ name: 'DataTable' }).props('total')).toBe(0)
    expect(wrapper.getComponent({ name: 'DataTable' }).props('loadError')).not.toBeNull()
  })

  it('discards cached rows and a pending detail when settings permission is revoked', async () => {
    const pending = deferred<typeof detail>()
    getTurn.mockReturnValueOnce(pending.promise)
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    await wrapper.get('button[aria-label="查看记双汇跟进"]').trigger('click')
    accessState.allowed.value = false
    await wrapper.vm.$nextTick()
    pending.resolve(detail)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    listTurns.mockRejectedValueOnce(new Error('forbidden'))
    accessState.allowed.value = true
    await wrapper.vm.$nextTick()
    await flushPromises()
    expect(wrapper.find('button[aria-label="查看记双汇跟进"]').exists()).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('clears server-side query and outcome from a filtered empty state', async () => {
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    await wrapper.get('input[aria-label="搜索日志"]').setValue('不存在')
    await wrapper.get('form[role="search"]').trigger('submit')
    await wrapper.get('select').setValue('failed')
    listTurns.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 })
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(wrapper.getComponent({ name: 'DataTable' }).props('emptyReason')).toBe('filtered')
    await wrapper.findAll('button').find((button) => button.text() === '清除筛选')?.trigger('click')
    await flushPromises()
    expect(listTurns).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
    expect(wrapper.get('select').element.value).toBe('all')
  })

  it('hides the log when the viewer lacks AI settings access', async () => {
    accessState.allowed.value = false
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无访问权限')
    expect(listTurns).not.toHaveBeenCalled()
  })

  it('loads turns after settings access becomes available', async () => {
    accessState.allowed.value = false
    accessState.pending.value = true
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()
    expect(listTurns).not.toHaveBeenCalled()
    accessState.allowed.value = true
    accessState.pending.value = false
    await wrapper.vm.$nextTick()
    await flushPromises()
    expect(listTurns).toHaveBeenCalled()
    expect(wrapper.text()).toContain('记双汇跟进')
  })
})
