<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { FormField, FormItem, FormMessage } from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import {
  DateField,
  IndustryHierarchySelectField,
  InputField,
  ProductIntentPicker,
  SegmentedChoiceControl,
  SelectField,
} from '@/components/crmwolf'
import FormErrorSummary from '@/components/crmwolf/FormErrorSummary.vue'
import { handleApiError } from '@/utils/errorHandler'
import { formatLocalDate } from '@/utils/format'
import { licenseStatusLabel } from '@/utils/licenseStatus'
import { productPublicIdFromIntent } from '@/utils/productIntent'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'
import customerApi, {
  type CustomerCreate,
  type CustomerDetailResponse,
  type CustomerResponse,
} from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import { buildCustomerUpdatePayload, type CustomerEditableSnapshot } from './customerFormDiff'
import {
  customerEditSchema,
  customerCreateSchema,
  companyScaleOptions,
  type CustomerForm,
  type CustomerEditForm,
  type CustomerCreateForm,
} from '@/schemas/customer-form'
import { useAcquisitionSourceOptions } from '@/composables/useAcquisitionSourceOptions'
import ErrorState from '@/components/ErrorState.vue'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import type { FormSuccessPayload } from '@/types/actionOutcome'

interface Props { open: boolean; mode: 'create' | 'edit'; customerId?: string; customer?: CustomerDetailResponse | null }
interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success', payload?: FormSuccessPayload): void
}
const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const schema = computed(() => props.mode === 'create' ? toTypedSchema(customerCreateSchema) : toTypedSchema(customerEditSchema))
interface CustomerEditFormValues {
  account_name: string
  city: string
  address: string
  company_scale?: string
  source_public_id?: string
  product_public_id: string
  default_procurement_method_id?: number
}

const { handleSubmit, resetForm, setValues, setFieldValue, setFieldError, setErrors, errors, values } = useForm<CustomerEditForm | CustomerCreateForm>({
  validationSchema: schema,
  initialValues: { account_name: '', city: '', address: '', company_scale: undefined, source_public_id: undefined, product_public_id: '', default_procurement_method_id: undefined, contact_name: '', contact_mobile: '', contact_position: '', contact_gender: undefined } as unknown as CustomerCreateForm,
})
const { value: contactGenderValue, errorMessage: contactGenderError } = useField<string>('contact_gender')
const genderOptions = [{ value: '男', label: '男', tone: 'primary' as const }, { value: '女', label: '女', tone: 'success' as const }]
const submitting = ref(false)
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const submitError = ref<FeedbackError | null>(null)
const loadedVersion = ref<number | null>(null)
const procurementMethodsLoading = ref(false)
const procurementMethodsError = ref<FeedbackError | null>(null)
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])
const procurementMethodSelectOptions = computed(() => procurementMethodOptions.value.map(option => ({ value: option.id, label: option.name })))
const companyScaleSelectOptions = computed<{ value: string; label: string }[]>(() => {
  const options: { value: string; label: string }[] = companyScaleOptions.map(option => ({ value: option.value, label: option.label }))
  const current = typeof values.company_scale === 'string' ? values.company_scale.trim() : ''
  if (current !== '' && !options.some(option => option.value === current)) options.push({ value: current, label: current })
  return options
})
const { formSelectOptions: sourceSelectOptions, loading: sourceOptionsLoading, loadFormOptions, ensureOption } = useAcquisitionSourceOptions()
const sourceOptionsError = ref<FeedbackError | null>(null)
const optionsLoading = computed(() => procurementMethodsLoading.value || sourceOptionsLoading.value)
const optionsError = computed(() => procurementMethodsError.value !== null || sourceOptionsError.value !== null)
const moreInfoOpen = ref(false)
const industryHierarchy = ref<import('@/schemas/customer').CustomerIndustryHierarchy>({})
const industryHierarchyLoading = ref(false)
const industryHierarchyError = ref<FeedbackError | null>(null)
const industryValue = ref('')
const industryBaseline = ref('')
const retainedIndustryInfo = ref<CustomerDetailResponse['industry_info']>(null)
const profileBaseline = ref<CustomerEditableSnapshot>(emptyEditableSnapshot())
const lifecycleStatusValue = ref<0 | 1 | null>(null)
const lifecycleStatusBaseline = ref<0 | 1 | null>(null)
const customerStatusPresent = ref(false)
const licenseTypeValue = ref<'TRIAL' | 'OFFICIAL' | null>(null)
const licenseExpiryDateValue = ref<string | null>(null)
const licenseTypeBaseline = ref<'TRIAL' | 'OFFICIAL' | null>(null)
const licenseExpiryDateBaseline = ref<string | null>(null)
const isDirty = ref(false)
const applyingFormValues = ref(false)
const writeSubmitting = computed(() => submitting.value)
const statusIsReadOnly = computed(() => props.mode === 'edit' && customerStatusPresent.value && lifecycleStatusValue.value === null)
const industryErrorMessage = computed(() => {
  const message = errors.value.industry
  return typeof message === 'string' ? message : ''
})
const closeGuard = useDialogCloseGuard({
  isDirty: computed(() => (
    isDirty.value
    || industryValue.value !== industryBaseline.value
    || lifecycleStatusValue.value !== lifecycleStatusBaseline.value
    || licenseTypeValue.value !== licenseTypeBaseline.value
    || licenseExpiryDateValue.value !== licenseExpiryDateBaseline.value
  )),
  submitting: writeSubmitting,
  emitOpen: (open) => emit('update:open', open),
})
const showConfirmDialog = closeGuard.showConfirmDialog
const fieldLabels: Record<string, string> = {
  account_name: '客户名称',
  city: '所在城市',
  address: '详细地址',
  company_scale: '公司规模',
  source_public_id: '获客来源',
  product_public_id: '产品',
  default_procurement_method_id: '采购方式',
  contact_name: '联系人姓名',
  contact_mobile: '联系电话',
  contact_position: '职位',
  contact_gender: '性别',
  industry: '行业',
  status: '客户状态',
  license_type: '授权类型',
  license_expiry_date: '授权到期日',
}
const contactFields = new Set(['contact_name', 'contact_mobile', 'contact_position', 'contact_gender'])
const progressiveFields = new Set(['industry', 'status', 'license_type', 'license_expiry_date'])
const errorSummary = computed(() => Object.entries(errors.value).flatMap(([field, message]) => {
  if (props.mode === 'edit' && contactFields.has(field)) return []
  if (typeof message !== 'string' || message === '') return []
  return [{ field, label: fieldLabels[field] ?? field, message, targetId: `customer-${field.split('_').join('-')}` }]
}))
const moreInfoCount = computed(() => {
  let count = 0
  if (industryValue.value !== '') count += 1
  if (lifecycleStatusValue.value !== null || (props.mode === 'edit' && customerStatusPresent.value)) count += 1
  if (licenseTypeValue.value !== null) count += 1
  if (licenseExpiryDateValue.value !== null) count += 1
  return count
})
const focusFirstError = async (): Promise<void> => {
  const firstError = errorSummary.value[0]
  if (firstError === undefined || typeof document === 'undefined') return
  if (progressiveFields.has(firstError.field)) moreInfoOpen.value = true
  await nextTick()
  const field = document.querySelector<HTMLElement>(`[name="${firstError.field}"], #customer-${firstError.field.split('_').join('-')}`)
  if (field === null) return
  field.scrollIntoView({ behavior: 'smooth', block: 'center' })
  field.focus({ preventScroll: true })
}
watch(values, () => { if (!applyingFormValues.value) { isDirty.value = true; submitError.value = null } }, { deep: true, flush: 'sync' })
async function fetchProcurementMethodOptions(): Promise<void> {
  if (procurementMethodOptions.value.length > 0 || procurementMethodsLoading.value) return
  procurementMethodsError.value = null
  procurementMethodsLoading.value = true
  try {
    procurementMethodOptions.value = await procurementApi.getProcurementMethodOptions()
  } catch (error) {
    procurementMethodsError.value = toFeedbackError(error, '采购方式', { operation: 'read' })
    handleApiError(error, '获取采购方式')
  } finally {
    procurementMethodsLoading.value = false
  }
}
async function fetchSourceOptions(): Promise<void> {
  sourceOptionsError.value = null
  try {
    await loadFormOptions({ throwOnError: true, notifyOnError: false })
  } catch (error) {
    sourceOptionsError.value = toFeedbackError(error, '获客来源', { operation: 'read' })
    handleApiError(error, '获取获客来源')
  }
}
function retryOptions(): void {
  if (procurementMethodsError.value !== null) void fetchProcurementMethodOptions()
  if (sourceOptionsError.value !== null) void fetchSourceOptions()
}
async function fetchIndustryHierarchy(): Promise<void> {
  if (industryHierarchyLoading.value) return
  industryHierarchyLoading.value = true
  industryHierarchyError.value = null
  try {
    industryHierarchy.value = await customerApi.getIndustryHierarchy()
  } catch (error) {
    industryHierarchyError.value = toFeedbackError(error, '行业', { operation: 'read' })
    handleApiError(error, '获取行业')
  } finally {
    industryHierarchyLoading.value = false
  }
}
function handleMoreInfoChange(open: boolean): void {
  moreInfoOpen.value = open
  if (open && Object.keys(industryHierarchy.value).length === 0 && industryHierarchyError.value === null) {
    void fetchIndustryHierarchy()
  }
}
function normalizeOptionalText(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? ''
  return normalized === '' ? null : normalized
}
function normalizeDateValue(value: string | null | undefined): string | null {
  return normalizeOptionalText(value)
}
function normalizeCompanyScale(value: string | null): CustomerEditForm['company_scale'] | undefined {
  const normalized = value?.trim() ?? ''
  return normalized === '' ? undefined : normalized
}
function emptyEditableSnapshot(): CustomerEditableSnapshot {
  return {
    account_name: '',
    city: '',
    address: null,
    company_scale: null,
    source_public_id: null,
    product_public_id: null,
    default_procurement_method_id: null,
    industry: null,
    status: null,
    license_type: null,
    license_expiry_date: null,
  }
}
function editableStatus(status: CustomerDetailResponse['status']): 0 | 1 | null {
  return status === 0 || status === 1 ? status : null
}
function editableLicenseType(value: string | null): 'TRIAL' | 'OFFICIAL' | null {
  return value === 'TRIAL' || value === 'OFFICIAL' ? value : null
}
function buildCustomerEditFormValues(customer: CustomerDetailResponse): CustomerEditFormValues {
  const formValues: CustomerEditFormValues = {
    account_name: customer.account_name,
    city: customer.city,
    address: customer.address ?? '',
    product_public_id: productPublicIdFromIntent(customer),
  }
  const companyScale = normalizeCompanyScale(customer.company_scale)
  if (companyScale !== undefined) formValues.company_scale = companyScale
  const sourcePublicId = customer.source_info?.public_id
  if (sourcePublicId !== undefined) formValues.source_public_id = sourcePublicId
  const procurementMethodId = customer.default_procurement_method_id ?? undefined
  if (procurementMethodId !== undefined) formValues.default_procurement_method_id = procurementMethodId
  return formValues
}
type CustomerProfileField = keyof CustomerEditFormValues
const customerProfileFields: readonly CustomerProfileField[] = ['account_name', 'city', 'address', 'company_scale', 'source_public_id', 'product_public_id', 'default_procurement_method_id']
function normalizeProfileValue(field: CustomerProfileField, value: unknown): string | number | null {
  if (field === 'default_procurement_method_id') {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      return Number.isFinite(parsed) ? parsed : null
    }
    return null
  }
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized === '' ? null : normalized
}
function hasProfileInputChanged(field: CustomerProfileField, current: Partial<CustomerEditFormValues>, baseline: CustomerEditableSnapshot): boolean {
  return normalizeProfileValue(field, current[field]) !== normalizeProfileValue(field, baseline[field])
}
function normalizeIndustryValue(value: string | null | undefined): string | null {
  return normalizeOptionalText(value)
}
function buildEditableSnapshot(customer: {
  account_name: string
  city: string
  address: string | null
  company_scale: string | null
  source_info?: { public_id?: string | null } | null
  product_public_id?: string | null
  default_procurement_method_id: number | null
  industry: string | null
  status: CustomerDetailResponse['status']
  license_type: string | null
  license_expiry_date: string | null
}): CustomerEditableSnapshot {
  return {
    account_name: customer.account_name,
    city: customer.city,
    address: customer.address,
    company_scale: customer.company_scale,
    source_public_id: customer.source_info?.public_id ?? null,
    product_public_id: productPublicIdFromIntent(customer) || null,
    default_procurement_method_id: customer.default_procurement_method_id,
    industry: customer.industry,
    status: editableStatus(customer.status),
    license_type: editableLicenseType(customer.license_type),
    license_expiry_date: customer.license_expiry_date,
  }
}
function buildCurrentSnapshot(editData: CustomerEditForm): CustomerEditableSnapshot {
  return {
    account_name: editData.account_name,
    city: editData.city,
    address: editData.address ?? null,
    company_scale: editData.company_scale ?? null,
    source_public_id: editData.source_public_id ?? null,
    product_public_id: editData.product_public_id ?? null,
    default_procurement_method_id: editData.default_procurement_method_id ?? null,
    industry: normalizeIndustryValue(industryValue.value),
    status: lifecycleStatusValue.value,
    license_type: licenseTypeValue.value,
    license_expiry_date: licenseExpiryDateValue.value,
  }
}
function mergeCustomerProfileValues(latest: CustomerDetailResponse): CustomerEditFormValues {
  const latestValues = buildCustomerEditFormValues(latest)
  const currentValues = values as unknown as Partial<CustomerEditFormValues>
  const preservedFields = new Set(customerProfileFields.filter((field) => hasProfileInputChanged(field, currentValues, profileBaseline.value)))
  const formValues: CustomerEditFormValues = {
    account_name: preservedFields.has('account_name') ? currentValues.account_name ?? '' : latestValues.account_name,
    city: preservedFields.has('city') ? currentValues.city ?? '' : latestValues.city,
    address: preservedFields.has('address') ? currentValues.address ?? '' : latestValues.address,
    product_public_id: preservedFields.has('product_public_id') ? currentValues.product_public_id ?? '' : latestValues.product_public_id,
  }
  const companyScale = preservedFields.has('company_scale') ? currentValues.company_scale : latestValues.company_scale
  if (companyScale !== undefined) formValues.company_scale = companyScale
  const sourcePublicId = preservedFields.has('source_public_id') ? currentValues.source_public_id : latestValues.source_public_id
  if (sourcePublicId !== undefined) formValues.source_public_id = sourcePublicId
  const procurementMethodId = preservedFields.has('default_procurement_method_id') ? currentValues.default_procurement_method_id : latestValues.default_procurement_method_id
  if (procurementMethodId !== undefined) formValues.default_procurement_method_id = procurementMethodId
  return formValues
}
function mapContactGenderToApi(gender: string): '1' | '2' { return gender === '女' ? '2' : '1' }
function handleLifecycleStatusChange(value: string | number): void {
  const normalized = Number(value)
  if (normalized === 0 || normalized === 1) lifecycleStatusValue.value = normalized
}
function handleProcurementMethodChange(value: string, handleChange: (value: number | undefined) => void): void {
  const procurementMethodId = Number(value)
  handleChange(Number.isFinite(procurementMethodId) && procurementMethodId > 0 ? procurementMethodId : undefined)
}
function handleLicenseTypeChange(value: string | number): void {
  licenseTypeValue.value = value === 'TRIAL' || value === 'OFFICIAL' ? value : null
}
function applyMoreInformationFromCustomer(customer: {
  industry: string | null
  industry_info?: CustomerDetailResponse['industry_info']
  status: CustomerDetailResponse['status']
  license_type: string | null
  license_expiry_date: string | null
}): void {
  industryValue.value = customer.industry ?? ''
  industryBaseline.value = customer.industry ?? ''
  retainedIndustryInfo.value = customer.industry_info ?? null
  customerStatusPresent.value = customer.status === 0 || customer.status === 1 || customer.status === 2 || customer.status === 3
  lifecycleStatusValue.value = editableStatus(customer.status)
  lifecycleStatusBaseline.value = lifecycleStatusValue.value
  licenseTypeValue.value = editableLicenseType(customer.license_type)
  licenseExpiryDateValue.value = customer.license_expiry_date
  licenseTypeBaseline.value = licenseTypeValue.value
  licenseExpiryDateBaseline.value = licenseExpiryDateValue.value
}
function resetCreateMoreInformation(): void {
  industryValue.value = ''
  industryBaseline.value = ''
  retainedIndustryInfo.value = null
  customerStatusPresent.value = false
  lifecycleStatusValue.value = null
  lifecycleStatusBaseline.value = null
  licenseTypeValue.value = null
  licenseExpiryDateValue.value = null
  licenseTypeBaseline.value = null
  licenseExpiryDateBaseline.value = null
  profileBaseline.value = emptyEditableSnapshot()
  loadedVersion.value = null
}
async function applyCustomerDetail(customer: CustomerDetailResponse): Promise<void> {
  loadedVersion.value = customer.version
  ensureOption(customer.source_info)
  applyMoreInformationFromCustomer(customer)
  setErrors({})
  profileBaseline.value = buildEditableSnapshot(customer)
  submitError.value = null
  const formValues = buildCustomerEditFormValues(customer)
  applyingFormValues.value = true
  setValues(formValues as unknown as CustomerForm | CustomerCreateForm, false)
  resetForm({ values: formValues as unknown as CustomerForm | CustomerCreateForm, errors: {} }, { force: true })
  await nextTick()
  for (const field of ['account_name', 'city', 'address', 'company_scale', 'source_public_id', 'product_public_id', 'default_procurement_method_id', 'industry', 'status', 'license_type', 'license_expiry_date', 'contact_name', 'contact_mobile', 'contact_position', 'contact_gender'] as const) {
    setFieldError(field, undefined)
  }
  applyingFormValues.value = false
  isDirty.value = false
}
async function loadCustomerDetail(customerId: string): Promise<void> {
  loadError.value = null
  submitError.value = null
  loading.value = true
  try {
    await applyCustomerDetail(await customerApi.getCustomerDetail(customerId))
  } catch (error) {
    loadError.value = toFeedbackError(error, '客户详情', { operation: 'read' })
    handleApiError(error, '加载客户详情')
  } finally {
    loading.value = false
  }
}
function retryCustomerDetail(): void {
  if (props.mode === 'edit' && props.customerId !== undefined && !loading.value) void loadCustomerDetail(props.customerId)
}
watch(
  [(): boolean => props.open, (): string | undefined => props.customerId, (): string => props.mode],
  async ([open, customerId]): Promise<void> => {
    if (!open) {
      if (closeGuard.handleParentClose()) return
      return
    }
    void fetchProcurementMethodOptions()
    void fetchSourceOptions()
    closeGuard.reset()
    loadError.value = null
    submitError.value = null
    moreInfoOpen.value = false
    industryHierarchyError.value = null
    if (props.mode === 'edit' && customerId !== undefined) {
      const prefetched = props.customer
      if (prefetched !== null && prefetched !== undefined && prefetched.id === customerId) await applyCustomerDetail(prefetched)
      else await loadCustomerDetail(customerId)
    } else if (props.mode === 'create') {
      applyingFormValues.value = true
      resetForm({
        values: {
          account_name: '',
          city: '',
          address: '',
          company_scale: undefined,
          source_public_id: undefined,
          product_public_id: '',
          default_procurement_method_id: undefined,
          contact_name: '',
          contact_mobile: '',
          contact_position: '',
          contact_gender: undefined,
        } as unknown as CustomerCreateForm,
      })
      resetCreateMoreInformation()
      isDirty.value = false
      await nextTick()
      applyingFormValues.value = false
    }
  },
  { immediate: true },
)
function clearFieldErrors(): void {
  setErrors({})
  for (const field of ['account_name', 'city', 'address', 'company_scale', 'source_public_id', 'product_public_id', 'default_procurement_method_id', 'industry', 'status', 'license_type', 'license_expiry_date', 'contact_name', 'contact_mobile', 'contact_position', 'contact_gender'] as const) {
    setFieldError(field, undefined)
  }
}
async function refreshConflict(preserveInput: boolean): Promise<void> {
  if (props.mode !== 'edit' || props.customerId === undefined || loading.value) return
  submitError.value = null
  loading.value = true
  try {
    const latest = await customerApi.getCustomerDetail(props.customerId)
    loadedVersion.value = latest.version
    if (!preserveInput) {
      await applyCustomerDetail(latest)
      return
    }

    const preservedIndustry = normalizeIndustryValue(industryValue.value) !== normalizeIndustryValue(industryBaseline.value)
    const preservedLifecycleStatus = lifecycleStatusValue.value !== lifecycleStatusBaseline.value
    const preservedLicenseSnapshot = licenseTypeValue.value !== licenseTypeBaseline.value || licenseExpiryDateValue.value !== licenseExpiryDateBaseline.value
    const previousLifecycleStatus = lifecycleStatusValue.value
    const previousLicenseType = licenseTypeValue.value
    const previousLicenseExpiryDate = licenseExpiryDateValue.value
    const mergedValues = mergeCustomerProfileValues(latest)
    const latestBaseline = buildEditableSnapshot(latest)
    const latestLifecycleStatus = editableStatus(latest.status)
    const latestLicenseType = editableLicenseType(latest.license_type)

    ensureOption(latest.source_info)
    profileBaseline.value = latestBaseline
    industryBaseline.value = normalizeIndustryValue(latest.industry) ?? ''
    industryValue.value = preservedIndustry ? industryValue.value : latest.industry ?? ''
    retainedIndustryInfo.value = latest.industry_info ?? null
    customerStatusPresent.value = latest.status === 0 || latest.status === 1 || latest.status === 2 || latest.status === 3
    lifecycleStatusBaseline.value = latestLifecycleStatus
    licenseTypeBaseline.value = latestLicenseType
    licenseExpiryDateBaseline.value = latest.license_expiry_date
    licenseTypeValue.value = preservedLicenseSnapshot ? previousLicenseType : latestLicenseType
    licenseExpiryDateValue.value = preservedLicenseSnapshot ? previousLicenseExpiryDate : latest.license_expiry_date
    lifecycleStatusValue.value = latestLifecycleStatus === null ? null : preservedLifecycleStatus ? previousLifecycleStatus : latestLifecycleStatus

    applyingFormValues.value = true
    setValues(mergedValues as unknown as CustomerForm | CustomerCreateForm, false)
    resetForm({ values: mergedValues as unknown as CustomerForm | CustomerCreateForm, errors: {} }, { force: true })
    await nextTick()
    clearFieldErrors()
    applyingFormValues.value = false
    const mergedProfileDirty = customerProfileFields.some((field) => hasProfileInputChanged(field, mergedValues, latestBaseline))
    const mergedIndustryDirty = normalizeIndustryValue(industryValue.value) !== normalizeIndustryValue(latestBaseline.industry)
    const mergedStatusDirty = lifecycleStatusValue.value !== lifecycleStatusBaseline.value
    const mergedLicenseDirty = licenseTypeValue.value !== licenseTypeBaseline.value || licenseExpiryDateValue.value !== licenseExpiryDateBaseline.value
    isDirty.value = mergedProfileDirty || mergedIndustryDirty || mergedStatusDirty || mergedLicenseDirty
  } catch (error) {
    submitError.value = toFeedbackError(error, '客户最新版本')
    handleApiError(error, '获取客户最新版本')
  } finally {
    loading.value = false
  }
}
function applySuccessfulWriteBaselines(customer: CustomerResponse): void {
  loadedVersion.value = customer.version
  profileBaseline.value = buildEditableSnapshot(customer)
  industryBaseline.value = customer.industry ?? ''
  industryValue.value = customer.industry ?? ''
  customerStatusPresent.value = customer.status === 0 || customer.status === 1 || customer.status === 2 || customer.status === 3
  lifecycleStatusValue.value = editableStatus(customer.status)
  lifecycleStatusBaseline.value = lifecycleStatusValue.value
  licenseTypeValue.value = editableLicenseType(customer.license_type)
  licenseExpiryDateValue.value = customer.license_expiry_date
  licenseTypeBaseline.value = licenseTypeValue.value
  licenseExpiryDateBaseline.value = licenseExpiryDateValue.value
  isDirty.value = false
}
function syncMoreInfoFormValues(): void {
  setFieldValue('industry', industryValue.value)
  setFieldValue('status', lifecycleStatusValue.value ?? undefined)
  setFieldValue('license_type', licenseTypeValue.value ?? '')
  setFieldValue('license_expiry_date', licenseExpiryDateValue.value ?? '')
}
function emitSuccessfulClose(entityId: string, operation: 'create' | 'update'): void {
  isDirty.value = false
  closeGuard.approveClose()
  emit('update:open', false)
  emit('success', { entityType: 'customer', entityId, operation, outcome: 'success', stateSyncRequested: true })
}
const submitForm = handleSubmit(async (formValues): Promise<void> => {
  submitting.value = true
  try {
    if (props.mode === 'create') {
      const createData = formValues as CustomerCreateForm
      const createPayload: CustomerCreate = {
        account_name: createData.account_name,
        city: createData.city,
        address: normalizeOptionalText(createData.address),
        company_scale: createData.company_scale ?? null,
        source_public_id: createData.source_public_id,
        product_public_id: createData.product_public_id,
        default_procurement_method_id: createData.default_procurement_method_id ?? null,
        primary_contact: {
          name: createData.contact_name,
          mobile: createData.contact_mobile,
          position: createData.contact_position,
          gender: mapContactGenderToApi(createData.contact_gender),
          is_decision_maker: false,
        },
      }
      const createIndustry = normalizeIndustryValue(industryValue.value)
      if (createIndustry !== null) createPayload.industry = createIndustry
      if (lifecycleStatusValue.value !== null) createPayload.status = lifecycleStatusValue.value
      const createExpiry = normalizeDateValue(licenseExpiryDateValue.value)
      if (createExpiry !== null && licenseTypeValue.value !== null) {
        createPayload.license_type = licenseTypeValue.value
        createPayload.license_expiry_date = createExpiry
      }
      const createdCustomer = await customerApi.createCustomer(createPayload)
      toast.success('客户创建成功')
      emitSuccessfulClose(createdCustomer.id, 'create')
      return
    }

    if (props.customerId === undefined || loadedVersion.value === null) return
    const editData = formValues as CustomerEditForm
    const payload = buildCustomerUpdatePayload(buildCurrentSnapshot(editData), profileBaseline.value, loadedVersion.value)
    if (payload !== null) {
      const updatedCustomer = await customerApi.updateCustomer(props.customerId, payload)
      toast.success('客户更新成功')
      applySuccessfulWriteBaselines(updatedCustomer)
      emitSuccessfulClose(updatedCustomer.id, 'update')
      return
    }

    emitSuccessfulClose(props.customerId, 'update')
  } catch (error) {
    submitError.value = toFeedbackError(error, props.mode === 'create' ? '创建客户' : '更新客户', { operation: 'write' })
    for (const fieldError of submitError.value.fieldErrors ?? []) {
      if (fieldError.field in fieldLabels) setFieldError(fieldError.field as keyof CustomerForm | keyof CustomerCreateForm, fieldError.message)
    }
    if ((submitError.value.fieldErrors?.length ?? 0) > 0) await focusFirstError()
    if (submitError.value.kind !== 'validation' && submitError.value.kind !== 'conflict') handleApiError(error, props.mode === 'create' ? '创建客户' : '更新客户')
  } finally {
    submitting.value = false
  }
}, async () => { await focusFirstError() })
async function onSubmit(event: Event): Promise<void> {
  syncMoreInfoFormValues()
  await submitForm(event)
}
function handleOpenChange(open: boolean): void { closeGuard.handleOpenChange(open) }
function handleCancel(): void { closeGuard.requestClose() }
function confirmCancel(): void { closeGuard.confirmDiscard() }
function continueEditing(): void { closeGuard.continueEditing() }
</script>


<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="w-[calc(100vw-2rem)] sm:max-w-2xl max-h-[min(90vh,90dvh)] overflow-y-auto overscroll-contain [scroll-padding-bottom:calc(5rem+env(safe-area-inset-bottom,0px))]">
      <DialogHeader>
        <DialogTitle>{{ mode === 'create' ? '新建客户' : '编辑客户' }}</DialogTitle>
        <DialogDescription data-testid="customer-dialog-description" class="text-sm text-slate-500">
          {{ mode === 'create' ? '填写客户基础信息和联系人信息' : '先修改常用客户资料，更多信息按需展开' }}
        </DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="flex justify-center py-8">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>

      <ErrorState
        v-else-if="loadError"
        :variant="loadError.kind === 'permission' ? 'forbidden' : 'error'"
        :title="loadError.title"
        :description="loadError.description"
      >
        <template #action>
          <Button type="button" variant="outline" @click="retryCustomerDetail">
            重新加载
          </Button>
        </template>
      </ErrorState>

      <form v-else class="space-y-4" @submit="onSubmit">
        <div v-if="submitError" class="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm" role="alert" aria-live="assertive">
          <p class="font-medium">{{ submitError.title }}</p>
          <p>{{ submitError.description }}</p>
          <div v-if="submitError.kind === 'conflict'" class="mt-2 flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" @click="refreshConflict(false)">
              使用最新数据
            </Button>
            <Button type="button" variant="outline" size="sm" @click="refreshConflict(true)">
              保留当前输入并继续编辑
            </Button>
          </div>
        </div>
        <FormErrorSummary :items="errorSummary" />
        <div
          v-if="optionsError"
          class="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          <p>部分选项暂时无法加载，受影响字段已禁用，请重试后再保存。</p>
          <ul class="mt-1 list-inside list-disc">
            <li v-if="sourceOptionsError">获客来源</li>
            <li v-if="procurementMethodsError">采购方式</li>
          </ul>
          <Button class="mt-2" type="button" variant="outline" @click="retryOptions">
            重试选项加载
          </Button>
        </div>

        <!-- Basic Information Section -->
        <div v-if="mode === 'edit'" id="customer-basic-info-heading" class="flex items-center justify-between text-sm font-semibold text-slate-700">
          <span>基础信息</span>
          <span class="text-xs font-medium text-slate-400">常用字段</span>
        </div>
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Customer Name (required) -->
            <FormField v-slot="{ value, handleChange }" name="account_name">
              <FormItem>
                <InputField
                  id="customer-account-name"
                  :model-value="String(value ?? '')"
                  label="客户名称"
                  required
                  autocomplete="organization"
                  placeholder="请输入客户名称"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- City (required) -->
            <FormField v-slot="{ value, handleChange }" name="city">
              <FormItem>
                <InputField
                  id="customer-city"
                  :model-value="String(value ?? '')"
                  label="所在城市"
                  required
                  autocomplete="address-level2"
                  placeholder="请输入城市"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ value, handleChange }" name="source_public_id">
              <FormItem>
                <SelectField
                  id="customer-source"
                  :model-value="String(value ?? '')"
                  label="客户来源"
                  required
                  :options="sourceSelectOptions"
                  placeholder="请选择来源"
                  :disabled="sourceOptionsLoading || sourceOptionsError !== null"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ value, handleChange }" name="product_public_id">
              <FormItem class="sm:col-span-2">
                <ProductIntentPicker
                  :model-value="String(value ?? '')"
                  id-prefix="customer-product"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Company Scale -->
            <FormField v-slot="{ value, handleChange }" name="company_scale">
              <FormItem>
                <SelectField
                  id="customer-company-scale"
                  :model-value="String(value ?? '')"
                  label="公司规模"
                  required
                  :options="companyScaleSelectOptions"
                  placeholder="请选择规模"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- Default Procurement Method -->
            <FormField v-slot="{ value, handleChange }" name="default_procurement_method_id">
              <FormItem>
                <SelectField
                  id="customer-procurement-method"
                  :model-value="String(value ?? '')"
                  label="采购方式"
                  required
                  :options="procurementMethodSelectOptions"
                  :placeholder="procurementMethodsLoading ? '采购方式加载中' : '请选择采购方式'"
                  :disabled="procurementMethodsLoading || procurementMethodsError !== null"
                  @update:model-value="(selectedValue) => handleProcurementMethodChange(selectedValue, handleChange)"
                />
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <!-- Address (full width) -->
          <FormField v-slot="{ value, handleChange }" name="address">
            <FormItem>
              <InputField
                id="customer-address"
                :model-value="String(value ?? '')"
                label="详细地址"
                autocomplete="street-address"
                placeholder="请输入详细地址"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>
        </div>
        <div v-if="mode === 'create'" class="space-y-4 pt-4 border-t">
          <h3 class="text-sm font-medium text-muted-foreground">联系人信息</h3>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormField v-slot="{ value, handleChange }" name="contact_name">
              <FormItem>
                <InputField
                  id="customer-contact-name"
                  :model-value="String(value ?? '')"
                  label="联系人姓名"
                  required
                  autocomplete="name"
                  placeholder="请输入联系人姓名"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ value, handleChange }" name="contact_mobile">
              <FormItem>
                <InputField
                  id="customer-contact-mobile"
                  :model-value="String(value ?? '')"
                  label="联系电话"
                  required
                  type="tel"
                  autocomplete="tel"
                  placeholder="请输入联系电话"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <FormField v-slot="{ value, handleChange }" name="contact_position">
              <FormItem>
                <InputField
                  id="customer-contact-position"
                  :model-value="String(value ?? '')"
                  label="职位"
                  required
                  placeholder="请输入职位"
                  @update:model-value="handleChange"
                />
                <FormMessage />
              </FormItem>
            </FormField>

            <div class="space-y-2">
              <div id="customer-contact-gender-label" class="text-sm font-medium">
                性别 <span class="text-destructive">*</span>
              </div>
              <SegmentedChoiceControl
                v-model="contactGenderValue"
                :options="genderOptions"
                labelled-by="customer-contact-gender-label"
                id-prefix="customer-contact-gender"
              />
              <p v-if="contactGenderError" class="text-sm font-medium text-destructive">
                {{ contactGenderError }}
              </p>
            </div>
          </div>
        </div>

        <Collapsible
          :open="moreInfoOpen"
          :unmount-on-hide="false"
          class="space-y-3 border-t border-slate-200 pt-4"
          @update:open="handleMoreInfoChange"
        >
          <CollapsibleTrigger as-child>
            <button
              id="customer-more-info-trigger"
              type="button"
              class="flex h-input-mobile min-h-input-mobile w-full items-center justify-between rounded-wolf-lg border border-blue-200 bg-blue-50/60 px-3 text-left text-sm font-semibold text-blue-900"
              :aria-expanded="moreInfoOpen"
              aria-controls="customer-more-info-content"
            >
              <span>{{ moreInfoOpen ? '收起更多客户信息' : '更多客户信息' }}</span>
              <span class="text-xs font-semibold text-blue-700">已填写 {{ moreInfoCount }} 项</span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent id="customer-more-info-content">
            <div class="grid gap-4 px-1 pt-1">
            <div v-if="industryHierarchyError" class="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-sm" role="alert">
              <span>{{ industryHierarchyError.description }}</span>
              <Button type="button" variant="outline" size="sm" class="ml-2" @click="fetchIndustryHierarchy">重试</Button>
            </div>
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <IndustryHierarchySelectField
                id="customer-industry"
                v-model="industryValue"
                :hierarchy="industryHierarchy"
                :loading="industryHierarchyLoading"
                :error="industryHierarchyError?.description ?? industryErrorMessage"
                :disabled="industryHierarchyError !== null"
                :retained-industry-info="retainedIndustryInfo"
                label="行业"
              />
              <SelectField
                id="customer-lifecycle-status"
                :model-value="lifecycleStatusValue ?? ''"
                label="客户状态"
                :options="[{ value: 0, label: '跟进中' }, { value: 1, label: '已成交' }]"
                :disabled="statusIsReadOnly || writeSubmitting"
                @update:model-value="handleLifecycleStatusChange"
              />
              <SelectField
                id="customer-license-type"
                :model-value="licenseTypeValue ?? ''"
                label="授权类型"
                :options="[{ value: 'TRIAL', label: '试用' }, { value: 'OFFICIAL', label: '正式' }]"
                :disabled="writeSubmitting"
                @update:model-value="handleLicenseTypeChange"
              />
              <DateField
                id="customer-license-expiry-date"
                label="授权到期日"
                :model-value="licenseExpiryDateValue === null ? null : new Date(`${licenseExpiryDateValue}T00:00:00`)"
                :disabled="writeSubmitting"
                @update:model-value="licenseExpiryDateValue = $event === null ? null : formatLocalDate($event)"
              />
            </div>
            <p v-if="statusIsReadOnly" class="text-xs leading-relaxed text-slate-500">该客户状态由其他流程管理，暂不支持在此修改。</p>
            <p class="text-xs leading-relaxed text-slate-500">此处只更新客户授权汇总信息，不创建 License 申请、不发起审批，也不修改正式 License 记录。</p>
            <p class="text-sm text-slate-700"><span class="font-medium">授权状态：</span>{{ licenseStatusLabel(licenseExpiryDateValue, licenseTypeValue) }}</p>
            </div>
          </CollapsibleContent>
        </Collapsible>

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" :disabled="writeSubmitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting" :disabled="writeSubmitting || optionsLoading || optionsError">
            {{ submitting ? '提交中...' : (mode === 'create' ? '创建客户' : '保存客户资料') }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- Confirm discard changes dialog -->
  <AlertDialog :open="showConfirmDialog" @update:open="closeGuard.handleConfirmOpenChange">
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
