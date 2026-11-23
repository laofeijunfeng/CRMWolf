<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight } from 'lucide-vue-next'

import ListCard from '@/components/crmwolf/ListCard.vue'

import type { AgentUIBlock, EntityRef } from '@/schemas/agent-contracts'
import { isAgentEntityOpenable } from '@/components/agent/agentEntityNavigation'

type EntityListBlock = Extract<AgentUIBlock, { type: 'entity_list' }>

interface EntityListRow {
  id: string
  name: string
  entityRef: EntityRef
  openable: boolean
}

const props = defineProps<{
  block: EntityListBlock
}>()

const emit = defineEmits<{
  'open-entity': [entityRef: EntityRef]
}>()

const rows = computed<EntityListRow[]>(() => props.block.items.map((item, index) => ({
  id: `${item.entity_ref.ref_id}#${index}`,
  name: item.entity_ref.display_name,
  entityRef: item.entity_ref,
  openable: isAgentEntityOpenable(item.entity_ref),
})))

const openRow = (row: EntityListRow): void => {
  emit('open-entity', row.entityRef)
}
</script>

<template>
  <ListCard
    density="compact"
    :title="block.entity_type === 'customer' ? '公司列表' : '实体列表'"
    :items="rows"
    empty-text="没有符合条件的记录。"
    :row-interactive="(row: EntityListRow) => row.openable"
    @row-click="openRow"
  >
    <template #itemMain="{ item }">
      <span class="block truncate text-body text-foreground">{{ item.name }}</span>
    </template>
    <template #itemMeta="{ item }">
      <ChevronRight v-if="item.openable" class="size-icon-xs shrink-0 text-muted-foreground" aria-hidden="true" />
    </template>
  </ListCard>
</template>
