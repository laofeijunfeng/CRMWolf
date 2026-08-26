<script setup lang="ts">
import AgentMessageBody from '@/components/agent/AgentMessageBody.vue'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type TextBlock = Extract<AgentUIBlock, { type: 'text' }>

defineProps<{ block: TextBlock }>()
</script>

<template>
  <AgentMessageBody :content="block.text" :format="block.format" />
</template>
