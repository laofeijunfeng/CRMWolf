import { FieldContextKey, useFieldRoot } from 'vee-validate'
import { inject, computed } from 'vue'
import type { InjectionKey, Ref } from 'vue'

export interface FormFieldContext {
  name: string
  formFieldId: string
  error: string | undefined
  value: unknown
  modelValue: unknown
  onBlur: () => void
  setInputValue: (value: unknown) => void
}

export const FORM_FIELD_INJECTION_KEY: InjectionKey<FormFieldContext> = Symbol('FormFieldContext')

export function useFormField(): {
  name: string
  formFieldId: Ref<string>
  error: Ref<string | undefined>
  value: Ref<unknown>
  modelValue: Ref<unknown>
  onBlur: () => void
  setInputValue: (value: unknown) => void
} {
  const fieldContext = inject(FORM_FIELD_INJECTION_KEY)
  const fieldRootContext = inject(FieldContextKey)

  if (!fieldContext) {
    throw new Error('useFormField should be used within <FormField>')
  }

  const { name, id } = fieldRootContext || fieldContext

  const formFieldId = computed(() => id || name)
  const error = computed(() => fieldContext.error)
  const value = computed(() => fieldContext.value)
  const modelValue = computed(() => fieldContext.modelValue)
  const onBlur = fieldContext.onBlur
  const setInputValue = fieldContext.setInputValue

  return {
    name,
    formFieldId,
    error,
    value,
    modelValue,
    onBlur,
    setInputValue,
  }
}