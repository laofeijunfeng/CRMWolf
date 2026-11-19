<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

type ErrorBlock = Extract<AgentUIBlock, { type: 'error' }>

defineProps<{ block: ErrorBlock }>()
</script>

<template>
  <aside class="grid grid-cols-[22px_minmax(0,1fr)] gap-2 rounded-lg border border-danger/30 bg-danger/5 p-3" role="alert">
    <span class="grid size-[22px] place-items-center rounded-md bg-danger/12 text-danger" aria-hidden="true">
      <AlertCircle class="h-3.5 w-3.5" />
    </span>
    <div>
      <strong class="text-[13px] text-foreground">{{ block.title }}</strong>
      <p class="mb-0 mt-1 text-[12px] text-muted-foreground">{{ block.message }}</p>
      <p class="mb-0 mt-1 text-[11px] text-muted-foreground">{{ block.retryable ? '可以重试' : '不能盲目重试' }}</p>
      <small v-if="block.trace_id" class="text-muted-foreground">追踪编号：{{ block.trace_id }}</small>
    </div>
  </aside>
</template>
