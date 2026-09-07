<script setup lang="ts">
/**
 * OpportunityWinDialog.vue - 赢单表单弹窗
 *
 * 收集实际成交金额和日期，遵循无障碍和动效规范。
 * 使用 vee-validate + Zod 进行表单校验。
 */
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
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
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import {
  DateField,
  InputField,
} from '@/components/crmwolf'
import FeedbackAlert from '@/components/crmwolf/FeedbackAlert.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SelectionSummary, { type SummaryItem } from '@/components/crmwolf/SelectionSummary.vue'
import { confirmDialog } from '@/utils/confirmDialog'
import { getTodayLocalDate, formatLocalDate } from '@/utils/format'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

const schema = toTypedSchema(
  z.object({
    actual_amount: z.number().min(0.01, '实际成交金额必须大于0'),
    actual_closing_date: z.string().min(1, '请选择实际成交日期'),
  }),
)

interface Props {
  opportunityId: string | null
  open: boolean
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { handleSubmit, resetForm, values } = useForm({
  validationSchema: schema,
  initialValues: {
    actual_amount: 0,
    actual_closing_date: getTodayLocalDate(),
  },
})

const loading = ref(false)
const submitting = ref(false)
const closeGuardPending = ref(false)
const opportunity = ref<Opportunity | null>(null)
const loadRequestId = ref(0)
const initialValues = ref<{ actualAmount: number; closingDate: string } | null>(null)
const loadError = ref<FeedbackError | null>(null)
const submitError = ref<FeedbackError | null>(null)

const currentStatusLabel = computed(() => {
  if (opportunity.value?.status === 1) return '已赢单'
  if (opportunity.value?.status === 2) return '已输单'
  return '跟进中'
})

const customerName = computed(() =>
  opportunity.value?.customer_name ?? opportunity.value?.customer_info?.account_name ?? '未关联客户',
)
const contextItems = computed<SummaryItem[]>(() => {
  if (opportunity.value === null) return []

  return [
    { key: 'opportunity', label: '商机', value: opportunity.value.opportunity_name },
    { key: 'customer', label: '客户', value: customerName.value },
    { key: 'status', label: '当前状态', value: currentStatusLabel.value },
    { key: 'resultStatus', label: '提交后状态', value: '已赢单' },
  ]
})

const hasFormChanges = computed(() => {
  const initial = initialValues.value
  if (initial === null) return false

  return Number(values.actual_amount ?? 0) !== initial.actualAmount
    || String(values.actual_closing_date ?? '') !== initial.closingDate
})

const handleDialogOpenChange = async (open: boolean): Promise<void> => {
  if (open) {
    emit('update:open', true)
    return
  }

  if (submitting.value || closeGuardPending.value) return

  if (!hasFormChanges.value) {
    emit('update:open', false)
    return
  }

  closeGuardPending.value = true
  try {
    const confirmed = await confirmDialog(
      '已填写赢单信息，关闭后这些内容不会保存。确定关闭吗？',
      '放弃本次标记？',
      { variant: 'destructive', confirmText: '放弃并关闭' },
    )
    if (confirmed) emit('update:open', false)
  } finally {
    closeGuardPending.value = false
  }
}

const loadOpportunity = async (opportunityId: string): Promise<void> => {
  const requestId = ++loadRequestId.value
  loadError.value = null
  loading.value = true
  try {
    const loadedOpportunity = await opportunityApi.getOpportunity(opportunityId)
    if (requestId !== loadRequestId.value || !props.open || props.opportunityId !== opportunityId) return

    opportunity.value = loadedOpportunity
    const closingDate = getTodayLocalDate()
    const amount = loadedOpportunity.total_amount
    initialValues.value = { actualAmount: amount, closingDate }
    resetForm({ values: { actual_amount: amount, actual_closing_date: closingDate } })
  } catch (error) {
    if (requestId !== loadRequestId.value || !props.open || props.opportunityId !== opportunityId) return
    loadError.value = toFeedbackError(error, '商机详情')
  } finally {
    if (requestId === loadRequestId.value) loading.value = false
  }
}

const retryLoad = async (): Promise<void> => {
  if (props.opportunityId === null || loading.value) return
  await loadOpportunity(props.opportunityId)
}

watch(
  () => [props.open, props.opportunityId] as const,
  async ([isOpen, opportunityId]) => {
    if (!isOpen || opportunityId === null) {
      loadRequestId.value += 1
      opportunity.value = null
      initialValues.value = null
      loadError.value = null
      submitError.value = null
      return
    }

    submitError.value = null
    await loadOpportunity(opportunityId)
  },
  { immediate: true },
)

const onSubmit = handleSubmit(async (formValues) => {
  if (props.opportunityId === null || submitting.value) return

  submitError.value = null
  submitting.value = true
  try {
    await opportunityApi.markAsWon(props.opportunityId, {
      actual_amount: formValues.actual_amount,
      actual_closing_date: formValues.actual_closing_date,
    })

    toast.success('商机已标记为赢单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    submitError.value = toFeedbackError(error, '标记赢单', { operation: 'write' })
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogOpenChange">
    <DialogContent class="opportunity-win-dialog w-[calc(100vw-2rem)] max-w-[425px]">
      <DialogHeader>
        <DialogTitle>标记赢单</DialogTitle>
        <DialogDescription>确认商机成交信息后，商机状态将变更为“已赢单”。</DialogDescription>
      </DialogHeader>

      <div class="opportunity-win-dialog__body">
        <SelectionSummary
          v-if="loading"
          variant="compact"
          aria-label="正在加载商机上下文"
          loading
          :loading-count="4"
          :items="[]"
          :details="[]"
        />

        <SelectionSummary
          v-else-if="opportunity !== null"
          variant="compact"
          aria-label="赢单操作上下文"
          :items="contextItems"
        >
          <template #value-resultStatus>
            <StatusBadge status="won" type="opportunity" size="small" />
          </template>
        </SelectionSummary>

        <FeedbackAlert
          v-if="loadError !== null"
          class="opportunity-win-dialog__feedback"
          :error="loadError"
          density="compact"
          retry-label="重新加载商机信息"
          @retry="retryLoad"
        />

        <FeedbackAlert
          v-if="submitError !== null"
          class="opportunity-win-dialog__feedback"
          :error="submitError"
          density="compact"
          retry-label="重新提交"
          @retry="onSubmit"
        />

        <form id="opportunity-win-form" class="opportunity-win-dialog__form" @submit="onSubmit">
          <FormField v-slot="{ value, handleChange }" name="actual_amount">
            <FormItem>
              <InputField
                id="opportunity-win-amount"
                :model-value="Number(value ?? 0)"
                label="实际成交金额"
                required
                type="number"
                step="0.01"
                min="0"
                placeholder="请输入金额"
                :disabled="loading || submitting || loadError !== null"
                @update:model-value="handleChange(Number($event))"
              />
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ value, handleChange }" name="actual_closing_date">
            <FormItem>
              <DateField
                id="opportunity-win-date"
                :model-value="value ? new Date(String(value)) : null"
                label="实际成交日期"
                required
                placeholder="请选择实际成交日期"
                :disabled="loading || submitting || loadError !== null"
                @update:model-value="(date: Date | null) => handleChange(date ? formatLocalDate(date) : '')"
              />
              <FormMessage />
            </FormItem>
          </FormField>
        </form>
      </div>

      <DialogFooter class="opportunity-win-dialog__footer">
        <Button
          variant="outline"
          class="opportunity-win-dialog__button"
          :disabled="submitting || closeGuardPending"
          @click="handleDialogOpenChange(false)"
        >
          取消
        </Button>
        <Button
          type="submit"
          form="opportunity-win-form"
          class="opportunity-win-dialog__button"
          :disabled="submitting || loading || loadError !== null || closeGuardPending"
          :loading="submitting"
        >
          {{ submitting ? '提交中...' : '确认标记赢单' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunity-win-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-height: $wolf-modal-height-mobile-v2;
  overflow: hidden;
}

.opportunity-win-dialog__body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-inline: calc($wolf-focus-ring-width-v2 + $wolf-focus-ring-offset-v2);
  scroll-padding-bottom: calc($wolf-space-xl-v2 + $wolf-safe-area-bottom-v2);
}

.opportunity-win-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-form-item-gap-v2;
}

.opportunity-win-dialog__feedback {
  min-width: 0;
}

.opportunity-win-dialog__footer {
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

.opportunity-win-dialog__button {
  height: $wolf-button-height-md-v2;
  min-height: $wolf-button-height-md-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .opportunity-win-dialog__button {
    width: 100%;
    height: $wolf-button-height-mobile-v2;
    min-height: $wolf-button-height-mobile-v2;
  }
}
</style>
