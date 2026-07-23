<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import {
  DateField,
  InputField,
  SearchableSelectField,
  SelectField,
} from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import { opportunityApi, type Opportunity, type OpportunityCreate, type OpportunityUpdate, LicenseType, PurchaseType } from '@/api/opportunity'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import customerApi, { type CustomerResponse, type CustomerDetailResponse } from '@/api/customer'
import { formatLocalDate } from '@/utils/format'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    customer_id: z.string().min(1, '请选择客户').refine((value) => {
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed > 0
    }, '请选择客户'),
    total_amount: z.coerce.number().gt(0, '商机金额必须大于0'),
    user_count: z.coerce.number().int('用户数必须为整数').min(1, '用户数至少为1'),
    license_type: z.nativeEnum(LicenseType, { errorMap: () => ({ message: '请选择授权类型' }) }),
    subscription_years: z.coerce.number().int('订阅年限必须为整数').min(1, '订阅年限至少为1年').optional().nullable(),
    purchase_type: z.nativeEnum(PurchaseType, { errorMap: () => ({ message: '请选择采购类型' }) }),
    expected_closing_date: z.string().min(1, '请选择预计成交日期'),
    procurement_method_id: z.coerce.number().optional().nullable()
  }).superRefine((values, ctx) => {
    if (values.license_type === LicenseType.SUBSCRIPTION && values.subscription_years == null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['subscription_years'],
        message: '订阅制下订阅年限必须大于0'
      })
    }
  })
)

interface Props {
  customerId?: number | undefined
  customerName?: string | undefined
  customerLocked?: boolean
  opportunity?: Opportunity | null
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = withDefaults(defineProps<Props>(), {
  customerId: undefined,
  customerName: undefined,
  customerLocked: false,
  opportunity: null,
  open: false
})
const emit = defineEmits<Emits>()

// Get default date (30 days from now)
function getDefaultDate(): string {
  const date = new Date()
  date.setDate(date.getDate() + 30)
  return formatLocalDate(date)
}

// VeeValidate form setup
const { handleSubmit, resetForm, values, setFieldValue } = useForm({
  validationSchema: schema,
  initialValues: {
    customer_id: '',
    total_amount: 0,
    user_count: 1,
    license_type: LicenseType.SUBSCRIPTION,
    subscription_years: 1,
    purchase_type: PurchaseType.NEW,
    expected_closing_date: getDefaultDate(),
    procurement_method_id: null
  }
})

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)
const procurementMethods = ref<ProcurementMethodOption[]>([])
const loadingMethods = ref(false)
const customers = ref<CustomerOption[]>([])
const loadingCustomers = ref(false)
const customerSearchKeyword = ref('')

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// Computed property for edit mode
const isEdit = computed(() => !!props.opportunity)

// License type options
const licenseTypeOptions = [
  { value: LicenseType.SUBSCRIPTION, label: '订阅制' },
  { value: LicenseType.PERPETUAL, label: '买断制' }
]

// Purchase type options
const purchaseTypeOptions = [
  { value: PurchaseType.NEW, label: '新购' },
  { value: PurchaseType.RENEWAL, label: '续购' },
  { value: PurchaseType.EXPANSION, label: '增购' }
]
const customerSelectOptions = computed(() =>
  customers.value.map(customer => ({
    value: customer.id,
    label: customer.account_name,
  }))
)
const procurementMethodOptions = computed(() =>
  procurementMethods.value.map(method => ({
    value: method.id,
    label: method.name,
  }))
)

interface CustomerOption {
  id: number
  account_name: string
}

type CustomerListResponse = CustomerResponse[] | { data?: { items?: CustomerResponse[] }; items?: CustomerResponse[] }

const toCustomerOption = (customer: CustomerOption): CustomerOption => ({
  id: customer.id,
  account_name: customer.account_name,
})

const normalizeCustomerList = (response: CustomerListResponse): CustomerOption[] => {
  if (Array.isArray(response)) {
    return response.map(toCustomerOption)
  }
  const items = response.items ?? response.data?.items ?? []
  return items.map(toCustomerOption)
}

const isLicenseType = (value: string | null | undefined): value is LicenseType => (
  value === LicenseType.SUBSCRIPTION || value === LicenseType.PERPETUAL
)

const isPurchaseType = (value: string | null | undefined): value is PurchaseType => (
  value === PurchaseType.NEW || value === PurchaseType.RENEWAL || value === PurchaseType.EXPANSION
)

const getLockedCustomerOption = (): CustomerOption | null => {
  if (props.customerId === undefined) return null
  const trimmedName = props.customerName?.trim()
  return {
    id: props.customerId,
    account_name: trimmedName !== undefined && trimmedName !== '' ? trimmedName : `客户 #${props.customerId}`,
  }
}

const setLockedCustomerOption = (): void => {
  const lockedCustomer = getLockedCustomerOption()
  if (lockedCustomer === null) return
  customers.value = [lockedCustomer]
}

const getOpportunityCustomerOption = (opportunity: Opportunity): CustomerOption => ({
  id: opportunity.customer_id,
  account_name: opportunity.customer_info?.account_name ?? opportunity.customer_name ?? `客户 #${opportunity.customer_id}`
})

const selectedCustomerName = computed<string>(() => {
  if (props.customerLocked) {
    const lockedCustomer = getLockedCustomerOption()
    if (lockedCustomer !== null) return lockedCustomer.account_name
  }

  const customerId = Number(values.customer_id)
  const selectedCustomer = customers.value.find((customer) => customer.id === customerId)
  if (selectedCustomer !== undefined) return selectedCustomer.account_name

  return ''
})

const buildOpportunityName = (formValues: typeof values): string => {
  const customerName = selectedCustomerName.value.trim() || '未命名客户'
  const userCount = Number(formValues.user_count) || 1
  const suffix = formValues.license_type === LicenseType.SUBSCRIPTION
    ? `${userCount}人-订阅${Number(formValues.subscription_years) || 1}年`
    : `${userCount}人-买断`
  const maxCustomerNameLength = Math.max(1, 255 - suffix.length - 1)
  return `${customerName.slice(0, maxCustomerNameLength)}-${suffix}`
}

// Fetch procurement methods
async function fetchProcurementMethods(): Promise<void> {
  loadingMethods.value = true
  try {
    procurementMethods.value = await procurementApi.getProcurementMethodOptions()
  } catch (error) {
    handleApiError(error, '获取采购方式')
  } finally {
    loadingMethods.value = false
  }
}

// Fetch customers for dropdown
async function fetchCustomers(keyword?: string): Promise<void> {
  loadingCustomers.value = true
  try {
    const params: { limit: number; keyword?: string } = { limit: 50 }
    const normalizedKeyword = keyword?.trim()
    if (normalizedKeyword !== undefined && normalizedKeyword !== '') {
      params.keyword = normalizedKeyword
    }
    const response = await customerApi.getCustomers(params)
    customers.value = normalizeCustomerList(response)
  } catch (error) {
    handleApiError(error, '获取客户列表')
  } finally {
    loadingCustomers.value = false
  }
}

// Handle customer search
async function handleCustomerSearch(keyword: string | number): Promise<void> {
  const normalizedKeyword = String(keyword).trim()
  customerSearchKeyword.value = normalizedKeyword
  await fetchCustomers(normalizedKeyword || undefined)
}

// Watch for form changes
watch(values, () => {
  isDirty.value = true
}, { deep: true })

const initializeForm = async (): Promise<void> => {
  customerSearchKeyword.value = ''

  // Edit mode: populate form with opportunity data
  if (isEdit.value && props.opportunity) {
    const opp = props.opportunity
    resetForm({
      values: {
        customer_id: String(opp.customer_id),
        total_amount: opp.total_amount,
        user_count: opp.user_count,
        license_type: opp.license_type,
        subscription_years: opp.subscription_years ?? 1,
        purchase_type: opp.purchase_type,
        expected_closing_date: opp.expected_closing_date,
        procurement_method_id: opp.procurement_method_id
      }
    })

    customers.value = [getOpportunityCustomerOption(opp)]

    if (props.customerLocked && props.customerId !== undefined) {
      setLockedCustomerOption()
      setFieldValue('customer_id', String(props.customerId))
    } else {
      try {
        const customerDetail: CustomerDetailResponse = await customerApi.getCustomerDetail(opp.customer_id)
        customers.value = [toCustomerOption(customerDetail)]
      } catch (error) {
        handleApiError(error, '获取客户详情')
      }
    }
  } else {
    const initialCustomerId = props.customerId === undefined ? '' : String(props.customerId)
    resetForm({
      values: {
        customer_id: initialCustomerId,
        total_amount: 0,
        user_count: 1,
        license_type: LicenseType.SUBSCRIPTION,
        subscription_years: 1,
        purchase_type: PurchaseType.NEW,
        expected_closing_date: getDefaultDate(),
        procurement_method_id: null
      }
    })

    if (props.customerId === undefined) {
      await fetchCustomers()
    } else {
      if (props.customerLocked) {
        setLockedCustomerOption()
        setFieldValue('customer_id', String(props.customerId))
      }
      try {
        const customerDetail: CustomerDetailResponse = await customerApi.getCustomerDetail(props.customerId)
        customers.value = [toCustomerOption(customerDetail)]
        setFieldValue('customer_id', String(customerDetail.id))

        if (customerDetail.default_opportunity) {
          setFieldValue('total_amount', customerDetail.default_opportunity.total_amount ?? 0)
          setFieldValue('user_count', customerDetail.default_opportunity.user_count ?? 1)
          setFieldValue(
            'license_type',
            isLicenseType(customerDetail.default_opportunity.license_type)
              ? customerDetail.default_opportunity.license_type
              : LicenseType.SUBSCRIPTION
          )
          setFieldValue('subscription_years', customerDetail.default_opportunity.subscription_years ?? 1)
          setFieldValue(
            'purchase_type',
            isPurchaseType(customerDetail.default_opportunity.purchase_type)
              ? customerDetail.default_opportunity.purchase_type
              : PurchaseType.NEW
          )
          if (customerDetail.default_opportunity.expected_closing_date !== null) {
            setFieldValue('expected_closing_date', customerDetail.default_opportunity.expected_closing_date)
          }
          if (customerDetail.default_opportunity.procurement_method_id !== null) {
            setFieldValue('procurement_method_id', customerDetail.default_opportunity.procurement_method_id)
          }
        }
        if (customerDetail.default_procurement_method_id !== null) {
          setFieldValue('procurement_method_id', customerDetail.default_procurement_method_id)
        }
      } catch (error) {
        if (props.customerLocked) {
          setLockedCustomerOption()
          setFieldValue('customer_id', String(props.customerId))
        }
        handleApiError(error, '获取客户详情')
      }
    }
  }

  isDirty.value = false
}

// Reset form when dialog opens
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    void initializeForm()
  }
}, { immediate: true })

// Fetch data on mount
onMounted(() => {
  fetchProcurementMethods()
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    const data: OpportunityCreate | OpportunityUpdate = {
      opportunity_name: buildOpportunityName(formValues),
      customer_id: Number(formValues['customer_id']),
      total_amount: formValues['total_amount'],
      user_count: formValues['user_count'],
      license_type: formValues['license_type'],
      subscription_years: formValues['license_type'] === LicenseType.SUBSCRIPTION ? formValues['subscription_years'] ?? null : null,
      purchase_type: formValues['purchase_type'],
      expected_closing_date: formValues['expected_closing_date'],
      procurement_method_id: formValues['procurement_method_id'] ?? null
    }

    if (isEdit.value && props.opportunity) {
      await opportunityApi.updateOpportunity(props.opportunity.id, data)
      toast.success('商机更新成功')
    } else {
      await opportunityApi.createOpportunity(data as OpportunityCreate)
      toast.success('商机创建成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新商机' : '创建商机')
  } finally {
    submitting.value = false
  }
})

// Cancel operation
function handleCancel(): void {
  if (isDirty.value) {
    showConfirmDialog.value = true
  } else {
    visible.value = false
  }
}

// Confirm discard changes
function confirmCancel(): void {
  showConfirmDialog.value = false
  visible.value = false
}

// Continue editing
function continueEditing(): void {
  showConfirmDialog.value = false
}
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>{{ isEdit ? '编辑商机' : '新建商机' }}</DialogTitle>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Customer (required) -->
        <FormField v-slot="{ value, handleChange }" name="customer_id">
          <FormItem>
            <InputField
              v-if="customerLocked === true"
              id="opportunity-customer-locked"
                :model-value="selectedCustomerName"
              label="所属客户"
              required
                readonly
              control-class="bg-wolf-bg-muted-v2 text-wolf-text-primary-v2"
                aria-readonly="true"
              />
            <SearchableSelectField
              v-else
              id="opportunity-customer"
              :model-value="String(value ?? '')"
              label="所属客户"
              required
              :options="customerSelectOptions"
              :search-value="customerSearchKeyword"
              placeholder="请选择客户"
              search-placeholder="搜索客户名称"
              :loading="loadingCustomers"
              loading-text="加载中..."
              empty-text="暂无客户"
              @update:model-value="handleChange"
              @update:open="(open: boolean) => { if (open) fetchCustomers(customerSearchKeyword) }"
              @update:search-value="handleCustomerSearch"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Total Amount (required) -->
        <FormField v-slot="{ value, handleChange }" name="total_amount">
          <FormItem>
            <InputField
                id="opportunity-total-amount"
                :model-value="Number(value ?? 0)"
                label="总金额"
                required
                type="number"
                inputmode="decimal"
                step="0.01"
                min="0"
                placeholder="请输入总金额"
                @update:model-value="handleChange"
              />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- User Count (required) -->
        <FormField v-slot="{ value, handleChange }" name="user_count">
          <FormItem>
            <InputField
                id="opportunity-user-count"
                :model-value="Number(value ?? 1)"
                label="用户数"
                required
                type="number"
                min="1"
                placeholder="请输入用户数"
                @update:model-value="handleChange"
              />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- License Type (Select) -->
        <FormField v-slot="{ value, handleChange }" name="license_type">
          <FormItem>
            <SelectField
              id="opportunity-license-type"
              :model-value="String(value ?? '')"
              label="授权类型"
              required
              :options="licenseTypeOptions"
              placeholder="请选择授权类型"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Subscription Years (required, only for SUBSCRIPTION) -->
        <FormField v-if="values.license_type === LicenseType.SUBSCRIPTION" v-slot="{ value, handleChange }" name="subscription_years">
          <FormItem>
            <InputField
                id="opportunity-subscription-years"
                :model-value="Number(value ?? 1)"
                label="订阅年限"
                required
                type="number"
                min="1"
                max="10"
                placeholder="请输入订阅年限"
                @update:model-value="handleChange"
              />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Purchase Type (Select) -->
        <FormField v-slot="{ value, handleChange }" name="purchase_type">
          <FormItem>
            <SelectField
              id="opportunity-purchase-type"
              :model-value="String(value ?? '')"
              label="采购类型"
              required
              :options="purchaseTypeOptions"
              placeholder="请选择采购类型"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Expected Closing Date (required) -->
        <FormField v-slot="{ value, handleChange }" name="expected_closing_date">
          <FormItem>
            <DateField
                id="opportunity-expected-closing-date"
                :model-value="value ? new Date(String(value)) : null"
                label="预计成交日期"
                required
                placeholder="请选择预计成交日期"
                @update:model-value="(date: Date | null) => handleChange(date ? formatLocalDate(date) : '')"
              />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Procurement Method (optional) -->
        <FormField v-slot="{ value, handleChange }" name="procurement_method_id">
          <FormItem>
            <SelectField
              id="opportunity-procurement-method"
              :model-value="String(value ?? '')"
              label="采购方式"
              :options="procurementMethodOptions"
              :placeholder="loadingMethods ? '加载采购方式中...' : '请选择采购方式'"
              :disabled="loadingMethods"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting">
            {{ submitting ? '提交中...' : '确定' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- Confirm discard changes dialog -->
  <AlertDialog v-model:open="showConfirmDialog">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃更改？</AlertDialogTitle>
        <AlertDialogDescription>
          您有未保存的更改，确定要关闭吗？
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">
          继续编辑
        </AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">
          放弃更改
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
