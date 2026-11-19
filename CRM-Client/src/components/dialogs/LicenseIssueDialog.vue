<script setup lang="ts">
/**
 * LicenseIssueDialog.vue - License 发放表单弹窗
 *
 * 收集 License 信息和备注，遵循无障碍和动效规范。
 * 使用 vee-validate + Zod 进行表单校验。
 */
import { computed, ref, watch } from 'vue'
import { Field, useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { TextareaField } from '@/components/crmwolf'
import { confirmDiscardChanges } from '@/utils/confirmDialog'
import { handleApiError } from '@/utils/errorHandler'
import licenseApplicationApi from '@/api/licenseApplication'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    license_info: z
      .string()
      .min(1, '请输入 License 信息')
      .max(10000, 'License 信息不能超过10000个字符'),
    comment: z
      .string()
      .max(500, '备注不能超过500个字符')
      .optional()
  })
)

interface Props {
  elevated?: boolean
  open: boolean
  applicationId: number
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'issued'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// VeeValidate form setup
const { handleSubmit, resetForm, setFieldValue, values } = useForm({
  validationSchema: schema,
  initialValues: {
    license_info: '',
    comment: ''
  }
})

// State
const submitting = ref(false)
const closeGuardPending = ref(false)
const submitError = ref<FeedbackError | null>(null)

const hasFormChanges = computed(() =>
  String(values.license_info ?? '').trim().length > 0
  || String(values.comment ?? '').trim().length > 0,
)

// Watch for dialog open to reset form
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    submitError.value = null
    resetForm({ values: { license_info: '', comment: '' } })
    setFieldValue('license_info', '')
    setFieldValue('comment', '')
  }
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
    const confirmed = await confirmDiscardChanges('close')
    if (confirmed) emit('update:open', false)
  } finally {
    closeGuardPending.value = false
  }
}

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitError.value = null
  submitting.value = true
  try {
    // Build payload conditionally to satisfy exactOptionalPropertyTypes
    const payload: { license_info: string; comment?: string } = {
      license_info: formValues.license_info.trim()
    }
    const comment = formValues.comment?.trim()
    if (comment !== undefined && comment !== '') {
      payload.comment = comment
    }
    await licenseApplicationApi.issueLicense(props.applicationId, payload)

    toast.success('已发放 License，License 信息已写入')
    emit('issued')
    emit('update:open', false)
  } catch (error) {
    submitError.value = toFeedbackError(error, '发放 License', { operation: 'write' })
    handleApiError(error, '发放 License')
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogOpenChange">
    <DialogContent v-bind="elevated ? { elevated: true } : {}">
      <DialogHeader>
        <DialogTitle>发放 License</DialogTitle>
        <DialogDescription>请输入 License 信息完成发放</DialogDescription>
      </DialogHeader>

      <div
        v-if="submitError"
        class="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm"
        role="alert"
        aria-live="assertive"
      >
        <strong class="block">{{ submitError.title }}</strong>
        <span class="text-muted-foreground">{{ submitError.description }}</span>
        <span v-if="submitError.outcomeUnknown" class="mt-1 block text-muted-foreground">
          请先查询申请的最新状态，确认尚未发放后再重试，避免重复操作。
        </span>
      </div>

      <form class="grid gap-4 py-4" @submit="onSubmit">
        <!-- License 信息 -->
        <Field v-slot="{ value, handleChange, errorMessage }" name="license_info">
          <div class="grid gap-space-1">
            <TextareaField
              id="license-issue-info"
              :model-value="String(value ?? '')"
              label="License 信息"
              required
              :rows="8"
              placeholder="请输入 License 信息"
              :disabled="submitting || closeGuardPending"
              :error="errorMessage ?? ''"
              maxlength="10000"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <span class="text-xs text-muted-foreground ml-auto">
              {{ (value as string)?.length || 0 }} / 10000
            </span>
          </div>
        </Field>

        <!-- 备注 -->
        <Field v-slot="{ value, handleChange, errorMessage }" name="comment">
          <div class="grid gap-space-1">
            <TextareaField
              id="license-issue-comment"
              :model-value="String(value ?? '')"
              label="备注"
              :rows="3"
              placeholder="请输入备注（可选）"
              :disabled="submitting || closeGuardPending"
              :error="errorMessage ?? ''"
              maxlength="500"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <span class="text-xs text-muted-foreground ml-auto">
              {{ (value as string)?.length || 0 }} / 500
            </span>
          </div>
        </Field>
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
          :disabled="submitting || closeGuardPending"
          :loading="submitting"
          class="w-full sm:w-auto"
          @click="onSubmit"
        >
          {{ submitting ? '提交中...' : '确认发放' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
