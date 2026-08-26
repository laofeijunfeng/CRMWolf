<script setup lang="ts">
import { formatAgentUIValue } from './agentUIFormatting'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type MetricGroupBlock = Extract<AgentUIBlock, { type: 'metric_group' }>

defineProps<{ block: MetricGroupBlock }>()
</script>

<template>
  <dl class="m-0 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
    <div v-for="metric in block.metrics" :key="metric.key" class="grid gap-1 rounded-xl border border-border bg-card p-3">
      <dt class="m-0 text-xs text-muted-foreground">{{ metric.label }}</dt>
      <dd class="m-0 text-base font-semibold text-foreground">{{ formatAgentUIValue(metric.value) }}</dd>
      <span v-if="metric.change" class="text-xs text-muted-foreground">{{ formatAgentUIValue(metric.change) }}</span>
    </div>
  </dl>
</template>
