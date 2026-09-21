import { BlobPartResponseSchema } from '@/schemas/common'
import request from '@/utils/request'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'

export interface ListExportPayload<TTab extends string> {
  fields: string[]
  tab: TTab
  search?: string
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
}

/**
 * 提交列表导出请求；仅导出请求覆盖 Axios 默认 30 秒超时（timeout: 0）。
 */
export async function postListExport<TTab extends string>(
  path: string,
  payload: ListExportPayload<TTab>,
): Promise<Blob> {
  const response = BlobPartResponseSchema.parse(await request.post<unknown>(path, payload, {
    responseType: 'blob',
    timeout: 0,
  }))
  return response instanceof Blob ? response : new Blob([response])
}
