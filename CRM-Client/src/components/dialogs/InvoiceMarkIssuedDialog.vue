<script setup lang="ts">
/**
 * InvoiceMarkIssuedDialog.vue - 发票开票对话框
 *
 * 审批通过后，上传发票文件和填写发票号码。
 * 使用 vee-validate + Zod 进行表单校验。
 */
import { ref, computed } from 'vue'
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
import { Alert, AlertDescription } from '@/components/ui/alert'
import invoiceApi from '@/api/invoice'
import { handleApiError } from '@/utils/errorHandler'

// Constants
const ALLOWED_FILE_TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'application/ofd']
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const FILE_TYPE_NAMES: Record<string, string> = {
  'application/pdf': 'PDF',
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'application/ofd': 'OFD'
}

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

// File info for display
const fileInfo = computed(() => {
  if (selectedFile.value === null) return null
  const file = selectedFile.value
  const sizeInMB = (file.size / (1024 * 1024)).toFixed(2)
  const typeName = FILE_TYPE_NAMES[file.type] ?? file.type.split('/')[1]?.toUpperCase() ?? '文件'
  return {
    name: file.name,
    size: `${sizeInMB} MB`,
    type: typeName
  }
})

// File validation
const validateFile = (file: File): string | null => {
  if (!ALLOWED_FILE_TYPES.includes(file.type)) {
    return `不支持的文件类型：${file.type}。仅支持 PDF、JPG、PNG、OFD 格式`
  }
  if (file.size > MAX_FILE_SIZE) {
    const sizeInMB = (file.size / (1024 * 1024)).toFixed(2)
    return `文件大小超出限制：${sizeInMB}MB，最大支持 10MB`
  }
  return null
}

// Handle file selection
const handleFileSelect = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]

  // Reset error
  fileError.value = null

  if (file === undefined || file === null) {
    selectedFile.value = null
    return
  }

  const error = validateFile(file)
  if (error !== null) {
    fileError.value = error
    selectedFile.value = null
    // Reset input
    target.value = ''
  } else {
    selectedFile.value = file
  }
}

// Remove selected file
const removeFile = (): void => {
  selectedFile.value = null
  fileError.value = null
  // Reset file input
  const fileInput = document.getElementById('invoice-file-input') as HTMLInputElement | null
  if (fileInput !== null) {
    fileInput.value = ''
  }
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
    selectedFile.value = null
    fileError.value = null
  }
  emit('update:open', open)
}
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogClose">
    <DialogContent class="sm:max-w-[425px] max-w-full">
      <DialogHeader>
        <DialogTitle>开票</DialogTitle>
        <DialogDescription>上传发票文件和填写发票号码（均为可选）</DialogDescription>
      </DialogHeader>

      <form class="grid gap-4 py-4" @submit="onSubmit">
        <!-- 文件上传 -->
        <div class="space-y-2">
          <label class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
            发票文件
          </label>

          <!-- 已选文件显示 -->
          <div
            v-if="fileInfo"
            class="flex items-center gap-3 p-3 rounded-md border bg-muted/50"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium truncate">{{ fileInfo.name }}</p>
              <p class="text-xs text-muted-foreground">{{ fileInfo.type }} · {{ fileInfo.size }}</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              class="shrink-0 h-8 w-8 p-0"
              :disabled="submitting"
              @click="removeFile"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              <span class="sr-only">移除文件</span>
            </Button>
          </div>

          <!-- 文件选择按钮 -->
          <div v-else>
            <label
              for="invoice-file-input"
              class="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-md cursor-pointer hover:bg-muted/50 transition-colors"
              :class="{ 'opacity-50 cursor-not-allowed': submitting }"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="text-muted-foreground mb-2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span class="text-sm text-muted-foreground">点击上传发票文件</span>
              <span class="text-xs text-muted-foreground mt-1">支持 PDF、JPG、PNG、OFD，最大 10MB</span>
            </label>
            <input
              id="invoice-file-input"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.ofd"
              class="hidden"
              :disabled="submitting"
              @change="handleFileSelect"
            />
          </div>

          <!-- 文件错误提示 -->
          <Alert v-if="fileError" variant="destructive" class="mt-2">
            <AlertDescription>{{ fileError }}</AlertDescription>
          </Alert>
        </div>

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