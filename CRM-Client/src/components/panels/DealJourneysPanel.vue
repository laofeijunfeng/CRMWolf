<script setup lang="ts">
/**
 * DealJourneysPanel.vue - 业务旅程列表面板
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + base.css 设计令牌
 */
import { nextTick, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { DataViewStatePanel } from '@/components/crmwolf'
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
        <DataViewStatePanel state="empty" class="w-full" empty-title="暂无业务旅程">
          <template v-if="showAdd" #empty-action>
            <Button
              type="button"
              size="sm"
              data-testid="empty-create-opportunity"
              @click="handleAdd"
            >
              <Plus class="w-4 h-4 mr-1" />
              新建商机
            </Button>
          </template>
        </DataViewStatePanel>
      </template>

      <template #itemMain="{ item }">
        <span class="font-medium text-foreground truncate">
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

.deal-journeys-panel {
  min-width: 0;
}
</style>
