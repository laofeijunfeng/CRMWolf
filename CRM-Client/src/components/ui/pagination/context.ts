import type { InjectionKey, Ref } from 'vue'

export interface LocalPaginationContext {
  page: Ref<number>
  pageCount: Ref<number>
  disabled: Ref<boolean>
  onPageChange: (value: number) => void
}

export const localPaginationContextKey: InjectionKey<LocalPaginationContext> = Symbol('local-pagination-context')
