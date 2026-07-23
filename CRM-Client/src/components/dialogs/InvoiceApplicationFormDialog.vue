<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import contractApi, { type ContractListResponse } from '@/api/contract'
import customerApi, { type CustomerResponse } from '@/api/customer'
import invoiceApi, {
  type InvoiceApplicationCreate,
  type InvoiceApplicationResponse,
  type InvoiceApplicationUpdate,
  type InvoiceTitleResponse,
  type InvoiceType,
} from '@/api/invoice'
import paymentApi, { type PaymentPlanResponse } from '@/api/payment'
import approvalGenericApi from '@/api/approvalGeneric'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency } from '@/utils/format'
import { normalizePaginatedResponse } from '@/types/pagination'
import InvoiceTypeSegmentedControl from '@/components/invoice/InvoiceTypeSegmentedControl.vue'
import {
  InputField,
  SelectField,
  SelectionSummary,
} from '@/components/crmwolf'

interface FixedCustomer {
  id: number
  account_name: string
}

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  application?: InvoiceApplicationResponse | null
  fixedCustomer?: FixedCustomer | null
  fixedInvoiceTitle?: InvoiceTitleResponse | null
  fixedContractId?: number | null
}

interface Emits {
  (event: 'update:open', value: boolean): void
  (event: 'success'): void
}

interface InvoiceApplicationForm {
  customerId: string
  contractId: string
  paymentPlanId: string
  invoiceTitleId: string
  invoiceType: InvoiceType
  invoiceAmount: string
}

interface InvoiceApplicationFormErrors {
  customerId: string
  contractId: string
  paymentPlanId: string
  invoiceTitleId: string
  invoiceAmount: string
}

const props = withDefaults(defineProps<Props>(), {
  application: null,
  fixedCustomer: null,
  fixedInvoiceTitle: null,
  fixedContractId: null,
})
const emit = defineEmits<Emits>()

const customers = ref<CustomerResponse[]>([])
const contracts = ref<ContractListResponse[]>([])
const paymentPlans = ref<PaymentPlanResponse[]>([])
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const loadingCustomers = ref(false)
const loadingContracts = ref(false)
const loadingPaymentPlans = ref(false)
const loadingInvoiceTitles = ref(false)
const submitting = ref(false)

const form = reactive<InvoiceApplicationForm>({
  customerId: '',
  contractId: '',
  paymentPlanId: '',
  invoiceTitleId: '',
  invoiceType: 'VAT_SPECIAL',
  invoiceAmount: '',
})

const errors = reactive<InvoiceApplicationFormErrors>({
  customerId: '',
  contractId: '',
  paymentPlanId: '',
  invoiceTitleId: '',
  invoiceAmount: '',
})

const visible = computed({
  get: (): boolean => props.open,
  set: (value: boolean): void => emit('update:open', value),
})

const isCreateMode = computed<boolean>(() => props.mode === 'create')
const hasFixedCustomer = computed<boolean>(() => props.fixedCustomer !== null)
const hasFixedInvoiceTitle = computed<boolean>(() => props.fixedInvoiceTitle !== null)
const hasFixedContract = computed<boolean>(() => props.fixedContractId !== null)
const title = computed<string>(() => isCreateMode.value ? '申请发票' : '编辑发票申请')
const description = computed<string>(() => {
  if (isCreateMode.value && hasFixedInvoiceTitle.value) {
    return '使用当前发票抬头创建申请，并提交到审批流程。'
  }

  return isCreateMode.value
    ? '选择客户、合同、回款计划和发票抬头后提交审批。'
    : '调整发票抬头、发票类型或开票金额。'
})
const selectedInvoiceTitle = computed<InvoiceTitleResponse | null>(() => {
  if (props.fixedInvoiceTitle !== null) return props.fixedInvoiceTitle
  return invoiceTitles.value.find(titleItem => String(titleItem.id) === form.invoiceTitleId) ?? null
})
const selectedCustomerName = computed<string>(() => {
  if (props.fixedCustomer !== null) return props.fixedCustomer.account_name
  return customers.value.find(customer => String(customer.id) === form.customerId)?.account_name
    ?? props.application?.customer_name
    ?? ''
})
const selectedContract = computed<ContractListResponse | null>(() => {
  return contracts.value.find(contract => String(contract.id) === form.contractId) ?? null
})
const selectedPaymentPlan = computed<PaymentPlanResponse | null>(() => {
  return paymentPlans.value.find(plan => String(plan.id) === form.paymentPlanId) ?? null
})
const selectedInvoiceTitleSummaryItems = computed(() => {
  if (selectedInvoiceTitle.value === null) return []

  return [
    { label: '税号', value: selectedInvoiceTitle.value.taxpayer_id },
    { label: '开户行', value: nullText(selectedInvoiceTitle.value.bank_name) },
    { label: '银行账号', value: nullText(selectedInvoiceTitle.value.bank_account) },
    { label: '地址电话', value: `${nullText(selectedInvoiceTitle.value.address)} / ${nullText(selectedInvoiceTitle.value.phone)}` },
  ]
})

const customerOptions = computed(() =>
  customers.value.map(customer => ({
    value: customer.id,
    label: customerOptionLabel(customer),
  }))
)

const contractOptions = computed(() =>
  contracts.value.map(contract => ({
    value: contract.id,
    label: contractOptionLabel(contract),
  }))
)

const paymentPlanOptions = computed(() =>
  paymentPlans.value.map(plan => ({
    value: plan.id,
    label: paymentPlanOptionLabel(plan),
  }))
)

const invoiceTitleOptions = computed(() =>
  invoiceTitles.value.map(invoiceTitle => ({
    value: invoiceTitle.id,
    label: `${invoiceTitle.title} · ${invoiceTitleTypeLabel(invoiceTitle.title_type)}`,
  }))
)
const isEditContextLoading = computed<boolean>(() => {
  return !isCreateMode.value && (loadingContracts.value || loadingPaymentPlans.value || loadingInvoiceTitles.value)
})

function clearErrors(): void {
  errors.customerId = ''
  errors.contractId = ''
  errors.paymentPlanId = ''
  errors.invoiceTitleId = ''
  errors.invoiceAmount = ''
}

function resetForm(keepCurrentCreatePaymentPlan = false): void {
  const application = props.application
  const fixedCustomerId = props.fixedCustomer?.id ?? props.fixedInvoiceTitle?.customer_id
  const previousCustomerId = form.customerId
  const previousContractId = form.contractId
  const previousPaymentPlanId = form.paymentPlanId
  const previousInvoiceAmount = form.invoiceAmount

  const nextCustomerId = fixedCustomerId !== undefined
    ? String(fixedCustomerId)
    : application?.customer_id !== undefined ? String(application.customer_id) : ''
  const nextContractId = application?.contract_id !== null && application?.contract_id !== undefined
    ? String(application.contract_id)
    : props.fixedContractId !== null ? String(props.fixedContractId) : ''
  const shouldKeepCreatePaymentPlan = isCreateMode.value
    && keepCurrentCreatePaymentPlan
    && application === null
    && previousPaymentPlanId !== ''
    && previousCustomerId === nextCustomerId
    && previousContractId === nextContractId

  form.customerId = nextCustomerId
  form.contractId = nextContractId
  form.paymentPlanId = application?.payment_plan_id !== null && application?.payment_plan_id !== undefined
    ? String(application.payment_plan_id)
    : shouldKeepCreatePaymentPlan ? previousPaymentPlanId : ''
  form.invoiceTitleId = props.fixedInvoiceTitle !== null
    ? String(props.fixedInvoiceTitle.id)
    : application?.invoice_title_id !== undefined ? String(application.invoice_title_id) : ''
  form.invoiceType = application?.invoice_type ?? 'VAT_SPECIAL'
  form.invoiceAmount = application?.invoice_amount !== undefined
    ? String(application.invoice_amount)
    : shouldKeepCreatePaymentPlan ? previousInvoiceAmount : ''
  clearErrors()
}

function validateForm(): boolean {
  clearErrors()

  if (form.customerId.trim() === '') {
    errors.customerId = '请选择客户'
  }

  if (isCreateMode.value && form.contractId.trim() === '') {
    errors.contractId = '请选择合同'
  }

  if (isCreateMode.value && form.paymentPlanId.trim() === '') {
    errors.paymentPlanId = '请选择回款计划'
  }

  if (form.invoiceTitleId.trim() === '') {
    errors.invoiceTitleId = '请选择发票抬头'
  }

  const amount = Number(form.invoiceAmount)
  if (form.invoiceAmount.trim() === '' || !Number.isFinite(amount) || amount <= 0) {
    errors.invoiceAmount = '请输入大于 0 的开票金额'
  }

  return errors.customerId === ''
    && errors.contractId === ''
    && errors.paymentPlanId === ''
    && errors.invoiceTitleId === ''
    && errors.invoiceAmount === ''
}

function buildCreatePayload(): InvoiceApplicationCreate {
  return {
    payment_plan_id: Number(form.paymentPlanId),
    invoice_title_id: Number(form.invoiceTitleId),
    invoice_amount: Number(form.invoiceAmount),
    invoice_type: form.invoiceType,
  }
}

function buildUpdatePayload(): InvoiceApplicationUpdate {
  return {
    invoice_title_id: Number(form.invoiceTitleId),
    invoice_amount: Number(form.invoiceAmount),
    invoice_type: form.invoiceType,
  }
}

async function fetchCustomers(): Promise<void> {
  if (hasFixedCustomer.value || form.customerId !== '' || customers.value.length > 0) return

  loadingCustomers.value = true
  try {
    const response = await customerApi.getCustomers({ skip: 0, limit: 100 })
    customers.value = normalizePaginatedResponse(response).items
  } catch (error: unknown) {
    handleApiError(error, '获取客户列表')
  } finally {
    loadingCustomers.value = false
  }
}

async function fetchCustomerRelatedData(customerId: number): Promise<void> {
  loadingContracts.value = true
  loadingInvoiceTitles.value = true
  try {
    const [contractList, titleResponse] = await Promise.all([
      contractApi.getCustomerContracts(customerId, { skip: 0, limit: 100 }),
      invoiceApi.getInvoiceTitles(customerId),
    ])
    contracts.value = contractList
    invoiceTitles.value = titleResponse.invoice_titles
  } catch (error: unknown) {
    handleApiError(error, '获取客户开票数据')
  } finally {
    loadingContracts.value = false
    loadingInvoiceTitles.value = false
  }
}

async function fetchPaymentPlans(contractId: number): Promise<void> {
  loadingPaymentPlans.value = true
  try {
    paymentPlans.value = await paymentApi.getPaymentPlans(contractId)
  } catch (error: unknown) {
    handleApiError(error, '获取回款计划')
  } finally {
    loadingPaymentPlans.value = false
  }
}

function normalizeSelectValue(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return null
}

function handleCustomerChange(value: unknown): void {
  const nextCustomerId = normalizeSelectValue(value)
  if (nextCustomerId === null || nextCustomerId === '') return
  if (nextCustomerId === form.customerId) return

  form.customerId = nextCustomerId
  form.contractId = ''
  form.paymentPlanId = ''
  form.invoiceTitleId = ''
  form.invoiceAmount = ''
  contracts.value = []
  paymentPlans.value = []
  invoiceTitles.value = []

  const customerId = Number(form.customerId)
  if (Number.isFinite(customerId) && customerId > 0) {
    void fetchCustomerRelatedData(customerId)
  }
}

function handleContractChange(value: unknown): void {
  if (hasFixedContract.value) return

  const nextContractId = normalizeSelectValue(value)
  if (nextContractId === null || nextContractId === '') return
  if (nextContractId === form.contractId) return

  form.contractId = nextContractId
  form.paymentPlanId = ''
  form.invoiceAmount = ''
  paymentPlans.value = []

  const contractId = Number(form.contractId)
  if (Number.isFinite(contractId) && contractId > 0) {
    void fetchPaymentPlans(contractId)
  }
}

function handlePaymentPlanChange(value: unknown): void {
  const nextPaymentPlanId = normalizeSelectValue(value)
  if (nextPaymentPlanId === null || nextPaymentPlanId === '') return
  if (nextPaymentPlanId === form.paymentPlanId) return

  form.paymentPlanId = nextPaymentPlanId
  const plan = selectedPaymentPlan.value
  if (plan === null || !isCreateMode.value) return

  const amount = plan.remaining_amount ?? plan.planned_amount
  form.invoiceAmount = String(amount)
}

function handleInvoiceTitleChange(value: unknown): void {
  const nextInvoiceTitleId = normalizeSelectValue(value)
  if (nextInvoiceTitleId === null || nextInvoiceTitleId === '') return
  if (nextInvoiceTitleId === form.invoiceTitleId) return

  form.invoiceTitleId = nextInvoiceTitleId
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || !validateForm()) return

  submitting.value = true
  try {
    if (isCreateMode.value) {
      const invoice = await invoiceApi.createInvoiceApplication(buildCreatePayload())
      try {
        const result = await approvalGenericApi.submitApproval('INVOICE', invoice.id)
        if (result.approval_id === 0 && result.status === 'APPROVED') {
          toast.success('发票申请已创建并自动批准')
        } else {
          toast.success('发票申请已创建并提交审批')
        }
      } catch (error: unknown) {
        handleApiError(error, '提交审批')
        toast.warning('发票申请已创建，但审批提交失败，请在发票管理页面手动提交')
      }
    } else if (props.application !== null) {
      await invoiceApi.updateInvoiceApplication(props.application.id, buildUpdatePayload())
      toast.success('发票申请已更新')
    }

    visible.value = false
    emit('success')
  } catch (error: unknown) {
    handleApiError(error, isCreateMode.value ? '创建发票申请' : '更新发票申请')
  } finally {
    submitting.value = false
  }
}

function handleCancel(): void {
  if (!submitting.value) {
    visible.value = false
  }
}

function customerOptionLabel(customer: CustomerResponse): string {
  return customer.account_name
}

function contractOptionLabel(contract: ContractListResponse): string {
  return `${contract.contract_name} · ${formatCurrency(Number(contract.total_amount))}`
}

function paymentPlanOptionLabel(plan: PaymentPlanResponse): string {
  const amount = plan.remaining_amount ?? plan.planned_amount
  return `${plan.stage_name} · 待开 ${formatCurrency(Number(amount))}`
}

function invoiceTitleTypeLabel(titleType: InvoiceTitleResponse['title_type']): string {
  return titleType === 'COMPANY' ? '企业' : '个人'
}

function nullText(value: string | null | undefined): string {
  return value === null || value === undefined || value.trim() === '' ? '-' : value
}

watch(
  () => [props.open, props.mode, props.application?.id, props.fixedCustomer?.id, props.fixedInvoiceTitle?.id, props.fixedContractId] as const,
  ([open], previousValues) => {
    if (!open) {
      clearErrors()
      return
    }

    resetForm(previousValues?.[0] === true)
    void fetchCustomers()

    const customerId = Number(form.customerId)
    if (Number.isFinite(customerId) && customerId > 0) {
      void fetchCustomerRelatedData(customerId).then(() => {
        const contractId = Number(form.contractId)
        if (Number.isFinite(contractId) && contractId > 0) {
          void fetchPaymentPlans(contractId)
        }
      })
    }
  },
  { immediate: true }
)
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="invoice-application-dialog">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ description }}</DialogDescription>
      </DialogHeader>

      <form class="invoice-application-dialog__form" novalidate @submit.prevent="handleSubmit">
        <InputField
          v-if="(hasFixedCustomer && fixedCustomer !== null) || !isCreateMode"
          id="invoice-application-fixed-customer"
          class="invoice-application-dialog__field"
          :model-value="selectedCustomerName"
          label="客户"
          disabled
        />

        <SelectField
          v-else
          id="invoice-application-customer"
          :model-value="form.customerId"
          class="invoice-application-dialog__field"
          label="客户"
          required
          :options="customerOptions"
          :placeholder="loadingCustomers ? '加载客户中...' : '请选择客户'"
          :disabled="loadingCustomers || submitting || !isCreateMode"
          :error="errors.customerId"
          @update:model-value="handleCustomerChange"
        />

        <div v-if="isCreateMode" class="invoice-application-dialog__grid">
          <SelectField
            id="invoice-application-contract"
            :model-value="form.contractId"
            class="invoice-application-dialog__field"
            label="合同"
            required
            :options="contractOptions"
            :placeholder="loadingContracts ? '加载合同中...' : '请选择合同'"
            :disabled="loadingContracts || submitting || form.customerId === '' || hasFixedContract"
            :error="errors.contractId"
            @update:model-value="handleContractChange"
          />

          <SelectField
            id="invoice-application-plan"
            :model-value="form.paymentPlanId"
            class="invoice-application-dialog__field"
            label="回款计划"
            required
            :options="paymentPlanOptions"
            :placeholder="loadingPaymentPlans ? '加载计划中...' : '请选择回款计划'"
            :disabled="loadingPaymentPlans || submitting || form.contractId === ''"
            :error="errors.paymentPlanId"
            @update:model-value="handlePaymentPlanChange"
          />
        </div>

        <div v-else class="invoice-application-dialog__readonly-grid">
          <div class="invoice-application-dialog__readonly-item">
            <span>合同</span>
            <strong>{{ selectedContract?.contract_name ?? application?.contract_name ?? '-' }}</strong>
          </div>
          <div class="invoice-application-dialog__readonly-item">
            <span>回款计划</span>
            <strong>{{ selectedPaymentPlan?.stage_name ?? application?.payment_plan_stage_name ?? '-' }}</strong>
          </div>
        </div>

        <div class="invoice-application-dialog__grid">
          <InputField
            v-if="hasFixedInvoiceTitle && fixedInvoiceTitle !== null"
            id="invoice-application-fixed-title"
            class="invoice-application-dialog__field"
            :model-value="fixedInvoiceTitle?.title ?? ''"
            label="发票抬头"
            disabled
          />

          <SelectField
            v-else
            id="invoice-application-title"
            :model-value="form.invoiceTitleId"
            class="invoice-application-dialog__field"
            label="发票抬头"
            required
            :options="invoiceTitleOptions"
            :placeholder="loadingInvoiceTitles ? '加载抬头中...' : '请选择发票抬头'"
            :disabled="loadingInvoiceTitles || submitting || form.customerId === ''"
            :error="errors.invoiceTitleId"
            @update:model-value="handleInvoiceTitleChange"
          />

          <div class="invoice-application-dialog__field">
            <label class="invoice-application-dialog__label" id="invoice-application-type-label">
              发票类型
              <span class="invoice-application-dialog__required" aria-hidden="true">*</span>
            </label>
            <InvoiceTypeSegmentedControl
              v-model="form.invoiceType"
              class="invoice-application-dialog__control h-11 min-h-11"
              :disabled="submitting"
              labelled-by="invoice-application-type-label"
            />
          </div>
        </div>

        <InputField
          id="invoice-application-amount"
          v-model="form.invoiceAmount"
          class="invoice-application-dialog__field"
          label="开票金额"
          required
          type="number"
          inputmode="decimal"
          min="0"
          step="0.01"
          placeholder="请输入开票金额"
          :disabled="submitting"
          :error="errors.invoiceAmount"
        />

        <SelectionSummary
          v-if="selectedInvoiceTitle !== null"
          :items="selectedInvoiceTitleSummaryItems"
        />

        <p v-if="isEditContextLoading" class="invoice-application-dialog__hint">
          正在加载原申请上下文...
        </p>

        <DialogFooter class="invoice-application-dialog__footer">
          <Button type="button" variant="outline" :disabled="submitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :disabled="submitting">
            {{ submitting ? '提交中...' : isCreateMode ? '提交申请' : '保存' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.invoice-application-dialog {
  max-width: 720px;
}

.invoice-application-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.invoice-application-dialog__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.invoice-application-dialog__field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.invoice-application-dialog__label {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.invoice-application-dialog__required,
.invoice-application-dialog__error {
  color: $wolf-danger-v2;
}

.invoice-application-dialog__control {
  width: 100%;
}

.invoice-application-dialog__error,
.invoice-application-dialog__hint {
  margin: 0;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
}

.invoice-application-dialog__hint {
  color: $wolf-text-secondary-v2;
}

.invoice-application-dialog__readonly-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-sm-v2 $wolf-space-md-v2;
  padding: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
}

.invoice-application-dialog__readonly-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;

  span {
    color: $wolf-text-tertiary-v2;
    font-size: $wolf-font-size-caption-v2;
  }

  strong {
    color: $wolf-text-primary-v2;
    font-size: $wolf-font-size-body-v2;
    font-weight: $wolf-font-weight-medium-v2;
    overflow-wrap: anywhere;
  }
}

.invoice-application-dialog__footer {
  padding-top: $wolf-space-sm-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .invoice-application-dialog__grid,
  .invoice-application-dialog__readonly-grid {
    grid-template-columns: 1fr;
  }
}
</style>
