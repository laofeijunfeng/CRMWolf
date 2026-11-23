<script setup lang="ts">
import AgentUIInteractionBlock from './AgentUIInteractionBlock.vue'
import type { AgentUIBlock, JsonObject } from '@/schemas/agent-contracts'

type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>

const props = defineProps<{
  blocks: InteractionBlock[]
  disabled?: boolean
  lockedActionIds?: ReadonlySet<string>
}>()

const emit = defineEmits<{
  submit: [actionId: string, values: JsonObject]
}>()

const isLocked = (actionId: string | null): boolean => (
  actionId !== null && props.lockedActionIds?.has(actionId) === true
)

const forwardSubmit = (actionId: string, values: JsonObject): void => {
  emit('submit', actionId, values)
}
</script>

<template>
  <section
    class="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card"
    aria-label="待办任务"
  >
    <AgentUIInteractionBlock
      v-for="block in blocks"
      :key="block.id"
      :block="block"
      :disabled="disabled === true"
      :locked="isLocked(block.submit_action_id)"
      grouped
      @submit="forwardSubmit"
    />
  </section>
</template>
