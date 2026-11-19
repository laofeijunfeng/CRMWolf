<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import { logger } from '@/utils/logger'
import { productPublicIdFromIntent } from '@/utils/productIntent'
import customerApi, { type CustomerCreate, type CustomerUpdate } from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import { usePageTitle } from '@/composables/usePageTitle'
import { useRouteLeaveGuard } from '@/composables/useRouteLeaveGuard'
import { useHeaderStore } from '@/stores/header'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ProductIntentPicker } from '@/components/crmwolf'
import ErrorState from '@/components/ErrorState.vue'
import { customerFormSchema, companyScaleOptions, type CustomerForm } from '@/schemas/customer-form'
import { useAcquisitionSourceOptions } from '@/composables/useAcquisitionSourceOptions'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

usePageTitle()

const router = useRouter()
const route = useRoute()
const headerStore = useHeaderStore()

const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const optionsError = ref<FeedbackError | null>(null)
const optionsLoading = ref(false)
const optionsLoaded = ref(false)
const submitError = ref<FeedbackError | null>(null)
const submitting = ref(false)
const loadedVersion = ref<number | null>(null)
const procurementMethodOptions = ref<ProcurementMethodOption[]>([])
const {
  formSelectOptions: sourceSelectOptions,
  loadFormOptions,
  ensureOption,
} = useAcquisitionSourceOptions()

const customerId = computed(() => String(route.params['id'] ?? ''))
const optionsReady = computed(() => optionsLoaded.value)
const isEdit = computed(() => !!customerId.value)

// VeeValidate form setup
const { handleSubmit, setFieldError, errors, meta, resetForm } = useForm({
  validationSchema: toTypedSchema(customerFormSchema),
  initialValues: {
    account_name: '',
    city: '',
    address: '',
    company_scale: undefined,
    source_public_id: undefined,
    product_public_id: '',
    default_procurement_method_id: undefined
  } as unknown as CustomerForm
})

const isDirty = computed(() => meta.value.dirty)
const leaveGuard = useRouteLeaveGuard({
  isDirty: (): boolean => isDirty.value,
  isSubmitting: (): boolean => submitting.value,
})

function normalizeCompanyScale(value: string | null): CustomerForm['company_scale'] | undefined {
  return companyScaleOptions.some(option => option.value === value)
    ? value as CustomerForm['company_scale']
    : undefined
}

function emptyToNull(value: string | null | undefined): string | null {
  return value === undefined || value === null || value === '' ? null : value
}

function toFormValues(res: { account_name: string; city: string; address: string | null; company_scale: string | null; source_info?: { public_id: string } | null; product_public_id?: string | null; products?: { public_id: string; name: string }[]; default_procurement_method_id: number | null }): Partial<CustomerForm> {
  const companyScale = normalizeCompanyScale(res.company_scale)
  const sourcePublicId = res.source_info?.public_id
  const procurementMethodId = res.default_procurement_method_id ?? undefined

  return {
    account_name: res.account_name ?? '',
    city: res.city ?? '',
    address: res.address ?? '',
    product_public_id: productPublicIdFromIntent(res),
    ...(companyScale === undefined ? {} : { company_scale: companyScale }),
    ...(sourcePublicId === undefined ? {} : { source_public_id: sourcePublicId }),
    ...(procurementMethodId === undefined ? {} : { default_procurement_method_id: procurementMethodId }),
  }
}

const fetchCustomerDetail = async (): Promise<void> => {
  if (!isEdit.value) return

  loadError.value = null
  loading.value = true
  try {
    const res = await customerApi.getCustomerDetail(customerId.value)
    ensureOption(res.source_info)
    loadedVersion.value = res.version
    resetForm({ values: toFormValues(res) })
  } catch (error: unknown) {
    loadError.value = toFeedbackError(error, '客户详情')
  } finally {
    loading.value = false
  }
}

const optionsErrorFields = ref<string[]>([])
const optionFieldLabels: Record<string, string> = {
  source_public_id: '获客来源',
  default_procurement_method_id: '采购方式',
}

const fetchOptions = async (): Promise<void> => {
  optionsError.value = null
  optionsErrorFields.value = []
  optionsLoaded.value = false
  optionsLoading.value = true
  procurementMethodOptions.value = []

  const [procurementResult, sourceResult] = await Promise.allSettled([
    procurementApi.getProcurementMethodOptions(),
    loadFormOptions({ throwOnError: true, notifyOnError: false }),
  ])

  const failedFields: string[] = []
  if (procurementResult.status === 'fulfilled') {
    procurementMethodOptions.value = procurementResult.value
  } else {
    failedFields.push('default_procurement_method_id')
  }
  if (sourceResult.status === 'rejected') {
    failedFields.push('source_public_id')
  }

  if (failedFields.length > 0) {
    optionsErrorFields.value = failedFields
    const firstFailure: unknown = procurementResult.status === 'rejected'
      ? procurementResult.reason
      : sourceResult.status === 'rejected'
        ? sourceResult.reason
        : new Error('表单选项加载失败')
    optionsError.value = toFeedbackError(firstFailure, '表单选项')
    logger.error('[CustomerEdit]', '获取选项失败', { failedFields, error: firstFailure })
  } else {
    optionsLoaded.value = true
  }
  optionsLoading.value = false
}

const customerStatusLabel = (status: number): string => {
  const labels: Record<number, string> = {
    0: '跟进中',
    1: '已成交',
    2: '已流失',
    3: '非激活',
  }
  return labels[status] ?? '未知状态'
}

const errorSummary = computed(() => Object.entries(errors.value)
  .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1] !== '')
  .map(([field, message]) => ({ field, message })))

const fieldLabels: Record<string, string> = {
  account_name: '客户名称',
  city: '所在城市',
  address: '公司地址',
  company_scale: '公司规模',
  source_public_id: '获客来源',
  product_public_id: '产品',
  default_procurement_method_id: '采购方式',
}

const getFieldLabel = (field: string): string => fieldLabels[field] ?? field

const focusFirstError = async (): Promise<void> => {
  await nextTick()
  const firstError = errorSummary.value[0]
  if (!firstError || typeof document === 'undefined') return

  const field = document.getElementsByName(firstError.field)[0]
  if (field instanceof HTMLElement) {
    field.scrollIntoView({ behavior: 'smooth', block: 'center' })
    field.focus({ preventScroll: true })
  }
}

const applyServerFieldErrors = async (feedback: FeedbackError): Promise<void> => {
  for (const fieldError of feedback.fieldErrors ?? []) {
    if (fieldError.field in fieldLabels) {
      setFieldError(fieldError.field as keyof CustomerForm, fieldError.message)
    }
  }
  await focusFirstError()
}

const refreshConflict = async (preserveInput: boolean): Promise<void> => {
  if (!isEdit.value || submitting.value) return

  submitError.value = null
  loading.value = true
  try {
    const latest = await customerApi.getCustomerDetail(customerId.value)
    loadedVersion.value = latest.version
    if (!preserveInput) {
      ensureOption(latest.source_info)
      resetForm({ values: toFormValues(latest) })
    }
  } catch (error: unknown) {
    submitError.value = toFeedbackError(error, '客户最新版本')
  } finally {
    loading.value = false
  }
}

// Form submission
const submitCustomer = async (formValues: CustomerForm): Promise<void> => {
  submitError.value = null
  submitting.value = true
  try {
    if (isEdit.value) {
      const updateData = {
        expected_version: loadedVersion.value,
        account_name: emptyToNull(formValues.account_name),
        city: emptyToNull(formValues.city),
        address: emptyToNull(formValues.address),
        company_scale: formValues.company_scale ?? null,
        source_public_id: formValues.source_public_id,
        product_public_id: formValues.product_public_id,
        default_procurement_method_id: formValues.default_procurement_method_id ?? null,
      } satisfies CustomerUpdate
      const updatedCustomer = await customerApi.updateCustomer(customerId.value, updateData)
      loadedVersion.value = updatedCustomer.version
      resetForm({ values: formValues })
      toast.success(`客户「${updatedCustomer.account_name}」更新成功，当前状态：${customerStatusLabel(updatedCustomer.status)}`)
    } else {
      const createData = {
        account_name: formValues.account_name,
        city: formValues.city,
        address: emptyToNull(formValues.address),
        company_scale: formValues.company_scale ?? null,
        source_public_id: formValues.source_public_id,
        product_public_id: formValues.product_public_id,
        default_procurement_method_id: formValues.default_procurement_method_id ?? null,
      } satisfies CustomerCreate
      const createdCustomer = await customerApi.createCustomer(createData)
      toast.success(`客户「${createdCustomer.account_name}」创建成功，当前状态：${customerStatusLabel(createdCustomer.status)}`)
    }
    leaveGuard.allowNextNavigation()
    router.back()
  } catch (error: unknown) {
    submitError.value = toFeedbackError(error, isEdit.value ? '更新客户' : '创建客户', { operation: 'write' })
    if (submitError.value.fieldErrors && submitError.value.fieldErrors.length > 0) {
      await applyServerFieldErrors(submitError.value)
    }
    if (submitError.value.kind !== 'conflict') {
      handleApiError(error, isEdit.value ? '更新客户' : '创建客户')
    }
  } finally {
    submitting.value = false
  }
}

const onSubmit = handleSubmit(async (formValues: CustomerForm) => {
  await submitCustomer(formValues)
})

const retryLoad = async (): Promise<void> => {
  if (isEdit.value) {
    await fetchCustomerDetail()
  }
  await fetchOptions()
}

const handleGoBack = (): void => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/customers')
  }
}

onMounted(async () => {
  headerStore.setBack(true)
  await fetchOptions()
  if (isEdit.value) {
    await fetchCustomerDetail()
  }
})

onUnmounted(() => {
  headerStore.clear()
})
</script>

<template>
  <div class="customer-edit-page">
    <!-- Loading State -->
    <div v-if="loading" class="loading-container" aria-busy="true" aria-live="polite">
      <div class="loading-spinner" />
    </div>

    <div v-else-if="loadError" class="state-container">
      <ErrorState
        :variant="loadError.variant ?? 'error'"
        :title="loadError.title"
        :description="loadError.description"
      >
        <template #action>
          <Button v-if="loadError.retryable !== false" type="button" @click="retryLoad">
            重新加载
          </Button>
        </template>
      </ErrorState>
    </div>

    <!-- Form Content -->
    <div v-else class="form-container">
      <div v-if="optionsError" class="form-feedback" role="alert">
        <ErrorState
          :variant="optionsError.variant ?? 'error'"
          :title="optionsError.title"
          :description="optionsError.description"
        >
          <template #action>
            <div class="options-error-action">
              <span v-if="optionsErrorFields.length > 0" class="options-error-fields">
                受影响字段：{{ optionsErrorFields.map(field => optionFieldLabels[field] ?? field).join('、') }}
              </span>
              <Button v-if="optionsError.retryable !== false" type="button" variant="outline" size="sm" @click="fetchOptions">
                重试加载选项
              </Button>
            </div>
          </template>
        </ErrorState>
      </div>
      <div v-if="submitError" class="submit-feedback" role="alert">
        <strong>{{ submitError.title }}</strong>
        <span>{{ submitError.description }}</span>
        <div v-if="submitError.kind === 'conflict'" class="submit-feedback__actions">
          <Button type="button" variant="outline" size="sm" @click="refreshConflict(false)">
            使用最新数据
          </Button>
          <Button type="button" variant="outline" size="sm" @click="refreshConflict(true)">
            保留当前输入并继续编辑
          </Button>
        </div>
      </div>
      <div v-if="errorSummary.length > 0" class="form-error-summary" role="alert" aria-live="assertive">
        <strong>请先修正以下内容</strong>
        <ul>
          <li v-for="error in errorSummary" :key="error.field">
            {{ getFieldLabel(error.field) }}：{{ error.message }}
          </li>
        </ul>
      </div>
      <!-- Basic Info Card -->
      <div class="form-card">
        <div class="card-title">基本信息</div>
        <form id="customer-edit-form" class="space-y-4" @submit="onSubmit">
          <div class="form-grid">
            <!-- Customer Name -->
            <FormField v-slot="{ componentField }" name="account_name">
              <FormItem>
                <FormLabel>客户名称 <span class="text-destructive">*</span></FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    placeholder="请输入客户公司名称"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- City -->
            <FormField v-slot="{ componentField }" name="city">
              <FormItem>
                <FormLabel>所在城市 <span class="text-destructive">*</span></FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    placeholder="请输入所在城市"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <div class="form-grid">
            <!-- Source -->
            <FormField v-slot="{ componentField }" name="source_public_id">
              <FormItem>
                <FormLabel>客户来源 <span class="text-destructive">*</span></FormLabel>
                <Select v-bind="componentField as any" :disabled="optionsLoading || optionsErrorFields.includes('source_public_id')">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择客户来源" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in sourceSelectOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
                <p v-if="optionsErrorFields.includes('source_public_id')" class="form-option-error">
                  获客来源加载失败，请点击上方“重试加载选项”。
                </p>
              </FormItem>
            </FormField>

            <div class="form-grid-full">
              <FormField v-slot="{ value, handleChange }" name="product_public_id">
                <FormItem>
                  <ProductIntentPicker
                    :model-value="String(value ?? '')"
                    id-prefix="customer-edit-product"
                    @update:model-value="handleChange"
                  />
                  <FormMessage />
                </FormItem>
              </FormField>
            </div>

            <!-- Company Scale -->
            <FormField v-slot="{ componentField }" name="company_scale">
              <FormItem>
                <FormLabel>公司规模 <span class="text-destructive">*</span></FormLabel>
                <Select v-bind="componentField as any">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择公司规模" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in companyScaleOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <div class="form-grid">
            <!-- Default Procurement Method -->
            <FormField v-slot="{ componentField }" name="default_procurement_method_id">
              <FormItem>
                <FormLabel>采购方式 <span class="text-destructive">*</span></FormLabel>
                <Select v-bind="componentField as any" :disabled="optionsLoading || optionsErrorFields.includes('default_procurement_method_id')">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择采购方式" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in procurementMethodOptions"
                      :key="option['id']"
                      :value="option['id']"
                    >
                      {{ option.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
                <p v-if="optionsErrorFields.includes('default_procurement_method_id')" class="form-option-error">
                  采购方式加载失败，请点击上方“重试加载选项”。
                </p>
              </FormItem>
            </FormField>

            <!-- Address -->
            <FormField v-slot="{ componentField }" name="address">
              <FormItem>
                <FormLabel>公司地址</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField as any"
                    placeholder="请输入公司地址"
                    class="h-11 sm:h-8"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>
        </form>
      </div>

      <!-- Form Actions -->
      <div class="form-actions-card">
        <Button variant="outline" type="button" @click="handleGoBack">
          取消
        </Button>
        <Button
          type="submit"
          form="customer-edit-form"
          :loading="submitting"
          :disabled="optionsLoading || optionsError !== null || !optionsReady"
        >
          {{ isEdit ? '保存' : '创建' }}
        </Button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.customer-edit-page {
  padding: 0;
  background: hsl(var(--card));
  min-height: 100%;
}

// Loading state
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  padding: var(--page-padding);
}

.state-container {
  display: flex;
  justify-content: center;
  padding: var(--page-padding);
}

.form-feedback {
  margin-bottom: $space-4;
}

.options-error-action {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: $space-2;
}

.options-error-fields {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
}

.form-option-error {
  margin-top: $space-1;
  color: hsl(var(--status-danger));
  font-size: var(--font-size-body);
}

.submit-feedback {
  display: flex;
  flex-direction: column;
  gap: $space-1;
  margin-bottom: $space-4;
  padding: $space-3;
  border: 1px solid hsl(var(--status-danger));
  border-radius: var(--radius-md);
  background: color-mix(in srgb, hsl(var(--status-danger)) 8%, transparent);
  color: hsl(var(--foreground));
}

.submit-feedback__actions {
  display: flex;
  flex-wrap: wrap;
  gap: $space-2;
  margin-top: $space-2;
}

.form-error-summary {
  margin-bottom: $space-4;
  padding: $space-3;
  border: 1px solid hsl(var(--status-danger));
  border-radius: var(--radius-md);
  background: color-mix(in srgb, hsl(var(--status-danger)) 8%, transparent);
  color: hsl(var(--foreground));
}

.form-error-summary ul {
  margin: $space-1 0 0;
  padding-left: $space-4;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid hsl(var(--border));
  border-top-color: hsl(var(--brand));
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

// Form container (full width)
.form-container {
  padding: var(--page-padding);
}

// Form card (full width)
.form-card {
  background: hsl(var(--card));
  border-radius: var(--radius-lg);
  padding: $space-4;
  margin-bottom: $space-4;
  box-shadow: var(--shadow-1);
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--font-size-body-strong);
  font-weight: 600;
  color: hsl(var(--foreground));
  margin-bottom: $space-4;
  padding-bottom: $space-2;
  border-bottom: 1px solid hsl(var(--border));
}

// Form grid (two columns)
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $space-4;
}

.form-grid-full {
  grid-column: 1 / -1;
}

// Form actions card
.form-actions-card {
  background: hsl(var(--card));
  border-radius: var(--radius-lg);
  padding: $space-4;
  box-shadow: var(--shadow-1);
  display: flex;
  justify-content: flex-end;
  gap: $space-2;
}

// Responsive
@media (max-width: 768px) {
  .form-container {
    padding: var(--page-padding);
  }

  .form-card {
    padding: $space-3;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions-card {
    flex-direction: column-reverse;
  }
}
</style>
