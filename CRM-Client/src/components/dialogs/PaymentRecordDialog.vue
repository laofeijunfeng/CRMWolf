<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { PaymentRecordCreate } from '@/api/payment'
import paymentApi from '@/api/payment'
import customerApi, {
  type CustomerMemberAccessLevel,
  type CustomerMemberCandidate,
  type CustomerMemberRole,
} from '@/api/customer'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'
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

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isSubmitting = computed((): boolean => props.submitting === true)
const hasAmountError = computed((): boolean => errors.actualAmount.length > 0)
const hasActualPayerNameError = computed((): boolean => errors.actualPayerName.length > 0)
const hasPaymentDateError = computed((): boolean => errors.paymentDate.length > 0)
const hasCommissionMemberError = computed((): boolean => errors.commissionMemberId.length > 0)
const hasNotesError = computed((): boolean => errors.notes.length > 0)

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

function handleSubmit(): void {
  if (
    isSubmitting.value
    || loadingCommissionMembers.value
    || addMemberDialogOpen.value
    || addingCustomerMember.value
    || !validateForm()
  ) {
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
  if (!isSubmitting.value) {
    visible.value = false
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
  if (!props.open || props.paymentPlanId === null) {
    paymentCustomerId.value = null
    commissionMemberOptions.value = mergeCommissionMemberOptions([])
    return
  }

  loadingCommissionMembers.value = true
  try {
    const plan = await paymentApi.getPaymentPlanDetail(props.paymentPlanId)
    if (plan.customer_id === undefined || plan.customer_id === null) {
      paymentCustomerId.value = null
      commissionMemberOptions.value = mergeCommissionMemberOptions([])
      return
    }
    paymentCustomerId.value = plan.customer_id
    const candidates = await customerApi.getCustomerMemberCandidates(plan.customer_id)
    commissionMemberOptions.value = mergeCommissionMemberOptions(candidates)
  } catch (error) {
    paymentCustomerId.value = null
    commissionMemberOptions.value = mergeCommissionMemberOptions([])
    handleApiError(error, '加载团队成员')
  } finally {
    loadingCommissionMembers.value = false
  }
}

watch(
  () => [props.open, props.defaultAmount, props.defaultPayerName, props.paymentPlanId] as const,
  ([isOpen]) => {
    if (isOpen) {
      resetForm()
      void loadCommissionMembers()
    } else {
      paymentCustomerId.value = null
      addMemberDialogOpen.value = false
      resetPendingCustomerMember()
      clearErrors()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="payment-record-dialog">
      <DialogHeader>
        <DialogTitle>登记回款</DialogTitle>
        <DialogDescription>
          填写实际到账金额、回款日期和可选凭证信息，用于创建回款记录。
        </DialogDescription>
      </DialogHeader>

      <form class="payment-record-dialog__form" novalidate @submit.prevent="handleSubmit">
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
            :disabled="isSubmitting || loadingCommissionMembers"
            @update:model-value="handleCommissionMemberSelect"
          >
            <SelectTrigger id="payment-record-commission-member">
              <SelectValue :placeholder="loadingCommissionMembers ? '加载成员中...' : '请选择团队成员'" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="member in commissionMemberSelectOptions" :key="member.value" :value="member.value">
                {{ member.label }}
              </SelectItem>
            </SelectContent>
          </Select>
          <p v-if="errors.commissionMemberId" class="m-0 text-wolf-caption font-wolf-medium text-wolf-danger" role="alert">
            {{ errors.commissionMemberId }}
          </p>
          <p v-else class="m-0 text-wolf-caption text-wolf-text-secondary">
            可选择团队成员；未在客户团队中的成员需要先添加。
          </p>
        </div>

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

        <DialogFooter class="payment-record-dialog__footer">
          <Button
            type="button"
            variant="outline"
            class="payment-record-dialog__button min-h-11"
            :disabled="isSubmitting"
            @click="closeDialog"
          >
            取消
          </Button>
          <Button
            type="submit"
            class="payment-record-dialog__button min-h-11"
            :disabled="isSubmitting || loadingCommissionMembers || addMemberDialogOpen || addingCustomerMember"
          >
            {{ isSubmitting ? '提交中...' : '确定' }}
          </Button>
        </DialogFooter>
      </form>
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
  max-height: $wolf-modal-height-mobile-v2;
  overflow-y: auto;
}

.payment-record-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-form-item-gap-v2;
}

.payment-record-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.payment-record-dialog__button {
  min-height: $wolf-touch-target-min-v2;
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
  .payment-record-dialog__button {
    width: 100%;
  }
}
</style>
