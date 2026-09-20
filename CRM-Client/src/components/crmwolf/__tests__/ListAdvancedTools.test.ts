import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ListAdvancedTools from '../ListAdvancedTools.vue'

const wrappers: VueWrapper[] = []
const props = {
  sorts: [],
  sortFields: [{ key: 'name', label: '名称', type: 'text' as const }],
  columns: [{ key: 'name', title: '名称', visible: true, configurable: true, hideable: true }],
  columnConfigEnabled: true,
  columnConfigActive: false,
  columnConfigActiveCount: 0,
  columnConfigScope: 'personal' as const,
  columnPreferenceMode: 'default' as const,
  columnConfigLoading: false,
  columnConfigSaving: false,
}

function matchesViewportQuery(query: string, width: number): boolean {
  const exclusiveMaxWidth = query.match(/width\s*<\s*([\d.]+)px/)?.[1]
  if (exclusiveMaxWidth !== undefined) return width < Number(exclusiveMaxWidth)

  const inclusiveMaxWidth = query.match(/max-width:\s*([\d.]+)px/)?.[1]
  return inclusiveMaxWidth !== undefined && width <= Number(inclusiveMaxWidth)
}

function mockViewportWidth(initialWidth: number): { setWidth: (width: number) => void } {
  const queries: { update: (width: number) => void }[] = []

  vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => {
    let matches = matchesViewportQuery(query, initialWidth)
    const target = new EventTarget()

    Object.defineProperties(target, {
      matches: { get: () => matches },
      media: { value: query },
      onchange: { value: null, writable: true },
      addListener: {
        value: (listener: EventListener) => target.addEventListener('change', listener),
      },
      removeListener: {
        value: (listener: EventListener) => target.removeEventListener('change', listener),
      },
    })

    queries.push({
      update(width: number): void {
        const nextMatches = matchesViewportQuery(query, width)
        if (nextMatches === matches) return

        matches = nextMatches
        const event = new Event('change')
        Object.defineProperties(event, {
          matches: { value: matches },
          media: { value: query },
        })
        target.dispatchEvent(event)
      },
    })

    return target as MediaQueryList
  }))

  return {
    setWidth(width: number): void {
      queries.forEach((query) => query.update(width))
    },
  }
}

describe('ListAdvancedTools', () => {
  afterEach(() => {
    while (wrappers.length > 0) wrappers.pop()?.unmount()
    vi.unstubAllGlobals()
  })

  it('shows sort and column configuration as first-level desktop actions', async () => {
    mockViewportWidth(1440)
    const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
    wrappers.push(wrapper)
    await flushPromises()

    const buttonLabels = Array.from(document.body.querySelectorAll('button')).map((button) => (
      button.textContent?.replace(/\s+/g, '') ?? ''
    ))
    expect(buttonLabels).toContain('排序')
    expect(buttonLabels).toContain('字段配置')
    expect(buttonLabels).not.toContain('更多设置')

    const sortButton = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.includes('排序') === true
    ))
    expect(sortButton).toBeDefined()
    sortButton?.click()
    await flushPromises()
    expect(document.body.textContent).toContain('排序条件')
  })

  it('keeps sort and column configuration in more settings on compact screens', async () => {
    mockViewportWidth(390)
    const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
    wrappers.push(wrapper)

    const buttonLabels = wrapper.findAll('button').map((button) => button.text().replace(/\s+/g, ''))
    expect(buttonLabels).toContain('更多设置')
    expect(buttonLabels).not.toContain('排序')
    expect(buttonLabels).not.toContain('字段配置')

    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('列表设置')
    expect(document.body.textContent).toContain('排序')
    expect(document.body.textContent).toContain('字段配置')

    const sortButton = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.replace(/\s+/g, '') === '排序'
    ))
    sortButton?.click()
    await flushPromises()
    expect(document.body.textContent).toContain('排序条件')
  })

  it('uses compact tools below 768px and direct tools at 768px', async () => {
    const viewport = mockViewportWidth(767.5)
    const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
    wrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.get('button').text()).toContain('更多设置')

    viewport.setWidth(768)
    await flushPromises()
    const desktopTarget = wrapper.get('.list-advanced-tools-desktop').element
    expect(desktopTarget.textContent).toContain('排序')
    expect(desktopTarget.textContent).toContain('字段配置')
  })

  it('preserves an open sort draft while crossing the compact breakpoint', async () => {
    const viewport = mockViewportWidth(1440)
    const wrapper = mount(ListAdvancedTools, {
      props: {
        ...props,
        sortFields: [
          ...props.sortFields,
          { key: 'created_at', label: '创建时间', type: 'date' as const },
        ],
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)

    await flushPromises()
    const sortTrigger = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.includes('排序') === true
    ))
    sortTrigger?.click()
    await flushPromises()
    const addButton = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.replace(/\s+/g, '') === '添加条件'
    ))
    addButton?.click()
    await flushPromises()
    expect(document.body.querySelectorAll('button[aria-label="删除排序条件"]')).toHaveLength(2)

    viewport.setWidth(390)
    await flushPromises()

    expect(document.body.textContent).toContain('排序条件')
    expect(document.body.querySelectorAll('button[aria-label="删除排序条件"]')).toHaveLength(2)

    const closeButton = document.body.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')
    closeButton?.click()
    await flushPromises()
    expect(wrapper.get('button').text()).toContain('更多设置')
  })

  it('preserves the selected column scope while crossing the compact breakpoint', async () => {
    const viewport = mockViewportWidth(1440)
    const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
    wrappers.push(wrapper)

    await flushPromises()
    const columnTrigger = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.includes('字段配置') === true
    ))
    columnTrigger?.click()
    await flushPromises()
    const teamButton = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.replace(/\s+/g, '') === '同步团队'
    ))
    teamButton?.click()
    await flushPromises()

    viewport.setWidth(390)
    await flushPromises()
    const saveButton = Array.from(document.body.querySelectorAll('button')).find((button) => (
      button.textContent?.replace(/\s+/g, '') === '保存'
    ))
    saveButton?.click()
    await flushPromises()

    expect(wrapper.emitted('column-config-save')).toEqual([['team']])
  })

  it('shows the optional journey view config and emits board mode', async () => {
    const wrapper = mount(ListAdvancedTools, {
      props: {
        ...props,
        viewDisplayModeEnabled: true,
        viewDisplayMode: 'table',
        viewConfigTriggerLabel: '视图配置',
        viewConfigPanelTitle: '视图配置',
        canSaveCurrentView: true,
        viewSaveLoading: false,
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    const trigger = Array.from(document.body.querySelectorAll('button')).find(button => (
      button.textContent?.includes('视图配置') === true
    ))
    expect(trigger).toBeDefined()
    trigger?.click()
    await flushPromises()
    const boardSwitch = document.body.querySelector('[role="switch"]')
    expect(boardSwitch).not.toBeNull()
    ;(boardSwitch as HTMLElement).click()
    await flushPromises()
    expect(wrapper.emitted('update:view-display-mode')).toEqual([['board']])
  })

  it('emits save-current-view from the same config surface', async () => {
    const wrapper = mount(ListAdvancedTools, {
      props: {
        ...props,
        viewDisplayModeEnabled: true,
        viewDisplayMode: 'board',
        viewConfigTriggerLabel: '视图配置',
        viewConfigPanelTitle: '视图配置',
        canSaveCurrentView: true,
        viewSaveLoading: false,
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()
    const trigger = Array.from(document.body.querySelectorAll('button')).find(button => (
      button.textContent?.includes('视图配置') === true
    ))
    trigger?.click()
    await flushPromises()
    const save = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.replace(/\s+/g, '') === '另存为视图')
    expect(save).toBeDefined()
    save?.click()
    await flushPromises()
    expect(wrapper.emitted('save-current-view')).toHaveLength(1)
  })

  it('keeps existing pages free of the board switch and view label', async () => {
    const wrapper = mount(ListAdvancedTools, { props, attachTo: document.body })
    wrappers.push(wrapper)
    await flushPromises()
    expect(document.body.textContent).not.toContain('看板视图')
    expect(document.body.textContent).not.toContain('视图配置')
    expect(document.body.textContent).toContain('字段配置')
  })

  it('preserves controlled board mode across the compact breakpoint', async () => {
    const viewport = mockViewportWidth(767.5)
    const wrapper = mount(ListAdvancedTools, {
      props: {
        ...props,
        viewDisplayModeEnabled: true,
        viewDisplayMode: 'table',
        viewConfigTriggerLabel: '视图配置',
        viewConfigPanelTitle: '视图配置',
        canSaveCurrentView: true,
        viewSaveLoading: false,
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const trigger = Array.from(document.body.querySelectorAll('button')).find(button => (
      button.textContent?.includes('视图配置') === true
    ))
    trigger?.click()
    await flushPromises()
    const boardSwitch = document.body.querySelector('[role="switch"]') as HTMLElement | null
    boardSwitch?.click()
    await wrapper.setProps({ viewDisplayMode: 'board' })
    viewport.setWidth(768)
    await flushPromises()
    expect(document.body.querySelector('[role="switch"]')?.getAttribute('data-state')).toBe('checked')
  })
})
