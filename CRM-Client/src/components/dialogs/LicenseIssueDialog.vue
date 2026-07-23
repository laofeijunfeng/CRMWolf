<script setup lang="ts">
/**
 * LicenseIssueDialog.vue - License 发放表单弹窗
 *
 * 收集 License 信息和备注，遵循无障碍和动效规范。
 * 使用 vee-validate + Zod 进行表单校验。
 */
import { ref, watch } from 'vue'
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
  DialogFooter
} from '@/components/ui/dialog'
import {
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { TextareaField } from '@/components/crmwolf'
import { handleApiError } from '@/utils/errorHandler'
import licenseApplicationApi from '@/api/licenseApplication'

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
const { handleSubmit, setFieldValue } = useForm({
  validationSchema: schema,
  initialValues: {
    license_info: '',
    comment: ''
  }
})

// State
const submitting = ref(false)

// Watch for dialog open to reset form
watch(() => props.open, (newOpen) => {
  if (newOpen) {
    setFieldValue('license_info', '')
    setFieldValue('comment', '')
  }
})

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
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
    handleApiError(error, '发放 License')
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <Dialog :open="props.open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-[525px] max-w-full">
      <DialogHeader>
        <DialogTitle>发放 License</DialogTitle>
        <DialogDescription>请输入 License 信息完成发放</DialogDescription>
      </DialogHeader>

      <form class="grid gap-4 py-4" @submit="onSubmit">
        <!-- License 信息 -->
        <FormField v-slot="{ value, handleChange }" name="license_info">
          <FormItem>
            <TextareaField
              id="license-issue-info"
              :model-value="String(value ?? '')"
              label="License 信息"
              required
              :rows="8"
              placeholder="请输入 License 信息"
              :disabled="submitting"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <div class="flex justify-between items-center">
              <FormMessage />
              <span class="text-xs text-muted-foreground ml-auto">
                {{ (value as string)?.length || 0 }} / 10000
              </span>
            </div>
          </FormItem>
        </FormField>

        <!-- 备注 -->
        <FormField v-slot="{ value, handleChange }" name="comment">
          <FormItem>
            <TextareaField
              id="license-issue-comment"
              :model-value="String(value ?? '')"
              label="备注"
              :rows="3"
              placeholder="请输入备注（可选）"
              :disabled="submitting"
              control-class="resize-none"
              @update:model-value="handleChange"
            />
            <div class="flex justify-between items-center">
              <FormMessage />
              <span class="text-xs text-muted-foreground ml-auto">
                {{ (value as string)?.length || 0 }} / 500
              </span>
            </div>
          </FormItem>
        </FormField>
      </form>

      <DialogFooter class="flex-col gap-2 sm:flex-row">
        <Button
          variant="outline"
          :disabled="submitting"
          class="w-full sm:w-auto"
          @click="emit('update:open', false)"
        >
          取消
        </Button>
        <Button
          type="submit"
          :disabled="submitting"
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
