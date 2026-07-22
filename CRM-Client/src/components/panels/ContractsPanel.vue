<script setup lang="ts">
/**
 * ContractsPanel.vue - 合同面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 *
 * Task 6: 改为 emit 'view' 事件，由父组件决定打开 Sheet 或导航
 */
import { Plus, Pencil, Send, RotateCcw, Trash2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import { HoverInfo } from '@/components/crmwolf'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { ContractListResponse, ContractStatus } from '@/api/contract'

type ContractActionPredicate = (contract: ContractListResponse) => boolean

interface Props {
  customerId: number
  contracts: ContractListResponse[]
  loading?: boolean
  showAdd?: boolean
  canEdit?: ContractActionPredicate | null
  canSubmitApproval?: ContractActionPredicate | null
  canWithdrawApproval?: ContractActionPredicate | null
  canDelete?: ContractActionPredicate | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  showAdd: true,
  canEdit: null,
  canSubmitApproval: null,
  canWithdrawApproval: null,
  canDelete: null
})

const emit = defineEmits<{
  'add': []
  'view': [contractId: number]
  'edit': [contract: ContractListResponse]
  'submit-approval': [contract: ContractListResponse]
  'withdraw-approval': [contract: ContractListResponse]
  'delete': [contract: ContractListResponse]
}>()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (contract: ContractListResponse): void => {
  emit('view', contract.id)
}

const shouldShowAction = (
  predicate: ContractActionPredicate | null | undefined,
  contract: ContractListResponse
): boolean => predicate?.(contract) === true

const hasActions = (contract: ContractListResponse): boolean =>
  shouldShowAction(props.canEdit, contract)
  || shouldShowAction(props.canSubmitApproval, contract)
  || shouldShowAction(props.canWithdrawApproval, contract)
  || shouldShowAction(props.canDelete, contract)

const handleEdit = (contract: ContractListResponse): void => {
  emit('edit', contract)
}

const handleSubmitApproval = (contract: ContractListResponse): void => {
  emit('submit-approval', contract)
}

const handleWithdrawApproval = (contract: ContractListResponse): void => {
  emit('withdraw-approval', contract)
}

const handleDelete = (contract: ContractListResponse): void => {
  emit('delete', contract)
}

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

const formatDate = (dateStr: string | null): string => {
  if (dateStr === null || dateStr === '') {
    return '-'
  }
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <ListCard
    title="合同"
    :items="contracts"
    empty-text="暂无合同"
    :loading="loading === true"
    row-interactive
    @row-click="handleView"
  >
    <template #headerActions>
      <Button v-if="showAdd" size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建合同
      </Button>
    </template>

    <template #itemMain="{ item }">
      <span class="font-medium text-wolf-text-primary-v2 truncate">
        {{ item.contract_name }}
      </span>
    </template>

    <template #itemMeta="{ item }">
      <span>{{ item.contract_number }}</span>
      <span> · </span>
      <AmountText :value="item.total_amount" size="sm" />
      <span> · 签署日期: {{ formatDate(item.signing_date) }}</span>
    </template>

    <template #itemBadges="{ item }">
      <StatusBadge
        :status="mapStatus(item.status)"
        type="contract"
        size="small"
      />
    </template>

    <template #itemActions="{ item }">
      <div v-if="hasActions(item)" class="contract-actions" @click.stop>
        <HoverInfo
          v-if="shouldShowAction(canEdit, item)"
          side="top"
          align="center"
          content-class="contract-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="contract-action-button contract-action-button--primary"
              :aria-label="`编辑合同 ${item.contract_name}`"
              @click="handleEdit(item)"
            >
              <Pencil class="w-4 h-4" />
            </Button>
          </template>
          <span class="contract-action-hover-text">编辑</span>
        </HoverInfo>

        <HoverInfo
          v-if="shouldShowAction(canSubmitApproval, item)"
          side="top"
          align="center"
          content-class="contract-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="contract-action-button contract-action-button--primary"
              :aria-label="`提交合同 ${item.contract_name} 审批`"
              @click="handleSubmitApproval(item)"
            >
              <Send class="w-4 h-4" />
            </Button>
          </template>
          <span class="contract-action-hover-text">提交审批</span>
        </HoverInfo>

        <HoverInfo
          v-if="shouldShowAction(canWithdrawApproval, item)"
          side="top"
          align="center"
          content-class="contract-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="contract-action-button contract-action-button--danger"
              :aria-label="`撤回合同 ${item.contract_name} 审批`"
              @click="handleWithdrawApproval(item)"
            >
              <RotateCcw class="w-4 h-4" />
            </Button>
          </template>
          <span class="contract-action-hover-text">撤回审批</span>
        </HoverInfo>

        <HoverInfo
          v-if="shouldShowAction(canDelete, item)"
          side="top"
          align="center"
          content-class="contract-action-hover-card"
        >
          <template #trigger>
            <Button
              variant="ghost"
              size="icon"
              class="contract-action-button contract-action-button--danger"
              :aria-label="`删除合同 ${item.contract_name}`"
              @click="handleDelete(item)"
            >
              <Trash2 class="w-4 h-4" />
            </Button>
          </template>
          <span class="contract-action-hover-text">删除</span>
        </HoverInfo>
      </div>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contract-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  min-width: 0;
}

.contract-action-button {
  width: 32px;
  height: 32px;
  color: $wolf-text-secondary-v2;
}

.contract-action-button--primary {
  &:hover {
    color: $wolf-primary-v2;
  }
}

.contract-action-button--danger {
  &:hover {
    color: $wolf-danger-v2;
  }
}

:global(.contract-action-hover-card) {
  width: auto;
  padding: 6px 10px;
}

.contract-action-hover-text {
  display: inline-flex;
  white-space: nowrap;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
}
</style>
