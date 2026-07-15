<script setup lang="ts">
/**
 * OpportunitiesPanel.vue - 商机面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, ExternalLink } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { OpportunityListResponse, OpportunityStatus } from '@/api/opportunity'

interface Props {
  customerId: number
  opportunities: OpportunityListResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
}>()

const router = useRouter()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (opportunityId: number): void => {
  router.push(`/opportunities/${opportunityId}`)
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
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <ListCard
    title="商机"
    :items="opportunities"
    empty-text="暂无商机"
  >
    <template #headerActions>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建商机
      </Button>
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
        :aria-label="`查看商机 ${item.opportunity_name} 详情`"
        @click.stop="handleView(item.id)"
      >
        <ExternalLink class="w-4 h-4" />
      </Button>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>