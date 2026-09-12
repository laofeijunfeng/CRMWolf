import { describe, expect, it } from 'vitest'
import {
  getEdgeInsertContext,
  getTerminalInsertContexts,
  insertNodeIntoGraph,
  type WorkflowEditorEdge,
  type WorkflowEditorNode,
} from '../workflowGraphEditing'

const node = (id: string): WorkflowEditorNode => ({
  id,
  type: 'action.notify',
  position: { x: 0, y: 0 },
  data: { config: {}, hasError: false, errorMessage: '' },
})

const edge = (id: string, source: string, target: string): WorkflowEditorEdge => ({ id, source, target })

const newNode = node('inserted')

describe('workflow graph editing', () => {
  it('splits exactly the referenced edge when inserting between nodes', () => {
    const nodes = [node('source'), node('target'), node('unrelated')]
    const edges = [edge('main', 'source', 'target'), edge('other', 'target', 'unrelated')]

    const result = insertNodeIntoGraph(nodes, edges, newNode, {
      kind: 'between-edge',
      edgeId: 'main',
      sourceNodeId: 'source',
      targetNodeId: 'target',
    })

    expect(result.nodes).toEqual([...nodes, newNode])
    expect(result.edges).toHaveLength(3)
    expect(result.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'source', target: 'inserted' }),
      expect.objectContaining({ source: 'inserted', target: 'target' }),
      edge('other', 'target', 'unrelated'),
    ]))
    expect(result.edges.find(candidate => candidate.source === 'source' && candidate.target === 'target')).toBeUndefined()
    expect(nodes).toHaveLength(3)
    expect(edges).toEqual([edge('main', 'source', 'target'), edge('other', 'target', 'unrelated')])
  })

  it('adds an edge after the explicitly selected node', () => {
    const nodes = [node('source')]
    const edges = [edge('existing', 'source', 'other')]

    const result = insertNodeIntoGraph(nodes, edges, newNode, {
      kind: 'after-node',
      sourceNodeId: 'source',
    })
    expect(result.edges).toHaveLength(2)
    expect(result.edges).toEqual(expect.arrayContaining([
      ...edges,
      expect.objectContaining({ source: 'source', target: 'inserted' }),
    ]))
    expect(result.nodes).toEqual([...nodes, newNode])
  })

  it('adds a root node without creating an edge', () => {
    const nodes = [node('existing')]
    const edges = [edge('existing-edge', 'existing', 'other')]

    const result = insertNodeIntoGraph(nodes, edges, newNode, { kind: 'root' })

    expect(result).toEqual({ nodes: [...nodes, newNode], edges })
  })

  it('returns the original graph unchanged for a missing or invalid context', () => {
    const nodes = [node('source'), node('target')]
    const edges = [edge('main', 'source', 'target')]

    const missing = insertNodeIntoGraph(nodes, edges, newNode, { kind: 'after-node' })
    const invalid = insertNodeIntoGraph(nodes, edges, newNode, {
      kind: 'between-edge',
      edgeId: 'main',
      sourceNodeId: 'wrong-source',
      targetNodeId: 'target',
    })

    expect(missing.nodes).toBe(nodes)
    expect(missing.edges).toBe(edges)
    expect(invalid.nodes).toBe(nodes)
    expect(invalid.edges).toBe(edges)
  })

  it('returns one terminal insertion context for each node without outgoing edges', () => {
    const nodes = [node('root'), node('branch-a'), node('branch-b'), node('target')]
    const edges = [edge('a', 'root', 'branch-a'), edge('b', 'root', 'branch-b'), edge('c', 'branch-a', 'target')]

    expect(getTerminalInsertContexts(nodes, edges)).toEqual([
      { kind: 'after-node', sourceNodeId: 'branch-b' },
      { kind: 'after-node', sourceNodeId: 'target' },
    ])
  })

  it('derives an explicit split context from an edge', () => {
    expect(getEdgeInsertContext(edge('main', 'source', 'target'))).toEqual({
      kind: 'between-edge',
      edgeId: 'main',
      sourceNodeId: 'source',
      targetNodeId: 'target',
    })
  })
})
