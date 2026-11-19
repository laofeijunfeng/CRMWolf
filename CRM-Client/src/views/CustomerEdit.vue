<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Field, useForm } from 'vee-validate'
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
import { Button } from '@/components/ui/button'
import { InputField, ProductIntentPicker, SelectField } from '@/components/crmwolf'
import ErrorState from '@/components/crmwolf/ErrorState.vue'
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
const procurementSelectOptions = computed(() =>
  procurementMethodOptions.value.map(option => ({ value: option.id, label: option.name })),
)
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
  <div class="min-h-full bg-card">
    <!-- Loading State -->
    <div v-if="loading" class="loading-container flex items-center justify-center p-[var(--page-padding)]" aria-busy="true" aria-live="polite">
      <div class="loading-spinner animate-spin rounded-full border-border border-t-brand" />
    </div>

    <div v-else-if="loadError" class="flex justify-center p-[var(--page-padding)]">
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
    <div v-else class="p-[var(--page-padding)]">
      <div v-if="optionsError" class="mb-space-4" role="alert">
        <ErrorState
          :variant="optionsError.variant ?? 'error'"
          :title="optionsError.title"
          :description="optionsError.description"
        >
          <template #action>
            <div class="flex flex-col items-start gap-space-2">
              <span v-if="optionsErrorFields.length > 0" class="text-body text-muted-foreground">
                受影响字段：{{ optionsErrorFields.map(field => optionFieldLabels[field] ?? field).join('、') }}
              </span>
              <Button v-if="optionsError.retryable !== false" type="button" variant="outline" size="sm" @click="fetchOptions">
                重试加载选项
              </Button>
            </div>
          </template>
        </ErrorState>
      </div>
      <div v-if="submitError" class="mb-space-4 flex flex-col gap-space-1 rounded-md border border-danger bg-danger/[0.08] p-space-3 text-foreground" role="alert">
        <strong>{{ submitError.title }}</strong>
        <span>{{ submitError.description }}</span>
        <div v-if="submitError.kind === 'conflict'" class="mt-space-2 flex flex-wrap gap-space-2">
          <Button type="button" variant="outline" size="sm" @click="refreshConflict(false)">
            使用最新数据
          </Button>
          <Button type="button" variant="outline" size="sm" @click="refreshConflict(true)">
            保留当前输入并继续编辑
          </Button>
        </div>
      </div>
      <div v-if="errorSummary.length > 0" class="mb-space-4 rounded-md border border-danger bg-danger/[0.08] p-space-3 text-foreground" role="alert" aria-live="assertive">
        <strong>请先修正以下内容</strong>
        <ul class="mt-space-1 pl-space-4">
          <li v-for="error in errorSummary" :key="error.field">
            {{ getFieldLabel(error.field) }}：{{ error.message }}
          </li>
        </ul>
      </div>
      <!-- Basic Info Card -->
      <div class="mb-space-4 rounded-lg bg-card p-space-4 shadow-1 max-sm:p-space-3">
        <div class="mb-space-4 flex items-center justify-between border-b border-border pb-space-2 text-body-strong leading-[var(--line-height-body)] font-semibold text-foreground">基本信息</div>
        <form id="customer-edit-form" class="space-y-4" @submit="onSubmit">
          <div class="grid grid-cols-2 gap-space-4 max-sm:grid-cols-1">
            <!-- Customer Name -->
            <Field v-slot="{ value, handleChange, handleBlur, errorMessage }" name="account_name">
              <InputField
                id="customer-edit-account-name"
                name="account_name"
                :model-value="String(value ?? '')"
                label="客户名称"
                required
                placeholder="请输入客户公司名称"
                :error="errorMessage ?? ''"
                @update:model-value="handleChange"
                @blur="handleBlur"
              />
            </Field>

            <!-- City -->
            <Field v-slot="{ value, handleChange, handleBlur, errorMessage }" name="city">
              <InputField
                id="customer-edit-city"
                name="city"
                :model-value="String(value ?? '')"
                label="所在城市"
                required
                placeholder="请输入所在城市"
                :error="errorMessage ?? ''"
                @update:model-value="handleChange"
                @blur="handleBlur"
              />
            </Field>
          </div>

          <div class="grid grid-cols-2 gap-space-4 max-sm:grid-cols-1">
            <!-- Source -->
            <Field v-slot="{ value, handleChange, errorMessage }" name="source_public_id">
              <div class="grid gap-space-1">
                <SelectField
                  id="customer-edit-source"
                  name="source_public_id"
                  :model-value="String(value ?? '')"
                  :options="sourceSelectOptions"
                  label="客户来源"
                  required
                  placeholder="请选择客户来源"
                  :disabled="optionsLoading || optionsErrorFields.includes('source_public_id')"
                  :error="errorMessage ?? ''"
                  @update:model-value="handleChange"
                />
                <p v-if="optionsErrorFields.includes('source_public_id')" class="mt-space-1 text-body text-danger">
                  获客来源加载失败，请点击上方“重试加载选项”。
                </p>
              </div>
            </Field>

            <div class="col-span-full">
              <Field v-slot="{ value, handleChange, errorMessage }" name="product_public_id">
                <div class="grid gap-space-1">
                  <ProductIntentPicker
                    :model-value="String(value ?? '')"
                    id-prefix="customer-edit-product"
                    :invalid="Boolean(errorMessage)"
                    @update:model-value="handleChange"
                  />
                  <p v-if="errorMessage" id="customer-edit-product-error" class="text-caption text-destructive" role="alert">
                    {{ errorMessage }}
                  </p>
                </div>
              </Field>
            </div>

            <!-- Company Scale -->
            <Field v-slot="{ value, handleChange, errorMessage }" name="company_scale">
              <SelectField
                id="customer-edit-company-scale"
                name="company_scale"
                :model-value="String(value ?? '')"
                :options="companyScaleOptions"
                label="公司规模"
                required
                placeholder="请选择公司规模"
                :error="errorMessage ?? ''"
                @update:model-value="handleChange"
              />
            </Field>
          </div>

          <div class="grid grid-cols-2 gap-space-4 max-sm:grid-cols-1">
            <!-- Default Procurement Method -->
            <Field v-slot="{ value, handleChange, errorMessage }" name="default_procurement_method_id">
              <div class="grid gap-space-1">
                <SelectField
                  id="customer-edit-procurement-method"
                  name="default_procurement_method_id"
                  :model-value="value === undefined || value === null ? '' : String(value)"
                  :options="procurementSelectOptions"
                  label="采购方式"
                  required
                  placeholder="请选择采购方式"
                  :disabled="optionsLoading || optionsErrorFields.includes('default_procurement_method_id')"
                  :error="errorMessage ?? ''"
                  @update:model-value="handleChange(Number($event))"
                />
                <p v-if="optionsErrorFields.includes('default_procurement_method_id')" class="mt-space-1 text-body text-danger">
                  采购方式加载失败，请点击上方“重试加载选项”。
                </p>
              </div>
            </Field>

            <!-- Address -->
            <Field v-slot="{ value, handleChange, handleBlur, errorMessage }" name="address">
              <InputField
                id="customer-edit-address"
                name="address"
                :model-value="String(value ?? '')"
                label="公司地址"
                placeholder="请输入公司地址"
                :error="errorMessage ?? ''"
                @update:model-value="handleChange"
                @blur="handleBlur"
              />
            </Field>
          </div>
        </form>
      </div>

      <!-- Form Actions -->
      <div class="flex justify-end gap-space-2 rounded-lg bg-card p-space-4 shadow-1 max-sm:flex-col-reverse">
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
.loading-container {
  min-height: 400px;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border-width: 3px;
}
</style>
