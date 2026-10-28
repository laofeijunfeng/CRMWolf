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
  <section class="overflow-hidden rounded-wolf-surface border border-border bg-white" :aria-label="block.entity_type === 'customer' ? '公司列表' : '实体列表'">
    <template v-for="item in block.items" :key="item.entity_ref.ref_id">
      <button
        v-if="isAgentEntityOpenable(item.entity_ref)"
        type="button"
        class="flex min-h-11 w-full items-center border-t border-border bg-white px-3 py-2.5 text-left text-sm font-semibold text-foreground first:border-t-0 hover:bg-[#eff6ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :aria-label="`打开${item.entity_ref.display_name}详情`"
        @click="emit('open-entity', item.entity_ref)"
      >
        <span class="min-w-0 truncate">{{ item.entity_ref.display_name }}</span>
      </button>
      <div
        v-else
        class="flex min-h-11 w-full items-center border-t border-border bg-white px-3 py-2.5 text-sm font-semibold text-foreground first:border-t-0"
      >
        <span class="min-w-0 truncate">{{ item.entity_ref.display_name }}</span>
      </div>
    </template>
    <p v-if="block.items.length === 0" class="m-0 text-xs text-muted-foreground">没有符合条件的记录。</p>
  </section>
</template>
