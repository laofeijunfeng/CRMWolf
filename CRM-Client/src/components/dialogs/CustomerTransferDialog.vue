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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  RadioGroup,
  RadioGroupItem,
} from '@/components/ui/radio-group'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  SelectField,
  TextareaField,
} from '@/components/crmwolf'
import customerApi, {
  type CustomerAssignRequest,
  type CustomerOpportunityTransferScope,
  type CustomerResponse,
} from '@/api/customer'
import { teamApi, type TeamMemberResponse } from '@/api/team'
import { useTeamStore } from '@/stores/team'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'
import { handleApiError } from '@/utils/errorHandler'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

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
const membersError = ref<FeedbackError | null>(null)
const submitError = ref<FeedbackError | null>(null)

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
const memberOptions = computed(() =>
  availableMembers.value.map((member) => ({
    value: member.id,
    label: member.name,
  }))
)

const selectedCustomerName = computed(() => props.customer?.account_name ?? '客户')
const currentOwnerName = computed(() => {
  const ownerName = props.customer?.owner_info?.name?.trim()
  if (ownerName !== undefined && ownerName.length > 0) return ownerName

  const ownerId = props.customer?.owner_id?.trim()
  return ownerId !== undefined && ownerId.length > 0 ? `用户 ${ownerId}` : '未分配'
})
const selectedOwnerName = computed(() => {
  const selectedMember = members.value.find(member => member.id === form.ownerId)
  const selectedMemberName = selectedMember?.name?.trim()
  return selectedMemberName !== undefined && selectedMemberName.length > 0
    ? selectedMemberName
    : '尚未选择'
})
const hasFormChanges = computed(() =>
  form.ownerId.trim() !== '' || form.scope !== 'none' || form.remark.trim() !== ''
)
const closeGuard = useDialogCloseGuard({
  isDirty: hasFormChanges,
  submitting,
  emitOpen: (open) => emit('update:open', open),
})
const showConfirmDialog = closeGuard.showConfirmDialog

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

const selectedScope = computed(() => scopeOptions.find(option => option.value === form.scope) ?? scopeOptions[0])

async function ensureTeamMembers(): Promise<void> {
  if (members.value.length > 0) return

  membersError.value = null
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
    membersError.value = toFeedbackError(error, '团队成员')
    handleApiError(error, '获取团队成员')
  } finally {
    loadingMembers.value = false
  }
}

function resetForm(): void {
  form.ownerId = ''
  form.scope = 'none'
  form.remark = ''
  membersError.value = null
  submitError.value = null
}

function handleOpenChange(open: boolean): void {
  closeGuard.handleOpenChange(open)
}

function handleCancel(): void {
  closeGuard.requestClose()
}

function confirmCancel(): void {
  closeGuard.confirmDiscard()
}

function continueEditing(): void {
  closeGuard.continueEditing()
}

async function handleSubmit(): Promise<void> {
  if (props.customer === null) return
  submitError.value = null
  if (form.ownerId.trim() === '') {
    submitError.value = {
      kind: 'validation',
      title: '移交客户校验失败',
      description: '请选择新负责人后再提交',
    }
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
    closeGuard.approveClose()
    visible.value = false
    emit('success')
  } catch (error) {
    submitError.value = toFeedbackError(error, '移交客户', { operation: 'write' })
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
      closeGuard.reset()
      void ensureTeamMembers()
      return
    }

    if (closeGuard.handleParentClose()) return
    closeGuard.reset()
  }
)
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
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
        <div class="customer-transfer-dialog__context" aria-label="移交前后负责人">
          <div class="customer-transfer-dialog__context-item">
            <span class="customer-transfer-dialog__context-label">当前负责人</span>
            <strong>{{ currentOwnerName }}</strong>
          </div>
          <ArrowRightLeft class="customer-transfer-dialog__context-icon" aria-hidden="true" />
          <div class="customer-transfer-dialog__context-item">
            <span class="customer-transfer-dialog__context-label">移交后负责人</span>
            <strong>{{ selectedOwnerName }}</strong>
          </div>
        </div>

        <div>
          <SelectField
            id="customer-transfer-owner"
            v-model="form.ownerId"
            class="customer-transfer-dialog__field"
            label="新负责人"
            required
            :options="memberOptions"
            :placeholder="loadingMembers ? '加载成员中...' : '请选择新负责人'"
            :disabled="loadingMembers || submitting || membersError !== null"
          />
          <div v-if="membersError" class="customer-transfer-dialog__error" role="alert">
            <strong>{{ membersError.title }}</strong>
            <span>{{ membersError.description }}</span>
            <Button type="button" variant="outline" size="sm" :disabled="loadingMembers" @click="ensureTeamMembers">
              {{ loadingMembers ? '重试中...' : '重新加载成员' }}
            </Button>
          </div>
          <p v-else-if="!loadingMembers && availableMembers.length === 0" class="customer-transfer-dialog__hint">
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

        <div v-if="form.ownerId" class="customer-transfer-dialog__impact" aria-live="polite">
          <div class="customer-transfer-dialog__impact-heading">本次移交影响</div>
          <p>
            客户“{{ selectedCustomerName }}”的负责人将从“{{ currentOwnerName }}”变更为“{{ selectedOwnerName }}”。
          </p>
          <p>
            同步范围：{{ selectedScope?.label }}。{{ selectedScope?.description }}
          </p>
          <p v-if="form.scope !== 'none'">实际移交数量将在提交成功后反馈。</p>
        </div>

        <div v-if="submitError" class="customer-transfer-dialog__error customer-transfer-dialog__error--submit" role="alert">
          <strong>{{ submitError.title }}</strong>
          <span>{{ submitError.description }}</span>
        </div>

        <TextareaField
          id="customer-transfer-remark"
          v-model="form.remark"
          class="customer-transfer-dialog__field"
          label="备注"
          :disabled="submitting"
          placeholder="填写移交原因或交接说明"
          maxlength="500"
          rows="3"
        />
      </div>

      <DialogFooter class="customer-transfer-dialog__footer">
        <Button variant="outline" :disabled="submitting" @click="handleCancel">取消</Button>
        <Button type="button" :disabled="submitting || form.ownerId.trim() === ''" @click="handleSubmit">
          {{ submitting ? '移交中...' : '确认移交' }}
        </Button>
  </DialogFooter>
    </DialogContent>
  </Dialog>

  <AlertDialog :open="showConfirmDialog" @update:open="closeGuard.handleConfirmOpenChange">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃更改？</AlertDialogTitle>
        <AlertDialogDescription>
          您有未保存的移交信息，确定要关闭吗？
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">继续编辑</AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">放弃更改</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
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

.customer-transfer-dialog__context {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
}

.customer-transfer-dialog__context-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.customer-transfer-dialog__context-item strong {
  overflow: hidden;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customer-transfer-dialog__context-label {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__context-icon {
  color: $wolf-text-tertiary-v2;
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

.customer-transfer-dialog__error {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-danger-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-danger-bg-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__error strong {
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.customer-transfer-dialog__error--submit {
  margin-top: $wolf-space-xs-v2;
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

.customer-transfer-dialog__impact {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-primary-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.customer-transfer-dialog__impact p {
  margin: 0;
}

.customer-transfer-dialog__impact-heading {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.customer-transfer-dialog__footer {
  margin-top: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-default-v2;
}

@media (max-width: 480px) {
  .customer-transfer-dialog__context {
    grid-template-columns: minmax(0, 1fr);
  }

  .customer-transfer-dialog__context-icon {
    justify-self: center;
    transform: rotate(90deg);
  }
}
</style>
