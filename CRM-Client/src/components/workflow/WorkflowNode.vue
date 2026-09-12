<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position, type NodeProps } from '@vue-flow/core'
import { WORKFLOW_NODE_REGISTRY, type WorkflowNodeType } from './workflowNodeRegistry'

interface NodeData { config?: Record<string, unknown>; hasError?: boolean; errorMessage?: string }
const props = defineProps<NodeProps<NodeData>>()
const definition = computed(() => WORKFLOW_NODE_REGISTRY[props.type as WorkflowNodeType])
const summary = computed(() => definition.value?.summary(props.data.config ?? {}))
const categoryLabel = computed(() => ({ trigger: '触发器', control: '控制', action: '动作' })[definition.value?.category ?? 'action'])
const statusLabel = computed(() => props.data.hasError ? '需配置' : '已配置')
</script>
<template>
  <button
    type="button"
    :data-node-id="props.id"
    :data-testid="`workflow-node-${props.type}`"
    class="workflow-node min-w-48 rounded-lg border bg-background p-3 text-left shadow-sm"
    :class="props.data.hasError ? 'border-wolf-danger ring-2 ring-wolf-danger/30' : 'border-border'"
    :aria-label="`${definition?.label ?? props.type}，${categoryLabel}，${statusLabel}：${summary}`"
    @click="$emit('select')"
  >
    <Handle type="target" :position="Position.Left" />
    <div class="mb-2 flex items-center justify-between gap-2">
      <span class="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground" data-testid="workflow-node-category">{{ categoryLabel }}</span>
      <span class="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground" data-testid="workflow-node-status">{{ statusLabel }}</span>
    </div>
    <div class="flex items-center gap-2 text-sm font-semibold"><component :is="definition?.icon" class="size-4" aria-hidden="true" />{{ definition?.label ?? props.type }}</div>
    <p class="mt-1 text-xs text-muted-foreground">{{ summary }}</p>
    <p v-if="props.data.errorMessage" class="mt-1 text-xs text-wolf-danger" role="alert">{{ props.data.errorMessage }}</p>
    <Handle type="source" :position="Position.Right" />
  </button>
</template>
