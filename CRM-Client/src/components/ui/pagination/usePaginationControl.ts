import { computed, inject, type ComputedRef } from 'vue'
import type { PrimitiveProps } from 'radix-vue'
import { localPaginationContextKey, type LocalPaginationContext } from './context'

export interface PaginationControlState {
  pagination: LocalPaginationContext
  disabled: ComputedRef<boolean>
}

export interface PaginationRenderedElementState {
  isNativeButton: ComputedRef<boolean>
  nativeDisabled: ComputedRef<boolean | undefined>
  ariaDisabled: ComputedRef<'true' | undefined>
  tabIndex: ComputedRef<number | undefined>
  buttonType: ComputedRef<'button' | undefined>
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

export const usePaginationRenderedElement = (
  props: Readonly<PrimitiveProps>,
  disabled: ComputedRef<boolean>
): PaginationRenderedElementState => {
  const isNativeButton = computed<boolean>(() => props.asChild !== true && props.as === 'button')
  const isDisabledCustomElement = computed<boolean>(() => disabled.value && !isNativeButton.value)

  return {
    isNativeButton,
    nativeDisabled: computed<boolean | undefined>(() =>
      isNativeButton.value ? disabled.value : undefined
    ),
    ariaDisabled: computed<'true' | undefined>(() =>
      isDisabledCustomElement.value ? 'true' : undefined
    ),
    tabIndex: computed<number | undefined>(() =>
      isDisabledCustomElement.value ? -1 : undefined
    ),
    buttonType: computed<'button' | undefined>(() =>
      isNativeButton.value ? 'button' : undefined
    )
  }
}

export const guardPaginationInteraction = (
  event: MouseEvent,
  disabled: boolean
): boolean => {
  if (!disabled) return true
  event.preventDefault()
  event.stopPropagation()
  return false
}
