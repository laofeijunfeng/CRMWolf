<script setup lang="ts">
import type { AgentUIBlock, EntityRef } from '@/schemas/agent-contracts'
import { isAgentEntityOpenable } from '@/components/agent/agentEntityNavigation'

type EntityListBlock = Extract<AgentUIBlock, { type: 'entity_list' }>

defineProps<{
  block: EntityListBlock
}>()

const emit = defineEmits<{
  'open-entity': [entityRef: EntityRef]
}>()

</script>

<template>
  <section class="grid gap-2" :aria-label="block.entity_type === 'customer' ? '公司列表' : '实体列表'">
    <template v-for="item in block.items" :key="item.entity_ref.ref_id">
      <button
        v-if="isAgentEntityOpenable(item.entity_ref)"
        type="button"
        class="flex min-h-11 w-full items-center rounded-xl border border-border bg-card px-4 py-3 text-left text-sm font-semibold text-foreground transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        :aria-label="`打开${item.entity_ref.display_name}详情`"
        @click="emit('open-entity', item.entity_ref)"
      >
        <span class="min-w-0 truncate">{{ item.entity_ref.display_name }}</span>
      </button>
      <div
        v-else
        class="flex min-h-11 w-full items-center rounded-xl border border-border bg-card px-4 py-3 text-sm font-semibold text-foreground"
      >
        <span class="min-w-0 truncate">{{ item.entity_ref.display_name }}</span>
      </div>
    </template>
    <p v-if="block.items.length === 0" class="m-0 text-xs text-muted-foreground">没有符合条件的记录。</p>
  </section>
</template>
