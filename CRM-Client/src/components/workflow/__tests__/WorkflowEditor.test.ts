import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowEditor from '../WorkflowEditor.vue'
import * as workflowValidation from '../workflowValidation'
import workflowApi from '@/api/workflow'
import procurementApi from '@/api/procurement'
import roleApi from '@/api/role'
beforeAll(() => { HTMLElement.prototype.scrollIntoView = () => undefined })

vi.mock('@/api/workflow', () => ({
  default: {
    create: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
  },
}))

vi.mock('@/api/procurement', () => ({
  default: {
    getStageTemplates: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/api/role', () => ({
  default: {
    getRoles: vi.fn().mockResolvedValue([]),
  },
}))

const detail = {
  id: 9,
  name: '测试工作流',
  description: null,
  status: 'draft' as const,
  node_count: 1,
  dsl: {
    schema_version: 1 as const,
    nodes: [{ id: 'trigger-1', type: 'trigger.opportunity_stage_changed', position: { x: 0, y: 0 }, config: { to_stage: 'QUOTE' } }],
    edges: [],
  },
  created_time: '2026-09-10T00:00:00Z',
  last_modified_time: '2026-09-10T00:00:00Z',
}

function mountEditor(workflowId: number | null = null) {
  return mount(WorkflowEditor, {
    props: { workflowId },
    attachTo: document.body,
    global: {
      stubs: {
        VueFlow: { props: { id: String }, template: '<div data-testid="vue-flow" :id="id"><slot /></div>' },
        Background: { template: '<div />' },
        Controls: { template: '<div />' },
      },
    },
  })
}

describe('WorkflowEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(workflowApi.create).mockResolvedValue(detail)
    vi.mocked(workflowApi.get).mockResolvedValue(detail)
    vi.mocked(workflowApi.update).mockResolvedValue(detail)
    vi.mocked(procurementApi.getStageTemplates).mockResolvedValue([])
    vi.mocked(roleApi.getRoles).mockResolvedValue([])
  })

  it('uses the fixed Vue Flow instance id', async () => {
    const wrapper = mountEditor()
    await nextTick()

    expect(wrapper.get('[data-testid="vue-flow"]').attributes('id')).toBe('workflow-editor-flow')
  })

  it('offers reload after a save conflict and reloads the workflow', async () => {
    vi.mocked(workflowApi.update).mockRejectedValue({ response: { status: 409 } })
    const wrapper = mountEditor(9)
    await nextTick()
    await wrapper.vm.save()

    expect(wrapper.text()).toContain('工作流已被修改，请刷新后重试')
    const reloadButton = wrapper.get('[data-testid="reload-workflow"]')
    expect(reloadButton.attributes('disabled')).toBeUndefined()

    await reloadButton.trigger('click')
    await nextTick()

    expect(workflowApi.get).toHaveBeenCalledTimes(2)
  })

  it('shows all five palette nodes on an empty canvas', async () => {
    const wrapper = mountEditor()
    await nextTick()

    expect(wrapper.find('[data-testid="workflow-palette"]').text()).toContain('商机阶段变化')
    expect(wrapper.findAll('[data-testid^="palette-node-"]')).toHaveLength(5)
  })

  it('disables the trigger palette item after adding a trigger', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').attributes('aria-disabled')).toBe('true')
  })
  it('opens the shared picker from the toolbar and inserts the selected node at root', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-add-node"]').trigger('click')
    await nextTick()
    const pickerItem = document.body.querySelector('[data-testid="workflow-picker-item-action.notify"]')
    if (!(pickerItem instanceof HTMLElement)) throw new Error('picker item missing')
    pickerItem.click()
    await nextTick()

    expect(wrapper.vm.nodes.some(node => node.type === 'action.notify')).toBe(true)
    expect(wrapper.vm.edges).toHaveLength(0)
  })
  it('focuses the inserted node after terminal selection removes its opener', async () => {
    const wrapper = mountEditor()
    wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 0, y: 0 }, { kind: 'root' })
    const trigger = wrapper.vm.nodes[0]
    if (trigger === undefined) throw new Error('trigger node missing')
    wrapper.vm.addNode('action.notify', { x: 100, y: 0 }, { kind: 'after-node', sourceNodeId: trigger.id })
    await nextTick()
    const terminalButton = wrapper.find(`[data-testid="workflow-insert-terminal-${wrapper.vm.nodes[1]?.id}"]`)
    await terminalButton.trigger('click')
    const pickerItem = document.body.querySelector('[data-testid="workflow-picker-item-action.create_follow_up_task"]')
    if (!(pickerItem instanceof HTMLElement)) throw new Error('picker item missing')
    pickerItem.click()
    await nextTick()
    await nextTick()

    const insertedNode = wrapper.vm.nodes[2]
    if (insertedNode === undefined) throw new Error('inserted node missing')
    const focusTarget = document.querySelector<HTMLElement>(`[data-node-id="${insertedNode.id}"]`)
    expect(focusTarget?.isConnected).toBe(true)
    expect(document.activeElement).toBe(focusTarget)
    expect(document.activeElement).not.toBe(terminalButton.element)
    expect(document.activeElement).not.toBe(document.body)
  })

  it('renders one terminal insertion button for each concrete branch tail', async () => {
    const wrapper = mountEditor()
    wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 0, y: 0 }, { kind: 'root' })
    const trigger = wrapper.vm.nodes[0]
    if (trigger === undefined) throw new Error('trigger node missing')
    wrapper.vm.addNode('action.notify', { x: 100, y: -40 }, { kind: 'after-node', sourceNodeId: trigger.id })
    wrapper.vm.addNode('action.create_follow_up_task', { x: 100, y: 40 }, { kind: 'root' })
    await nextTick()

    const buttons = wrapper.findAll('[data-testid^="workflow-insert-terminal-"]')
    expect(buttons).toHaveLength(2)
    expect(buttons.map(button => button.attributes('data-testid'))).toEqual(expect.arrayContaining([
      `workflow-insert-terminal-${wrapper.vm.nodes[2]?.id}`,
      `workflow-insert-terminal-${wrapper.vm.nodes[1]?.id}`,
    ]))
  })
  it('connects a newly added node to an explicit chain tail context', async () => {
    const wrapper = mountEditor()

    wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 0, y: 0 }, { kind: 'root' })
    const triggerNode = wrapper.vm.nodes[0]
    if (triggerNode === undefined) throw new Error('trigger node missing')
    wrapper.vm.addNode('action.create_follow_up_task', { x: 120, y: 0 }, {
      kind: 'after-node',
      sourceNodeId: triggerNode.id,
    })
    await nextTick()

    expect(wrapper.vm.edges).toHaveLength(1)
    expect(wrapper.vm.edges[0]?.source).toBe(triggerNode.id)
    expect(wrapper.vm.edges[0]?.target).toBe(wrapper.vm.nodes[1]?.id)
  })
  it('keeps manual connections between existing nodes', async () => {
    const wrapper = mountEditor()

    wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 0, y: 0 }, { kind: 'root' })
    wrapper.vm.addNode('action.notify', { x: 120, y: 0 }, { kind: 'root' })
    const source = wrapper.vm.nodes[0]
    const target = wrapper.vm.nodes[1]
    if (source === undefined || target === undefined) throw new Error('nodes missing')

    wrapper.vm.onConnect({ source: source.id, target: target.id })

    expect(wrapper.vm.edges).toEqual([expect.objectContaining({ source: source.id, target: target.id })])
  })

  it('connects a dropped node to the sole terminal node', async () => {
    const wrapper = mountEditor()
    wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 0, y: 0 }, { kind: 'root' })
    const triggerNode = wrapper.vm.nodes[0]
    if (triggerNode === undefined) throw new Error('trigger node missing')
    wrapper.vm.addNode('action.create_follow_up_task', { x: 120, y: 0 }, {
      kind: 'after-node',
      sourceNodeId: triggerNode.id,
    })
    const tailNode = wrapper.vm.nodes[1]
    if (tailNode === undefined) throw new Error('tail node missing')

    wrapper.vm.onDrop({
      preventDefault: () => undefined,
      clientX: 240,
      clientY: 0,
      dataTransfer: { getData: () => 'action.notify' },
    })
    await nextTick()

    const droppedNode = wrapper.vm.nodes[2]
    expect(droppedNode).toBeDefined()
    expect(wrapper.vm.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: tailNode.id, target: droppedNode?.id }),
    ]))
  })
  it('does not guess a source when the graph has multiple chain tails', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    await wrapper.get('[data-testid="palette-node-action.create_follow_up_task"]').trigger('click')
    await wrapper.get('[data-testid="palette-node-action.notify"]').trigger('click')

    const actionNode = wrapper.vm.nodes[1]
    if (actionNode === undefined) throw new Error('action node missing')
    wrapper.vm.removeNode(actionNode.id)
    await nextTick()
    const edgeCountBeforeNewNode = wrapper.vm.edges.length

    await wrapper.get('[data-testid="palette-node-approval.step"]').trigger('click')
    await nextTick()

    expect(wrapper.vm.edges).toHaveLength(edgeCountBeforeNewNode)
  })

  it('opens a node config panel and writes config updates back to the node', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="palette-node-action.create_follow_up_task"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="config-panel-action.create_follow_up_task"]').exists()).toBe(true)
    const titleInput = wrapper.get('[data-testid="config-title"]')
    await titleInput.setValue('跟进客户')
    await nextTick()
    expect(wrapper.get('[data-testid="workflow-node-action.create_follow_up_task"]').text()).toContain('跟进客户')
  })

  it('saves the automatically created edge in the workflow DSL', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('销售工作流')
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    await nextTick()
    const triggerNode = wrapper.vm.nodes[0]
    if (triggerNode === undefined) throw new Error('trigger node missing')
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    await wrapper.get('[data-testid="palette-node-action.create_follow_up_task"]').trigger('click')
    await nextTick()
    const actionNode = wrapper.vm.nodes[1]
    if (actionNode === undefined) throw new Error('action node missing')
    wrapper.vm.updateSelectedConfig({ title: '创建跟进任务' })
    await wrapper.get('[data-testid="save-workflow"]').trigger('click')

    expect(workflowApi.create).toHaveBeenCalledWith(expect.objectContaining({
      name: '销售工作流',
      dsl: expect.objectContaining({
        schema_version: 1,
        nodes: expect.any(Array),
        edges: [expect.objectContaining({ source: triggerNode.id, target: actionNode.id })],
      }),
    }))
  })

  it('does not call the create API or validate again while saving is in progress', async () => {
    const validateSpy = vi.spyOn(workflowValidation, 'validateWorkflow')
    let resolveCreate!: (workflow: typeof detail) => void
    const pendingCreate = new Promise<typeof detail>(resolve => { resolveCreate = resolve })
    vi.mocked(workflowApi.create).mockImplementation(() => pendingCreate)

    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('重复保存工作流')
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    await nextTick()
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })

    const firstSave = wrapper.vm.save()
    const secondSave = wrapper.vm.save()
    await nextTick()

    expect(validateSpy).toHaveBeenCalledTimes(2)
    expect(workflowApi.create).toHaveBeenCalledTimes(1)

    resolveCreate(detail)
    await firstSave
    await secondSave
  })


  it('blocks saving without a trigger and displays validation issues', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('不完整工作流')
    await wrapper.get('[data-testid="palette-node-action.notify"]').trigger('click')
    await wrapper.get('[data-testid="save-workflow"]').trigger('click')

    expect(workflowApi.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('trigger')
  })

  it('keeps node-bound detail errors from a 422 create response', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('后端校验工作流')
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    await wrapper.get('[data-testid="palette-node-action.create_follow_up_task"]').trigger('click')
    const actionNode = wrapper.vm.nodes[1]
    if (actionNode === undefined) throw new Error('action node missing')
    wrapper.vm.updateSelectedConfig({ title: '本地有效配置' })
    const expectedMessage = `节点 ${actionNode.id} 缺少必填配置: title`
    vi.mocked(workflowApi.create).mockRejectedValue({
      response: { status: 422, data: { detail: { errors: [expectedMessage] } } },
    })

    await wrapper.vm.save()

    expect(wrapper.get('[data-testid="workflow-issues"]').text()).toContain(expectedMessage)
    expect(wrapper.vm.nodes.find(node => node.id === actionNode.id)?.data).toMatchObject({
      hasError: true,
      errorMessage: expectedMessage,
    })
    expect(wrapper.text()).toContain('工作流校验失败')
  })
})
