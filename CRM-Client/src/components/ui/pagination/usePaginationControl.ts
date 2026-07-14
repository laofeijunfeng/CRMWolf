import { computed, inject, type ComputedRef } from 'vue'
import { localPaginationContextKey, type LocalPaginationContext } from './context'

export type PaginationElement = 'button' | 'a'

export interface PaginationControlState {
  pagination: LocalPaginationContext
  disabled: ComputedRef<boolean>
}

export interface PaginationElementState {
  nativeDisabled: ComputedRef<boolean | undefined>
  ariaDisabled: ComputedRef<'true' | undefined>
  tabIndex: ComputedRef<number | undefined>
  buttonType: ComputedRef<'button' | undefined>
}

export type SafePaginationAttrs = Record<string, unknown>

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

export const usePaginationElement = (
  as: ComputedRef<PaginationElement>,
  disabled: ComputedRef<boolean>
): PaginationElementState => {
  const isButton = computed<boolean>(() => as.value === 'button')

  return {
    nativeDisabled: computed<boolean | undefined>(() =>
      isButton.value ? disabled.value : undefined
    ),
    ariaDisabled: computed<'true' | undefined>(() =>
      !isButton.value && disabled.value ? 'true' : undefined
    ),
    tabIndex: computed<number | undefined>(() =>
      !isButton.value && disabled.value ? -1 : undefined
    ),
    buttonType: computed<'button' | undefined>(() =>
      isButton.value ? 'button' : undefined
    )
  }
}

export const filterSafePaginationAttrs = (
  attrs: Readonly<Record<string, unknown>>
): SafePaginationAttrs => Object.fromEntries(
  Object.entries(attrs).filter(([key]) => key === 'id' || key.startsWith('data-'))
)

export const guardPaginationInteraction = (
  event: MouseEvent,
  disabled: boolean
): boolean => {
  if (!disabled) return true
  event.preventDefault()
  event.stopPropagation()
  return false
}
