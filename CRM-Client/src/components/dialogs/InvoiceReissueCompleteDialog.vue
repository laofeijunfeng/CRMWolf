<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
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
import { FileAttachment, InputField } from '@/components/crmwolf'
import invoiceApi from '@/api/invoice'
import { handleApiError } from '@/utils/errorHandler'
import type { FileAttachmentItem } from '@/types/fileAttachment'

const MAX_FILE_SIZE = 10 * 1024 * 1024

interface Props {
  open: boolean
  reissueId: number
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'completed'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const submitting = ref(false)
const redInvoiceNumber = ref('')
const newInvoiceNumber = ref('')
const redFile = ref<File | null>(null)
const newFile = ref<File | null>(null)
const redFileError = ref<string | null>(null)
const newFileError = ref<string | null>(null)
const redFileUrl = ref('')
const newFileUrl = ref('')

const getFileExtension = (fileName: string): string => {
  return fileName.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const buildFileItem = (file: File, url: string): FileAttachmentItem => ({
  id: file.name,
  name: file.name,
  size: file.size,
  mimeType: file.type,
  extension: getFileExtension(file.name),
  status: 'idle',
  ...(url.length > 0 ? { url } : {})
})

const redFileItems = computed<FileAttachmentItem[]>(() =>
  redFile.value === null ? [] : [buildFileItem(redFile.value, redFileUrl.value)]
)

const newFileItems = computed<FileAttachmentItem[]>(() =>
  newFile.value === null ? [] : [buildFileItem(newFile.value, newFileUrl.value)]
)

const revokeFileUrl = (kind: 'red' | 'new'): void => {
  const url = kind === 'red' ? redFileUrl.value : newFileUrl.value
  if (url.length === 0) return
  window.URL.revokeObjectURL(url)
  if (kind === 'red') {
    redFileUrl.value = ''
  } else {
    newFileUrl.value = ''
  }
}

const setFile = (kind: 'red' | 'new', file: File | null): void => {
  revokeFileUrl(kind)
  if (kind === 'red') {
    redFile.value = file
    redFileError.value = null
    redFileUrl.value = file === null ? '' : window.URL.createObjectURL(file)
  } else {
    newFile.value = file
    newFileError.value = null
    newFileUrl.value = file === null ? '' : window.URL.createObjectURL(file)
  }
}

const handleUpload = (kind: 'red' | 'new', files: File[]): void => {
  setFile(kind, files[0] ?? null)
}

const handleError = (kind: 'red' | 'new', message: string): void => {
  setFile(kind, null)
  if (kind === 'red') {
    redFileError.value = message
  } else {
    newFileError.value = message
  }
}

const reset = (): void => {
  redInvoiceNumber.value = ''
  newInvoiceNumber.value = ''
  setFile('red', null)
  setFile('new', null)
  redFileError.value = null
  newFileError.value = null
}

const handleDialogOpenChange = (open: boolean): void => {
  if (!open) reset()
  emit('update:open', open)
}

const submit = async (): Promise<void> => {
  if (redFile.value === null || newFile.value === null) {
    toast.warning('请上传红字发票和新发票文件')
    return
  }

  submitting.value = true
  try {
    await invoiceApi.completeInvoiceReissue(props.reissueId, {
      red_file: redFile.value,
      new_file: newFile.value,
      red_invoice_number: redInvoiceNumber.value,
      new_invoice_number: newInvoiceNumber.value
    })
    toast.success('发票重开已完成')
    emit('completed')
    emit('update:open', false)
    reset()
  } catch (error) {
    handleApiError(error, '完成发票重开')
  } finally {
    submitting.value = false
  }
}

watch(
  (): boolean => props.open,
  (open): void => {
    if (!open) reset()
  }
)

onUnmounted(() => {
  revokeFileUrl('red')
  revokeFileUrl('new')
})
</script>

<template>
  <Dialog :open="props.open" @update:open="handleDialogOpenChange">
    <DialogContent class="sm:max-w-[520px] max-w-full">
      <DialogHeader>
        <DialogTitle>上传重开发票</DialogTitle>
        <DialogDescription>上传红字发票和新蓝字发票，发票号码可选。</DialogDescription>
      </DialogHeader>

      <div class="grid gap-4 py-4">
        <InputField
          id="approval-red-invoice-number"
          v-model="redInvoiceNumber"
          label="红字发票号码"
          type="text"
          placeholder="请输入红字发票号码（可选）"
          :disabled="submitting"
        />

        <FileAttachment
          title="红字发票文件"
          description="支持 PDF、JPG、PNG、OFD，最大 10MB"
          mode="manage"
          accept=".pdf,.jpg,.jpeg,.png,.ofd"
          :max-size-mb="MAX_FILE_SIZE / 1024 / 1024"
          :files="redFileItems"
          :multiple="false"
          :required="true"
          :disabled="submitting"
          :allow-download="false"
          empty-text="暂无红字发票文件"
          @upload="handleUpload('red', $event)"
          @remove="setFile('red', null)"
          @error="handleError('red', $event)"
        />
        <p v-if="redFileError" class="text-sm text-destructive" role="alert">{{ redFileError }}</p>

        <InputField
          id="approval-new-invoice-number"
          v-model="newInvoiceNumber"
          label="新发票号码"
          type="text"
          placeholder="请输入新发票号码（可选）"
          :disabled="submitting"
        />

        <FileAttachment
          title="新发票文件"
          description="支持 PDF、JPG、PNG、OFD，最大 10MB"
          mode="manage"
          accept=".pdf,.jpg,.jpeg,.png,.ofd"
          :max-size-mb="MAX_FILE_SIZE / 1024 / 1024"
          :files="newFileItems"
          :multiple="false"
          :required="true"
          :disabled="submitting"
          :allow-download="false"
          empty-text="暂无新发票文件"
          @upload="handleUpload('new', $event)"
          @remove="setFile('new', null)"
          @error="handleError('new', $event)"
        />
        <p v-if="newFileError" class="text-sm text-destructive" role="alert">{{ newFileError }}</p>
      </div>

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
          :disabled="submitting"
          :loading="submitting"
          class="w-full sm:w-auto"
          @click="submit"
        >
          {{ submitting ? '提交中...' : '确认完成重开' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
