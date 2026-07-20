<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { ArrowRightLeft, Info } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  RadioGroup,
  RadioGroupItem,
} from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import customerApi, {
  type CustomerAssignRequest,
  type CustomerOpportunityTransferScope,
  type CustomerResponse,
} from '@/api/customer'
import { teamApi, type TeamMemberResponse } from '@/api/team'
import { useTeamStore } from '@/stores/team'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  open: boolean
  customer: CustomerResponse | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:open': [open: boolean]
  success: []
}>()

const teamStore = useTeamStore()
const loadingMembers = ref(false)
const submitting = ref(false)
const members = ref<TeamMemberResponse[]>([])

const form = reactive({
  ownerId: '',
  scope: 'none' as CustomerOpportunityTransferScope,
  remark: ''
})

const visible = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value)
})

const availableMembers = computed(() => {
  const currentOwnerId = props.customer?.owner_id ?? ''
  return members.value.filter(member => member.id !== currentOwnerId)
})

const selectedCustomerName = computed(() => props.customer?.account_name ?? '客户')

const scopeOptions: {
  value: CustomerOpportunityTransferScope
  label: string
  description: string
}[] = [
  {
    value: 'none',
    label: '仅客户',
    description: '只变更客户负责人，商机和合同负责人保持不变。'
  },
  {
    value: 'following',
    label: '客户 + 跟进中商机',
    description: '同步移交该客户下仍在推进的商机及其关联合同。'
  },
  {
    value: 'all',
    label: '客户 + 全部商机',
    description: '同步移交该客户下全部商机及其关联合同。'
  }
]

async function ensureTeamMembers(): Promise<void> {
  if (members.value.length > 0) return

  loadingMembers.value = true
  try {
    if (teamStore.currentTeam === null) {
      await teamStore.fetchUserTeams()
    }

    const teamId = teamStore.currentTeam?.id
    if (teamId === undefined) {
      members.value = []
      return
    }

    members.value = await teamApi.getTeamMembers(teamId)
  } catch (error) {
    members.value = []
    handleApiError(error, '获取团队成员')
  } finally {
    loadingMembers.value = false
  }
}

function resetForm(): void {
  form.ownerId = ''
  form.scope = 'none'
  form.remark = ''
}

async function handleSubmit(): Promise<void> {
  if (props.customer === null) return
  if (form.ownerId.trim() === '') {
    toast.error('请选择新负责人')
    return
  }

  submitting.value = true
  try {
    const payload: CustomerAssignRequest = {
      owner_id: form.ownerId,
      opportunity_transfer_scope: form.scope,
    }
    const trimmedRemark = form.remark.trim()
    if (trimmedRemark !== '') {
      payload.remark = trimmedRemark
    }

    const response = await customerApi.assignCustomer(props.customer.id, payload)

    const details = response.transferred_opportunities > 0
      ? `，同步移交 ${response.transferred_opportunities} 个商机、${response.transferred_contracts} 个合同`
      : ''
    toast.success(`客户已移交${details}`)
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, '移交客户')
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      resetForm()
      void ensureTeamMembers()
    }
  }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="customer-transfer-dialog">
      <DialogHeader>
        <DialogTitle class="customer-transfer-dialog__title">
          <ArrowRightLeft class="size-4" />
          移交客户
        </DialogTitle>
        <DialogDescription>
          将“{{ selectedCustomerName }}”移交给新的负责人。
        </DialogDescription>
      </DialogHeader>

      <div class="customer-transfer-dialog__body">
        <div class="customer-transfer-dialog__field">
          <Label for="customer-transfer-owner">新负责人 <span class="text-destructive">*</span></Label>
          <Select v-model="form.ownerId" :disabled="loadingMembers || submitting">
            <SelectTrigger id="customer-transfer-owner" class="h-11 sm:h-8">
              <SelectValue :placeholder="loadingMembers ? '加载成员中...' : '请选择新负责人'" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="member in availableMembers"
                :key="member.id"
                :value="member.id"
              >
                {{ member.name }}
              </SelectItem>
            </SelectContent>
          </Select>
          <p v-if="!loadingMembers && availableMembers.length === 0" class="customer-transfer-dialog__hint">
            暂无可移交的团队成员
          </p>
        </div>

        <div class="customer-transfer-dialog__field">
          <Label>移交范围</Label>
          <RadioGroup v-model="form.scope" class="customer-transfer-dialog__scope" :disabled="submitting">
            <Label
              v-for="option in scopeOptions"
              :key="option.value"
              :for="`transfer-scope-${option.value}`"
              class="customer-transfer-dialog__scope-item"
              :class="{ 'customer-transfer-dialog__scope-item--active': form.scope === option.value }"
            >
              <RadioGroupItem :id="`transfer-scope-${option.value}`" :value="option.value" />
              <span class="customer-transfer-dialog__scope-copy">
                <span class="customer-transfer-dialog__scope-label">{{ option.label }}</span>
                <span class="customer-transfer-dialog__scope-description">{{ option.description }}</span>
              </span>
            </Label>
          </RadioGroup>
        </div>

        <div v-if="form.scope !== 'none'" class="customer-transfer-dialog__notice">
          <Info class="size-4" />
          <span>移交商机时，系统会同步移交这些商机关联的合同，确保业务归属一致。</span>
        </div>

        <div class="customer-transfer-dialog__field">
          <Label for="customer-transfer-remark">备注</Label>
          <Textarea
            id="customer-transfer-remark"
            v-model="form.remark"
            :disabled="submitting"
            placeholder="填写移交原因或交接说明"
            maxlength="500"
            rows="3"
          />
        </div>
      </div>

      <DialogFooter class="customer-transfer-dialog__footer">
        <Button variant="outline" :disabled="submitting" @click="visible = false">取消</Button>
        <Button type="button" :disabled="submitting || form.ownerId.trim() === ''" @click="handleSubmit">
          {{ submitting ? '移交中...' : '确认移交' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customer-transfer-dialog {
  max-width: 520px;
}

.customer-transfer-dialog__title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.customer-transfer-dialog__body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.customer-transfer-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.customer-transfer-dialog__hint {
  margin: 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__scope {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.customer-transfer-dialog__scope-item {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
  min-height: 52px;
  padding: 10px $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-card-v2;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.customer-transfer-dialog__scope-item:hover,
.customer-transfer-dialog__scope-item--active {
  border-color: $wolf-border-hover-v2;
  background: $wolf-primary-light-v2;
}

.customer-transfer-dialog__scope-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.customer-transfer-dialog__scope-label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__scope-description {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__notice {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
  padding: 10px $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__notice svg {
  flex: none;
  margin-top: 1px;
}

.customer-transfer-dialog__footer {
  margin-top: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-default-v2;
}
</style>
