<script setup lang="ts">
import { computed } from 'vue'
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@vue-flow/core'
import type { WorkflowInsertContext } from './workflowGraphEditing'

export interface WorkflowInsertEdgeData {
  insertionContext: WorkflowInsertContext
}

const props = defineProps<EdgeProps<WorkflowInsertEdgeData>>()
const emit = defineEmits<{ insert: [edgeId: string] }>()
const edgeGeometry = computed(() => getBezierPath(props))
const edgePath = computed(() => edgeGeometry.value[0])
const midpointStyle = computed(() => ({ transform: `translate(-50%, -50%) translate(${edgeGeometry.value[1]}px,${edgeGeometry.value[2]}px)` }))

function insert(): void { emit('insert', props.id) }
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    insert()
  }
}
</script>

<template>
  <BaseEdge :id="props.id" :path="edgePath" :marker-end="props.markerEnd" />
  <EdgeLabelRenderer>
    <div class="nodrag nopan pointer-events-auto absolute" :style="midpointStyle">
      <button
        type="button"
        class="flex size-7 items-center justify-center rounded-full border border-primary bg-background text-lg leading-none text-primary shadow-sm transition-colors hover:bg-primary hover:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :data-testid="`workflow-insert-edge-${props.id}`"
        aria-label="在此处添加节点"
        @click="insert"
        @keydown="onKeydown"
      >
        <span aria-hidden="true">+</span>
        <span class="sr-only">添加节点</span>
      </button>
    </div>
  </EdgeLabelRenderer>
</template>
