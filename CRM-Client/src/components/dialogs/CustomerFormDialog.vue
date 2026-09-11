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
  SegmentedChoiceControl,
  SelectField,
} from '@/components/crmwolf'
import FormErrorSummary from '@/components/crmwolf/FormErrorSummary.vue'
import { handleApiError } from '@/utils/errorHandler'
import { formatLocalDate } from '@/utils/format'
import { licenseStatusLabel } from '@/utils/licenseStatus'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'
import customerApi, { type CustomerDetailResponse, type CustomerUpdate } from '@/api/customer'
import procurementApi, { type ProcurementMethodOption } from '@/api/procurement'
import { buildCustomerUpdatePayload } from './customerFormDiff'
import {
  customerFormSchema,
  customerCreateSchema,
  companyScaleOptions,
  type CustomerForm,
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
  (e: 'refresh'): void
}
const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const schema = computed(() => props.mode === 'create' ? toTypedSchema(customerCreateSchema) : toTypedSchema(customerFormSchema))
const { handleSubmit, resetForm, setValues, setFieldError, setErrors, errors, values } = useForm<CustomerForm | CustomerCreateForm>({
  validationSchema: schema,
  initialValues: { account_name: '', city: '', address: '', company_scale: undefined, source_public_id: undefined, default_procurement_method_id: undefined, contact_name: '', contact_mobile: '', contact_position: '', contact_gender: undefined } as unknown as CustomerCreateForm,
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
const profileBaseline = ref<CustomerUpdate>({ account_name: '', city: '', address: null, company_scale: null, source_public_id: null, default_procurement_method_id: null, industry: null })
const lifecycleStatusValue = ref<0 | 1 | null>(null)
const lifecycleStatusBaseline = ref<0 | 1 | null>(null)
const lifecycleSubmitting = ref(false)
const lifecycleError = ref<FeedbackError | null>(null)
const licenseTypeValue = ref<'TRIAL' | 'OFFICIAL' | null>(null)
const licenseExpiryDateValue = ref<string | null>(null)
const licenseTypeBaseline = ref<'TRIAL' | 'OFFICIAL' | null>(null)
const licenseExpiryDateBaseline = ref<string | null>(null)
const licenseSubmitting = ref(false)
const licenseError = ref<FeedbackError | null>(null)
const isDirty = ref(false)
const applyingFormValues = ref(false)
const visible = computed({ get: () => props.open, set: (val) => emit('update:open', val) })
const writeSubmitting = computed(() => submitting.value || lifecycleSubmitting.value || licenseSubmitting.value)
const closeGuard = useDialogCloseGuard({ isDirty: computed(() => isDirty.value || industryValue.value !== industryBaseline.value || lifecycleStatusValue.value !== lifecycleStatusBaseline.value || licenseTypeValue.value !== licenseTypeBaseline.value || licenseExpiryDateValue.value !== licenseExpiryDateBaseline.value), submitting: writeSubmitting, emitOpen: (open) => emit('update:open', open) })
const showConfirmDialog = closeGuard.showConfirmDialog
const fieldLabels: Record<string, string> = { account_name: '客户名称', city: '所在城市', address: '详细地址', company_scale: '公司规模', source_public_id: '获客来源', default_procurement_method_id: '采购方式', contact_name: '联系人姓名', contact_mobile: '联系电话', contact_position: '职位', contact_gender: '性别', industry: '行业' }
const contactFields = new Set(['contact_name', 'contact_mobile', 'contact_position', 'contact_gender'])
const progressiveFields = new Set(['industry'])
const errorSummary = computed(() => Object.entries(errors.value).filter(([field, message]) => !(props.mode === 'edit' && contactFields.has(field)) && typeof message === 'string' && message !== '').map(([field, message]) => ({ field, label: fieldLabels[field] ?? field, message, targetId: `customer-${field.split('_').join('-')}` })))
const focusFirstError = async (): Promise<void> => { const firstError = errorSummary.value[0]; if (firstError === undefined || typeof document === 'undefined') return; if (progressiveFields.has(firstError.field)) moreInfoOpen.value = true; await nextTick(); const field = document.querySelector<HTMLElement>(`[name="${firstError.field}"], #customer-${firstError.field.split('_').join('-')}`); if (field === null) return; field.scrollIntoView({ behavior: 'smooth', block: 'center' }); field.focus({ preventScroll: true }) }
watch(values, () => { if (!applyingFormValues.value) { isDirty.value = true; submitError.value = null } }, { deep: true, flush: 'sync' })
async function fetchProcurementMethodOptions(): Promise<void> { if (procurementMethodOptions.value.length > 0 || procurementMethodsLoading.value) return; procurementMethodsError.value = null; procurementMethodsLoading.value = true; try { procurementMethodOptions.value = await procurementApi.getProcurementMethodOptions() } catch (error) { procurementMethodsError.value = toFeedbackError(error, '采购方式', { operation: 'read' }); handleApiError(error, '获取采购方式') } finally { procurementMethodsLoading.value = false } }
async function fetchSourceOptions(): Promise<void> { sourceOptionsError.value = null; try { await loadFormOptions({ throwOnError: true, notifyOnError: false }) } catch (error) { sourceOptionsError.value = toFeedbackError(error, '获客来源', { operation: 'read' }); handleApiError(error, '获取获客来源') } }
function retryOptions(): void { if (procurementMethodsError.value !== null) void fetchProcurementMethodOptions(); if (sourceOptionsError.value !== null) void fetchSourceOptions() }
async function fetchIndustryHierarchy(): Promise<void> { if (industryHierarchyLoading.value) return; industryHierarchyLoading.value = true; industryHierarchyError.value = null; try { industryHierarchy.value = await customerApi.getIndustryHierarchy() } catch (error) { industryHierarchyError.value = toFeedbackError(error, '行业', { operation: 'read' }); handleApiError(error, '获取行业') } finally { industryHierarchyLoading.value = false } }
function handleMoreInfoChange(open: boolean): void { moreInfoOpen.value = open; if (open && Object.keys(industryHierarchy.value).length === 0 && industryHierarchyError.value === null) void fetchIndustryHierarchy() }
function normalizeCompanyScale(value: string | null): CustomerForm['company_scale'] | undefined { return companyScaleOptions.some(option => option.value === value) ? value as CustomerForm['company_scale'] : undefined }
function mapContactGenderToApi(gender: string): '1' | '2' { return gender === '女' ? '2' : '1' }
function handleLifecycleStatusChange(value: string | number): void { const normalized = Number(value); if (normalized === 0 || normalized === 1) lifecycleStatusValue.value = normalized }
function handleProcurementMethodChange(value: string, handleChange: (value: number | undefined) => void): void { const procurementMethodId = Number(value); handleChange(Number.isFinite(procurementMethodId) && procurementMethodId > 0 ? procurementMethodId : undefined) }
async function applyCustomerDetail(customer: CustomerDetailResponse): Promise<void> { loadedVersion.value = customer.version; ensureOption(customer.source_info); industryValue.value = customer.industry ?? ''; industryBaseline.value = customer.industry ?? ''; lifecycleStatusValue.value = customer.status === 0 || customer.status === 1 ? customer.status : null; lifecycleStatusBaseline.value = lifecycleStatusValue.value; licenseTypeValue.value = customer.license_type === 'TRIAL' || customer.license_type === 'OFFICIAL' ? customer.license_type : null; licenseExpiryDateValue.value = customer.license_expiry_date; licenseTypeBaseline.value = licenseTypeValue.value; licenseExpiryDateBaseline.value = licenseExpiryDateValue.value; profileBaseline.value = { account_name: customer.account_name, city: customer.city, address: customer.address, company_scale: customer.company_scale, source_public_id: customer.source_info?.public_id ?? null, default_procurement_method_id: customer.default_procurement_method_id, industry: customer.industry }; setErrors({}); applyingFormValues.value = true; setValues({ account_name: customer.account_name, city: customer.city, address: customer.address ?? '', company_scale: normalizeCompanyScale(customer.company_scale), source_public_id: customer.source_info?.public_id, default_procurement_method_id: customer.default_procurement_method_id ?? undefined, industry: customer.industry ?? '' } as Partial<CustomerForm>); isDirty.value = false; moreInfoOpen.value = false; lifecycleError.value = null; licenseError.value = null; await nextTick(); applyingFormValues.value = false }
async function loadCustomerDetail(customerId: string): Promise<void> { loadError.value = null; submitError.value = null; loading.value = true; try { await applyCustomerDetail(await customerApi.getCustomerDetail(customerId)) } catch (error) { loadError.value = toFeedbackError(error, '客户详情', { operation: 'read' }); handleApiError(error, '加载客户详情') } finally { loading.value = false } }
watch([(): boolean => props.open, (): string | undefined => props.customerId, (): string => props.mode], async ([open, customerId]): Promise<void> => { if (!open) { if (closeGuard.handleParentClose()) return; return }; void fetchProcurementMethodOptions(); void fetchSourceOptions(); closeGuard.reset(); loadError.value = null; moreInfoOpen.value = false; industryHierarchyError.value = null; lifecycleError.value = null; licenseError.value = null; if (props.mode === 'edit' && customerId !== undefined) { const prefetched = props.customer; if (prefetched !== null && prefetched !== undefined && prefetched.id === customerId) await applyCustomerDetail(prefetched); else await loadCustomerDetail(customerId) } else if (props.mode === 'create') { applyingFormValues.value = true; resetForm({ values: { account_name: '', city: '', address: '', company_scale: undefined, source_public_id: undefined, default_procurement_method_id: undefined, contact_name: '', contact_mobile: '', contact_position: '', contact_gender: undefined } as unknown as CustomerCreateForm }); industryValue.value = ''; industryBaseline.value = ''; lifecycleStatusValue.value = null; lifecycleStatusBaseline.value = null; licenseTypeValue.value = null; licenseExpiryDateValue.value = null; licenseTypeBaseline.value = null; licenseExpiryDateBaseline.value = null; isDirty.value = false; await nextTick(); applyingFormValues.value = false } }, { immediate: true })
async function refreshConflict(preserveInput: boolean): Promise<void> { if (props.mode !== 'edit' || props.customerId === undefined || loading.value) return; submitError.value = null; loading.value = true; try { const latest = await customerApi.getCustomerDetail(props.customerId); loadedVersion.value = latest.version; if (!preserveInput) await applyCustomerDetail(latest) } catch (error) { submitError.value = toFeedbackError(error, '客户最新版本'); handleApiError(error, '获取客户最新版本') } finally { loading.value = false } }
function updateProfileBaselineFromResponse(customer: { account_name: string; city: string; address: string | null; company_scale: string | null; source_info?: { public_id?: string | null } | null; default_procurement_method_id: number | null; industry: string | null }): void { profileBaseline.value = { account_name: customer.account_name, city: customer.city, address: customer.address, company_scale: customer.company_scale, source_public_id: customer.source_info?.public_id ?? null, default_procurement_method_id: customer.default_procurement_method_id, industry: customer.industry }; industryBaseline.value = customer.industry ?? ''; isDirty.value = false }
const onSubmit = handleSubmit(async (formValues): Promise<void> => { submitting.value = true; try { if (props.mode === 'create') { const createData = formValues as CustomerCreateForm; const createdCustomer = await customerApi.createCustomer({ account_name: createData.account_name, city: createData.city, address: createData.address !== '' && createData.address !== undefined ? createData.address : null, company_scale: createData.company_scale ?? null, source_public_id: createData.source_public_id, default_procurement_method_id: createData.default_procurement_method_id ?? null, primary_contact: { name: createData.contact_name, mobile: createData.contact_mobile, position: createData.contact_position, gender: mapContactGenderToApi(createData.contact_gender), is_decision_maker: false } }); toast.success('客户创建成功'); isDirty.value = false; closeGuard.approveClose(); visible.value = false; emit('success', { entityType: 'customer', entityId: createdCustomer.id, operation: 'create', outcome: 'success', stateSyncRequested: true }); return } if (props.customerId === undefined || loadedVersion.value === null) return; const editData = formValues as CustomerForm; const current: CustomerUpdate = { account_name: editData.account_name, city: editData.city, address: editData.address ?? null, company_scale: editData.company_scale ?? null, source_public_id: editData.source_public_id, default_procurement_method_id: editData.default_procurement_method_id ?? null, industry: industryValue.value }; const payload = buildCustomerUpdatePayload(current, profileBaseline.value, loadedVersion.value); const inlineDirty = lifecycleStatusValue.value !== lifecycleStatusBaseline.value || licenseTypeValue.value !== licenseTypeBaseline.value || licenseExpiryDateValue.value !== licenseExpiryDateBaseline.value; if (payload !== null) { const updatedCustomer = await customerApi.updateCustomer(props.customerId, payload); loadedVersion.value = updatedCustomer.version; updateProfileBaselineFromResponse(updatedCustomer); toast.success('客户更新成功'); if (inlineDirty) { emit('refresh'); return } closeGuard.approveClose(); visible.value = false; emit('success', { entityType: 'customer', entityId: updatedCustomer.id, operation: 'update', outcome: 'success', stateSyncRequested: true }); return } if (!inlineDirty) { isDirty.value = false; closeGuard.approveClose(); visible.value = false; emit('success', { entityType: 'customer', entityId: props.customerId, operation: 'update', outcome: 'success', stateSyncRequested: true }); } } catch (error) { submitError.value = toFeedbackError(error, props.mode === 'create' ? '创建客户' : '更新客户', { operation: 'write' }); for (const fieldError of submitError.value.fieldErrors ?? []) if (fieldError.field in fieldLabels) setFieldError(fieldError.field as keyof CustomerForm | keyof CustomerCreateForm, fieldError.message); if ((submitError.value.fieldErrors?.length ?? 0) > 0) await focusFirstError(); if (submitError.value.kind !== 'validation' && submitError.value.kind !== 'conflict') handleApiError(error, props.mode === 'create' ? '创建客户' : '更新客户') } finally { submitting.value = false } }, async () => { await focusFirstError() })
async function saveLifecycleStatus(): Promise<void> { if (props.mode !== 'edit' || props.customerId === undefined || loadedVersion.value === null || lifecycleStatusValue.value === null || lifecycleStatusValue.value === lifecycleStatusBaseline.value || writeSubmitting.value) return; const status = lifecycleStatusValue.value; lifecycleSubmitting.value = true; lifecycleError.value = null; try { const updated = await customerApi.updateCustomerLifecycleStatus(props.customerId, { status, expected_version: loadedVersion.value }); loadedVersion.value = updated.version; lifecycleStatusBaseline.value = updated.status === 0 || updated.status === 1 ? updated.status : null; lifecycleStatusValue.value = lifecycleStatusBaseline.value; emit('refresh'); toast.success('客户生命周期状态已更新') } catch (error) { lifecycleError.value = toFeedbackError(error, '客户生命周期状态', { operation: 'write' }); handleApiError(error, '更新客户生命周期状态') } finally { lifecycleSubmitting.value = false } }
async function saveLicenseSnapshot(): Promise<void> { if (props.mode !== 'edit' || props.customerId === undefined || loadedVersion.value === null || writeSubmitting.value) return; if (licenseTypeValue.value === licenseTypeBaseline.value && licenseExpiryDateValue.value === licenseExpiryDateBaseline.value) return; licenseSubmitting.value = true; licenseError.value = null; try { const updated = await customerApi.updateCustomerLicenseSnapshot(props.customerId, { expected_version: loadedVersion.value, license_type: licenseTypeValue.value, license_expiry_date: licenseExpiryDateValue.value }); loadedVersion.value = updated.version; licenseTypeBaseline.value = licenseTypeValue.value; licenseExpiryDateBaseline.value = licenseExpiryDateValue.value; emit('refresh'); toast.success('客户授权汇总已更新') } catch (error) { licenseError.value = toFeedbackError(error, '客户授权汇总', { operation: 'write' }); handleApiError(error, '更新客户授权汇总') } finally { licenseSubmitting.value = false } }
function clearLicenseExpiryDate(): void { licenseExpiryDateValue.value = null }
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
        <DialogDescription class="sr-only">填写客户信息</DialogDescription>
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

            <!-- Customer Source -->
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

            <!-- Company Scale -->
            <FormField v-slot="{ value, handleChange }" name="company_scale">
              <FormItem>
                <SelectField
                  id="customer-company-scale"
                  :model-value="String(value ?? '')"
                  label="公司规模"
                  required
                  :options="companyScaleOptions"
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

        <Collapsible
          v-if="mode === 'edit'"
          :open="moreInfoOpen"
          class="space-y-3 border-t pt-4"
          @update:open="handleMoreInfoChange"
        >
          <CollapsibleTrigger as-child>
            <button
              id="customer-more-info-trigger"
              type="button"
              class="flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm font-medium"
              :aria-expanded="moreInfoOpen"
              aria-controls="customer-more-info-content"
            >
              <span>更多客户信息</span>
              <span class="text-xs text-muted-foreground">{{ [industryValue, licenseTypeValue, licenseExpiryDateValue].filter(Boolean).length }} 项</span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent id="customer-more-info-content" class="space-y-4">
            <div v-if="industryHierarchyError" class="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-sm" role="alert">
              <span>{{ industryHierarchyError.description }}</span>
              <Button type="button" variant="outline" size="sm" class="ml-2" @click="fetchIndustryHierarchy">重试</Button>
            </div>
            <IndustryHierarchySelectField
              id="customer-industry"
              v-model="industryValue"
              :hierarchy="industryHierarchy"
              :loading="industryHierarchyLoading"
              :error="industryHierarchyError?.description ?? ''"
              :disabled="industryHierarchyError !== null"
              label="行业"
            />
            <div class="space-y-2 rounded-md border p-3">
              <div class="text-sm font-medium">生命周期状态</div>
              <template v-if="lifecycleStatusBaseline === 0 || lifecycleStatusBaseline === 1">
                <SelectField
                  id="customer-lifecycle-status"
                  :model-value="lifecycleStatusValue"
                  :options="[{ value: 0, label: '跟进中' }, { value: 1, label: '已赢单' }]"
                  :disabled="writeSubmitting"
                  @update:model-value="handleLifecycleStatusChange"
                />
                <p v-if="lifecycleError" class="text-sm text-destructive" role="alert">{{ lifecycleError.description }}</p>
                <Button type="button" size="sm" :disabled="writeSubmitting || lifecycleStatusValue === lifecycleStatusBaseline" @click="saveLifecycleStatus">保存生命周期状态</Button>
              </template>
              <p v-else class="text-sm text-muted-foreground">该客户状态由其他流程管理，暂不支持在此修改。</p>
            </div>
            <div class="space-y-3 rounded-md border p-3">
              <div class="text-sm font-medium">授权信息</div>
              <p class="text-xs text-muted-foreground">授权信息仅作客户档案汇总，不代表许可证申请或审批结果。</p>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <SelectField
                  id="customer-license-type"
                  v-model="licenseTypeValue"
                  label="授权类型"
                  :options="[{ value: 'TRIAL', label: '试用' }, { value: 'OFFICIAL', label: '正式' }]"
                  :disabled="writeSubmitting"
                  placeholder="未授权"
                />
                <div>
                  <DateField
                    id="customer-license-expiry-date"
                    label="授权到期日"
                    :model-value="licenseExpiryDateValue ? new Date(`${licenseExpiryDateValue}T00:00:00`) : null"
                    :disabled="writeSubmitting"
                    @update:model-value="licenseExpiryDateValue = $event ? formatLocalDate($event) : null"
                  />
                  <Button type="button" variant="ghost" size="sm" :disabled="writeSubmitting || licenseExpiryDateValue === null" @click="clearLicenseExpiryDate">清除日期</Button>
                </div>
              </div>
              <span class="inline-flex rounded-full border px-2 py-1 text-xs">{{ licenseStatusLabel(licenseExpiryDateValue, licenseTypeValue) }}</span>
              <p v-if="licenseError" class="text-sm text-destructive" role="alert">{{ licenseError.description }}</p>
              <Button type="button" :disabled="writeSubmitting" @click="saveLicenseSnapshot">保存授权信息</Button>
            </div>
          </CollapsibleContent>
        </Collapsible>

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

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" :disabled="writeSubmitting" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting" :disabled="writeSubmitting || optionsLoading || optionsError">
            {{ submitting ? '提交中...' : (mode === 'create' ? '创建' : '保存') }}
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
