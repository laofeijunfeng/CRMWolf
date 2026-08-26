<script setup lang="ts">
import { computed } from 'vue'
import AgentUIActionBar from './AgentUIActionBar.vue'
import AgentUIActionResultBlock from './AgentUIActionResultBlock.vue'
import AgentUIEntityCardBlock from './AgentUIEntityCardBlock.vue'
import AgentUIEntityListBlock from './AgentUIEntityListBlock.vue'
import AgentUIErrorBlock from './AgentUIErrorBlock.vue'
import AgentUICompactTaskList from './AgentUICompactTaskList.vue'
import AgentUIInteractionBlock from './AgentUIInteractionBlock.vue'
import AgentUIMetricGroupBlock from './AgentUIMetricGroupBlock.vue'
import AgentUINoticeBlock from './AgentUINoticeBlock.vue'
import AgentUIPaginationBlock from './AgentUIPaginationBlock.vue'
import AgentUIProcessBlock from './AgentUIProcessBlock.vue'
import AgentUITableBlock from './AgentUITableBlock.vue'
import AgentUITextBlock from './AgentUITextBlock.vue'
import AgentUITimelineBlock from './AgentUITimelineBlock.vue'
import type { AgentUIBlock, AgentUIEnvelope, EntityRef, JsonObject } from '@/schemas/agent-contracts'

type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>

const EMPTY_ACTION_IDS: ReadonlySet<string> = new Set()

const props = defineProps<{
  message: AgentUIEnvelope
  disabled?: boolean
  lockedActionIds?: ReadonlySet<string>
}>()

const emit = defineEmits<{
  action: [actionId: string]
  interaction: [actionId: string, values: JsonObject]
  'open-entity': [entityRef: EntityRef]
}>()

const forwardInteraction = (actionId: string, values: JsonObject): void => {
  emit('interaction', actionId, values)
}

const isInteractionLocked = (actionId: string | null): boolean => (
  actionId !== null && props.lockedActionIds?.has(actionId) === true
)

const compactTaskBlocks = computed(() => props.message.blocks.filter(
  (block): block is InteractionBlock => (
    block.type === 'interaction' && block.presentation === 'COMPACT_TASK_COMPLETION'
  )
))
const isCompactTaskMessage = computed(() => (
  compactTaskBlocks.value.length > 0
  && compactTaskBlocks.value.length === props.message.blocks.length
))
</script>

<template>
  <div
    class="agent-ui-message grid min-w-0 gap-3"
    :aria-label="message.metadata.accessibility_label ?? undefined"
  >
    <AgentUICompactTaskList
      v-if="isCompactTaskMessage"
      :blocks="compactTaskBlocks"
      :disabled="disabled === true"
      :locked-action-ids="lockedActionIds ?? EMPTY_ACTION_IDS"
      @submit="forwardInteraction"
    />
    <template v-else v-for="block in message.blocks" :key="block.id">
      <AgentUITextBlock v-if="block.type === 'text'" :block="block" />
      <AgentUIEntityListBlock
        v-else-if="block.type === 'entity_list'"
        :block="block"
        @open-entity="emit('open-entity', $event)"
      />
      <AgentUIEntityCardBlock
        v-else-if="block.type === 'entity_card'"
        :block="block"
        :disabled="disabled === true"
        @action="emit('action', $event)"
      />
      <AgentUITableBlock v-else-if="block.type === 'table'" :block="block" />
      <AgentUITimelineBlock v-else-if="block.type === 'timeline'" :block="block" />
      <AgentUIProcessBlock v-else-if="block.type === 'process'" :block="block" />
      <AgentUIMetricGroupBlock v-else-if="block.type === 'metric_group'" :block="block" />
      <AgentUINoticeBlock v-else-if="block.type === 'notice'" :block="block" />
      <AgentUIErrorBlock v-else-if="block.type === 'error'" :block="block" />
      <AgentUIInteractionBlock
        v-else-if="block.type === 'interaction'"
        :block="block"
        :disabled="disabled === true"
        :locked="isInteractionLocked(block.submit_action_id)"
        @submit="forwardInteraction"
      />
      <AgentUIActionResultBlock v-else-if="block.type === 'action_result'" :block="block" />
      <AgentUIPaginationBlock
        v-else
        :block="block"
        :disabled="disabled === true"
        @action="emit('action', $event)"
      />
    </template>
    <AgentUIActionBar
      :actions="message.suggested_actions"
      :disabled="disabled === true"
      @action="emit('action', $event)"
    />
  </div>
</template>
