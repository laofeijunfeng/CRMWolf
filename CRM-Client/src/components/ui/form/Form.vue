<script setup lang="ts">
/**
 * Form - vee-validate Form wrapper
 * Form container with Zod schema validation
 */
import type { HTMLAttributes } from 'vue'
import { Form, type GenericObject } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import type { ZodType } from 'zod'
import { cn } from '@/lib/utils'

interface Props {
  class?: HTMLAttributes['class']
  schema?: ZodType<GenericObject>
  initialValues?: Record<string, unknown>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  submit: [values: GenericObject]
}>()

function handleSubmit(values: GenericObject): void {
  emit('submit', values)
}
</script>

<template>
  <Form
    v-if="props.schema"
    :validation-schema="toTypedSchema(props.schema)"
    :initial-values="props.initialValues"
    :class="cn('space-y-wolf-md', props.class)"
    @submit="handleSubmit"
  >
    <slot />
  </Form>
  <Form
    v-else
    :initial-values="props.initialValues"
    :class="cn('space-y-wolf-md', props.class)"
    @submit="handleSubmit"
  >
    <slot />
  </Form>
</template>