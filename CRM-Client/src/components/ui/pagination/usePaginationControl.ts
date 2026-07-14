import { computed, inject, type ComputedRef } from 'vue'
import { localPaginationContextKey, type LocalPaginationContext } from './context'

export interface PaginationControlState {
  pagination: LocalPaginationContext
  disabled: ComputedRef<boolean>
}

export const usePaginationControl = (
  controlName: string,
  isDisabled: (context: LocalPaginationContext) => boolean
): PaginationControlState => {
  const pagination = inject(localPaginationContextKey)
  if (pagination === undefined) {
    throw new Error(`${controlName} must be used within Pagination`)
  }

  return {
    pagination,
    disabled: computed<boolean>(() => pagination.disabled.value || isDisabled(pagination))
  }
}
