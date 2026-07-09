<script setup lang="ts">
/**
 * Form - shadcn-vue Form component
 * Form container with vee-validate integration
 */
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { FormRoot } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import type { ZodType, ZodTypeDef } from 'zod'
import type { GenericObject } from 'vee-validate'
import { cn } from '@/lib/utils'

interface Props {
  class?: HTMLAttributes['class']
  schema?: ZodType<GenericObject, ZodTypeDef, GenericObject>
  initialValues?: GenericObject
  keepValues?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  submit: [values: GenericObject]
}>()

const formProps = computed(() => {
  const result: Record<string, unknown> = {}
  if (props.schema) {
    result.validationSchema = toTypedSchema(props.schema)
  }
  if (props.initialValues) {
    result.initialValues = props.initialValues
  }
  if (props.keepValues !== undefined) {
    result.keepValues = props.keepValues
  }
  return result
})
</script>

<template>
  <FormRoot
    v-bind="formProps"
    :class="cn('space-y-wolf-md', props.class)"
    @submit="emit('submit', $event as GenericObject)"
  >
    <slot />
  </FormRoot>
</template>