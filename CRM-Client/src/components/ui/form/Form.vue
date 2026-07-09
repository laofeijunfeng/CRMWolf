<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import type { FormRootProps, GenericObject } from 'vee-validate'
import { FormRoot } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import type { ZodType, ZodTypeDef } from 'zod'
import { cn } from '@/lib/utils'

interface Props extends Omit<FormRootProps, 'validationSchema'> {
  class?: HTMLAttributes['class']
  schema?: ZodType<GenericObject, ZodTypeDef, GenericObject>
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, schema: __, ...delegated } = props
  return delegated
})

const formProps = computed(() => {
  if (props.schema) {
    return {
      ...delegatedProps.value,
      validationSchema: toTypedSchema(props.schema),
    }
  }
  return delegatedProps.value
})
</script>

<template>
  <FormRoot v-bind="formProps" :class="cn('space-y-wolf-md', props.class)">
    <slot />
  </FormRoot>
</template>