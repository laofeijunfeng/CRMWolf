import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { DetailContextNode } from '@/types/detailContext'

export interface DetailContextStack {
  nodes: Ref<DetailContextNode[]>
  current: ComputedRef<DetailContextNode | null>
  depth: ComputedRef<number>
  canGoBack: ComputedRef<boolean>
  push: (node: DetailContextNode) => void
  replace: (node: DetailContextNode) => void
  pop: () => DetailContextNode | null
  closeRoot: () => void
  reset: (nodes?: readonly DetailContextNode[]) => void
}

const DEFAULT_MAX_DEPTH = 5

const sameNode = (left: DetailContextNode, right: DetailContextNode): boolean =>
  left.type === right.type && left.id === right.id

/**
 * Manages the bounded object context stack inside one detail surface.
 *
 * The composable is deliberately UI-agnostic: callers decide how each node is
 * rendered while this module owns the push/back/close semantics.
 */
export function useDetailContextStack(maxDepth = DEFAULT_MAX_DEPTH): DetailContextStack {
  const nodes = ref<DetailContextNode[]>([])

  const current = computed<DetailContextNode | null>(() => {
    const lastIndex = nodes.value.length - 1
    return lastIndex >= 0 ? nodes.value[lastIndex] ?? null : null
  })

  const depth = computed<number>(() => nodes.value.length)
  const canGoBack = computed<boolean>(() => nodes.value.length > 1)

  const push = (node: DetailContextNode): void => {
    const existingIndex = nodes.value.findIndex(item => sameNode(item, node))
    if (existingIndex >= 0) {
      nodes.value = nodes.value.slice(0, existingIndex + 1)
      nodes.value[existingIndex] = node
      return
    }

    const nextNodes = [...nodes.value, node]
    nodes.value = nextNodes.slice(-Math.max(1, maxDepth))
  }

  const replace = (node: DetailContextNode): void => {
    if (nodes.value.length === 0) {
      nodes.value = [node]
      return
    }
    nodes.value = [...nodes.value.slice(0, -1), node]
  }

  const pop = (): DetailContextNode | null => {
    if (nodes.value.length <= 1) return current.value
    const popped = current.value
    nodes.value = nodes.value.slice(0, -1)
    return popped
  }

  const closeRoot = (): void => {
    nodes.value = []
  }

  const reset = (nextNodes: readonly DetailContextNode[] = []): void => {
    nodes.value = [...nextNodes].slice(-Math.max(1, maxDepth))
  }

  return {
    nodes,
    current,
    depth,
    canGoBack,
    push,
    replace,
    pop,
    closeRoot,
    reset
  }
}
