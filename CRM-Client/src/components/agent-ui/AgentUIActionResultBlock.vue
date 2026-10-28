<script setup lang="ts">
import { AlertCircle, CheckCircle2, CircleSlash2 } from 'lucide-vue-next'

import type { AgentUIBlock, EntityRef } from '@/schemas/agent-contracts'
import { isAgentEntityOpenable } from '@/components/agent/agentEntityNavigation'

type ActionResultBlock = Extract<AgentUIBlock, { type: 'action_result' }>

defineProps<{ block: ActionResultBlock }>()

const emit = defineEmits<{
  'open-entity': [entityRef: EntityRef]
}>()

const iconByStatus = {
  SUCCESS: CheckCircle2,
  FAILED: AlertCircle,
  CANCELLED: CircleSlash2
}

const classesByStatus = {
  SUCCESS: 'border-success/25 text-success',
  FAILED: 'border-destructive/25 text-destructive',
  CANCELLED: 'border-border bg-muted text-muted-foreground'
} satisfies Record<ActionResultBlock['status'], string>
</script>

<template>
  <section class="grid grid-cols-[22px_minmax(0,1fr)] gap-2 rounded-wolf-surface border p-3" :class="block.status === 'SUCCESS' ? 'border-[#a7f3d0] bg-[#f7fffb]' : classesByStatus[block.status]">
    <span class="grid size-[22px] place-items-center rounded-wolf text-[11px] font-semibold" :class="block.status === 'SUCCESS' ? 'bg-[#d1fae5] text-[#047857]' : 'bg-muted text-muted-foreground'" aria-hidden="true">
      <component :is="iconByStatus[block.status]" class="h-3.5 w-3.5" />
    </span>
    <div>
      <strong class="text-[13px] text-foreground">{{ block.title }}</strong>
      <p class="mb-0 mt-1 text-[12px] text-muted-foreground">{{ block.message }}</p>
      <button
        v-if="block.entity_ref && isAgentEntityOpenable(block.entity_ref)"
        type="button"
        class="mt-1 block max-w-full truncate text-left text-xs text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        :aria-label="`打开${block.entity_ref.display_name}详情`"
        @click="emit('open-entity', block.entity_ref)"
      >
        {{ block.entity_ref.display_name }}
      </button>
      <span
        v-else-if="block.entity_ref"
        class="mt-1 block max-w-full truncate text-xs text-muted-foreground"
      >
        {{ block.entity_ref.display_name }}
      </span>
    </div>
  </section>
</template>
