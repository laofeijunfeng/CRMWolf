<script setup lang="ts">
import { computed } from 'vue'
import JourneyStyleBoardView, {
  type JourneyBoardColumn,
} from '@/components/crmwolf/JourneyStyleBoardView.vue'
import type { BoardCardActivation } from '@/components/crmwolf/boardTypes'
import type { ContractBoardResponse } from '@/schemas/contractBoard'

const props = withDefaults(defineProps<{
  response?: ContractBoardResponse | null
  loading?: boolean
  refreshing?: boolean
  stale?: boolean
  error?: Error | null
}>(), {
  response: null,
  loading: false,
  refreshing: false,
  stale: false,
  error: null,
})

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  retry: []
}>()

const columns = computed<JourneyBoardColumn[] | null>(() => {
  const response = props.response
  if (response === null) return null
  return response.columns.map((column) => ({
    key: column.key,
    label: column.label,
    tone: column.tone,
    countLabel: String(column.count),
    cards: column.items.map((item) => ({
      id: item.id,
      context: item.metadata.customer_name ?? '',
      title: item.title,
      owner: item.owner?.name ?? '',
    })),
  }))
})
</script>

<template>
  <JourneyStyleBoardView
    :columns="columns"
    :loading="props.loading"
    :refreshing="props.refreshing"
    :stale="props.stale"
    :error="props.error"
    @activate-card="emit('activate-card', $event)"
    @retry="emit('retry')"
  />
</template>
