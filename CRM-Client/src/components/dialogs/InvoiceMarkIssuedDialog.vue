<script setup lang="ts">
/**
 * InvoiceMarkIssuedDialog.vue - 发票开票对话框
 *
 * 审批通过后，上传发票文件和填写发票号码。
 * 使用 vee-validate + Zod 进行表单校验。
 */
import { ref, computed, watch, onUnmounted } from 'vue'
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
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FileAttachment } from '@/components/crmwolf'
import invoiceApi from '@/api/invoice'
import { handleApiError } from '@/utils/errorHandler'
import type { FileAttachmentItem } from '@/types/fileAttachment'

// Constants
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

// Zod schema for form validation
const schema = toTypedSchema(
  z.object({
    invoice_number: z.string().optional()
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
const { handleSubmit } = useForm({
  validationSchema: schema,
  initialValues: {
    invoice_number: ''
  }
})

// State
const submitting = ref(false)
const selectedFile = ref<File | null>(null)
const fileError = ref<string | null>(null)
const selectedFileUrl = ref<string>('')

// File info for display
const selectedFileItems = computed<FileAttachmentItem[]>(() => {
  if (selectedFile.value === null) return []
  const file = selectedFile.value
  const item: FileAttachmentItem = {
    id: file.name,
    name: file.name,
    size: file.size,
    mimeType: file.type,
    extension: getFileExtension(file.name),
    status: 'idle'
  }
  if (selectedFileUrl.value) {
    item.url = selectedFileUrl.value
  }
  return [item]
})

const getFileExtension = (fileName: string): string => {
  return fileName.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const revokeSelectedFileUrl = (): void => {
  if (selectedFileUrl.value) {
    window.URL.revokeObjectURL(selectedFileUrl.value)
    selectedFileUrl.value = ''
  }
}

const handleFileUpload = (files: File[]): void => {
  const file = files[0]
  if (!file) return
  fileError.value = null
  revokeSelectedFileUrl()
  selectedFile.value = file
  selectedFileUrl.value = window.URL.createObjectURL(file)
}

const removeFile = (): void => {
  selectedFile.value = null
  fileError.value = null
  revokeSelectedFileUrl()
}

const handleFileError = (message: string): void => {
  removeFile()
  fileError.value = message
}

// Form submission
const onSubmit = handleSubmit(async (formValues) => {
  submitting.value = true

  try {
    const invoiceNumber = formValues.invoice_number?.trim()
    // Build payload conditionally to satisfy exactOptionalPropertyTypes
    const payload: { file?: File; invoice_number?: string } = {}
    if (selectedFile.value !== null) {
      payload.file = selectedFile.value
    }
    if (invoiceNumber !== undefined && invoiceNumber !== '') {
      payload.invoice_number = invoiceNumber
    }
    await invoiceApi.markIssued(props.applicationId, payload)

    toast.success('已开票，发票文件已上传')
    emit('issued')
    emit('update:open', false)
  } catch (error) {
    handleApiError(error, '开票')
  } finally {
    submitting.value = false
  }
})

// Reset state when dialog closes
const handleDialogClose = (open: boolean): void => {
  if (!open) {
    // Reset form state
    removeFile()
  }
  emit('update:open', open)
}

watch(
  (): boolean => props.open,
  (open): void => {
    if (!open) {
      removeFile()
    }
  }
)

onUnmounted(() => {
  revokeSelectedFileUrl()
})
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogClose">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>开票</DialogTitle>
        <DialogDescription>上传发票文件和填写发票号码（均为可选）</DialogDescription>
      </DialogHeader>

      <form class="grid gap-4 py-4" @submit="onSubmit">
        <FileAttachment
          title="发票文件"
          description="支持 PDF、JPG、PNG、OFD，最大 10MB"
          mode="manage"
          accept=".pdf,.jpg,.jpeg,.png,.ofd"
          :max-size-mb="MAX_FILE_SIZE / 1024 / 1024"
          :files="selectedFileItems"
          :multiple="false"
          :disabled="submitting"
          :allow-download="false"
          empty-text="暂无发票文件"
          @upload="handleFileUpload"
          @remove="removeFile"
          @error="handleFileError"
        />
        <p v-if="fileError" class="text-sm text-destructive" role="alert">{{ fileError }}</p>

        <!-- 发票号码 -->
        <FormField v-slot="{ componentField }" name="invoice_number">
          <FormItem>
            <FormLabel>发票号码</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as any"
                type="text"
                placeholder="请输入发票号码（可选）"
                :disabled="submitting"
              />
            </FormControl>
            <FormMessage />
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
          {{ submitting ? '提交中...' : '确认开票' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
