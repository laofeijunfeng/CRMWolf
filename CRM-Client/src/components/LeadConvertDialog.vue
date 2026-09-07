<script setup lang="ts">
/**
 * LeadConvertDialog.vue - 线索转化为客户弹窗
 *
 * 设计规范：
 * - 使用 shadcn-vue Dialog + Form
 * - V2 Design Tokens
 * - 替代 LeadConvert.vue 页面跳转
 */
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Building2 } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { getAcquisitionSourceDisplayName } from '@/schemas/acquisition-source'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  InputField,
  SelectField,
} from '@/components/crmwolf'
import FeedbackAlert from '@/components/crmwolf/FeedbackAlert.vue'
import { leadApi, type LeadDetail } from '@/api/lead'
import customerApi from '@/api/customer'
import procurementApi from '@/api/procurement'
import { confirmDialog } from '@/utils/confirmDialog'
import { handleApiError, handleOutcomeUnknown, isOutcomeUnknown } from '@/utils/errorHandler'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import {
  createCommandRequestOptions,
  isNetworkOrTimeoutError,
  operationIdFromError,
  pollCommandStatus,
  type CommandExecutionResponse,
  type CommandRequestOptions,
} from '@/api/command'

interface Props {
  open: boolean
  leadId: string | null
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== State ====================
const leadLoading = ref(props.open && props.leadId !== null)
const procurementLoading = ref(props.open && props.leadId !== null)
const loading = computed(() => leadLoading.value || procurementLoading.value)
const submitting = ref(false)
const closeGuardPending = ref(false)
const convertCommandOptions = ref<CommandRequestOptions | null>(null)
const leadData = ref<LeadDetail | null>(null)
const procurementMethodOptions = ref<{ id: number; name: string }[]>([])
const loadError = ref<FeedbackError | null>(null)
const loadRequestId = ref(0)
const initialForm = ref({
  account_name: '',
  city: '',
  address: '',
  default_procurement_method_id: '' as string | number,
})

// 表单数据
const formValues = reactive({
  account_name: '',
  city: '',
  address: '',
  default_procurement_method_id: '' as string | number
})

// 计算属性
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})
const procurementSelectOptions = computed(() =>
  procurementMethodOptions.value.map((option) => ({
    value: String(option.id),
    label: option.name,
  }))
)

const hasFormChanges = computed(() =>
  formValues.account_name.trim() !== String(initialForm.value.account_name).trim()
  || formValues.city.trim() !== String(initialForm.value.city).trim()
  || formValues.address.trim() !== String(initialForm.value.address).trim()
  || String(formValues.default_procurement_method_id) !== String(initialForm.value.default_procurement_method_id)
)

// ==================== Methods ====================

// 加载线索详情
const fetchLeadDetail = async (leadId: string, requestId: number): Promise<void> => {
  leadLoading.value = true
  try {
    const res = await leadApi.getLeadDetail(leadId)
    if (requestId !== loadRequestId.value || !props.open || props.leadId !== leadId) return

    leadData.value = res
    formValues.account_name = res.lead_name ?? ''
    formValues.city = res.city ?? ''
    formValues.address = ''
    formValues.default_procurement_method_id = ''
    initialForm.value = { ...formValues }
  } catch (error: unknown) {
    if (requestId !== loadRequestId.value || !props.open || props.leadId !== leadId) return
    loadError.value = toFeedbackError(error, '线索详情')
  } finally {
    if (requestId === loadRequestId.value) leadLoading.value = false
  }
}

// 加载采购方式选项
const fetchProcurementMethodOptions = async (requestId: number): Promise<void> => {
  procurementLoading.value = true
  try {
    const res = await procurementApi.getProcurementMethodOptions()
    if (requestId !== loadRequestId.value || !props.open) return
    procurementMethodOptions.value = res ?? []
  } catch (error: unknown) {
    if (requestId !== loadRequestId.value || !props.open) return
    procurementMethodOptions.value = []
    loadError.value = toFeedbackError(error, '默认采购方式')
  } finally {
    if (requestId === loadRequestId.value) procurementLoading.value = false
  }
}

function commandErrorMessage(error: Record<string, unknown> | null | undefined): string {
  const message = error?.['message']
  return typeof message === 'string' && message.length > 0 ? message : '请稍后重试'
}

function isConversionSucceeded(result: { status?: string; customer_id?: string }): boolean {
  if (result.status === undefined) return typeof result.customer_id === 'string' && result.customer_id.length > 0
  return result.status === 'SUCCEEDED'
}

interface ConversionRecovery {
  succeeded: boolean
  keepCommand: boolean
}

async function recoverConversion(options: CommandRequestOptions): Promise<ConversionRecovery> {
  try {
    const result: CommandExecutionResponse = await pollCommandStatus(options.operationId ?? '', {
      attempts: 8,
      intervalMs: 500,
    })
    if (result.status === 'SUCCEEDED') return { succeeded: true, keepCommand: false }
    if (result.status === 'PENDING' || result.status === 'UNKNOWN') {
      handleOutcomeUnknown('线索转化')
      return { succeeded: false, keepCommand: true }
    }
    toast.error('线索转化失败', { description: commandErrorMessage(result.error) })
    return { succeeded: false, keepCommand: false }
  } catch {
    handleOutcomeUnknown('线索转化')
    return { succeeded: false, keepCommand: true }
  }
}

// 提交转化
const handleSubmit = async (): Promise<void> => {
  if (props.leadId === undefined || props.leadId === null || submitting.value || loading.value) return

  // 简单校验
  if (!formValues.account_name.trim()) {
    toast.error('请输入客户公司名称')
    return
  }
  if (!formValues.city.trim()) {
    toast.error('请输入所在城市')
    return
  }
  if (formValues.default_procurement_method_id === null
    || formValues.default_procurement_method_id === undefined
    || String(formValues.default_procurement_method_id).trim() === '') {
    toast.error('请选择默认采购方式')
    return
  }

  submitting.value = true
  const commandOptions = convertCommandOptions.value ?? createCommandRequestOptions()
  convertCommandOptions.value = commandOptions
  try {
    const data = {
      lead_id: props.leadId,
      account_name: formValues.account_name.trim().length > 0 ? formValues.account_name.trim() : null,
      address: formValues.address.trim().length > 0 ? formValues.address.trim() : null,
      default_procurement_method_id: Number(formValues.default_procurement_method_id),
    }
    let succeeded = false
    let keepCommand = true
    try {
      const result = await customerApi.convertLeadToCustomer(data, commandOptions)
      succeeded = isConversionSucceeded(result)
      if (result.status === 'PENDING' || result.status === 'UNKNOWN') {
        const recovery = await recoverConversion(commandOptions)
        succeeded = recovery.succeeded
        keepCommand = recovery.keepCommand
      } else if (result.status === 'FAILED' || result.status === 'CONFLICT' || result.status === 'PARTIAL') {
        toast.error('线索转化失败', { description: commandErrorMessage(result.error) })
        keepCommand = false
      }
    } catch (error: unknown) {
      const operationId = operationIdFromError(error)
      if (isNetworkOrTimeoutError(error) || operationId !== null || isOutcomeUnknown(error)) {
        const recovery = await recoverConversion(operationId === null ? commandOptions : { ...commandOptions, operationId })
        succeeded = recovery.succeeded
        keepCommand = recovery.keepCommand
      } else {
        keepCommand = false
        throw error
      }
    }
    if (!succeeded) {
      if (!keepCommand) convertCommandOptions.value = null
      return
    }
    toast.success('线索转化成功')
    visible.value = false
    convertCommandOptions.value = null
    emit('success')
    // 不跳转，留在线索管理页面，通过 emit('success') 触发列表刷新
  } catch (error: unknown) {
    handleApiError(error, '转化线索')
  } finally {
    submitting.value = false
  }
}

// 关闭弹窗
const handleClose = async (): Promise<void> => {
  if (submitting.value || closeGuardPending.value) return

  if (!hasFormChanges.value) {
    visible.value = false
    return
  }

  closeGuardPending.value = true
  try {
    const confirmed = await confirmDialog(
      '已填写客户信息，关闭后这些内容不会保存。确定关闭吗？',
      '放弃本次转化？',
      { variant: 'destructive', confirmText: '放弃并关闭' },
    )
    if (confirmed) visible.value = false
  } finally {
    closeGuardPending.value = false
  }
}

const handleDialogOpenChange = async (open: boolean): Promise<void> => {
  if (open) {
    visible.value = true
    return
  }
  await handleClose()
}

const startLoad = (leadId: string): void => {
  const requestId = ++loadRequestId.value
  loadError.value = null
  leadData.value = null
  procurementMethodOptions.value = []
  formValues.account_name = ''
  formValues.city = ''
  formValues.address = ''
  formValues.default_procurement_method_id = ''
  initialForm.value = { ...formValues }
  leadLoading.value = true
  procurementLoading.value = true
  void fetchProcurementMethodOptions(requestId)
  void fetchLeadDetail(leadId, requestId)
}

const retryLoad = (): void => {
  if (props.leadId === null || loading.value) return
  startLoad(props.leadId)
}

// ==================== Watch ====================
watch(
  () => [props.open, props.leadId] as const,
  ([open, leadId]) => {
    if (!open || leadId === null) {
      loadRequestId.value += 1
      leadLoading.value = false
      procurementLoading.value = false
      leadData.value = null
      loadError.value = null
      return
    }

    startLoad(leadId)
  },
  { immediate: true },
)

// 重置状态
watch(
  () => props.open,
  (open) => {
    if (!open) {
      formValues.account_name = ''
      formValues.city = ''
      formValues.address = ''
      formValues.default_procurement_method_id = ''
      initialForm.value = { ...formValues }
      leadData.value = null
      procurementMethodOptions.value = []
      leadLoading.value = false
      procurementLoading.value = false
      loadError.value = null
      convertCommandOptions.value = null
    }
  },
)
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogOpenChange">
    <DialogContent class="lead-convert-dialog w-[calc(100vw-2rem)] max-w-[600px]">
      <DialogHeader>
        <DialogTitle>转化为客户</DialogTitle>
        <DialogDescription>
          将线索转化为客户，创建客户档案
        </DialogDescription>
      </DialogHeader>

      <div class="lead-convert-dialog__body">
        <div
          v-if="loading"
          class="lead-convert-dialog__loading"
          role="status"
          aria-live="polite"
          aria-busy="true"
          aria-label="正在加载线索信息"
        >
          <div class="lead-convert-dialog__loading-card">
            <div class="lead-convert-dialog__loading-header">
              <Skeleton class="lead-convert-dialog__loading-avatar" />
              <div class="lead-convert-dialog__loading-heading">
                <Skeleton class="lead-convert-dialog__loading-name" />
                <Skeleton class="lead-convert-dialog__loading-badge" />
              </div>
            </div>
            <div class="lead-convert-dialog__loading-divider" />
            <div class="lead-convert-dialog__loading-grid">
              <Skeleton v-for="i in 6" :key="i" class="lead-convert-dialog__loading-attribute" />
            </div>
          </div>
        </div>

        <!-- 线索信息卡片 -->
        <div v-else-if="leadData" class="info-card">
          <div class="info-header">
            <div class="avatar">
              {{ leadData.lead_name?.charAt(0) || '线' }}
            </div>
            <div class="info-content">
              <div class="entity-name">{{ leadData.lead_name }}</div>
              <div class="info-badge">线索信息</div>
            </div>
          </div>

          <div class="info-divider" />

          <div class="attributes-grid">
            <div class="attribute-item">
              <span class="attribute-label">线索来源</span>
              <span class="attribute-value">{{ getAcquisitionSourceDisplayName(leadData) }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">所在城市</span>
              <span class="attribute-value">{{ leadData.city || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">联系人</span>
              <span class="attribute-value">{{ leadData.contact_name || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">联系电话</span>
              <span class="attribute-value">{{ leadData.contact_phone || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">公司规模</span>
              <span class="attribute-value">{{ leadData.company_scale || '-' }}</span>
            </div>
            <div class="attribute-item">
              <span class="attribute-label">负责人</span>
              <span class="attribute-value">{{ leadData.owner_info?.name || '-' }}</span>
            </div>
          </div>
        </div>

        <FeedbackAlert
          v-if="loadError !== null && !loading"
          class="lead-convert-dialog__feedback"
          :error="loadError"
          density="compact"
          retry-label="重新加载线索信息"
          @retry="retryLoad"
        />

        <!-- 客户信息表单 -->
        <form id="lead-convert-form" class="form-section" @submit.prevent="handleSubmit">
          <h4 class="form-section-title">客户信息</h4>

          <div class="space-y-4">
            <InputField
              id="lead-convert-account-name"
              v-model="formValues.account_name"
              class="form-item"
              label="客户公司名称"
              required
              :disabled="submitting || loading || loadError !== null || closeGuardPending"
              placeholder="请输入客户公司名称（默认使用线索名称）"
            />

            <div class="form-grid">
              <InputField
                id="lead-convert-city"
                v-model="formValues.city"
                class="form-item"
                label="所在城市"
                required
                :disabled="submitting || loading || loadError !== null || closeGuardPending"
                placeholder="请输入所在城市"
              />

              <SelectField
                id="lead-convert-procurement-method"
                v-model="formValues.default_procurement_method_id"
                class="form-item"
                label="默认采购方式"
                required
                :disabled="submitting || loading || loadError !== null || closeGuardPending"
                :options="procurementSelectOptions"
                placeholder="请选择默认采购方式"
              />
            </div>

            <InputField
              id="lead-convert-address"
              v-model="formValues.address"
              class="form-item"
              label="公司地址"
              :disabled="submitting || loading || loadError !== null || closeGuardPending"
              placeholder="请输入公司地址（可选）"
            />
          </div>
        </form>
      </div>

      <DialogFooter class="lead-convert-dialog__footer">
        <Button
          type="button"
          variant="outline"
          class="lead-convert-dialog__button"
          :disabled="submitting || closeGuardPending"
          @click="handleClose"
        >
          取消
        </Button>
        <Button
          type="submit"
          form="lead-convert-form"
          class="lead-convert-dialog__button"
          :disabled="submitting || loading || loadError !== null"
        >
          <Building2 v-if="!submitting" class="w-4 h-4 mr-2" />
          {{ submitting ? '转化中...' : '确认转化' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.lead-convert-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-height: $wolf-modal-height-mobile-v2;
  overflow: hidden;
}

.lead-convert-dialog__body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-inline: calc($wolf-focus-ring-width-v2 + $wolf-focus-ring-offset-v2);
  scroll-padding-bottom: calc($wolf-space-xl-v2 + $wolf-safe-area-bottom-v2);
}

.lead-convert-dialog__loading-card,
.info-card {
  min-width: 0;
  padding: $wolf-space-md-v2;
  border-radius: $wolf-radius-lg-v2;
  background: $wolf-bg-muted-v2;
}

.lead-convert-dialog__loading-header,
.info-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
}

.lead-convert-dialog__loading-avatar {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  border-radius: $wolf-radius-full-v2;
}

.lead-convert-dialog__loading-heading {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.lead-convert-dialog__loading-name {
  width: 140px;
  height: 24px;
}

.lead-convert-dialog__loading-badge {
  width: 72px;
  height: 18px;
}

.lead-convert-dialog__loading-divider,
.info-divider {
  height: 1px;
  margin: $wolf-space-md-v2 0;
  background: $wolf-border-default-v2;
}

.lead-convert-dialog__loading-grid,
.attributes-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.lead-convert-dialog__loading-attribute {
  width: 80%;
  height: 40px;
}

.avatar {
  display: flex;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.entity-name {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.info-badge {
  display: inline-flex;
  width: fit-content;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm-v2;
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.attribute-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-label {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.attribute-value {
  overflow: hidden;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-section {
  padding-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-light-v2;
}

.form-section-title {
  margin: 0 0 $wolf-space-md-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.form-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.lead-convert-dialog__feedback {
  flex-shrink: 0;
}

.lead-convert-dialog__footer {
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

.lead-convert-dialog__button {
  height: $wolf-button-height-md-v2;
  min-height: $wolf-button-height-md-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .lead-convert-dialog__loading-grid,
  .attributes-grid,
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .lead-convert-dialog__button {
    width: 100%;
    height: $wolf-button-height-mobile-v2;
    min-height: $wolf-button-height-mobile-v2;
  }
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
