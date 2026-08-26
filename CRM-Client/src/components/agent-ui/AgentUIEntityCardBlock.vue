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
  <article class="grid gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground">
    <h3 class="m-0 text-base font-semibold text-foreground">{{ block.title }}</h3>
    <section v-for="section in block.sections" :key="section.key" class="grid gap-2">
      <h4 v-if="section.title" class="m-0 text-xs font-medium text-muted-foreground">{{ section.title }}</h4>
      <dl class="m-0 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-x-4 gap-y-2">
        <div v-for="field in section.fields" :key="field.key" class="grid min-w-0 gap-0.5">
          <dt class="m-0 text-xs font-medium text-muted-foreground">{{ field.label }}</dt>
          <dd class="m-0 break-words text-foreground">{{ formatAgentUIValue(field.value) }}</dd>
        </div>
      </dl>
    </section>
    <AgentUIActionBar :actions="block.actions" :disabled="disabled === true" @action="emit('action', $event)" />
  </article>
</template>
