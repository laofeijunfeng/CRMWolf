<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { cn } from '@/lib/utils'
import Label from '@/components/ui/label/Label.vue'

interface Props extends HTMLAttributes {
  class?: HTMLAttributes['class']
  required?: boolean
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, required: __, ...delegated } = props
  return delegated
})

const { formItemId } = useFormField()
</script>

<template>
  <Label
    :for="formItemId"
    :class="cn('text-wolf-sm font-wolf-medium text-wolf-text-secondary', props.class)"
    v-bind="delegatedProps"
  >
    <slot />
    <span v-if="required" class="text-wolf-danger ml-wolf-xs">*</span>
  </Label>
</template>