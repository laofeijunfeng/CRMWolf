<script setup lang="ts">
import { ref, computed, watch } from 'vue'
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
  FileAttachment,
  InputField,
  SearchableSelectField,
  SelectField,
} from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import contractApi, { type ContractCreate, type ContractUpdate, type ContractResponse, type LicenseType } from '@/api/contract'
import { opportunityApi } from '@/api/opportunity'
import customerApi, { type ContactResponse, type CustomerResponse, type CustomerDetailResponse } from '@/api/customer'
import { formatLocalDate } from '@/utils/format'
import type { FileAttachmentItem } from '@/types/fileAttachment'

// Zod schema for form validation - use coerce for number fields
const schema = toTypedSchema(
  z.object({
    customer_id: z.string().min(1, '请选择客户').refine((value) => {
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed > 0
    }, '请选择客户'),
    contract_name: z.string().min(1, '请输入合同名称').max(100, '合同名称不能超过100字'),
    opportunity_id: z.coerce.number().min(1, '请选择商机'),
    signing_contact_id: z.coerce.number().min(1, '请选择签署联系人'),
    user_count: z.coerce.number().int('用户数必须为整数').min(1, '用户数至少为1'),
    total_amount: z.coerce.number().min(0, '金额不能为负数'),
    license_type: z.enum(['SUBSCRIPTION', 'PERPETUAL'], { errorMap: () => ({ message: '请选择授权类型' }) }),
    subscription_years: z.coerce.number().int('订阅年限必须为整数').min(1, '订阅年限至少为1年').optional().nullable(),
    signing_date: z.string().optional().nullable(),
    effective_date: z.string().optional().nullable()
  })
)

interface Props {
  customerId?: number | undefined
  customerName?: string | undefined
  customerLocked?: boolean
  fixedOpportunity?: ContractOpportunityOption | null
  open: boolean
  contract?: ContractResponse | null
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = withDefaults(defineProps<Props>(), {
  customerId: undefined,
  customerName: undefined,
  customerLocked: false,
  fixedOpportunity: null,
  open: false,
  contract: null
})
const emit = defineEmits<Emits>()

// VeeValidate form setup
const { handleSubmit, resetForm, setValues, setFieldValue, values } = useForm({
  validationSchema: schema,
  initialValues: {
    customer_id: '',
    contract_name: '',
    user_count: 1,
    total_amount: 0,
    license_type: 'SUBSCRIPTION',
    subscription_years: 1
  }
})

// State
const submitting = ref(false)
const isDirty = ref(false)
const showConfirmDialog = ref(false)
const opportunities = ref<ContractOpportunityOption[]>([])
const contacts = ref<ContactResponse[]>([])
const loadingOpportunities = ref(false)
const loadingContacts = ref(false)
const customers = ref<CustomerOption[]>([])
const loadingCustomers = ref(false)
const customerSearchKeyword = ref('')
const contractNameManuallyEdited = ref(false)
const isApplyingGeneratedName = ref(false)
const lastGeneratedContractName = ref('')
const selectedContractFile = ref<File | null>(null)

interface CustomerOption {
  id: number
  account_name: string
}

interface ContractOpportunityOption {
  id: number
  opportunity_name: string
  customer_id: number
  customer_name?: string
  total_amount: number
  user_count: number
  license_type: string
  subscription_years: number | null
}

type CustomerListResponse = CustomerResponse[] | { data?: { items?: CustomerResponse[] }; items?: CustomerResponse[] }

const normalizeCustomerList = (response: CustomerListResponse): CustomerOption[] => {
  if (Array.isArray(response)) {
    return response.map(c => ({ id: c.id, account_name: c.account_name }))
  }
  const items = response.items ?? response.data?.items ?? []
  return items.map(c => ({ id: c.id, account_name: c.account_name }))
}

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

// Computed property for edit mode
const isEdit = computed(() => !!props.contract)
const hasFixedOpportunity = computed(() => props.fixedOpportunity !== null && props.fixedOpportunity !== undefined)
const canSubmit = computed(() => !submitting.value && (isEdit.value || selectedContractFile.value !== null))
const selectedContractFileItems = computed<FileAttachmentItem[]>(() => {
  if (selectedContractFile.value === null) return []
  const fileName = selectedContractFile.value.name
  return [{
    id: fileName,
    name: fileName,
    size: selectedContractFile.value.size,
    mimeType: selectedContractFile.value.type,
    extension: getFileExtension(fileName),
    status: 'idle'
  }]
})

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// License type options
const licenseTypeOptions = [
  { value: 'SUBSCRIPTION', label: '订阅制' },
  { value: 'PERPETUAL', label: '买断制' }
]

const selectedOpportunity = computed<ContractOpportunityOption | null>(() => {
  if (props.fixedOpportunity !== null) return props.fixedOpportunity

  const opportunityId = Number(values.opportunity_id)
  if (!Number.isFinite(opportunityId) || opportunityId <= 0) return null

  return opportunities.value.find((opportunity) => opportunity.id === opportunityId) ?? null
})

const selectedCustomerName = computed<string>(() => {
  const customerId = Number(values.customer_id)
  const selectedCustomer = customers.value.find((customer) => customer.id === customerId)
  const opportunityCustomerName = selectedOpportunity.value?.customer_name?.trim()

  if (selectedCustomer !== undefined) return selectedCustomer.account_name
  if (opportunityCustomerName !== undefined && opportunityCustomerName !== '') return opportunityCustomerName
  if (props.customerName !== undefined && props.customerName.trim() !== '') return props.customerName.trim()

  return ''
})

const opportunitySelectDisabled = computed<boolean>(() => {
  if (hasFixedOpportunity.value) return true
  return Number(values.customer_id) <= 0
})

const opportunitySelectPlaceholder = computed<string>(() => {
  if (Number(values.customer_id) <= 0) return '请先选择客户'
  return loadingOpportunities.value ? '加载商机中...' : '请选择商机'
})
const customerSelectOptions = computed(() =>
  customers.value.map(customer => ({
    value: customer.id,
    label: customer.account_name,
  }))
)
const opportunitySelectOptions = computed(() =>
  opportunities.value.map(opportunity => ({
    value: opportunity.id,
    label: opportunity.opportunity_name,
  }))
)
const contactSelectOptions = computed(() =>
  contacts.value.map(contact => {
    const position = contact.position?.trim()
    return {
      value: contact.id,
      label: `${contact.name}${position !== undefined && position !== '' ? ` (${position})` : ''}`,
    }
  })
)

// Fetch available opportunities for this customer
async function fetchOpportunities(customerId: number): Promise<void> {
  loadingOpportunities.value = true
  try {
    opportunities.value = await opportunityApi.getAvailableForContract(customerId)
    if (props.fixedOpportunity !== null && !opportunities.value.some((item) => item.id === props.fixedOpportunity?.id)) {
      opportunities.value = [props.fixedOpportunity, ...opportunities.value]
    }
  } catch (error) {
    if (props.fixedOpportunity !== null) {
      opportunities.value = [props.fixedOpportunity]
    }
    handleApiError(error, '获取商机列表')
  } finally {
    loadingOpportunities.value = false
  }
}

// Fetch contacts for this customer
async function fetchContacts(customerId: number): Promise<void> {
  loadingContacts.value = true
  try {
    contacts.value = await customerApi.getContacts(customerId)
  } catch (error) {
    handleApiError(error, '获取联系人列表')
  } finally {
    loadingContacts.value = false
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

watch(() => values.contract_name, (contractName) => {
  if (isApplyingGeneratedName.value) return
  contractNameManuallyEdited.value = contractName !== lastGeneratedContractName.value
})

function normalizeLicenseType(value: string): LicenseType {
  return value === 'PERPETUAL' ? 'PERPETUAL' : 'SUBSCRIPTION'
}

function getFileExtension(fileName: string): string {
  return fileName.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

function isAllowedContractFile(file: File): boolean {
  return ['pdf', 'docx'].includes(getFileExtension(file.name))
}

function handleContractFileUpload(files: File[]): void {
  const file = files[0]
  if (file === undefined) return
  if (!isAllowedContractFile(file)) {
    toast.error('仅支持上传 PDF 或 DOCX 文件，旧版 DOC 请转存后上传')
    return
  }
  selectedContractFile.value = file
  isDirty.value = true
}

function handleContractFileRemove(): void {
  selectedContractFile.value = null
  isDirty.value = true
}

function handleContractFileError(message: string): void {
  toast.error(message)
}

function buildContractName(opportunity: ContractOpportunityOption): string {
  const customerName = selectedCustomerName.value || '客户'
  const userCount = Number(opportunity.user_count) || 1
  const licenseType = normalizeLicenseType(opportunity.license_type)

  if (licenseType === 'PERPETUAL') {
    return `${customerName}-${userCount}人-买断`
  }

  const years = Number(opportunity.subscription_years ?? 1) || 1
  return `${customerName}-${userCount}人-订阅${years}年`
}

function setGeneratedContractName(name: string): void {
  isApplyingGeneratedName.value = true
  lastGeneratedContractName.value = name
  contractNameManuallyEdited.value = false
  setFieldValue('contract_name', name)
  setTimeout(() => {
    isApplyingGeneratedName.value = false
  }, 0)
}

function applyOpportunityDefaults(opportunity: ContractOpportunityOption, options: { forceName: boolean }): void {
  const licenseType = normalizeLicenseType(opportunity.license_type)

  setFieldValue('opportunity_id', opportunity.id)
  setFieldValue('user_count', opportunity.user_count)
  setFieldValue('total_amount', opportunity.total_amount)
  setFieldValue('license_type', licenseType)
  setFieldValue('subscription_years', licenseType === 'SUBSCRIPTION' ? opportunity.subscription_years ?? 1 : null)

  const generatedName = buildContractName(opportunity)
  if (options.forceName || !contractNameManuallyEdited.value || values.contract_name === lastGeneratedContractName.value) {
    setGeneratedContractName(generatedName)
  } else {
    lastGeneratedContractName.value = generatedName
  }
}

function handleOpportunityChange(value: unknown): void {
  const opportunityId = Number(value)
  if (!Number.isFinite(opportunityId) || opportunityId <= 0) return
  setFieldValue('opportunity_id', opportunityId)

  const opportunity = opportunities.value.find((item) => item.id === opportunityId)
  if (opportunity !== undefined) {
    applyOpportunityDefaults(opportunity, { forceName: true })
  }
}

// Reset or populate form when dialog opens
watch(() => props.open, async (newOpen) => {
  if (newOpen) {
    customerSearchKeyword.value = ''

    if (props.contract) {
      selectedContractFile.value = null
      // Edit mode: populate form with contract data
      setValues({
        customer_id: props.contract.customer_id.toString(),
        contract_name: props.contract.contract_name,
        opportunity_id: props.contract.opportunity_id,
        signing_contact_id: props.contract.signing_contact_id,
        user_count: props.contract.user_count,
        total_amount: parseFloat(props.contract.total_amount),
        license_type: props.contract.license_type,
        subscription_years: props.contract.subscription_years ?? null,
        signing_date: props.contract.signing_date ?? null,
        effective_date: props.contract.effective_date ?? null
      })

      // Fetch customer for display
      if (props.contract.customer_id) {
        try {
          const customerDetail: CustomerDetailResponse = await customerApi.getCustomerDetail(props.contract.customer_id)
          customers.value = [{ id: customerDetail.id, account_name: customerDetail.account_name }]
        } catch (error) {
          handleApiError(error, '获取客户详情')
        }
      }

      // Fetch opportunities and contacts for this customer
      await fetchOpportunities(props.contract.customer_id)
      await fetchContacts(props.contract.customer_id)
    } else {
      // Create mode: reset form
      const initialCustomerId = props.customerId === undefined ? '' : String(props.customerId)

      const initialValues = {
        customer_id: initialCustomerId,
        contract_name: '',
        user_count: 1,
        total_amount: 0,
        license_type: 'SUBSCRIPTION' as const,
        subscription_years: 1
      }
      resetForm({
        values: props.fixedOpportunity === null
          ? initialValues
          : { ...initialValues, opportunity_id: props.fixedOpportunity.id }
      })
      contractNameManuallyEdited.value = false
      lastGeneratedContractName.value = ''
      selectedContractFile.value = null

      if (props.customerLocked && props.customerId !== undefined) {
        setLockedCustomerOption()
        await fetchOpportunities(props.customerId)
        await fetchContacts(props.customerId)
      } else if (props.customerId === undefined) {
        await fetchCustomers()
      } else {
        // customerId provided but not locked - fetch customer detail and dependent data
        try {
          const customerDetail: CustomerDetailResponse = await customerApi.getCustomerDetail(props.customerId)
          customers.value = [{ id: customerDetail.id, account_name: customerDetail.account_name }]
          await fetchOpportunities(props.customerId)
          await fetchContacts(props.customerId)

          // Auto-fill contract name based on customer
          setFieldValue('contract_name', `${customerDetail.account_name}合同`)
        } catch (error) {
          if (props.customerLocked) {
            setLockedCustomerOption()
          }
          handleApiError(error, '获取客户详情')
        }
      }

      if (props.fixedOpportunity !== null) {
        applyOpportunityDefaults(props.fixedOpportunity, { forceName: true })
      }
    }

    // Reset dirty state after form is populated/reset
    setTimeout(() => {
      isDirty.value = false
    }, 100)
  }
})

// Watch customer_id changes to fetch opportunities and contacts
watch(() => values.customer_id, async (newCustomerId) => {
  const customerId = Number(newCustomerId)
  if (customerId > 0 && !props.customerLocked && !hasFixedOpportunity.value) {
    // Clear previous selections
    setFieldValue('opportunity_id', undefined as unknown as number)
    setFieldValue('signing_contact_id', undefined as unknown as number)
    opportunities.value = []

    // Fetch dependent data
    await fetchOpportunities(customerId)
    await fetchContacts(customerId)
  }
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true
  try {
    if (isEdit.value && props.contract) {
      // Edit mode: use update
      const data: ContractUpdate = {
        contract_name: formValues['contract_name'] ?? null,
        signing_contact_id: formValues['signing_contact_id'] ?? null,
        user_count: formValues['user_count'] ?? null,
        total_amount: formValues['total_amount'] ?? null,
        license_type: formValues['license_type'] ?? null,
        subscription_years: formValues['license_type'] === 'SUBSCRIPTION' ? formValues['subscription_years'] ?? null : null,
        signing_date: formValues['signing_date'] ?? null,
        effective_date: formValues['effective_date'] ?? null
      }
      await contractApi.updateContract(props.contract.id, data)
      toast.success('合同更新成功')
    } else {
      if (selectedContractFile.value === null) {
        toast.warning('请上传合同邮件附件')
        return
      }

      // Create mode
      const data: ContractCreate = {
        contract_name: formValues['contract_name'],
        customer_id: Number(formValues['customer_id']),
        opportunity_id: formValues['opportunity_id'],
        signing_contact_id: formValues['signing_contact_id'],
        user_count: formValues['user_count'],
        total_amount: formValues['total_amount'],
        license_type: formValues['license_type'] as LicenseType,
        subscription_years: formValues['license_type'] === 'SUBSCRIPTION' ? formValues['subscription_years'] ?? null : null,
        signing_date: formValues['signing_date'] ?? null,
        effective_date: formValues['effective_date'] ?? null
      }
      await contractApi.createContract({
        data,
        file: selectedContractFile.value
      })
      toast.success('合同创建成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新合同' : '创建合同')
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
        <DialogTitle>{{ isEdit ? '编辑合同' : '新建合同' }}</DialogTitle>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- Customer (required, only in create mode) -->
        <FormField v-if="!isEdit" v-slot="{ value, handleChange }" name="customer_id">
          <FormItem>
            <InputField
              v-if="customerLocked === true"
              id="contract-customer-locked"
              :model-value="selectedCustomerName"
              label="所属客户"
              required
              readonly
              control-class="bg-wolf-bg-muted-v2 text-wolf-text-primary-v2"
              aria-readonly="true"
            />
            <SearchableSelectField
              v-else
              id="contract-customer"
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

        <!-- Opportunity (required, only in create mode) -->
        <FormField v-if="!isEdit" v-slot="{ value }" name="opportunity_id">
          <FormItem>
            <SelectField
              id="contract-opportunity"
              :model-value="value !== undefined && value !== null ? String(value) : ''"
              label="关联商机"
              required
              :options="opportunitySelectOptions"
              :placeholder="opportunitySelectPlaceholder"
              :disabled="opportunitySelectDisabled"
              @update:model-value="handleOpportunityChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Contract Name (required) -->
        <FormField v-slot="{ value, handleChange }" name="contract_name">
          <FormItem>
            <InputField
              id="contract-name"
              :model-value="String(value ?? '')"
              label="合同名称"
              required
              placeholder="选择商机后自动生成，可手动修改"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <FileAttachment
          v-if="!isEdit"
          title="合同邮件附件"
          description="仅支持 PDF 或 DOCX，旧版 DOC 请转存后上传"
          mode="manage"
          accept=".pdf,.docx"
          required
          :files="selectedContractFileItems"
          :multiple="false"
          :allow-preview="false"
          empty-text="请上传合同邮件附件"
          @upload="handleContractFileUpload"
          @remove="handleContractFileRemove"
          @error="handleContractFileError"
        />

        <!-- Signing Contact (required) -->
        <FormField v-slot="{ value, handleChange }" name="signing_contact_id">
          <FormItem>
            <SelectField
              id="contract-signing-contact"
              :model-value="value !== undefined && value !== null ? String(value) : ''"
              label="签署联系人"
              required
              :options="contactSelectOptions"
              :placeholder="loadingContacts ? '加载联系人中...' : '请选择签署联系人'"
              :disabled="loadingContacts"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- User Count (required) -->
        <FormField v-slot="{ value, handleChange }" name="user_count">
          <FormItem>
            <InputField
              id="contract-user-count"
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

        <!-- Total Amount (required) -->
        <FormField v-slot="{ value, handleChange }" name="total_amount">
          <FormItem>
            <InputField
              id="contract-total-amount"
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

        <!-- License Type (Select) -->
        <FormField v-slot="{ value, handleChange }" name="license_type">
          <FormItem>
            <SelectField
              id="contract-license-type"
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

        <!-- Subscription Years (optional, only for SUBSCRIPTION) -->
        <FormField v-if="values.license_type === 'SUBSCRIPTION'" v-slot="{ value, handleChange }" name="subscription_years">
          <FormItem>
            <InputField
              id="contract-subscription-years"
              :model-value="Number(value ?? 1)"
              label="订阅年限"
              type="number"
              min="1"
              max="10"
              placeholder="请输入订阅年限"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Signing Date (optional) -->
        <FormField v-slot="{ value, handleChange }" name="signing_date">
          <FormItem>
            <DateField
              id="contract-signing-date"
              :model-value="value ? new Date(String(value)) : null"
              label="签署日期"
              placeholder="请选择签署日期"
              @update:model-value="(date: Date | null) => handleChange(date ? formatLocalDate(date) : null)"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Effective Date (optional) -->
        <FormField v-slot="{ value, handleChange }" name="effective_date">
          <FormItem>
            <DateField
              id="contract-effective-date"
              :model-value="value ? new Date(String(value)) : null"
              label="生效日期"
              placeholder="请选择生效日期"
              @update:model-value="(date: Date | null) => handleChange(date ? formatLocalDate(date) : null)"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting" :disabled="!canSubmit">
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
