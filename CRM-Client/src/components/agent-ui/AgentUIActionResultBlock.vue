<script setup lang="ts">
import { AlertCircle, CheckCircle2, CircleSlash2 } from 'lucide-vue-next'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

type ActionResultBlock = Extract<AgentUIBlock, { type: 'action_result' }>

defineProps<{ block: ActionResultBlock }>()

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
  <section class="grid grid-cols-[18px_minmax(0,1fr)] gap-2 rounded-xl border p-3" :class="classesByStatus[block.status]">
    <component :is="iconByStatus[block.status]" class="h-[18px] w-[18px]" aria-hidden="true" />
    <div>
      <strong class="text-foreground">{{ block.title }}</strong>
      <p class="mb-0 mt-1 text-muted-foreground">{{ block.message }}</p>
      <span v-if="block.entity_ref" class="text-xs text-primary">{{ block.entity_ref.display_name }}</span>
    </div>
  </section>
</template>
