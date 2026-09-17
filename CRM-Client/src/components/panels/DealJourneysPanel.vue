<script setup lang="ts">
/**
 * DealJourneysPanel.vue - 业务旅程列表面板
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { nextTick, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import AmountText from '@/components/crmwolf/AmountText.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { DealJourney } from '@/api/dealJourney'

const PURCHASE_TYPE_LABELS: Record<string, string> = {
  NEW: '新购',
  RENEWAL: '续购',
  EXPANSION: '增购'
}

interface Props {
  customerId: string
  journeys: DealJourney[]
  showAdd?: boolean
  highlightedJourneyId?: string | null
  restoreFocusJourneyId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  showAdd: false,
  highlightedJourneyId: null,
  restoreFocusJourneyId: null
})

const emit = defineEmits<{
  add: []
  view: [journeyPublicId: string]
}>()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (journey: DealJourney): void => {
  emit('view', journey.public_id)
}

const purchaseTypeLabel = (purchaseType: string | null): string | null => {
  if (purchaseType === null) return null
  return PURCHASE_TYPE_LABELS[purchaseType] ?? null
}

watch(
  () => props.restoreFocusJourneyId,
  async (journeyId): Promise<void> => {
    if (journeyId === undefined || journeyId === null || journeyId === '') return
    await nextTick()
    const row = document.querySelector(`[data-list-card-row-id="${journeyId}"]`)
    if (row instanceof HTMLElement) row.focus()
  },
  { immediate: true }
)
</script>

<template>
  <div class="deal-journeys-panel">
    <ListCard
      title="业务旅程"
      :items="journeys"
      empty-text="暂无业务旅程"
      row-interactive
      :highlighted-item-id="highlightedJourneyId"
      @row-click="handleView"
    >
      <template #headerActions>
        <Button v-if="showAdd" size="sm" @click="handleAdd">
          <Plus class="w-4 h-4 mr-1" />
          新建商机
        </Button>
      </template>

      <template #empty>
        <Empty class="deal-journeys-empty">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Plus class="h-5 w-5" aria-hidden="true" />
            </EmptyMedia>
            <EmptyTitle class="text-sm font-medium">暂无业务旅程</EmptyTitle>
          </EmptyHeader>
          <EmptyContent>
            <Button
              v-if="showAdd"
              type="button"
              size="sm"
              data-testid="empty-create-opportunity"
              @click="handleAdd"
            >
              <Plus class="w-4 h-4 mr-1" />
              新建商机
            </Button>
          </EmptyContent>
        </Empty>
      </template>

      <template #itemMain="{ item }">
        <span class="font-medium text-wolf-text-primary-v2 truncate">
          {{ item.name }}
        </span>
      </template>

      <template #itemMeta="{ item }">
        <span>{{ item.current_board_stage_label }}</span>
        <span> · </span>
        <AmountText :value="item.amount" size="sm" tone="primary" />
        <span v-if="purchaseTypeLabel(item.purchase_type) !== null">
          · {{ purchaseTypeLabel(item.purchase_type) }}
        </span>
      </template>
    </ListCard>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.deal-journeys-panel {
  min-width: 0;
}

.deal-journeys-empty {
  min-height: 160px;
  border: 0;
  padding: 0;
}
</style>
