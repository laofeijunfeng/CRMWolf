import { ref, type Ref } from 'vue'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import { downloadBlob } from '@/utils/downloadBlob'

export interface UseDataTableExportOptions {
  request: (fields: string[]) => Promise<Blob>
  fileName: () => string
  successMessage?: string
  download?: (blob: Blob, fileName: string) => void
}

export interface DataTableExport {
  exporting: Readonly<Ref<boolean>>
  exportFields: (fields: string[]) => Promise<void>
}

export function useDataTableExport(options: UseDataTableExportOptions): DataTableExport {
  const exporting = ref(false)

  async function exportFields(fields: string[]): Promise<void> {
    if (exporting.value) return
    exporting.value = true
    try {
      const blob = await options.request(fields)
      const download = options.download ?? downloadBlob
      download(blob, options.fileName())
      toast.success(options.successMessage ?? '导出完成')
    } catch (error) {
      handleApiError(error, '导出 Excel')
      // 重新抛出让 DataTableExportDialog 保留弹窗和已选字段。
      throw error
    } finally {
      exporting.value = false
    }
  }

  return { exporting, exportFields }
}
