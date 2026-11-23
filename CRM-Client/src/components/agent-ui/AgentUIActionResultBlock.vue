<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, CheckCircle2, CircleSlash2 } from 'lucide-vue-next'

import AgentUIBanner from './AgentUIBanner.vue'
import { Button } from '@/components/ui/button'
import type { AgentUIBlock, EntityRef } from '@/schemas/agent-contracts'
import { isAgentEntityOpenable } from '@/components/agent/agentEntityNavigation'

type ActionResultBlock = Extract<AgentUIBlock, { type: 'action_result' }>

const props = defineProps<{ block: ActionResultBlock }>()
const messageLines = computed(() => props.block.message.split('\n').map(line => line.trim()).filter(line => line !== ''))
const multiline = computed(() => messageLines.value.length > 1)
const openableEntity = computed<EntityRef | null>(() => (
  props.block.entity_ref && isAgentEntityOpenable(props.block.entity_ref) ? props.block.entity_ref : null
))

const emit = defineEmits<{
  'open-entity': [entityRef: EntityRef]
}>()

const iconByStatus = {
  SUCCESS: CheckCircle2,
  FAILED: AlertCircle,
  CANCELLED: CircleSlash2
} satisfies Record<ActionResultBlock['status'], unknown>

const toneByStatus = {
  SUCCESS: 'success',
  FAILED: 'danger',
  CANCELLED: 'neutral'
} as const satisfies Record<ActionResultBlock['status'], string>
</script>

<template>
  <AgentUIBanner
    :tone="toneByStatus[block.status]"
    :icon="iconByStatus[block.status]"
    :title="block.title"
    :role="block.status === 'FAILED' ? 'alert' : 'status'"
  >
    <template v-if="multiline">
      <p v-for="(line, index) in messageLines" :key="index" class="m-0 text-body text-foreground">{{ line }}</p>
    </template>
    <p v-else class="m-0 text-caption text-muted-foreground">{{ block.message }}</p>
    <Button
      v-if="openableEntity"
      type="button"
      variant="link"
      size="sm"
      class="max-w-full justify-start"
      :aria-label="`打开${openableEntity.display_name}详情`"
      @click="emit('open-entity', openableEntity)"
    >
      {{ openableEntity.display_name }}
    </Button>
    <p v-else-if="block.entity_ref" class="m-0 max-w-full truncate text-caption text-muted-foreground">
      {{ block.entity_ref.display_name }}
    </p>
  </AgentUIBanner>
</template>
