import {
  WORKFLOW_NODE_REGISTRY,
  type WorkflowNodeType,
} from './workflowNodeRegistry'

export interface WorkflowGraphNode {
  id: string
  type: string
  position?: { x: number; y: number }
  config?: Record<string, unknown>
  [key: string]: unknown
}

export interface WorkflowGraphEdge {
  id: string
  source: string
  target: string
  [key: string]: unknown
}

export interface WorkflowGraph {
  schema_version?: number
  nodes: WorkflowGraphNode[]
  edges: WorkflowGraphEdge[]
  [key: string]: unknown
}

export interface WorkflowValidationIssue {
  nodeId?: string
  message: string
}

const VALID_OPERATORS = new Set(['eq', 'neq', 'gt', 'lt', 'in'])
const VALID_NOTIFY_TARGETS = new Set(['owner', 'role', 'users'])

const isNonEmptyValue = (value: unknown): boolean => {
  if (value === null || value === undefined) {
    return false
  }
  return typeof value !== 'string' || value.trim() !== ''
}

const isWorkflowNodeType = (type: string): type is WorkflowNodeType => type in WORKFLOW_NODE_REGISTRY

export function validateWorkflow(graph: WorkflowGraph, name: string): WorkflowValidationIssue[] {
  const issues: WorkflowValidationIssue[] = []
  const trimmedName = name.trim()
  if (trimmedName === '') {
    issues.push({ message: '工作流名称不能为空' })
  } else if (trimmedName.length > 100) {
    issues.push({ message: '工作流名称不能超过 100 个字符' })
  }

  if (graph.schema_version !== undefined && graph.schema_version !== 1) {
    issues.push({ message: 'schema_version 必须为 1' })
  }
  if (!Array.isArray(graph.nodes) || graph.nodes.length === 0) {
    issues.push({ message: '工作流至少需要一个节点' })
    return issues
  }
  if (!Array.isArray(graph.edges)) {
    issues.push({ message: '工作流边必须是列表' })
    return issues
  }

  const nodesById = new Map<string, WorkflowGraphNode>()
  let triggerId: string | undefined
  let triggerCount = 0

  for (const node of graph.nodes) {
    if (typeof node.id !== 'string' || node.id.trim() === '') {
      issues.push({ message: '节点 id 必须是非空字符串' })
      continue
    }
    if (nodesById.has(node.id)) {
      issues.push({ nodeId: node.id, message: `节点 id 重复：${node.id}` })
      continue
    }
    nodesById.set(node.id, node)

    if (!isWorkflowNodeType(node.type)) {
      issues.push({ nodeId: node.id, message: `节点类型未知：${node.type}` })
      continue
    }
    const definition = WORKFLOW_NODE_REGISTRY[node.type]
    if (definition.isTrigger) {
      triggerCount += 1
      triggerId = node.id
    }
    const config = node.config ?? {}
    for (const field of definition.requiredFields) {
      if (!isNonEmptyValue(config[field])) {
        issues.push({ nodeId: node.id, message: `缺少必填配置：${field}` })
      }
    }
    if (node.type === 'control.condition' && !VALID_OPERATORS.has(String(config['operator']))) {
      issues.push({ nodeId: node.id, message: 'operator 必须是 eq、neq、gt、lt 或 in' })
    }
    if (node.type === 'action.notify' && !VALID_NOTIFY_TARGETS.has(String(config['notify_target']))) {
      issues.push({ nodeId: node.id, message: 'notify_target 必须是 owner、role 或 users' })
    }
  }

  if (triggerCount === 0) {
    issues.push({ message: '工作流必须恰好包含一个 trigger 节点' })
  } else if (triggerCount > 1) {
    issues.push({ message: '工作流必须恰好包含一个 trigger 节点' })
  }

  const adjacency = new Map<string, string[]>()
  for (const nodeId of nodesById.keys()) {
    adjacency.set(nodeId, [])
  }
  for (const edge of graph.edges) {
    const source = nodesById.get(edge.source)
    const target = nodesById.get(edge.target)
    if (source === undefined || target === undefined) {
      issues.push({ message: `边引用了不存在的节点：${edge.source} -> ${edge.target}` })
      continue
    }
    if (edge.source === edge.target) {
      issues.push({ nodeId: edge.source, message: '不允许自环边' })
    }
    if (isWorkflowNodeType(target.type) && WORKFLOW_NODE_REGISTRY[target.type].isTrigger) {
      issues.push({ nodeId: target.id, message: '边的目标不能是 trigger 节点' })
    }
    adjacency.get(edge.source)?.push(edge.target)
  }

  if (triggerId !== undefined && triggerCount === 1) {
    const reachable = new Set<string>([triggerId])
    const pending: string[] = [triggerId]
    while (pending.length > 0) {
      const current = pending.shift()
      if (current === undefined) {
        continue
      }
      for (const next of adjacency.get(current) ?? []) {
        if (!reachable.has(next)) {
          reachable.add(next)
          pending.push(next)
        }
      }
    }
    for (const node of graph.nodes) {
      if (node.id !== triggerId && typeof node.id === 'string' && !reachable.has(node.id)) {
        issues.push({ nodeId: node.id, message: '节点从 trigger 不可达' })
      }
    }
  }

  return issues
}
