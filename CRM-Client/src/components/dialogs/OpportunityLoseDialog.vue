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
import { confirmDialog } from '@/utils/confirmDialog'
import { handleApiError } from '@/utils/errorHandler'
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
    handleApiError(error, '加载商机详情')
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
    handleApiError(error, '标记输单')
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogOpenChange">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>标记输单</DialogTitle>
        <DialogDescription>确认输单原因后，商机状态将变更为“已输单”。</DialogDescription>
      </DialogHeader>

      <div
        v-if="loadError"
        class="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm"
        role="alert"
        aria-live="assertive"
      >
        <strong class="block">{{ loadError.title }}</strong>
        <span class="text-muted-foreground">{{ loadError.description }}</span>
        <Button
          v-if="loadError.retryable !== false"
          type="button"
          variant="outline"
          size="sm"
          class="mt-3"
          :disabled="loading"
          @click="retryLoad"
        >
          {{ loading ? '加载中...' : '重新加载商机信息' }}
        </Button>
      </div>

      <div
        v-if="submitError"
        class="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm"
        role="alert"
        aria-live="assertive"
      >
        <strong class="block">{{ submitError.title }}</strong>
        <span class="text-muted-foreground">{{ submitError.description }}</span>
        <span v-if="submitError.outcomeUnknown" class="mt-1 block text-muted-foreground">
          请先刷新商机状态，确认尚未标记为输单后再重试，避免重复操作。
        </span>
      </div>

      <div v-if="opportunity" class="rounded-md border bg-muted/30 p-3 text-sm" aria-label="输单操作上下文">
        <div class="grid gap-2 sm:grid-cols-2">
          <div>
            <div class="text-muted-foreground">商机</div>
            <div class="font-medium break-words">{{ opportunity.opportunity_name }}</div>
          </div>
          <div>
            <div class="text-muted-foreground">客户</div>
            <div class="font-medium break-words">{{ customerName }}</div>
          </div>
          <div>
            <div class="text-muted-foreground">当前状态</div>
            <div class="font-medium">{{ currentStatusLabel }}</div>
          </div>
          <div>
            <div class="text-muted-foreground">提交后状态</div>
            <div class="font-medium text-destructive">已输单</div>
          </div>
        </div>
      </div>

      <div v-if="loading" class="py-8 text-center text-muted-foreground" role="status">
        加载商机信息中...
      </div>

      <form v-else-if="!loadError" class="grid gap-4 py-4" @submit="onSubmit">
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
              :disabled="submitting"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>
      </form>

      <DialogFooter class="flex-col gap-2 sm:flex-row">
        <Button
          variant="outline"
          :disabled="submitting || closeGuardPending"
          class="w-full sm:w-auto"
          @click="handleDialogOpenChange(false)"
        >
          取消
        </Button>
        <Button
          type="submit"
          :disabled="submitting || loading || loadError !== null || closeGuardPending"
          :loading="submitting"
          class="w-full sm:w-auto"
          @click="onSubmit"
        >
          {{ submitting ? '提交中...' : '确认标记输单' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
