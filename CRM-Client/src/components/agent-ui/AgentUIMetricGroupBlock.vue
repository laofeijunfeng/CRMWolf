<script setup lang="ts">
import { formatAgentUIValue } from './agentUIFormatting'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type MetricGroupBlock = Extract<AgentUIBlock, { type: 'metric_group' }>

defineProps<{ block: MetricGroupBlock }>()
</script>

<template>
  <!-- 单容器 hairline 分栏：每格自带上、左边线，容器把外侧那两条裁掉 -->
  <dl class="m-0 grid list-none overflow-hidden rounded-lg border border-border bg-card p-0">
    <div class="-ml-px -mt-px grid grid-cols-2 sm:grid-cols-3">
      <div
        v-for="metric in block.metrics"
        :key="metric.key"
        class="grid min-w-0 gap-space-1 border-l border-t border-border bg-card px-space-4 py-space-3"
      >
        <dt class="text-caption text-muted-foreground">{{ metric.label }}</dt>
        <dd class="m-0 text-body font-semibold tabular-nums text-foreground">{{ formatAgentUIValue(metric.value) }}</dd>
        <span v-if="metric.change" class="text-caption tabular-nums text-muted-foreground">{{ formatAgentUIValue(metric.change) }}</span>
      </div>
    </div>
  </dl>
</template>
