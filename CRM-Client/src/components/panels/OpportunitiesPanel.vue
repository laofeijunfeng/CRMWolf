<script setup lang="ts">
import { Plus, ExternalLink } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
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

// Map numeric status to StatusBadge string status
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
  if (dateStr === null || dateStr === undefined || dateStr === '') {
    return '-'
  }
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <Card class="opportunities-panel">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">商机</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建商机
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <div v-if="opportunities.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
        暂无商机
      </div>
      <div v-else class="divide-y divide-wolf-border-light-v2">
        <div
          v-for="opportunity in opportunities"
          :key="opportunity.id"
          class="p-4 flex items-center justify-between hover:bg-wolf-bg-hover-v2 transition-colors cursor-pointer"
          @click="handleView(opportunity.id)"
        >
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium text-wolf-text-primary-v2">{{ opportunity.opportunity_name }}</span>
              <StatusBadge
                v-if="opportunity.status !== null && opportunity.status !== undefined"
                :status="mapStatus(opportunity.status)"
                type="opportunity"
                size="small"
              />
            </div>
            <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
              {{ formatCurrency(opportunity.total_amount) }} · {{ opportunity.stage_info?.stage_name ?? '-' }}
              · 预计成交: {{ formatDate(opportunity.expected_closing_date) }}
            </div>
          </div>
          <Button variant="ghost" size="sm" @click.stop="handleView(opportunity.id)">
            <ExternalLink class="w-4 h-4" />
          </Button>
        </div>
      </div>
    </CardContent>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>