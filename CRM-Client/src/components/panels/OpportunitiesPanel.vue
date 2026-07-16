<script setup lang="ts">
/**
 * OpportunitiesPanel.vue - 商机面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { nextTick, ref, watch } from 'vue'
import { Plus, ExternalLink } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { OpportunityListResponse, OpportunityStatus } from '@/api/opportunity'

interface Props {
  customerId: number
  opportunities: OpportunityListResponse[]
  highlightedOpportunityId?: number | null
  restoreFocusOpportunityId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  highlightedOpportunityId: null,
  restoreFocusOpportunityId: null
})

const emit = defineEmits<{
  'add': []
  'view-opportunity': [opportunityId: number]
  'open-full-page': [opportunityId: number]
}>()

const panelRootRef = ref<HTMLElement | null>(null)

const handleAdd = (): void => {
  emit('add')
}

const handleView = (opportunity: OpportunityListResponse): void => {
  emit('view-opportunity', opportunity.id)
}

const handleOpenFullPage = (opportunityId: number): void => {
  emit('open-full-page', opportunityId)
}

const mapStatus = (status: OpportunityStatus): string => {
  const statusMap: Record<OpportunityStatus, string> = {
    0: 'active',
    1: 'won',
    2: 'lost'
  }
  return statusMap[status]
}

const formatCurrency = (amount: number): string => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(amount)
}

const formatDate = (dateStr: string): string => {
  if (dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

const restoreRowFocus = async (): Promise<void> => {
  if (props.restoreFocusOpportunityId === null) return
  await nextTick()
  const row = panelRootRef.value?.querySelector<HTMLElement>(
    `[data-list-card-row-id="${props.restoreFocusOpportunityId}"]`
  )
  row?.focus()
}

watch(() => props.restoreFocusOpportunityId, () => {
  restoreRowFocus()
}, { immediate: true })
</script>

<template>
  <div ref="panelRootRef" class="opportunities-panel">
    <ListCard
      title="商机"
      :items="opportunities"
      empty-text="暂无商机"
      :highlighted-item-id="highlightedOpportunityId"
      row-interactive
      @row-click="handleView"
    >
      <template #headerActions>
        <Button size="sm" @click="handleAdd">
          <Plus class="w-4 h-4 mr-1" />
          新建商机
        </Button>
      </template>

      <template #empty>
        <div class="opportunities-empty">
          <p class="opportunities-empty-text">暂无商机</p>
          <Button
            type="button"
            size="sm"
            data-testid="empty-create-opportunity"
            @click="handleAdd"
          >
            <Plus class="w-4 h-4 mr-1" />
            新建商机
          </Button>
        </div>
      </template>

      <template #itemMain="{ item }">
        <div class="flex items-center gap-2">
          <span class="font-medium text-wolf-text-primary-v2">
            {{ item.opportunity_name }}
          </span>
          <StatusBadge
            v-if="item.status !== null && item.status !== undefined"
            :status="mapStatus(item.status)"
            type="opportunity"
            size="small"
          />
        </div>
        <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
          {{ formatCurrency(item.total_amount) }} ·
          {{ item.stage_info?.stage_name ?? '-' }}
          · 预计成交: {{ formatDate(item.expected_closing_date) }}
        </div>
      </template>

      <template #itemActions="{ item }">
        <Button
          variant="ghost"
          size="sm"
          :aria-label="`打开商机 ${item.opportunity_name} 完整详情`"
          @click.stop="handleOpenFullPage(item.id)"
        >
          <ExternalLink class="w-4 h-4" />
        </Button>
      </template>
    </ListCard>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunities-panel {
  min-width: 0;
}

.opportunities-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-md-v2;
}

.opportunities-empty-text {
  margin: 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-body-v2;
}
</style>
