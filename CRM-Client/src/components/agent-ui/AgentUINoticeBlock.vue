<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info } from 'lucide-vue-next'

import AgentUIBanner from './AgentUIBanner.vue'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type NoticeBlock = Extract<AgentUIBlock, { type: 'notice' }>

defineProps<{ block: NoticeBlock }>()

const iconByTone = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle
} satisfies Record<NoticeBlock['tone'], unknown>
</script>

<template>
  <AgentUIBanner
    v-if="block.title === null"
    tone="neutral"
    role="status"
    :aria-label="block.text"
    data-agent-ui-notice="text"
  >
    <p class="m-0 text-caption text-muted-foreground">{{ block.text }}</p>
  </AgentUIBanner>
  <AgentUIBanner
    v-else
    :tone="block.tone"
    :icon="iconByTone[block.tone]"
    :title="block.title"
    role="status"
    :aria-label="block.title"
    data-agent-ui-notice="titled"
  >
    <p class="m-0 text-caption text-muted-foreground">{{ block.text }}</p>
  </AgentUIBanner>
</template>
