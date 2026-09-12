import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { NodeProps } from '@vue-flow/core'
import WorkflowNode from '../WorkflowNode.vue'

vi.mock('@vue-flow/core', () => ({
  Handle: defineComponent({
    name: 'VueFlowHandle',
    props: {
      type: { type: String, required: true },
      position: { type: String, required: true },
    },
    template: '<span data-testid="vue-flow-handle" :data-type="type" :data-position="position" />',
  }),
  Position: {
    Left: 'left',
    Right: 'right',
  },
}))


interface NodeData {
  config?: Record<string, unknown>
  hasError?: boolean
  errorMessage?: string
}

const nodeProps: NodeProps<NodeData> = {
  id: 'node-1',
  type: 'approval.step',
  selected: false,
  connectable: true,
  position: { x: 0, y: 0 },
  dimensions: { width: 192, height: 80 },
  dragging: false,
  resizing: false,
  zIndex: 0,
  data: { config: { node_name: '审核合同', approve_role: '经理' } },
  events: {} as NodeProps<NodeData>['events'],
}
describe('WorkflowNode', () => {
  it('renders target and source handles on the expected sides', () => {
    const wrapper = mount(WorkflowNode, {
      props: nodeProps,
    })

    expect(wrapper.findAll('[data-testid="vue-flow-handle"]').map(handle => ({
      type: handle.attributes('data-type'),
      position: handle.attributes('data-position'),
    }))).toEqual([
      { type: 'target', position: 'left' },
      { type: 'source', position: 'right' },
    ])
  })
  it('renders category and status badges with stable accessible labels', () => {
    const wrapper = mount(WorkflowNode, {
      props: { ...nodeProps, data: { ...nodeProps.data, hasError: true, errorMessage: '缺少审批角色' } },
    })

    expect(wrapper.get('[data-testid="workflow-node-category"]').text()).toBe('审批')
    expect(wrapper.get('[data-testid="workflow-node-status"]').text()).toContain('需配置')
    expect(wrapper.get('button').attributes('aria-label')).toContain('审批节点')
    expect(wrapper.get('[role="alert"]').text()).toContain('缺少审批角色')
  })
  it('labels approval and CRM nodes with their specific categories', () => {
    const approval = mount(WorkflowNode, { props: nodeProps })
    expect(approval.get('[data-testid="workflow-node-category"]').text()).toBe('审批')

    const crm = mount(WorkflowNode, { props: { ...nodeProps, type: 'crm.create_customer', data: { config: {} } } })
    expect(crm.get('[data-testid="workflow-node-category"]').text()).toBe('CRM 业务')
  })
})
