<script setup lang="ts">
/**
 * OpportunityLoseDialog.vue - 输单表单弹窗
 *
 * 收集输单原因，遵循无障碍和动效规范。
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
import { TextareaField } from '@/components/crmwolf'
import FeedbackAlert from '@/components/crmwolf/FeedbackAlert.vue'
import SelectionSummary, { type SummaryItem } from '@/components/crmwolf/SelectionSummary.vue'
import { confirmDialog } from '@/utils/confirmDialog'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

const schema = toTypedSchema(
  z.object({
    loss_reason: z
      .string()
      .min(1, '请输入输单原因')
      .max(500, '输单原因不能超过500个字符'),
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
    loss_reason: '',
  },
})

const loading = ref(false)
const submitting = ref(false)
const closeGuardPending = ref(false)
const opportunity = ref<Opportunity | null>(null)
const loadRequestId = ref(0)
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
    { key: 'resultStatus', label: '提交后状态', value: '已输单' },
  ]
})

const hasFormChanges = computed(() => String(values.loss_reason ?? '').trim().length > 0)

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
      '已填写输单原因，关闭后这些内容不会保存。确定关闭吗？',
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
    resetForm({ values: { loss_reason: '' } })
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
    await opportunityApi.markAsLost(props.opportunityId, {
      loss_reason: formValues.loss_reason.trim(),
    })

    toast.success('商机已标记为输单')
    emit('success')
    emit('update:open', false)
  } catch (error) {
    submitError.value = toFeedbackError(error, '标记输单', { operation: 'write' })
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogOpenChange">
    <DialogContent class="opportunity-lose-dialog w-[calc(100vw-2rem)] max-w-[425px]">
      <DialogHeader>
        <DialogTitle>标记输单</DialogTitle>
        <DialogDescription>确认输单原因后，商机状态将变更为“已输单”。</DialogDescription>
      </DialogHeader>

      <div class="opportunity-lose-dialog__body">
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
          aria-label="输单操作上下文"
          :items="contextItems"
        >
          <template #value-resultStatus>
            <span class="font-medium text-destructive">已输单</span>
          </template>
        </SelectionSummary>

        <FeedbackAlert
          v-if="loadError !== null"
          class="opportunity-lose-dialog__feedback"
          :error="loadError"
          density="compact"
          retry-label="重新加载商机信息"
          @retry="retryLoad"
        />

        <FeedbackAlert
          v-if="submitError !== null"
          class="opportunity-lose-dialog__feedback"
          :error="submitError"
          density="compact"
          retry-label="重新提交"
          @retry="onSubmit"
        />

        <form id="opportunity-lose-form" class="opportunity-lose-dialog__form" @submit="onSubmit">
          <FormField v-slot="{ value, handleChange }" name="loss_reason">
            <FormItem>
              <TextareaField
                id="opportunity-lose-reason"
                :model-value="String(value ?? '')"
                label="输单原因"
                required
                :rows="4"
                :maxlength="500"
                placeholder="请输入输单原因"
                :disabled="loading || submitting || loadError !== null"
                control-class="resize-none"
                @update:model-value="handleChange"
              />
              <FormMessage />
            </FormItem>
          </FormField>
        </form>
      </div>

      <DialogFooter class="opportunity-lose-dialog__footer">
        <Button
          variant="outline"
          class="opportunity-lose-dialog__button"
          :disabled="submitting || closeGuardPending"
          @click="handleDialogOpenChange(false)"
        >
          取消
        </Button>
        <Button
          type="submit"
          form="opportunity-lose-form"
          class="opportunity-lose-dialog__button"
          :disabled="submitting || loading || loadError !== null || closeGuardPending"
          :loading="submitting"
        >
          {{ submitting ? '提交中...' : '确认标记输单' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunity-lose-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  max-height: $wolf-modal-height-mobile-v2;
  overflow: hidden;
}

.opportunity-lose-dialog__body {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-inline: calc($wolf-focus-ring-width-v2 + $wolf-focus-ring-offset-v2);
  scroll-padding-bottom: calc($wolf-space-xl-v2 + $wolf-safe-area-bottom-v2);
}

.opportunity-lose-dialog__form {
  display: flex;
  flex-direction: column;
  gap: $wolf-form-item-gap-v2;
}

.opportunity-lose-dialog__feedback {
  min-width: 0;
}

.opportunity-lose-dialog__footer {
  gap: $wolf-space-sm-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-divider-v2;
}

.opportunity-lose-dialog__button {
  height: $wolf-button-height-md-v2;
  min-height: $wolf-button-height-md-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .opportunity-lose-dialog__button {
    width: 100%;
    height: $wolf-button-height-mobile-v2;
    min-height: $wolf-button-height-mobile-v2;
  }
}
</style>
