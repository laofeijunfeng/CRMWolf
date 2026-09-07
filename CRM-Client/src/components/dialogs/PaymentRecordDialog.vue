<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import type { PaymentPlanResponse, PaymentPlanStatus, PaymentRecordCreate } from '@/api/payment'
import paymentApi from '@/api/payment'
import customerApi, {
  type CustomerMemberAccessLevel,
  type CustomerMemberCandidate,
  type CustomerMemberRole,
} from '@/api/customer'
import { useUserStore } from '@/stores/user'
import FormErrorSummary from '@/components/crmwolf/FormErrorSummary.vue'
import FeedbackAlert from '@/components/crmwolf/FeedbackAlert.vue'
import SelectionSummary, { type SummaryItem } from '@/components/crmwolf/SelectionSummary.vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import {
  customerMemberAccessOptions,
  customerMemberRoleOptions,
  defaultCustomerMemberAccessLevel,
  defaultCustomerMemberRole,
} from '@/constants/customerMembers'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DateField,
  InputField,
  TextareaField,
} from '@/components/crmwolf'

interface Props {
  open: boolean
  paymentPlanId?: number | null
  defaultAmount?: number | null
  defaultPayerName?: string | null
  submitting?: boolean
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'submit', payload: PaymentRecordCreate): void
}

interface PaymentRecordForm {
  actualAmount: string
  actualPayerName: string
  paymentDate: string
  proofAttachment: string
  commissionMemberId: string
  notes: string
}

interface PaymentRecordErrors {
  actualAmount: string
  actualPayerName: string
  paymentDate: string
  commissionMemberId: string
  notes: string
}

const props = withDefaults(defineProps<Props>(), {
  paymentPlanId: null,
  defaultAmount: null,
  defaultPayerName: null,
  submitting: false,
})

const emit = defineEmits<Emits>()
const userStore = useUserStore()

interface CommissionMemberOption {
  id: string
  name: string
  source: 'self' | 'team_member'
  alreadyMember: boolean
}

interface AddCustomerMemberForm {
  memberRole: CustomerMemberRole
  accessLevel: CustomerMemberAccessLevel
}

const form = reactive<PaymentRecordForm>({
  actualAmount: '',
  actualPayerName: '',
  paymentDate: '',
  proofAttachment: '',
  commissionMemberId: '',
  notes: '',
})

const errors = reactive<PaymentRecordErrors>({
  actualAmount: '',
  actualPayerName: '',
  paymentDate: '',
  commissionMemberId: '',
  notes: '',
})

const loadingCommissionMembers = ref(false)
const commissionMembersRequestId = ref(0)
const commissionMembersError = ref<FeedbackError | null>(null)
const paymentCustomerId = ref<string | null>(null)
const commissionMemberOptions = ref<CommissionMemberOption[]>([])
const commissionMemberSelectOptions = computed(() =>
  commissionMemberOptions.value.map((member) => ({
    value: member.id,
    label: `${member.name}${member.source === 'self' ? '（我）' : ''}`,
  }))
)
const addMemberDialogOpen = ref(false)
const addingCustomerMember = ref(false)
const pendingCustomerMember = ref<CommissionMemberOption | null>(null)
const addMemberForm = reactive<AddCustomerMemberForm>({
  memberRole: defaultCustomerMemberRole,
  accessLevel: defaultCustomerMemberAccessLevel,
})
const roleOptions = customerMemberRoleOptions
const accessOptions = customerMemberAccessOptions
const initialFormSnapshot = ref('')
const supplementOpen = ref(false)

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isSubmitting = computed((): boolean => props.submitting === true)
const paymentPlanContext = ref<PaymentPlanResponse | null>(null)
const closeGuardPending = ref(false)
const hasFormChanges = computed(() =>
  JSON.stringify({
    actualAmount: form.actualAmount,
    actualPayerName: form.actualPayerName,
    paymentDate: form.paymentDate,
    proofAttachment: form.proofAttachment,
    commissionMemberId: form.commissionMemberId,
    notes: form.notes,
  }) !== initialFormSnapshot.value
)
const paymentPlanRemainingAmount = computed(() =>
  paymentPlanContext.value?.remaining_amount ?? paymentPlanContext.value?.planned_amount ?? 0,
)
const isPaymentPlanLoading = computed((): boolean =>
  props.paymentPlanId !== null
  && paymentPlanContext.value === null
  && commissionMembersError.value === null
  && loadingCommissionMembers.value,
)
const paymentPlanStatusLabels: Record<PaymentPlanStatus, string> = {
  PENDING: '待登记',
  OVERDUE: '已逾期',
  PARTIAL: '部分回款',
  COMPLETED: '已登记',
}
const paymentPlanStatus = computed(() => {
  const status = paymentPlanContext.value?.status
  return status === undefined ? '' : paymentPlanStatusLabels[status] ?? '未知'
})
const paymentPlanContextItems = computed<SummaryItem[]>(() => {
  const plan = paymentPlanContext.value
  if (plan === null) return []

  return [
    { key: 'customer', label: '客户', value: displayValue(plan.customer_name, '未知客户') },
    { key: 'contract', label: '合同', value: displayValue(plan.contract_name, '未知合同') },
    { key: 'stage', label: '回款阶段', value: plan.stage_name },
    { key: 'remainingAmount', label: '待回款', value: paymentPlanRemainingAmount.value },
    { key: 'status', label: '当前状态', value: paymentPlanStatus.value },
  ]
})
const paymentPlanDetailItems = computed<SummaryItem[]>(() => {
  const plan = paymentPlanContext.value
  if (plan === null) return []

  return [
    { key: 'planNumber', label: '计划编号', value: displayValue(plan.plan_number, '-') },
    { key: 'plannedAmount', label: '计划金额', value: plan.planned_amount },
    { key: 'paidAmount', label: '已回款', value: plan.paid_amount ?? 0 },
  ]
})
function displayValue(value: string | null | undefined, fallback: string): string {
  const normalizedValue = value?.trim()
  return normalizedValue === undefined || normalizedValue === '' ? fallback : normalizedValue
}

const hasAmountError = computed((): boolean => errors.actualAmount.length > 0)
const hasActualPayerNameError = computed((): boolean => errors.actualPayerName.length > 0)
const hasPaymentDateError = computed((): boolean => errors.paymentDate.length > 0)
const hasCommissionMemberError = computed((): boolean => errors.commissionMemberId.length > 0)
const hasNotesError = computed((): boolean => errors.notes.length > 0)
const validationErrorItems = computed(() => [
  { field: 'actualAmount', label: '回款金额', message: errors.actualAmount, targetId: 'payment-record-amount' },
  { field: 'actualPayerName', label: '实际付款方', message: errors.actualPayerName, targetId: 'payment-record-payer-name' },
  { field: 'paymentDate', label: '回款日期', message: errors.paymentDate, targetId: 'payment-record-date' },
  { field: 'commissionMemberId', label: '团队成员', message: errors.commissionMemberId, targetId: 'payment-record-commission-member' },
  { field: 'notes', label: '备注', message: errors.notes, targetId: 'payment-record-notes' },
].filter((item): item is { field: string; label: string; message: string; targetId: string } => item.message.length > 0))

function getLocalDateString(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseLocalDateString(value: string): Date | null {
  if (!isValidLocalDate(value)) return null

  const [year, month, day] = value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return null
  return new Date(year, month - 1, day)
}

function handlePaymentDateChange(date: Date | null): void {
  form.paymentDate = date !== null ? getLocalDateString(date) : ''
}

function formatDefaultAmount(defaultAmount: number | null): string {
  if (defaultAmount === null) {
    return ''
  }
  return Number.isFinite(defaultAmount) ? String(defaultAmount) : ''
}

function clearErrors(): void {
  errors.actualAmount = ''
  errors.actualPayerName = ''
  errors.paymentDate = ''
  errors.commissionMemberId = ''
  errors.notes = ''
}

function resetForm(): void {
  form.actualAmount = formatDefaultAmount(props.defaultAmount)
  form.actualPayerName = props.defaultPayerName?.trim() ?? ''
  form.paymentDate = getLocalDateString()
  form.proofAttachment = ''
  form.commissionMemberId = String(userStore.userInfo?.id ?? '')
  form.notes = ''
  resetPendingCustomerMember()
  clearErrors()
  commissionMembersError.value = null
  supplementOpen.value = false
  initialFormSnapshot.value = JSON.stringify({ ...form })
}

function resetPendingCustomerMember(): void {
  pendingCustomerMember.value = null
  addMemberForm.memberRole = defaultCustomerMemberRole
  addMemberForm.accessLevel = defaultCustomerMemberAccessLevel
}

function trimmedOptional(value: string): string | undefined {
  const trimmedValue = value.trim()
  return trimmedValue.length > 0 ? trimmedValue : undefined
}

function isValidLocalDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

function validateForm(): boolean {
  clearErrors()

  const normalizedAmount = form.actualAmount.trim()
  const amount = Number(normalizedAmount)
  if (normalizedAmount.length === 0 || !Number.isFinite(amount) || amount <= 0) {
    errors.actualAmount = '请输入大于 0 的回款金额'
  }

  const normalizedPayerName = form.actualPayerName.trim()
  if (normalizedPayerName.length === 0) {
    errors.actualPayerName = '请输入实际付款方'
  } else if (normalizedPayerName.length > 200) {
    errors.actualPayerName = '实际付款方不能超过 200 字'
  }

  const normalizedDate = form.paymentDate.trim()
  if (normalizedDate.length === 0 || !isValidLocalDate(normalizedDate)) {
    errors.paymentDate = '请选择回款日期'
  }

  if (form.commissionMemberId.trim().length === 0) {
    errors.commissionMemberId = '请选择团队成员'
  }

  if (form.notes.length > 200) {
    errors.notes = '备注不能超过 200 字'
  }

  return !hasAmountError.value
    && !hasActualPayerNameError.value
    && !hasPaymentDateError.value
    && !hasCommissionMemberError.value
    && !hasNotesError.value
}

watch(
  () => errors.notes,
  (message) => {
    if (message.length > 0) supplementOpen.value = true
  },
)

async function focusFirstError(): Promise<void> {
  await nextTick()
  const fieldIds: [keyof PaymentRecordErrors, string][] = [
    ['actualAmount', 'payment-record-amount'],
    ['actualPayerName', 'payment-record-payer-name'],
    ['paymentDate', 'payment-record-date'],
    ['commissionMemberId', 'payment-record-commission-member'],
    ['notes', 'payment-record-notes'],
  ]

  for (const [field, id] of fieldIds) {
    if (errors[field].length === 0) continue
    const element = document.getElementById(id)
    if (element instanceof HTMLElement) {
      element.focus()
      return
    }
  }
}

function handleSubmit(): void {
  if (
    isSubmitting.value
    || loadingCommissionMembers.value
    || addMemberDialogOpen.value
    || addingCustomerMember.value
  ) {
    return
  }

  if (!validateForm()) {
    void focusFirstError()
    return
  }

  const payload: PaymentRecordCreate = {
    actual_amount: Number(form.actualAmount.trim()),
    actual_payer_name: form.actualPayerName.trim(),
    payment_date: form.paymentDate.trim(),
    commission_member_id: form.commissionMemberId.trim(),
  }

  const proofAttachment = trimmedOptional(form.proofAttachment)
  if (proofAttachment !== undefined) {
    payload.proof_attachment = proofAttachment
  }

  const notes = trimmedOptional(form.notes)
  if (notes !== undefined) {
    payload.notes = notes
  }

  emit('submit', payload)
}

function closeDialog(): void {
  void handleOpenChange(false)
}

async function handleOpenChange(open: boolean): Promise<void> {
  if (open) {
    visible.value = true
    return
  }
  if (isSubmitting.value || addMemberDialogOpen.value || addingCustomerMember.value || closeGuardPending.value) return
  if (!hasFormChanges.value) {
    visible.value = false
    return
  }

  closeGuardPending.value = true
  try {
    const confirmed = await confirmDialog(
      '已填写回款信息，关闭后这些内容不会保存。确定关闭吗？',
      '放弃本次回款登记？',
      { variant: 'destructive', confirmText: '放弃并关闭' },
    )
    if (confirmed) visible.value = false
  } finally {
    closeGuardPending.value = false
  }
}

function mergeCommissionMemberOptions(candidates: CustomerMemberCandidate[]): CommissionMemberOption[] {
  const options = new Map<string, CommissionMemberOption>()
  const currentUserId = String(userStore.userInfo?.id ?? '')
  if (currentUserId.length > 0) {
    options.set(currentUserId, {
      id: currentUserId,
      name: userStore.userInfo?.name ?? '我',
      source: 'self',
      alreadyMember: true,
    })
  }

  for (const candidate of candidates) {
    const memberName = candidate.name.trim()
    const isCurrentUser = candidate.id === currentUserId
    options.set(candidate.id, {
      id: candidate.id,
      name: memberName.length > 0 ? memberName : `用户 ${candidate.id}`,
      source: isCurrentUser ? 'self' : 'team_member',
      alreadyMember: candidate.already_member || isCurrentUser,
    })
  }
  return Array.from(options.values())
}

function findCommissionMemberOption(memberId: string): CommissionMemberOption | undefined {
  return commissionMemberOptions.value.find(member => member.id === memberId)
}

function handleCommissionMemberSelect(value: unknown): void {
  if (typeof value !== 'string') return

  form.commissionMemberId = value
  errors.commissionMemberId = ''

  const member = findCommissionMemberOption(value)
  if (member === undefined || member.alreadyMember) {
    return
  }

  pendingCustomerMember.value = member
  addMemberForm.memberRole = defaultCustomerMemberRole
  addMemberForm.accessLevel = defaultCustomerMemberAccessLevel
  addMemberDialogOpen.value = true
}

function resetCommissionMemberToCurrentUser(): void {
  form.commissionMemberId = String(userStore.userInfo?.id ?? '')
}

function handleAddMemberDialogOpenChange(open: boolean): void {
  if (!open && addingCustomerMember.value) {
    return
  }

  addMemberDialogOpen.value = open
  if (!open && !addingCustomerMember.value && pendingCustomerMember.value !== null) {
    resetCommissionMemberToCurrentUser()
    resetPendingCustomerMember()
  }
}

function cancelAddCustomerMember(): void {
  addMemberDialogOpen.value = false
  resetCommissionMemberToCurrentUser()
  resetPendingCustomerMember()
}

async function confirmAddCustomerMember(): Promise<void> {
  if (addingCustomerMember.value || pendingCustomerMember.value === null || paymentCustomerId.value === null) return

  const member = pendingCustomerMember.value
  addingCustomerMember.value = true
  try {
    await customerApi.addCustomerMember(paymentCustomerId.value, {
      user_id: member.id,
      member_role: addMemberForm.memberRole,
      access_level: addMemberForm.accessLevel,
      remark: null,
    })
    commissionMemberOptions.value = commissionMemberOptions.value.map(option =>
      option.id === member.id ? { ...option, alreadyMember: true } : option
    )
    form.commissionMemberId = member.id
    resetPendingCustomerMember()
    addMemberDialogOpen.value = false
  } catch (error) {
    handleApiError(error, '添加客户团队成员')
  } finally {
    addingCustomerMember.value = false
  }
}

async function loadCommissionMembers(): Promise<void> {
  const requestId = commissionMembersRequestId.value + 1
  commissionMembersRequestId.value = requestId

  if (!props.open || props.paymentPlanId === null) {
    commissionMembersError.value = null
    paymentPlanContext.value = null
    paymentCustomerId.value = null
    commissionMemberOptions.value = mergeCommissionMemberOptions([])
    return
  }

  loadingCommissionMembers.value = true
  commissionMembersError.value = null
  try {
    const plan = await paymentApi.getPaymentPlanDetail(props.paymentPlanId)
    if (requestId !== commissionMembersRequestId.value || !props.open) return

    paymentPlanContext.value = plan
    if (plan.customer_id === undefined || plan.customer_id === null) {
      paymentCustomerId.value = null
      commissionMemberOptions.value = mergeCommissionMemberOptions([])
      return
    }
    paymentCustomerId.value = plan.customer_id
    const candidates = await customerApi.getCustomerMemberCandidates(plan.customer_id)
    if (requestId !== commissionMembersRequestId.value || !props.open) return

    commissionMemberOptions.value = mergeCommissionMemberOptions(candidates)
  } catch (error) {
    if (requestId !== commissionMembersRequestId.value || !props.open) return

    paymentPlanContext.value = null
    paymentCustomerId.value = null
    commissionMemberOptions.value = mergeCommissionMemberOptions([])
    commissionMembersError.value = toFeedbackError(error, '回款计划和团队成员')
  } finally {
    if (requestId === commissionMembersRequestId.value) {
      loadingCommissionMembers.value = false
    }
  }
}

watch(
  () => [props.open, props.defaultAmount, props.defaultPayerName, props.paymentPlanId] as const,
  ([isOpen]) => {
    if (isOpen) {
      resetForm()
      void loadCommissionMembers()
    } else {
      commissionMembersRequestId.value += 1
      loadingCommissionMembers.value = false
      paymentPlanContext.value = null
      paymentCustomerId.value = null
      commissionMembersError.value = null
      addMemberDialogOpen.value = false
      resetPendingCustomerMember()
      clearErrors()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="payment-record-dialog w-[calc(100vw-2rem)] max-w-[640px]">
      <DialogHeader>
        <DialogTitle>登记回款</DialogTitle>
        <DialogDescription>
          登记实际到账信息；提交后将重算回款计划与合同状态。
        </DialogDescription>
      </DialogHeader>

      <div class="payment-record-dialog__body">
        <FormErrorSummary :items="validationErrorItems" />

        <SelectionSummary
          v-if="isPaymentPlanLoading"
          class="payment-record-dialog__context"
          variant="compact"
          aria-label="正在加载回款计划上下文"
          loading
          :loading-count="5"
          :loading-details="true"
          :items="[]"
          :details="[]"
        />

        <SelectionSummary
          v-else-if="paymentPlanContext !== null"
          class="payment-record-dialog__context"
          variant="compact"
          aria-label="回款计划上下文"
          :items="paymentPlanContextItems"
          :details="paymentPlanDetailItems"
        >
          <template #value-status>
            <StatusBadge
              :status="paymentPlanContext.status.toLowerCase()"
              type="paymentPlan"
            />
          </template>
          <template #value-remainingAmount>
            <AmountText :value="paymentPlanRemainingAmount" size="md" tone="primary" />
          </template>
          <template #value-plannedAmount>
            <AmountText :value="paymentPlanContext.planned_amount" size="md" />
          </template>
          <template #value-paidAmount>
            <AmountText :value="paymentPlanContext.paid_amount ?? 0" size="md" />
          </template>
        </SelectionSummary>

        <FeedbackAlert
          v-if="commissionMembersError !== null"
          class="payment-record-dialog__feedback"
          :error="commissionMembersError"
          density="compact"
          retry-label="重新加载团队成员"
          @retry="loadCommissionMembers"
        />

        <form id="payment-record-form" class="payment-record-dialog__form" novalidate @submit.prevent="handleSubmit">
          <div class="payment-record-dialog__required-grid">
            <InputField
              id="payment-record-amount"
              v-model="form.actualAmount"
              class="payment-record-dialog__field"
              label="回款金额"
              required
              name="actual_amount"
              type="number"
              inputmode="decimal"
              min="0"
              step="0.01"
              placeholder="请输入回款金额"
              :disabled="isSubmitting"
              helper-text="金额需大于 0，可精确到分。"
              :error="errors.actualAmount"
            />

            <InputField
              id="payment-record-payer-name"
              v-model="form.actualPayerName"
              class="payment-record-dialog__field"
              label="实际付款方"
              required
              name="actual_payer_name"
              type="text"
              maxlength="200"
              placeholder="请输入实际付款方"
              :disabled="isSubmitting"
              helper-text="默认使用客户名称，可按实际付款公司抬头修改。"
              :error="errors.actualPayerName"
            />

            <DateField
              id="payment-record-date"
              :model-value="parseLocalDateString(form.paymentDate)"
              class="payment-record-dialog__field"
              label="回款日期"
              required
              placeholder="请选择回款日期"
              :disabled="isSubmitting"
              helper-text="使用本地日期，格式为 YYYY-MM-DD。"
              :error="errors.paymentDate"
              @update:model-value="handlePaymentDateChange"
            />

            <div class="payment-record-dialog__field">
              <Label for="payment-record-commission-member" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
                团队成员
                <span class="text-wolf-danger" aria-hidden="true">*</span>
              </Label>
              <Select
                :model-value="form.commissionMemberId"
                :disabled="isSubmitting || loadingCommissionMembers || commissionMembersError !== null"
                @update:model-value="handleCommissionMemberSelect"
              >
                <SelectTrigger
                  id="payment-record-commission-member"
                  :aria-invalid="errors.commissionMemberId.length > 0 ? 'true' : undefined"
                  :aria-describedby="errors.commissionMemberId.length > 0 ? 'payment-record-commission-member-error' : undefined"
                >
                  <SelectValue :placeholder="loadingCommissionMembers ? '加载成员中...' : '请选择团队成员'" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="member in commissionMemberSelectOptions" :key="member.value" :value="member.value">
                    {{ member.label }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <p
                v-if="errors.commissionMemberId"
                id="payment-record-commission-member-error"
                class="m-0 text-wolf-caption font-wolf-medium text-wolf-danger"
                role="alert"
              >
                {{ errors.commissionMemberId }}
              </p>
              <p v-else-if="commissionMembersError === null" class="m-0 text-wolf-caption text-wolf-text-secondary">
                可选择团队成员；未在客户团队中的成员需要先添加。
              </p>
            </div>
          </div>

          <Collapsible v-model:open="supplementOpen" class="payment-record-dialog__supplement">
            <CollapsibleTrigger as-child>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                class="payment-record-dialog__supplement-trigger"
              >
                补充信息
                <ChevronDown class="payment-record-dialog__supplement-icon" aria-hidden="true" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div class="payment-record-dialog__optional-grid">
                <InputField
                  id="payment-record-proof"
                  v-model="form.proofAttachment"
                  class="payment-record-dialog__field"
                  label="凭证附件 URL"
                  name="proof_attachment"
                  type="url"
                  placeholder="请输入附件 URL（可选）"
                  :disabled="isSubmitting"
                />

                <TextareaField
                  id="payment-record-notes"
                  v-model="form.notes"
                  class="payment-record-dialog__field"
                  label="备注"
                  name="notes"
                  maxlength="200"
                  placeholder="请输入备注信息（可选，最多 200 字）"
                  control-class="min-h-20"
                  :disabled="isSubmitting"
                  :helper-text="`${form.notes.length}/200`"
                  :error="errors.notes"
                />
              </div>
            </CollapsibleContent>
          </Collapsible>
        </form>
      </div>

      <DialogFooter class="payment-record-dialog__footer">
        <Button
          type="button"
          variant="outline"
          class="payment-record-dialog__button"
          :disabled="isSubmitting || closeGuardPending"
          @click="closeDialog"
        >
          取消
        </Button>
        <Button
          type="submit"
          form="payment-record-form"
          class="payment-record-dialog__button"
          :disabled="isSubmitting || loadingCommissionMembers || commissionMembersError !== null || addMemberDialogOpen || addingCustomerMember"
        >
          {{ isSubmitting ? '提交中...' : '确定' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <Dialog :open="addMemberDialogOpen" @update:open="handleAddMemberDialogOpenChange">
    <DialogContent class="payment-record-add-member-dialog">
      <DialogHeader>
        <DialogTitle>添加团队成员</DialogTitle>
        <DialogDescription>
          {{ pendingCustomerMember?.name ?? '该成员' }}目前没有在团队成员中，是否添加
        </DialogDescription>
      </DialogHeader>

      <div class="payment-record-add-member-dialog__form">
        <InputField
          id="payment-record-add-member-user"
          :model-value="pendingCustomerMember?.name ?? ''"
          label="成员"
          disabled
          aria-readonly="true"
        />

        <div class="payment-record-dialog__field">
          <Label for="payment-record-add-member-role">角色</Label>
          <Select v-model="addMemberForm.memberRole" :disabled="addingCustomerMember">
            <SelectTrigger id="payment-record-add-member-role">
              <SelectValue placeholder="请选择角色" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="option in roleOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="payment-record-dialog__field">
          <Label for="payment-record-add-member-access">权限</Label>
          <Select v-model="addMemberForm.accessLevel" :disabled="addingCustomerMember">
            <SelectTrigger id="payment-record-add-member-access">
              <SelectValue placeholder="请选择权限" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="option in accessOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" :disabled="addingCustomerMember" @click="cancelAddCustomerMember">否</Button>
        <Button :disabled="addingCustomerMember" @click="confirmAddCustomerMember">
          {{ addingCustomerMember ? '添加中...' : '是' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-record-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-height: $wolf-modal-height-mobile-v2;
  overflow: hidden;
}

.payment-record-dialog__body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-inline: calc($wolf-focus-ring-width-v2 + $wolf-focus-ring-offset-v2);
  scroll-padding-bottom: calc($wolf-space-xl-v2 + $wolf-safe-area-bottom-v2);
}

.payment-record-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.payment-record-dialog__required-grid,
.payment-record-dialog__optional-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-xl-v2 $wolf-form-item-gap-v2;
}

.payment-record-dialog__field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.payment-record-dialog__context {
  min-width: 0;
}

.payment-record-dialog__feedback {
  min-width: 0;
}

.payment-record-dialog__supplement {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.payment-record-dialog__supplement-trigger {
  align-self: flex-start;
  min-height: 36px;
  padding: 0 $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.payment-record-dialog__supplement-icon {
  width: 14px;
  height: 14px;
  transition: transform 150ms ease;
}

.payment-record-dialog__supplement-trigger[aria-expanded='true'] .payment-record-dialog__supplement-icon {
  transform: rotate(180deg);
}

.payment-record-dialog__button {
  height: $wolf-button-height-md-v2;
  min-height: $wolf-button-height-md-v2;
}

.payment-record-dialog__footer {
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

.payment-record-add-member-dialog__form {
  display: grid;
  gap: $wolf-form-item-gap-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .payment-record-dialog__required-grid,
  .payment-record-dialog__optional-grid {
    grid-template-columns: 1fr;
  }

  .payment-record-dialog__button {
    width: 100%;
    height: $wolf-button-height-mobile-v2;
    min-height: $wolf-button-height-mobile-v2;
  }
}
</style>
