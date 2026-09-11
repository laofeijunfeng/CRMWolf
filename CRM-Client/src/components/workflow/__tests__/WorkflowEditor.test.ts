import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowEditor from '../WorkflowEditor.vue'
import * as workflowValidation from '../workflowValidation'
import workflowApi from '@/api/workflow'
import procurementApi from '@/api/procurement'
import roleApi from '@/api/role'

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

  it('saves a payload containing schema_version, nodes, and edges', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('销售工作流')
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    await nextTick()
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    await wrapper.get('[data-testid="save-workflow"]').trigger('click')
    expect(workflowApi.create).toHaveBeenCalledWith(expect.objectContaining({
      name: '销售工作流',
      dsl: expect.objectContaining({ schema_version: 1, nodes: expect.any(Array), edges: expect.any(Array) }),
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
    vi.mocked(workflowApi.create).mockRejectedValue({
      response: { status: 422, data: { detail: { errors: ['节点 node-1 缺少必填配置: title'] } } },
    })
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('后端校验工作流')
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    await wrapper.get('[data-testid="palette-node-action.create_follow_up_task"]').trigger('click')
    wrapper.vm.updateSelectedConfig({ title: '本地有效但后端拒绝' })
    const actionNode = wrapper.vm.nodes[1]
    if (actionNode !== undefined) actionNode.id = 'node-1'
    const triggerNode = wrapper.vm.nodes[0]
    if (triggerNode !== undefined) triggerNode.id = 'trigger-1'
    wrapper.vm.onConnect({ source: 'trigger-1', target: 'node-1' })
    await wrapper.vm.save()

    expect(wrapper.get('[data-testid="workflow-issues"]').text()).toContain('节点 node-1 缺少必填配置: title')
    expect(wrapper.vm.nodes.find(node => node.id === 'node-1')?.data).toMatchObject({
      hasError: true,
      errorMessage: '节点 node-1 缺少必填配置: title',
    })
    expect(wrapper.text()).toContain('工作流校验失败')
  })

  it('shows a refresh message when saving hits an optimistic-lock conflict', async () => {
    vi.mocked(workflowApi.create).mockRejectedValue({ response: { status: 409 } })
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="workflow-name"]').setValue('冲突工作流')
    await wrapper.get('[data-testid="palette-node-trigger.opportunity_stage_changed"]').trigger('click')
    wrapper.vm.updateSelectedConfig({ to_stage: 'QUOTE' })
    await wrapper.get('[data-testid="save-workflow"]').trigger('click')
    expect(wrapper.text()).toContain('工作流已被修改，请刷新后重试')
  })
})
