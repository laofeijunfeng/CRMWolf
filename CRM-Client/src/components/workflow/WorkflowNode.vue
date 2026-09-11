<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position, type NodeProps } from '@vue-flow/core'
import { WORKFLOW_NODE_REGISTRY, type WorkflowNodeType } from './workflowNodeRegistry'

interface NodeData { config?: Record<string, unknown>; hasError?: boolean; errorMessage?: string }
const props = defineProps<NodeProps<NodeData>>()
const definition = computed(() => WORKFLOW_NODE_REGISTRY[props.type as WorkflowNodeType])
const summary = computed(() => definition.value?.summary(props.data.config ?? {}))
</script>
<template>
  <button
    type="button"
    :data-testid="`workflow-node-${props.type}`"
    class="workflow-node min-w-48 rounded-lg border bg-background p-3 text-left shadow-sm"
    :class="props.data.hasError ? 'border-wolf-danger ring-2 ring-wolf-danger/30' : 'border-border'"
    @click="$emit('select')"
  >
    <Handle type="target" :position="Position.Left" />
    <div class="flex items-center gap-2 text-sm font-semibold"><component :is="definition?.icon" class="size-4" aria-hidden="true" />{{ definition?.label ?? props.type }}</div>
    <p class="mt-1 text-xs text-muted-foreground">{{ summary }}</p>
    <p v-if="props.data.errorMessage" class="mt-1 text-xs text-wolf-danger">{{ props.data.errorMessage }}</p>
    <Handle type="source" :position="Position.Right" />
  </button>
</template>
