<script setup lang="ts">
import AgentUIActionBar from './AgentUIActionBar.vue'
import { formatAgentUIValue } from './agentUIFormatting'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type EntityCardBlock = Extract<AgentUIBlock, { type: 'entity_card' }>

defineProps<{
  block: EntityCardBlock
  disabled?: boolean
}>()

const emit = defineEmits<{
  action: [actionId: string]
}>()
</script>

<template>
  <article class="grid min-w-0 gap-space-3 rounded-lg border border-border bg-card p-space-4 text-foreground">
    <h3 class="m-0 text-body font-semibold text-foreground">{{ block.title }}</h3>
    <section v-for="section in block.sections" :key="section.key" class="grid gap-space-2">
      <h4 v-if="section.title" class="m-0 text-caption font-medium text-muted-foreground">{{ section.title }}</h4>
      <dl class="m-0 grid grid-cols-1 gap-x-space-4 gap-y-space-2 sm:grid-cols-2">
        <div v-for="field in section.fields" :key="field.key" class="grid min-w-0 gap-space-1">
          <dt class="m-0 text-caption font-medium text-muted-foreground">{{ field.label }}</dt>
          <dd class="m-0 break-words text-body text-foreground">{{ formatAgentUIValue(field.value) }}</dd>
        </div>
      </dl>
    </section>
    <AgentUIActionBar :actions="block.actions" :disabled="disabled === true" @action="emit('action', $event)" />
  </article>
</template>
