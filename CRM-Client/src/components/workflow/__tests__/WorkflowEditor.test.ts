import { defineComponent, nextTick } from 'vue'
import type { VueWrapper } from '@vue/test-utils'
import { mount } from '@vue/test-utils'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowEditor from '../WorkflowEditor.vue'
import type { WorkflowNodeType } from '../workflowNodeRegistry'
import WorkflowNodePickerDialog from '../WorkflowNodePickerDialog.vue'
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
const VueFlowStub = defineComponent({
  name: 'VueFlow',
  props: { id: { type: String, required: true } },
  emits: ['nodeDragStop'],
  template: '<div data-testid="vue-flow" :id="id"><button data-testid="stop-node-drag" @click="$emit(\'nodeDragStop\')" /><slot /></div>',
})

function mountEditor(workflowId: number | null = null) {
  return mount(WorkflowEditor, {
    props: { workflowId },
    attachTo: document.body,
    global: {
      stubs: {
        VueFlow: VueFlowStub,
        Background: { template: '<div />' },
        Controls: { template: '<div />' },
      },
    },
  })
}
interface WorkflowEditorExposed { addNode: (type: WorkflowNodeType, position: { x: number; y: number }, context: { kind: 'root' } | { kind: 'after-node'; sourceNodeId: string }) => string | null }
async function selectRootNode(wrapper: VueWrapper, type: WorkflowNodeType): Promise<void> {
  const insertedNodeId = (wrapper.vm as unknown as WorkflowEditorExposed).addNode(type, { x: 120, y: 120 }, { kind: 'root' })
  if (insertedNodeId === null) throw new Error(`unable to add root node: ${type}`)
  await nextTick()
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

  it('does not render a fixed left node palette', async () => {
    const wrapper = mountEditor()
    await nextTick()

    expect(wrapper.find('[data-testid="workflow-palette"]').exists()).toBe(false)
    expect(wrapper.find('.grid-cols-\\[220px_minmax\\(0\\,1fr\\)_320px\\]').exists()).toBe(false)
  })

  it('provides a non-empty description for every picker item', async () => {
    const wrapper = mountEditor()
    await nextTick()

    const picker = wrapper.findComponent(WorkflowNodePickerDialog)
    const items = picker.props('nodeTypes') as ReadonlyArray<{ description: unknown }>
    expect(items.every(item => typeof item.description === 'string' && item.description.trim() !== '')).toBe(true)
  })

  it('uses the root picker to disable the trigger after adding one', async () => {
    const wrapper = mountEditor()
    await selectRootNode(wrapper, 'trigger.opportunity_stage_changed')
    await wrapper.get('[data-testid="workflow-add-node"]').trigger('click')
    await nextTick()

    expect(document.body.querySelector('[data-testid="workflow-picker-item-trigger.opportunity_stage_changed"]')?.getAttribute('aria-disabled')).toBe('true')
  })
  it('opens the shared picker from the toolbar and inserts the selected node at root', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-add-node"]').trigger('click')
    await nextTick()
    wrapper.getComponent(WorkflowNodePickerDialog).vm.$emit('select', 'action.notify')
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
    await nextTick()
    wrapper.getComponent(WorkflowNodePickerDialog).vm.$emit('select', 'action.create_follow_up_task')
    await nextTick()
    await nextTick()

    const insertedNode = wrapper.vm.nodes[2]
    if (insertedNode === undefined) throw new Error('inserted node missing')
    const focusTarget = document.querySelector<HTMLElement>(`[data-node-id="${insertedNode.id}"]`)
    expect(focusTarget?.isConnected).toBe(true)
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
      dataTransfer: { getData: () => 'action.notify' } as unknown as DataTransfer,
    } as unknown as DragEvent)
    await nextTick()

    const droppedNode = wrapper.vm.nodes[2]
    expect(droppedNode).toBeDefined()
    expect(wrapper.vm.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: tailNode.id, target: droppedNode?.id }),
    ]))
  })
  it('does not guess a source when the graph has multiple chain tails', async () => {
    const wrapper = mountEditor()
    await selectRootNode(wrapper, 'trigger.opportunity_stage_changed')
    await selectRootNode(wrapper, 'action.create_follow_up_task')
    await selectRootNode(wrapper, 'action.notify')

    const actionNode = wrapper.vm.nodes[1]
    if (actionNode === undefined) throw new Error('action node missing')
    wrapper.vm.removeNode(actionNode.id)
    await nextTick()
    const edgeCountBeforeNewNode = wrapper.vm.edges.length

    await selectRootNode(wrapper, 'approval.step')
    expect(wrapper.vm.edges).toHaveLength(edgeCountBeforeNewNode)
  })

  it('opens a node config panel and writes config updates back to the node', async () => {
    const wrapper = mountEditor()
    await selectRootNode(wrapper, 'action.create_follow_up_task')
    expect(wrapper.find('[data-testid="config-panel-action.create_follow_up_task"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="workflow-config-header"]').text()).toContain('创建跟进任务')
    const titleInput = wrapper.get('[data-testid="config-title"]')
    await titleInput.setValue('跟进客户')
    await nextTick()
    expect(wrapper.get('[data-testid="workflow-node-action.create_follow_up_task"]').text()).toContain('跟进客户')
  })
  it('shows semantic category labels in node configuration headers', async () => {
    const wrapper = mountEditor()
    await selectRootNode(wrapper, 'approval.step')
    expect(wrapper.get('[data-testid="workflow-config-header"]').text()).toContain('审批')
    wrapper.vm.closeConfigPanel()
    await selectRootNode(wrapper, 'crm.create_customer')
    expect(wrapper.get('[data-testid="workflow-config-header"]').text()).toContain('CRM 业务')
  })

  it('saves the automatically created edge in the workflow DSL', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('销售工作流')
    const triggerNodeId = wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 120, y: 120 }, { kind: 'root' })
    if (triggerNodeId === null) throw new Error('trigger node missing')
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    const actionNodeId = wrapper.vm.addNode('action.create_follow_up_task', { x: 300, y: 120 }, { kind: 'after-node', sourceNodeId: triggerNodeId })
    if (actionNodeId === null) throw new Error('action node missing')
    wrapper.vm.updateSelectedConfig({ title: '创建跟进任务' })
    await wrapper.get('[data-testid="save-workflow"]').trigger('click')
    const triggerNode = wrapper.vm.nodes.find(node => node.id === triggerNodeId)
    const actionNode = wrapper.vm.nodes.find(node => node.id === actionNodeId)
    if (triggerNode === undefined || actionNode === undefined) throw new Error('nodes missing')
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
    await selectRootNode(wrapper, 'trigger.opportunity_stage_changed')
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
    await selectRootNode(wrapper, 'action.notify')
    await wrapper.get('[data-testid="save-workflow"]').trigger('click')

    expect(workflowApi.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('trigger')
  })

  it('keeps node-bound detail errors from a 422 create response', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('后端校验工作流')
    const triggerNodeId = wrapper.vm.addNode('trigger.opportunity_stage_changed', { x: 120, y: 120 }, { kind: 'root' })
    if (triggerNodeId === null) throw new Error('trigger node missing')
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    const actionNodeId = wrapper.vm.addNode('action.create_follow_up_task', { x: 300, y: 120 }, { kind: 'after-node', sourceNodeId: triggerNodeId })
    if (actionNodeId === null) throw new Error('action node missing')
    wrapper.vm.updateSelectedConfig({ title: '本地有效配置' })
    const actionNode = wrapper.vm.nodes.find(node => node.id === actionNodeId)
    if (actionNode === undefined) throw new Error('action node missing')
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
  it('shows draft, unsaved, and validation status in the top toolbar', async () => {
    const wrapper = mountEditor()
    await nextTick()

    expect(wrapper.get('[data-testid="workflow-status-toolbar"]').text()).toContain('草稿')
    expect(wrapper.get('[data-testid="workflow-status-toolbar"]').text()).toContain('未保存')
    expect(wrapper.get('[data-testid="workflow-status-toolbar"]').text()).toContain('校验通过')
  })

  it('provides an accessible root add-node control', async () => {
    const wrapper = mountEditor()
    await nextTick()

    const rootAdd = wrapper.get('[data-testid="workflow-root-add-node"]')
    expect(rootAdd.text()).toContain('添加节点')
    expect(rootAdd.attributes('aria-label')).toBe('添加根节点')
  })

  it('closes the selected node configuration panel without changing the graph', async () => {
    const wrapper = mountEditor()
    await selectRootNode(wrapper, 'action.notify')
    await nextTick()
    const nodeCount = wrapper.vm.nodes.length

    await wrapper.get('[data-testid="workflow-config-close"]').trigger('click')
    await nextTick()

    expect(wrapper.vm.nodes).toHaveLength(nodeCount)
    expect(wrapper.get('[data-testid="workflow-config-panel"]').text()).toContain('选择节点以配置')
  })
  it('marks an existing workflow dirty after a node drag stops', async () => {
    const wrapper = mountEditor(9)
    await nextTick()
    await nextTick()
    expect(wrapper.get('[data-testid="workflow-save-status"]').text()).toBe('已保存')

    await wrapper.get('[data-testid="stop-node-drag"]').trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="workflow-save-status"]').text()).toBe('有未保存的更改')
  })

  it('keeps an existing workflow saved after hydration watcher effects settle', async () => {
    const wrapper = mountEditor(9)
    await nextTick()
    await nextTick()

    expect(wrapper.get('[data-testid="workflow-save-status"]').text()).toBe('已保存')
  })

  it('uses the approved draft status and save action copy', async () => {
    const wrapper = mountEditor()
    await nextTick()

    expect(wrapper.get('[data-testid="workflow-save-status"]').text()).toBe('有未保存的更改')
    expect(wrapper.get('[data-testid="save-workflow"]').text()).toContain('保存草稿')
  })
})
