<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'

import AgentUIBanner from './AgentUIBanner.vue'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type ErrorBlock = Extract<AgentUIBlock, { type: 'error' }>

defineProps<{ block: ErrorBlock }>()
</script>

<template>
  <AgentUIBanner role="alert" tone="danger" :icon="AlertCircle" :title="block.title">
    <p class="m-0 text-caption text-muted-foreground">{{ block.message }}</p>
    <p class="m-0 text-caption text-muted-foreground">{{ block.retryable ? '可以重试' : '暂时不能重试' }}</p>
    <p v-if="block.trace_id" class="m-0 text-caption text-muted-foreground">追踪编号：{{ block.trace_id }}</p>
  </AgentUIBanner>
</template>
