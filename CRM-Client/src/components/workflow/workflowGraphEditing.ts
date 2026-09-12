export interface WorkflowEditorNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: {
    config: Record<string, unknown>
    hasError: boolean
    errorMessage: string
  }
}

export interface WorkflowEditorEdge {
  id: string
  source: string
  target: string
}

export interface WorkflowInsertContext {
  kind: 'between-edge' | 'after-node' | 'root'
  sourceNodeId?: string
  targetNodeId?: string
  edgeId?: string
}

function nextEdgeId(base: string, edges: WorkflowEditorEdge[]): string {
  const existingIds = new Set(edges.map(edge => edge.id))
  let id = base
  let suffix = 2
  while (existingIds.has(id)) {
    id = `${base}-${suffix}`
    suffix += 1
  }
  return id
}

export function insertNodeIntoGraph(
  nodes: WorkflowEditorNode[],
  edges: WorkflowEditorEdge[],
  node: WorkflowEditorNode,
  context: WorkflowInsertContext,
): { nodes: WorkflowEditorNode[]; edges: WorkflowEditorEdge[] } {
  if (nodes.some(existing => existing.id === node.id)) return { nodes, edges }

  if (context.kind === 'root') {
    return { nodes: [...nodes, node], edges: [...edges] }
  }

  const sourceNodeId = context.sourceNodeId
  if (sourceNodeId === undefined || !nodes.some(existing => existing.id === sourceNodeId)) return { nodes, edges }

  if (context.kind === 'after-node') {
    const edgeId = nextEdgeId(`insert-${sourceNodeId}-${node.id}`, edges)
    return {
      nodes: [...nodes, node],
      edges: [...edges, { id: edgeId, source: sourceNodeId, target: node.id }],
    }
  }

  if (context.kind === 'between-edge') {
    const targetNodeId = context.targetNodeId
    if (
      targetNodeId === undefined
      || context.edgeId === undefined
      || !nodes.some(existing => existing.id === targetNodeId)
    ) return { nodes, edges }
    const edgeIndex = edges.findIndex(edge => edge.id === context.edgeId)
    const referencedEdge = edgeIndex === -1 ? undefined : edges[edgeIndex]
    if (
      referencedEdge === undefined
      || referencedEdge.source !== sourceNodeId
      || referencedEdge.target !== targetNodeId
    ) return { nodes, edges }
    const remainingEdges = edges.filter((_, index) => index !== edgeIndex)
    const sourceEdgeId = nextEdgeId(`insert-${node.id}-from-${sourceNodeId}`, remainingEdges)
    const sourceEdge = { id: sourceEdgeId, source: sourceNodeId, target: node.id }
    const targetEdgeId = nextEdgeId(`insert-${node.id}-to-${targetNodeId}`, [...remainingEdges, sourceEdge])
    return {
      nodes: [...nodes, node],
      edges: [...remainingEdges, sourceEdge, { id: targetEdgeId, source: node.id, target: targetNodeId }],
    }
  }

  return { nodes, edges }
}

export function getTerminalInsertContexts(
  nodes: WorkflowEditorNode[],
  edges: WorkflowEditorEdge[],
): WorkflowInsertContext[] {
  const outgoingSources = new Set(edges.map(edge => edge.source))
  return nodes
    .filter(node => !outgoingSources.has(node.id))
    .map(node => ({ kind: 'after-node' as const, sourceNodeId: node.id }))
}

export function getEdgeInsertContext(edge: WorkflowEditorEdge): WorkflowInsertContext {
  return {
    kind: 'between-edge',
    edgeId: edge.id,
    sourceNodeId: edge.source,
    targetNodeId: edge.target,
  }
}
