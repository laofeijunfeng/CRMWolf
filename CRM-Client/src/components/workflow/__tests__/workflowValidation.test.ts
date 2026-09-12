import { describe, expect, it } from 'vitest'
import { validateWorkflow, type WorkflowGraph, type WorkflowGraphNode, type WorkflowValidationIssue } from '../workflowValidation'

const validGraph: WorkflowGraph = {
  schema_version: 1,
  nodes: [
    {
      id: 'trigger',
      type: 'trigger.opportunity_stage_changed',
      position: { x: 0, y: 0 },
      config: { to_stage: 'QUOTE' },
    },
    {
      id: 'condition',
      type: 'control.condition',
      position: { x: 200, y: 0 },
      config: { field: 'amount', operator: 'gt', value: 1000 },
    },
    {
      id: 'action',
      type: 'action.create_follow_up_task',
      position: { x: 400, y: 0 },
      config: { title: '联系客户' },
    },
  ],
  edges: [
    { id: 'edge-1', source: 'trigger', target: 'condition' },
    { id: 'edge-2', source: 'condition', target: 'action' },
  ],
}

const issuesFor = (graph: WorkflowGraph, name = '商机工作流'): WorkflowValidationIssue[] => validateWorkflow(graph, name)

const withGraph = (overrides: Partial<WorkflowGraph>): WorkflowGraph => ({
  ...validGraph,
  ...overrides,
})

describe('validateWorkflow', () => {
  it('accepts a valid shared workflow DSL graph', () => {
    expect(issuesFor(validGraph)).toEqual([])
  })

  it('rejects an empty workflow name', () => {
    expect(issuesFor(validGraph, '   ').some(issue => issue.message.includes('名称'))).toBe(true)
  })

  it('rejects a workflow name longer than 100 characters', () => {
    expect(issuesFor(validGraph, 'a'.repeat(101)).some(issue => issue.message.includes('100'))).toBe(true)
  })
  it('rejects a missing schema_version', () => {
    const graphWithoutSchemaVersion = { ...validGraph }
    delete graphWithoutSchemaVersion.schema_version
    const issues = issuesFor(graphWithoutSchemaVersion)

    expect(issues.some(issue => issue.message === 'schema_version 必须为 1')).toBe(true)
  })

  it('rejects missing or non-numeric node positions with the node id', () => {
    const missingPositionIssues = issuesFor(withGraph({
      nodes: validGraph.nodes.map(node => node.id === 'condition' ? { ...node, position: undefined } : node) as unknown as WorkflowGraphNode[],
    }))
    expect(missingPositionIssues.some(issue => issue.nodeId === 'condition' && issue.message.includes('坐标'))).toBe(true)

    const nonNumericPositionIssues = issuesFor(withGraph({
      nodes: validGraph.nodes.map(node => node.id === 'action' ? { ...node, position: { x: Number.NaN, y: 'invalid' } } : node) as unknown as WorkflowGraphNode[],
    }))
    expect(nonNumericPositionIssues.some(issue => issue.nodeId === 'action' && issue.message.includes('坐标'))).toBe(true)
  })

  it('requires exactly one trigger', () => {
    const withoutTrigger = withGraph({
      nodes: validGraph.nodes.filter(node => node.id !== 'trigger'),
      edges: [{ id: 'edge-2', source: 'condition', target: 'action' }],
    })
    expect(issuesFor(withoutTrigger).some(issue => issue.message.includes('trigger'))).toBe(true)

    const secondTrigger = {
      id: 'trigger-2',
      type: 'trigger.opportunity_stage_changed',
      position: { x: 0, y: 200 },
      config: { to_stage: 'WON' },
    }
    expect(issuesFor(withGraph({ nodes: [...validGraph.nodes, secondTrigger] })).some(issue => issue.message.includes('trigger'))).toBe(true)
  })

  it('rejects dangling edges', () => {
    const graph = withGraph({
      edges: [{ id: 'bad', source: 'condition', target: 'missing' }],
    })
    expect(issuesFor(graph).some(issue => issue.message.includes('不存在'))).toBe(true)
  })

  it('rejects self loops', () => {
    const graph = withGraph({
      edges: [{ id: 'bad', source: 'condition', target: 'condition' }],
    })
    expect(issuesFor(graph).some(issue => issue.message.includes('自环'))).toBe(true)
  })

  it('rejects edges targeting the trigger', () => {
    const graph = withGraph({
      edges: [
        { id: 'edge-1', source: 'trigger', target: 'condition' },
        { id: 'bad', source: 'action', target: 'trigger' },
      ],
    })
    expect(issuesFor(graph).some(issue => issue.message.includes('trigger'))).toBe(true)
  })

  it('rejects nodes that are unreachable from the trigger', () => {
    const graph = withGraph({
      nodes: [
        ...validGraph.nodes,
        {
          id: 'orphan',
          type: 'approval.step',
          position: { x: 600, y: 0 },
          config: { node_name: '审批', approve_role: 'manager' },
        },
      ],
    })
    expect(issuesFor(graph).some(issue => issue.nodeId === 'orphan' && issue.message.includes('不可达'))).toBe(true)
  })

  it('rejects missing required node configuration', () => {
    const graph = withGraph({
      nodes: validGraph.nodes.map(node => node.id === 'action' ? { ...node, config: {} } : node),
    })
    const issue = issuesFor(graph).find(item => item.nodeId === 'action')
    expect(issue?.message).toContain('title')
  })

  it('accepts valid minimal configs for each CRM resource node', () => {
    const crmNodes: WorkflowGraphNode[] = [
      { id: 'customer', type: 'crm.create_customer', position: { x: 600, y: 0 }, config: { account_name: 'Acme', city: '上海' } },
      { id: 'contact', type: 'crm.create_contact', position: { x: 800, y: 0 }, config: { customer_ref: 'customer', name: '王总', gender: '1', position: '采购', mobile: '13800138000' } },
      { id: 'opportunity', type: 'crm.create_opportunity', position: { x: 1000, y: 0 }, config: { customer_ref: 'customer', total_amount: 100, user_count: 1, license_type: 'SUBSCRIPTION', purchase_type: 'NEW', expected_closing_date: '2026-12-31' } },
    ]
    const graph = withGraph({
      nodes: [...validGraph.nodes, ...crmNodes],
      edges: [...validGraph.edges, { id: 'edge-3', source: 'action', target: 'customer' }, { id: 'edge-4', source: 'customer', target: 'contact' }, { id: 'edge-5', source: 'contact', target: 'opportunity' }],
    })
    expect(issuesFor(graph)).toEqual([])
  })

  it('rejects missing required values for each CRM resource node', () => {
    const cases: WorkflowGraphNode[] = [
      { id: 'customer', type: 'crm.create_customer', position: { x: 600, y: 0 }, config: {} },
      { id: 'contact', type: 'crm.create_contact', position: { x: 600, y: 0 }, config: {} },
      { id: 'opportunity', type: 'crm.create_opportunity', position: { x: 600, y: 0 }, config: {} },
    ]
    for (const node of cases) {
      const issue = issuesFor(withGraph({ nodes: [...validGraph.nodes, node], edges: [...validGraph.edges, { id: `edge-${node.id}`, source: 'action', target: node.id }] })).find(item => item.nodeId === node.id)
      expect(issue?.message).toContain('缺少必填配置')
    }
  })
})
