<script setup lang="ts">
import { computed } from 'vue'
import { WORKFLOW_NODE_REGISTRY, WORKFLOW_NODE_TYPES, type WorkflowNodeType } from './workflowNodeRegistry'

const props = defineProps<{ triggerUsed: boolean }>()
const emit = defineEmits<{ add: [type: WorkflowNodeType] }>()
const nodeTypes = computed(() => WORKFLOW_NODE_TYPES.map(type => WORKFLOW_NODE_REGISTRY[type]))
function add(type: WorkflowNodeType): void { if (!(type === 'trigger.opportunity_stage_changed' && props.triggerUsed)) emit('add', type) }
</script>
<template>
  <aside data-testid="workflow-palette" class="workflow-node-palette grid content-start gap-2 p-4">
    <h2 class="text-sm font-semibold">节点</h2>
    <button
      v-for="definition in nodeTypes"
      :key="definition.type"
      :data-testid="`palette-node-${definition.type}`"
      type="button"
      class="flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="definition.isTrigger && props.triggerUsed"
      :aria-disabled="definition.isTrigger && props.triggerUsed ? 'true' : undefined"
      draggable="true"
      @click="add(definition.type)"
      @dragstart="$event.dataTransfer?.setData('application/workflow-node', definition.type)"
    >
      <component :is="definition.icon" class="size-4" aria-hidden="true" />
      <span>{{ definition.label }}</span>
    </button>
  </aside>
</template>
