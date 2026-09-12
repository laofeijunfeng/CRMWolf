import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import WorkflowInsertEdge, { type WorkflowInsertEdgeData } from '../WorkflowInsertEdge.vue'

const props = {
  id: 'edge-main',
  source: 'source',
  target: 'target',
  sourceX: 0,
  sourceY: 20,
  targetX: 200,
  targetY: 20,
  sourcePosition: 'right',
  targetPosition: 'left',
  data: {
    insertionContext: {
      kind: 'between-edge' as const,
      edgeId: 'edge-main',
      sourceNodeId: 'source',
      targetNodeId: 'target',
    },
  } satisfies WorkflowInsertEdgeData,
  markerEnd: '',
  sourceNode: {},
  targetNode: {},
  type: 'workflow-insert',
  events: {},
}

describe('WorkflowInsertEdge', () => {
  it('renders the insertion button and label at the edge midpoint', () => {
    const wrapper = mount(WorkflowInsertEdge, { props: props as never })

    const button = wrapper.get('[data-testid="workflow-insert-edge-edge-main"]')
    expect(button.attributes('aria-label')).toBe('在此处添加节点')
    expect(button.text()).toContain('+')
    expect(wrapper.text()).toContain('添加节点')
  })

  it('emits the edge id when the insertion button is activated', async () => {
    const wrapper = mount(WorkflowInsertEdge, { props: props as never })

    await wrapper.get('[data-testid="workflow-insert-edge-edge-main"]').trigger('click')
    expect(wrapper.emitted('insert')).toEqual([['edge-main']])
  })

  it('supports keyboard activation', async () => {
    const wrapper = mount(WorkflowInsertEdge, { props: props as never })
    const button = wrapper.get('[data-testid="workflow-insert-edge-edge-main"]')
    const preventDefault = vi.fn()

    await button.trigger('keydown', { key: 'Enter', preventDefault })
    expect(wrapper.emitted('insert')).toEqual([['edge-main']])
  })
})
