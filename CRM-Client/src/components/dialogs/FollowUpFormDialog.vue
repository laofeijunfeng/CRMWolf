<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useForm, useField } from 'vee-validate'
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
  SegmentedChoiceControl,
  TextareaField,
} from '@/components/crmwolf'
import FormErrorSummary from '@/components/crmwolf/FormErrorSummary.vue'
import customerActivityApi, { type CustomerActivityCreate } from '@/api/customerActivity'
import { formatLocalDate } from '@/utils/format'
import { useDialogCloseGuard } from '@/composables/useDialogCloseGuard'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    method: z.string().min(1, '请选择活动类型'),
    content: z.string().min(1, '请输入活动内容').max(20000, '内容不能超过20000字'),
    next_follow_time: z.string().optional(),
    next_action: z.string().max(200, '动作不能超过200字').optional()
  })
)

interface Props {
  customerId: string
  open: boolean
  sourceTaskPublicId?: string | null
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success', completedTaskPublicId: string | null): void
}

type SubmitMode = 'activity' | 'activity_and_complete_tracking'

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// VeeValidate form setup
const { handleSubmit, resetForm, meta, errors } = useForm({
  validationSchema: schema,
  initialValues: {
    method: '',
    content: '',
    next_follow_time: '',
    next_action: ''
  }
})

// Use useField for RadioGroup to handle type compatibility
const { value: methodValue, errorMessage: methodError } = useField<string>('method')

// State
const submittingMode = ref<SubmitMode | null>(null)

// Computed property for dialog visibility
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})
const submitting = computed(() => submittingMode.value !== null)
const isDirty = computed(() => meta.value.dirty)
const closeGuard = useDialogCloseGuard({
  isDirty,
  submitting,
  emitOpen: (open) => emit('update:open', open),
})
const showConfirmDialog = closeGuard.showConfirmDialog
const canSubmitAndCompleteTracking = computed(() => {
  const taskPublicId = props.sourceTaskPublicId
  return taskPublicId !== null && taskPublicId !== undefined && taskPublicId.trim().length > 0
})

const validationErrorItems = computed(() => [
  { field: 'method', label: '活动类型', message: errors.value.method ?? '', targetId: 'follow-up-method-PHONE_FOLLOW_UP' },
  { field: 'content', label: '活动内容', message: errors.value.content ?? '', targetId: 'follow-up-content' },
  { field: 'next_follow_time', label: '下次跟进时间', message: errors.value.next_follow_time ?? '', targetId: 'follow-up-next-time' },
  { field: 'next_action', label: '下一步动作', message: errors.value.next_action ?? '', targetId: 'follow-up-next-action' },
].filter((item): item is { field: string; label: string; message: string; targetId: string } => item.message.length > 0))

async function focusFirstError(): Promise<void> {
  await nextTick()
  const firstError = validationErrorItems.value[0]
  if (firstError === undefined || typeof document === 'undefined') return

  const target = document.getElementById(firstError.targetId)
  if (!(target instanceof HTMLElement)) return
  target.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  target.focus({ preventScroll: true })
}

// Follow-up method options
const methodOptions: { value: string; label: string }[] = [
  { value: 'PHONE_FOLLOW_UP', label: '电话' },
  { value: 'WECHAT_FOLLOW_UP', label: '微信' },
  { value: 'VISIT_FOLLOW_UP', label: '拜访' },
  { value: 'EMAIL_FOLLOW_UP', label: '邮件' },
  { value: 'ONLINE_MEETING', label: '线上会议' },
  { value: 'OFFLINE_MEETING', label: '线下会议' },
  { value: 'OTHER_FOLLOW_UP', label: '其他' }
]

// Reset form when dialog opens
watch(() => props.open, (newOpen) => {
  if (!newOpen) {
    if (closeGuard.handleParentClose()) return
    closeGuard.reset()
    return
  }

  if (newOpen) {
    resetForm({
      values: {
        method: '',
        content: '',
        next_follow_time: '',
        next_action: ''
      }
    })
    closeGuard.reset()
  }
})

function handleNextFollowTimeChange(
  handleChange: (value: string) => void,
  date: Date | null
): void {
  handleChange(date ? formatLocalDate(date) : '')
}

function toOptionalText(value: string | undefined): string | null {
  const normalizedValue = value?.trim()
  return normalizedValue === undefined || normalizedValue.length === 0 ? null : normalizedValue
}

function activityPayload(formValues: Record<string, string | undefined>): CustomerActivityCreate {
  const nextFollowTime = toOptionalText(formValues['next_follow_time'])
  const nextAction = toOptionalText(formValues['next_action'])

  return {
    activity_kind: formValues['method'] ?? '',
    source_content: formValues['content'] ?? '',
    next_follow_time: nextFollowTime,
    next_follow_time_source: nextFollowTime === null ? null : 'USER' as const,
    next_action: nextAction,
  }
}

async function submitActivity(
  formValues: Record<string, string | undefined>,
  mode: SubmitMode,
): Promise<void> {
  const activity = activityPayload(formValues)
  submittingMode.value = mode
  try {
    if (mode === 'activity_and_complete_tracking') {
      const taskPublicId = props.sourceTaskPublicId
      if (taskPublicId === null || taskPublicId === undefined || taskPublicId.trim().length === 0) {
        throw new Error('缺少要完成的追踪任务')
      }
      await customerActivityApi.createActivityAndCompleteTracking(props.customerId, taskPublicId, activity)
      toast.success('客户活动已添加，追踪已完成')
      emit('success', taskPublicId)
    } else {
      await customerActivityApi.createActivity(props.customerId, activity)
      toast.success('客户活动添加成功')
      emit('success', null)
    }
    closeGuard.approveClose()
    visible.value = false
  } catch {
    toast.error(mode === 'activity_and_complete_tracking' ? '提交并完成追踪失败' : '添加客户活动失败')
  } finally {
    submittingMode.value = null
  }
}

const onInvalidSubmit = (): void => {
  void focusFirstError()
}

const onSubmit = handleSubmit(
  async (formValues) => submitActivity(formValues, 'activity'),
  onInvalidSubmit
)
const submitAndCompleteTracking = handleSubmit(
  async (formValues) => submitActivity(formValues, 'activity_and_complete_tracking'),
  onInvalidSubmit
)

// Cancel operation
function handleCancel(): void {
  closeGuard.requestClose()
}

// Confirm discard changes
function confirmCancel(): void {
  closeGuard.confirmDiscard()
}

// Continue editing
function continueEditing(): void {
  closeGuard.continueEditing()
}

function handleOpenChange(open: boolean): void {
  closeGuard.handleOpenChange(open)
}
</script>

<template>
  <Dialog :open="props.open" @update:open="handleOpenChange">
    <DialogContent class="w-[calc(100vw-2rem)] max-h-[min(90vh,90dvh)] overflow-y-auto overscroll-contain [scroll-padding-bottom:calc(5rem+env(safe-area-inset-bottom,0px))]">
      <DialogHeader>
        <DialogTitle>添加客户活动</DialogTitle>
        <DialogDescription class="sr-only">记录本次客户活动的详细信息</DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <FormErrorSummary :items="validationErrorItems" />

        <!-- Follow-up Method (RadioGroup) -->
        <div class="space-y-2">
          <p id="follow-up-method-label" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
            活动类型 <span class="text-wolf-danger" aria-hidden="true">*</span>
          </p>
          <SegmentedChoiceControl
            v-model="methodValue"
            :options="methodOptions"
            labelled-by="follow-up-method-label"
            id-prefix="follow-up-method"
            :invalid="Boolean(methodError)"
            described-by="follow-up-method-error"
            style="--segmented-choice-columns: 4;"
          />
          <p v-if="methodError" id="follow-up-method-error" class="text-sm text-destructive" role="alert">{{ methodError }}</p>
        </div>

        <!-- Follow-up Content (Textarea, required) -->
        <FormField v-slot="{ value, handleChange }" name="content">
          <FormItem>
            <TextareaField
              id="follow-up-content"
              :model-value="String(value ?? '')"
              label="活动内容"
              required
              :rows="6"
              placeholder="可直接粘贴跟进内容或完整会议纪要"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Next Follow-up Time -->
        <FormField v-slot="{ value, handleChange }" name="next_follow_time">
          <FormItem>
            <DateField
              id="follow-up-next-time"
              :model-value="value ? new Date(value as string) : null"
              label="下次跟进时间（可选）"
              placeholder="如有下一步安排，请选择时间"
              @update:model-value="(date: Date | null) => handleNextFollowTimeChange(handleChange, date)"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- Next Action (Textarea) -->
        <FormField v-slot="{ value, handleChange }" name="next_action">
          <FormItem>
            <TextareaField
              id="follow-up-next-action"
              :model-value="String(value ?? '')"
              label="下一步动作（可选）"
              :rows="3"
              placeholder="请输入下一步动作"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- DialogFooter -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" :disabled="submittingMode !== null" @click="handleCancel">
            取消
          </Button>
          <Button
            variant="outline"
            type="submit"
            :loading="submittingMode === 'activity'"
            :disabled="submittingMode !== null"
          >
            提交
          </Button>
          <Button
            v-if="canSubmitAndCompleteTracking"
            type="button"
            :loading="submittingMode === 'activity_and_complete_tracking'"
            :disabled="submittingMode !== null"
            @click="submitAndCompleteTracking"
          >
            提交并完成追踪
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
