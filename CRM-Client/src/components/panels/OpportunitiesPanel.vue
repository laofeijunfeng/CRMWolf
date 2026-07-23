<script setup lang="ts">
/**
 * OpportunitiesPanel.vue - 商机面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import StatusBadge from '@/components/StatusBadge.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { OpportunityListResponse, OpportunityStatus } from '@/api/opportunity'

interface Props {
  customerId: number
  opportunities: OpportunityListResponse[]
  showAdd?: boolean
}

withDefaults(defineProps<Props>(), {
  showAdd: false,
})

const emit = defineEmits<{
  'add': []
  'view': [opportunityId: number]
}>()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (opportunity: OpportunityListResponse): void => {
  emit('view', opportunity.id)
}

const mapStatus = (status: OpportunityStatus): string => {
  const statusMap: Record<OpportunityStatus, string> = {
    0: 'active',
    1: 'won',
    2: 'lost'
  }
  return statusMap[status]
}

const formatDate = (dateStr: string): string => {
  if (dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <div class="opportunities-panel">
    <ListCard
      title="商机"
      :items="opportunities"
      empty-text="暂无商机"
      row-interactive
      @row-click="handleView"
    >
      <template #headerActions>
        <Button v-if="showAdd" size="sm" @click="handleAdd">
          <Plus class="w-4 h-4 mr-1" />
          新建商机
        </Button>
      </template>

      <template #empty>
        <Empty class="opportunities-empty">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Plus class="h-5 w-5" aria-hidden="true" />
            </EmptyMedia>
            <EmptyTitle class="text-sm font-medium">暂无商机</EmptyTitle>
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
          {{ item.opportunity_name }}
        </span>
      </template>

      <template #itemMeta="{ item }">
        <AmountText :value="item.total_amount" size="sm" tone="primary" />
        <span> · {{ item.stage_info?.stage_name ?? '-' }}</span>
        <span> · 预计成交: {{ formatDate(item.expected_closing_date) }}</span>
      </template>

      <template #itemBadges="{ item }">
        <StatusBadge
          v-if="item.status !== null && item.status !== undefined"
          :status="mapStatus(item.status)"
          type="opportunity"
          size="small"
        />
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
  min-height: 160px;
  border: 0;
  padding: 0;
}
</style>
