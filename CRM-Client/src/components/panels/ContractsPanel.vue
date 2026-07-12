<script setup lang="ts">
import { Plus, ExternalLink } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ContractListResponse, ContractStatus } from '@/api/contract'

interface Props {
  customerId: number
  contracts: ContractListResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
}>()

const router = useRouter()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (contractId: number): void => {
  router.push(`/contracts/${contractId}`)
}

// Map ContractStatus to StatusBadge string status
const mapStatus = (status: ContractStatus): string => {
  const statusMap: Record<ContractStatus, string> = {
    'DRAFT': 'draft',
    'PENDING_REVIEW': 'pending_review',
    'SIGNED': 'signed',
    'EFFECTIVE': 'effective',
    'EXPIRED': 'expired',
    'TERMINATED': 'terminated'
  }
  return statusMap[status]
}

const formatCurrency = (amount: string | number): string => {
  const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(numAmount)
}

const formatDate = (dateStr: string | null): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') {
    return '-'
  }
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <Card class="contracts-panel">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">合同</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建合同
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <div v-if="contracts.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
        暂无合同
      </div>
      <div v-else class="divide-y divide-wolf-border-light-v2">
        <div
          v-for="contract in contracts"
          :key="contract.id"
          class="p-4 flex items-center justify-between hover:bg-wolf-bg-hover-v2 transition-colors cursor-pointer"
          @click="handleView(contract.id)"
        >
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium text-wolf-text-primary-v2">{{ contract.contract_name }}</span>
              <StatusBadge
                :status="mapStatus(contract.status)"
                type="contract"
                size="small"
              />
            </div>
            <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
              {{ contract.contract_number }} · {{ formatCurrency(contract.total_amount) }}
              · 签署日期: {{ formatDate(contract.signing_date) }}
            </div>
          </div>
          <Button variant="ghost" size="sm" @click.stop="handleView(contract.id)">
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