<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

type ErrorBlock = Extract<AgentUIBlock, { type: 'error' }>

defineProps<{ block: ErrorBlock }>()
</script>

<template>
  <aside class="grid grid-cols-[18px_minmax(0,1fr)] gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3" role="alert">
    <AlertCircle class="h-[18px] w-[18px] text-destructive" aria-hidden="true" />
    <div>
      <strong class="text-foreground">{{ block.title }}</strong>
      <p class="mb-0 mt-1 text-muted-foreground">{{ block.message }}</p>
      <small v-if="block.trace_id" class="text-muted-foreground">追踪编号：{{ block.trace_id }}</small>
    </div>
  </aside>
</template>
