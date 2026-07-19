import type { ComputedRef, MaybeRef, Ref } from "vue"
import { FieldContextKey } from "vee-validate"
import { computed, inject } from "vue"
import { FORM_ITEM_INJECTION_KEY } from "./injectionKeys"

interface FieldState {
  valid: ComputedRef<boolean | undefined>
  isDirty: ComputedRef<boolean | undefined>
  isTouched: ComputedRef<boolean | undefined>
  error: Ref<string | undefined>
}

interface UseFormFieldReturn extends FieldState {
  id: string | undefined
  name: MaybeRef<string | number | symbol>
  formItemId: string
  formDescriptionId: string
  formMessageId: string
}

export function useFormField(): UseFormFieldReturn {
  const fieldContext = inject(FieldContextKey)
  const fieldItemContext = inject(FORM_ITEM_INJECTION_KEY)

  if (!fieldContext)
    throw new Error("useFormField should be used within <FormField>")

  const { name, errorMessage: error, meta } = fieldContext
  const id = fieldItemContext

  const fieldState = {
    valid: computed(() => meta.valid),
    isDirty: computed(() => meta.dirty),
    isTouched: computed(() => meta.touched),
    error,
  }

  return {
    id,
    name,
    formItemId: `${id}-form-item`,
    formDescriptionId: `${id}-form-item-description`,
    formMessageId: `${id}-form-item-message`,
    ...fieldState,
  }
}
